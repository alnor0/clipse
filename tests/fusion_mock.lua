-- A stand-in for Fusion's composition, just enough to run Clipse's Lua
-- (inserting nodes, keyframes, expressions) under LuaJIT without Resolve.
-- Not Fusion: it only checks that the scripts run and what they'd leave behind.
local KINDS = {
    MediaIn = {main = nil, inputs = {"EffectMask"}},
    MediaOut = {main = "Input", inputs = {"Input"}, no_output = true},
    Transform = {main = "Input", inputs = {"Input", "Center", "Size", "Angle", "Blend", "EffectMask"}},
    Merge = {main = "Background", inputs = {"Background", "Foreground", "Center", "Size", "Angle", "Blend", "EffectMask"}},
    MultiMerge = {main = "Background", inputs = {"Background", "Layer1.Foreground", "Layer2.Foreground", "Layer10.Foreground"}},
    BrightnessContrast = {main = "Input", inputs = {"Input", "Gain", "Alpha", "Blend", "EffectMask"}},
    Blur = {main = "Input", inputs = {"Input", "XBlurSize", "Blend", "EffectMask"}},
    TextPlus = {main = nil, inputs = {"StyledText", "Center", "Size", "Blend"}},
    Background = {main = nil, inputs = {"Blend", "EffectMask"}},
    Ellipse = {main = nil, inputs = {"EffectMask"}},
    GroupOperator = {main = nil, inputs = {}},
    Note = {main = nil, inputs = {}, no_output = true},
    Underlay = {main = nil, inputs = {}, no_output = true},
    BezierSpline = {main = nil, inputs = {}, modifier = true},
    XYPath = {main = nil, inputs = {"X", "Y"}, modifier = true},
}
local PICTURES = {Input = true, Background = true, Foreground = true}
local tools, order, counts, pos, data = {}, {}, {}, {}, {}
local selected = {}
local modifiers = {}
local inner = {}
comp = {CurrentTime = 0}

local Input = {}
Input.__index = Input
function Input:GetConnectedOutput() return self.source end
function Input:GetAttrs()
    local kind = "Number"
    if self.ID == "EffectMask" then kind = "Mask" elseif PICTURES[self.ID] or self.ID:find("Foreground") then kind = "Image" end
    return {INPS_ID = self.ID, INPS_DataType = kind}
