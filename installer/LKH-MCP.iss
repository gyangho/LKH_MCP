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
Source: "..\dist\LKH-MCP-Admin-Setup\*"; DestDir: "{app}\LKH-MCP-Admin-Setup"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\scripts\native-installer-preflight.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\install-agent-task.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\windows_agent\config.example.json"; DestDir: "{commonappdata}\LKH-MCP\config"; DestName: "agent.example.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\LKH MCP Tray"; Filename: "{app}\LKH-MCP-Tray\LKH-MCP-Tray.exe"
Name: "{group}\Open LKH MCP Admin"; Filename: "http://127.0.0.1:18081/admin"
Name: "{group}\Uninstall LKH MCP"; Filename: "{uninstallexe}"

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\native-installer-preflight.ps1"" -InstallDir ""{app}"""; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Admin-Setup\LKH-MCP-Admin-Setup.exe"; Parameters: "--initialize"; Flags: waituntilterminated
Filename: "{app}\LKH-MCP-Enroll\LKH-MCP-Enroll.exe"; Parameters: "--provision"; Flags: runhidden waituntilterminated
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\install-agent-task.ps1"" -InstallDir ""{app}"" -AgentUser ""{code:GetAgentUser}"" -ProjectAlias ""{code:GetProjectAlias}"" -Repository ""{code:GetRepository}"" -CheckoutPath ""{code:GetCheckoutPath}"""; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "--startup auto --username ""NT AUTHORITY\LocalService"" install"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "start"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Tray\LKH-MCP-Tray.exe"; Description: "Start Pixel Pig tray"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ""Unregister-ScheduledTask -TaskName 'LKH-Codex-Agent' -Confirm:$false -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName 'LKH-MCP-Tray' -Confirm:$false -ErrorAction SilentlyContinue"""; Flags: runhidden waituntilterminated

[Code]
var
  AgentPage: TInputQueryWizardPage;
  ProjectPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  AgentPage := CreateInputQueryPage(wpSelectDir,
    'Codex Agent Windows user', 'Select the logged-in Codex CLI account',
    'The Agent starts only after a project checkout is configured and the Codex CLI login account is available.');
  AgentPage.Add('Agent username (DOMAIN\User or local name):', False);
  AgentPage.Values[0] := ExpandConstant('{username}');
  ProjectPage := CreateInputQueryPage(AgentPage.ID,
    'Codex Agent project', 'Optional initial local checkout',
    'Enter an existing Git checkout; leave the path empty to disable the Agent task until configured.');
  ProjectPage.Add('Project alias:', False);
  ProjectPage.Add('GitHub owner/repository:', False);
  ProjectPage.Add('Absolute Windows checkout path:', False);
  ProjectPage.Values[0] := 'LKH_MCP';
  ProjectPage.Values[1] := 'gyangho/LKH_MCP';
  ProjectPage.Values[2] := '';
end;

function GetAgentUser(Param: String): String;
begin
  Result := AgentPage.Values[0];
end;

function GetProjectAlias(Param: String): String;
begin
  Result := Trim(ProjectPage.Values[0]);
end;

function GetRepository(Param: String): String;
begin
  Result := Trim(ProjectPage.Values[1]);
end;

function GetCheckoutPath(Param: String): String;
begin
  Result := Trim(ProjectPage.Values[2]);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  AccountName, Checkout: String;
begin
  Result := True;
  if CurPageID = AgentPage.ID then begin
    AccountName := Trim(AgentPage.Values[0]);
    if (AccountName = '') or (Pos('"', AccountName) > 0) or
       (Pos(';', AccountName) > 0) then begin
      MsgBox('Provide a valid Windows Agent username.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = ProjectPage.ID then begin
    Checkout := Trim(ProjectPage.Values[2]);
    if (Pos('"', ProjectPage.Values[0]) > 0) or
       (Pos('"', ProjectPage.Values[1]) > 0) or
       (Pos('"', Checkout) > 0) then begin
      MsgBox('Double quotes are not allowed in project settings.', mbError, MB_OK);
      Result := False;
    end;
    if Checkout <> '' then begin
      if Length(Checkout) < 3 then begin
        MsgBox('The project checkout must be an absolute local Windows path.', mbError, MB_OK);
        Result := False;
      end else if (Checkout[2] <> ':') or (Checkout[3] <> '\') then begin
        MsgBox('The project checkout must be an absolute local Windows path.', mbError, MB_OK);
        Result := False;
      end;
    end;
  end;
end;
