; LKH MCP Windows native installer — UNSIGNED PREVIEW
; Build with scripts/build-native-suite.ps1 then Inno Setup 6 ISCC.
; Does not migrate Docker/Naru, edit Cloudflare, or delete existing SQLite data.
#define AppVersion "0.0.1"
[Setup]
AppId=LKH-MCP-Native
AppName=LKH MCP
AppVersion={#AppVersion}
AppPublisher=LKH
DefaultDirName={autopf}\LKH MCP
DefaultGroupName=LKH MCP
OutputBaseFilename=LKH-MCP-Setup-UNSIGNED
OutputDir=..\dist\installer
SetupIconFile=..\assets\lkh-mcp.ico
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\LKH-MCP-Tray\LKH-MCP-Tray.exe
ChangesEnvironment=no
DisableDirPage=no
UsePreviousAppDir=yes
CloseApplications=yes

[Files]
Source: "..\dist\LKH-MCP-Server\*"; DestDir: "{app}\LKH-MCP-Server"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\LKH-MCP-Service\*"; DestDir: "{app}\LKH-MCP-Service"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\LKH-MCP-Tray\*"; DestDir: "{app}\LKH-MCP-Tray"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\LKH-Codex-Agent\*"; DestDir: "{app}\agent"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\LKH-MCP-Enroll\*"; DestDir: "{app}\LKH-MCP-Enroll"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\scripts\native-installer-preflight.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\install-agent-task.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\windows_agent\config.example.json"; DestDir: "{commonappdata}\LKH-MCP\config"; DestName: "agent.example.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\LKH MCP Tray"; Filename: "{app}\LKH-MCP-Tray\LKH-MCP-Tray.exe"
Name: "{group}\Open LKH MCP Admin"; Filename: "http://127.0.0.1:18081/admin"
Name: "{group}\Uninstall LKH MCP"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "LKH-MCP-Tray"; ValueData: """{app}\LKH-MCP-Tray\LKH-MCP-Tray.exe"""; Flags: uninsdeletevalue

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\native-installer-preflight.ps1"" -InstallDir ""{app}"""; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Enroll\LKH-MCP-Enroll.exe"; Parameters: "--provision"; Flags: runhidden waituntilterminated
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\install-agent-task.ps1"" -InstallDir ""{app}"" -AgentUser ""{code:GetAgentUser}"""; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "install --startup auto --username ""NT AUTHORITY\LocalService"""; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "start"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Tray\LKH-MCP-Tray.exe"; Description: "Start Pixel Pig tray"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ""Unregister-ScheduledTask -TaskName 'LKH-Codex-Agent' -Confirm:$false -ErrorAction SilentlyContinue"""; Flags: runhidden waituntilterminated

[Code]
var
  AgentPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  AgentPage := CreateInputQueryPage(wpSelectDir,
    'Codex Agent Windows user', 'Select the logged-in Codex CLI account',
    'The Agent requires an interactive Windows logon and a valid project config. It is not started automatically until configured.');
  AgentPage.Add('Agent username (DOMAIN\User or local name):', False);
  AgentPage.Values[0] := ExpandConstant('{username}');
end;

function GetAgentUser(Param: String): String;
begin
  Result := AgentPage.Values[0];
end;
