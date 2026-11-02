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
Source: "..\scripts\native-upgrade-preflight.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\install-agent-task.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\native-uninstall.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\dist\LKH-MCP-DB-Backup\*"; DestDir: "{app}\LKH-MCP-DB-Backup"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\windows_agent\config.example.json"; DestDir: "{commonappdata}\LKH-MCP\config"; DestName: "agent.example.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\LKH MCP Tray"; Filename: "{app}\LKH-MCP-Tray\LKH-MCP-Tray.exe"
Name: "{group}\Open LKH MCP Admin"; Filename: "http://127.0.0.1:8001/admin"
Name: "{group}\Uninstall LKH MCP"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\LKH-MCP-Enroll\LKH-MCP-Enroll.exe"; Parameters: "--provision"; Flags: runhidden waituntilterminated
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\install-agent-task.ps1"" -InstallDir ""{app}"" -AgentUser ""{code:GetAgentUser}"" -ProjectAlias ""{code:GetProjectAlias}"" -Repository ""{code:GetRepository}"" -CheckoutPath ""{code:GetCheckoutPath}"""; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "--startup auto --username ""NT AUTHORITY\LocalService"" install"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "start"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Tray\LKH-MCP-Tray.exe"; Description: "Start Pixel Pig tray"; Flags: nowait postinstall skipifsilent runasoriginaluser

; Native removal handled by checked [Code] hook; no unchecked automatic uninstall actions.

[Code]
var
  AdminPage: TInputQueryWizardPage;
  AgentPage: TInputQueryWizardPage;
  ProjectPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  AdminPage := CreateInputQueryPage(wpSelectDir,
    'LKH MCP administrator', 'Create your administrator account',
    'First installation only. Existing credentials are preserved. Oracle connections are managed after installation.');
  AdminPage.Add('Administrator account:', False);
  AdminPage.Add('Password (14-256 characters):', True);
  AdminPage.Add('Repeat password:', True);
  AdminPage.Values[0] := 'admin';
  AdminPage.Edits[0].MaxLength := 64;
  AdminPage.Edits[1].MaxLength := 256;
  AdminPage.Edits[2].MaxLength := 256;
  AgentPage := CreateInputQueryPage(AdminPage.ID,
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

function ValidAdministratorName(Value: String): Boolean;
var
  I: Integer;
begin
  Result := (Length(Value) >= 1) and (Length(Value) <= 64);
  for I := 1 to Length(Value) do
    if Pos(Copy(Value, I, 1), 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-') = 0 then
      Result := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  AccountName, Checkout: String;
begin
  Result := True;
  if CurPageID = AdminPage.ID then begin
    if (Length(AdminPage.Values[1]) < 14) or
       (AdminPage.Values[1] <> AdminPage.Values[2]) or
       (not ValidAdministratorName(Trim(AdminPage.Values[0]))) then begin
      MsgBox('Provide an administrator account and matching passwords of at least 14 characters.', mbError, MB_OK);
      Result := False;
    end;
  end;
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


{ Installer credentials travel through stdin, never command-line arguments or files. }
function AdministratorConfigured(): Boolean;
begin
  Result := FileExists(ExpandConstant('{commonappdata}\LKH-MCP\config\bootstrap.json'));
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = AdminPage.ID) and AdministratorConfigured();
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not AdministratorConfigured() then begin
    if (Length(AdminPage.Values[1]) < 14) or
       (AdminPage.Values[1] <> AdminPage.Values[2]) or
       (not ValidAdministratorName(Trim(AdminPage.Values[0]))) then
      Result := 'First installation requires administrator credentials in the interactive wizard.';
  end;
end;

function JsonString(Value: String): String;
var
  I: Integer;
begin
  Result := '"';
  for I := 1 to Length(Value) do
    Result := Result + '\u' + IntToHex(Ord(Value[I]), 4);
  Result := Result + '"';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode, Attempts: Integer;
  Shell, Process: Variant;
  Command, Payload: String;
begin
  if CurStep <> ssPostInstall then Exit;
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\scripts\native-installer-preflight.ps1') + '" -InstallDir "' +
    ExpandConstant('{app}') + '"', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    RaiseException('Service data permission preparation failed.');
  if ExitCode <> 0 then RaiseException('Service data permission preparation failed.');
  if AdministratorConfigured() then Exit;
  try
    Shell := CreateOleObject('WScript.Shell');
    Command := '"' + ExpandConstant('{app}\LKH-MCP-Admin-Setup\LKH-MCP-Admin-Setup.exe') +
      '" --initialize --stdin-json';
    Process := Shell.Exec(Command);
    Payload := '{"username":' + JsonString(Trim(AdminPage.Values[0])) +
      ',"password":' + JsonString(AdminPage.Values[1]) + '}';
    Process.StdIn.Write(Payload);
    Process.StdIn.Close;
    Payload := '';
    AdminPage.Values[1] := '';
    AdminPage.Values[2] := '';
    Attempts := 0;
    while (Process.Status = 0) and (Attempts < 600) do begin
      Sleep(100);
      Attempts := Attempts + 1;
    end;
    if Process.Status = 0 then begin
      Process.Terminate();
      RaiseException('Administrator setup timed out.');
    end;
    if Process.ExitCode <> 0 then RaiseException('Administrator setup failed.');
  except
    { Never include a COM exception, process output or credential payload. }
    RaiseException('Administrator setup failed. Verify the account and password, then retry installation.');
  end;
end;

{ Uninstaller default: remove program and settings, preserve SQLite/WAL/logs/backups. }
var
  RemovalMode: String;

function RunNativeRemoval(StageName: String): Boolean;
var
  Params: String;
  ExitCode: Integer;
begin
  ExitCode := -1;
  Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\scripts\native-uninstall.ps1') + '" -Stage ' +
    StageName + ' -Mode ' + RemovalMode + ' -InstallDir "' + ExpandConstant('{app}') + '"';
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Params, '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  Result := Result and (ExitCode = 0);
end;

function InitializeUninstall(): Boolean;
var
  Selection: Integer;
begin
  RemovalMode := 'settings';
  Result := True;
  if not UninstallSilent() then begin
    Selection := MsgBox(
      'LKH MCP 제거 방식' + #13#10 + #13#10 +
      '[예] 프로그램 + 설정 제거 (기본값; SQLite DB/로그/백업 보존)' + #13#10 +
      '[아니요] 다른 제거 옵션 선택' + #13#10 +
      '[취소] 중단', mbConfirmation, MB_YESNOCANCEL or MB_DEFBUTTON1);
    if Selection = idCancel then begin Result := False; Exit; end;
    if Selection = idNo then begin
      Selection := MsgBox(
        '[예] 프로그램만 제거 (설정 및 SQLite DB 보존)' + #13#10 +
        '[아니요] 모든 앱 데이터 제거 (SQLite 포함)' + #13#10 +
        '[취소] 중단', mbConfirmation, MB_YESNOCANCEL or MB_DEFBUTTON1);
      if Selection = idCancel then begin Result := False; Exit; end;
      if Selection = idYes then
        RemovalMode := 'program'
      else begin
        RemovalMode := 'all';
        if MsgBox('전체 삭제: ProgramData의 LKH-MCP 설정/SQLite/로그/백업이 삭제됩니다.' + #13#10 +
          'SQLite는 별도 ACL 보호 폴더에 먼저 검증 백업하고 그 백업은 보존합니다.' + #13#10 +
          '계속하시겠습니까?',
          mbCriticalError, MB_YESNO or MB_DEFBUTTON2) <> idYes then begin
          Result := False; Exit;
        end;
        if MsgBox('최종 확인: 모든 LKH-MCP 데이터의 삭제를 승인합니까?',
          mbCriticalError, MB_YESNO or MB_DEFBUTTON2) <> idYes then begin
          Result := False; Exit;
        end;
      end;
    end;
  end;
  if not RunNativeRemoval('verify') then begin
    MsgBox('제거 사전 검증 실패: 서비스/작업 소유권, 실행 상태 또는 데이터 경로를 확인하세요.',
      mbCriticalError, MB_OK);
    Result := False;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then begin
    if not RunNativeRemoval('remove') then begin
      MsgBox('제거 처리 실패: 일부 서비스/작업이 중지되었을 수 있습니다.' + #13#10 +
        '프로그램 파일 삭제는 중단합니다. 보존 데이터를 확인하세요.',
        mbCriticalError, MB_OK);
      Abort;
    end;
  end;
end;
