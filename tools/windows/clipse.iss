; Clipse's installer for Windows (Inno Setup 6) - made by tools/build_compiled.sh on GitHub's Windows machine:
;   ISCC /DVersion=1.0.0 /DSource=<compiled_main.dist> /DOut=<build> clipse.iss  ->  build\clipse-windows.exe
; For the one person using the computer, no admin asked: %LOCALAPPDATA%\Programs\Clipse (where VS Code, Discord ...
; go). Afterwards the app sets itself up (--install: Resolve's scripts, starting with Resolve) and opens the picker if
; ticked. Uninstalling takes the scripts and the login start away first; the cache and logs (%LOCALAPPDATA%\Clipse) go, your settings, key and history (%APPDATA%\Clipse) stay - clipse/paths.py.
; Update in the app runs it quietly over the running one (self_update.py): CloseApplications ends what's left of it,
; and /OPEN=1 opens the picker on the new version.
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6C1F0E3A-4B7D-4E3C-9A51-2F8D6B0C7E14}
AppName=Clipse
AppVersion={#Version}
AppVerName=Clipse {#Version}
AppPublisher=alnor
AppPublisherURL=https://alnor.store
AppSupportURL=https://alnor.store/docs.html
DefaultDirName={localappdata}\Programs\Clipse
DefaultGroupName=Clipse
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Out}
OutputBaseFilename=clipse-windows
SetupIconFile=clipse.ico
UninstallDisplayIcon={app}\clipse.exe
UninstallDisplayName=Clipse
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Clipse"; Filename: "{app}\clipse.exe"

[Run]
Filename: "{app}\clipse.exe"; Parameters: "--install"; StatusMsg: "Adding Clipse to DaVinci Resolve..."; Flags: runhidden waituntilterminated
Filename: "{app}\clipse.exe"; Description: "Open Clipse"; Flags: postinstall nowait skipifsilent
; (an update from inside the app - self_update.py: quiet, and /OPEN=1 - opens the picker on the new version)
Filename: "{app}\clipse.exe"; Flags: nowait; Check: OpenAfterUpdate

[Code]
function OpenAfterUpdate: Boolean;
begin
  Result := ExpandConstant('{param:OPEN|0}') = '1';
end;

[UninstallRun]
Filename: "{app}\clipse.exe"; Parameters: "--client --shutdown"; Flags: runhidden waituntilterminated; RunOnceId: "Shutdown"
Filename: "{app}\clipse.exe"; Parameters: "--client --uninstall-resolve-shortcuts"; Flags: runhidden waituntilterminated; RunOnceId: "Scripts"
Filename: "{app}\clipse.exe"; Parameters: "--client --no-autostart"; Flags: runhidden waituntilterminated; RunOnceId: "Autostart"

[UninstallDelete]
; (what can be made again - the cache, the logs; the program itself is in Programs\Clipse)
Type: filesandordirs; Name: "{localappdata}\Clipse"