end
function Input:GetTool() return self.tool end
function Input:ConnectTo(out)
    if self.source then
        for i, inp in ipairs(self.source.feeds) do if inp == self then table.remove(self.source.feeds, i) break end end
    end
    self.source = out
    if out then out.feeds[#out.feeds + 1] = self end
end
function Input:SetExpression(code) self.expression = code end

local Output = {}
Output.__index = Output
function Output:GetTool() return self.tool end
function Output:GetAttrs() return {OUTS_DataType = rawget(self.tool, "_kind") == "Ellipse" and "Mask" or "Image"} end
function Output:GetConnectedInputs()
    local t = {}
    for i, inp in ipairs(self.feeds) do t[i] = inp end
    return t
end

local Tool = {}
local methods = {}
Tool.__index = function(t, k)
    if methods[k] then return methods[k] end
    if k == "UserControls" then return rawget(t, "_controls") end
    return rawget(t, "_inputs")[k]
end
Tool.__newindex = function(t, k, v)  -- tool.Size = BezierSpline({}) / tool.Alpha = 1
    if k == "UserControls" then  -- sliders of your own on the node: each becomes a setting
        rawset(t, "_controls", v)
        for id, control in pairs(v) do
            if not rawget(t, "_inputs")[id] then
                rawget(t, "_inputs")[id] = setmetatable({ID = id, tool = t, value = control.INP_Default}, Input)
            end
        end
        return
    end
    local inp = rawget(t, "_inputs")[k]
    if not inp then error("no input " .. tostring(k) .. " on " .. rawget(t, "_name")) end
    if type(v) == "table" and rawget(v, "_out") then inp:ConnectTo(rawget(v, "_out")) else inp.value = v end
end
function methods:GetAttrs() return {TOOLS_Name = rawget(self, "_name"), TOOLS_RegID = rawget(self, "_kind"),
                                    TOOLB_NameSet = rawget(self, "_named"), TOOLB_PassThrough = rawget(self, "_off"),
                                    TOOLH_GroupParent = rawget(self, "_group"),
                                    TOOLI_ImageWidth = rawget(self, "_w"), TOOLI_ImageHeight = rawget(self, "_h")} end
function methods:SaveSettings()
    return {Tools = {[rawget(self, "_name")] = {ViewInfo = {Flags = rawget(self, "_pic") and {ShowPic = true} or nil}}}}
end
function methods:Refresh() return self end
function methods:SetAttrs(a)
    if a.TOOLB_PassThrough ~= nil then rawset(self, "_off", a.TOOLB_PassThrough) end
    if a.TOOLS_Name then
        local old = rawget(self, "_name")
        tools[old] = nil
        rawset(self, "_name", a.TOOLS_Name)
        tools[a.TOOLS_Name] = self
        pos[a.TOOLS_Name], pos[old] = pos[old], nil
    end
end
function methods:FindMainInput(n) local k = KINDS[rawget(self, "_kind")]; return k.main and rawget(self, "_inputs")[k.main] or nil end
function methods:FindMainOutput(n) return rawget(self, "_out") end
function methods:GetInputList() local t = {}; for _, inp in pairs(rawget(self, "_inputs")) do t[#t + 1] = inp end; return t end
function methods:GetInput(id, time) return rawget(self, "_inputs")[id] and rawget(self, "_inputs")[id].value end
function methods:SetInput(id, value) rawget(self, "_inputs")[id].value = value end
function methods:SetKeyFrames(keys, replace) rawset(self, "_keys", keys) end
function methods:GetKeyFrames() return rawget(self, "_keys") or {} end

local function make(kind, x, y)
    local spec = KINDS[kind]
    if not spec then return nil end
    counts[kind] = (counts[kind] or 0) + 1
    local name = kind .. counts[kind]
    local t = setmetatable({_name = name, _kind = kind, _inputs = {}}, Tool)
    for _, id in ipairs(spec.inputs) do
        rawget(t, "_inputs")[id] = setmetatable({ID = id, tool = t}, Input)
    end
    if not spec.no_output then rawset(t, "_out", setmetatable({tool = t, feeds = {}}, Output)) end
    tools[name] = t
    if not spec.modifier then
        order[#order + 1] = t
        pos[name] = {x, y}
    else
        modifiers[#modifiers + 1] = t
    end
    return t
end

function BezierSpline(_) return make("BezierSpline") end
function XYPath(_) return make("XYPath") end
bmd = {readstring = function() return nil end, readfile = function() return nil end}

local flow = {}
function flow:GetPosTable(t) local p = pos[t:GetAttrs().TOOLS_Name]; return p and {p[1], p[2]} or nil end
function flow:SetPos(t, x, y) pos[t:GetAttrs().TOOLS_Name] = {x, y} end
function flow:FrameAll() mock.framed = (mock.framed or 0) + 1; mock.scale = 2 end
function flow:GetScale() return mock.scale or 1 end
function flow:SetScale(s) mock.scale = s end
function flow:Select(t, on) if t == nil then selected = {} elseif on then selected[#selected + 1] = t end end
comp.CurrentFrame = {FlowView = flow}

function comp:GetToolList(only_selected)
    local t = {}
    if only_selected then
        for i, tool in ipairs(selected) do t[i] = tool end
        if #t == 0 and self.ActiveTool then t[1] = self.ActiveTool end
    else
        for i, tool in ipairs(order) do t[i] = tool end
        for _, tool in ipairs(inner) do t[#t + 1] = tool end  -- (a group's own nodes: no place in the view)
        if mock.lists_modifiers then  -- (Fusion may hand splines and paths back too: they have no place in the view)
            for _, tool in ipairs(modifiers) do t[#t + 1] = tool end
        end
    end
    return t
end
function comp:AddTool(kind, x, y)
    -- (Fusion puts a new node near the last click; anywhere will do here - the script moves it)
    return make(kind, 40 + #order, 9)
end
function comp:FindTool(name) return tools[name] end
function comp:SetActiveTool(t) self.ActiveTool = t; selected = t and {t} or {} end
function comp:SetData(k, v) data[k] = v end
function comp:GetData(k) return data[k] end
function comp:GetAttrs() return {COMPN_RenderStart = 0, COMPN_RenderEnd = 119} end
-- (the node view's options: no tile pictures unless a test switches them on - mock.pictures)
function comp:GetPrefs(key) return key == "Comp.FlowView" and (mock.pictures or {ShowThumbnails = false}) or nil end
function comp:Lock() end
function comp:Unlock() end
function comp:StartUndo(_) end
function comp:EndUndo(_) end
function comp:Paste(_) end
fusion = {GetCurrentComp = function() return comp end}

-- for the test: build a comp, run a script, say what's there
mock = {}
function mock.add(kind, x, y) return make(kind, x, y) end
function mock.connect(from, to, input) to[input]:ConnectTo(from:FindMainOutput(1)) end
function mock.run(code)
    data.ClipseResult = nil
    local chunk, problem = loadstring(code)
    if not chunk then return "SYNTAX " .. tostring(problem) end
    local ok, err = pcall(chunk)
    if not ok then return "CRASH " .. tostring(err) end
    return tostring(data.ClipseResult)
end
function mock.row()  -- the nodes on the main row, left to right: "MediaIn1@0 Transform1@1 MediaOut1@5"
    local list = {}
    for _, t in ipairs(order) do list[#list + 1] = t end
    table.sort(list, function(a, b)
        local pa, pb = pos[a:GetAttrs().TOOLS_Name], pos[b:GetAttrs().TOOLS_Name]
        if pa[2] ~= pb[2] then return pa[2] < pb[2] end
        return pa[1] < pb[1]
    end)
    local out = {}
    for _, t in ipairs(list) do
        local p = pos[t:GetAttrs().TOOLS_Name]
        out[#out + 1] = t:GetAttrs().TOOLS_Name .. "@" .. tostring(p[1]) .. (p[2] ~= 0 and ("," .. tostring(p[2])) or "")
    end
    return table.concat(out, " ")
end
function mock.chain()  -- back from MediaOut along the main inputs: "MediaOut1<Transform1<MediaIn1"
    local out, t, n = {}, tools.MediaOut1, 0
    while t and n < 30 do
        out[#out + 1] = t:GetAttrs().TOOLS_Name
        local inp = t:FindMainInput(1)
        local src = inp and inp:GetConnectedOutput()
        t = src and src:GetTool() or nil
        n = n + 1
    end
    return table.concat(out, "<")
end
function mock.keys(tool, input, axis)  -- "0=-0.5 24=0.5"
    local inp = tool[input]
    local mod = inp and inp:GetConnectedOutput() and inp:GetConnectedOutput():GetTool()
    if mod and axis then
        local sub = mod[axis]:GetConnectedOutput()
        mod = sub and sub:GetTool()
    end
    if not mod then return "none" end
    local times = {}
    for t, _ in pairs(mod:GetKeyFrames()) do times[#times + 1] = t end
    table.sort(times)
    local out = {}
    for _, t in ipairs(times) do out[#out + 1] = tostring(t) .. "=" .. tostring(mod:GetKeyFrames()[t][1]) end
    return table.concat(out, " ")
end
function mock.expression(tool, input) return tostring(tool[input] and tool[input].expression) end
function mock.value(tool, input) return tostring(tool[input] and tool[input].value) end
function mock.animated(tool, input) return tostring(tool[input]:GetConnectedOutput() ~= nil) end
function mock.tool(name) return tools[name] end
function mock.picture(tool, w, h) rawset(tool, "_pic", true); rawset(tool, "_w", w); rawset(tool, "_h", h) end  -- this tile shows one
function mock.inside(group, kind)  -- a node inside a group, as Fusion lists it: no place in the node view
    local t = make(kind, 0, 0)
    pos[t:GetAttrs().TOOLS_Name] = nil
    table.remove(order, #order)
    inner[#inner + 1] = t
    rawset(t, "_group", group)
    return t
end
function mock.into(group, tool) rawset(tool, "_group", group) end  -- the tool is inside the group
function mock.places()  -- every node and its spot: "MediaIn1@0,0 Merge1@1,0"
    local list = {}
    for _, t in ipairs(order) do list[#list + 1] = t:GetAttrs().TOOLS_Name end
    table.sort(list)
    for i, name in ipairs(list) do list[i] = name .. "@" .. tostring(pos[name][1]) .. "," .. tostring(pos[name][2]) end
    return table.concat(list, " ")
end
function mock.wires()  -- "MediaIn1>Merge1.Background ..."
    local out = {}
    for _, t in ipairs(order) do
        for id, inp in pairs(rawget(t, "_inputs")) do
            local src = inp:GetConnectedOutput()
            if src and pos[src:GetTool():GetAttrs().TOOLS_Name] then
                out[#out + 1] = src:GetTool():GetAttrs().TOOLS_Name .. ">" .. t:GetAttrs().TOOLS_Name .. "." .. id
            end
        end
    end
    table.sort(out)
    return table.concat(out, " ")
end
