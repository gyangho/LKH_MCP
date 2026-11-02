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
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\native-installer-preflight.ps1"" -InstallDir ""{app}"""; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Admin-Setup\LKH-MCP-Admin-Setup.exe"; Parameters: "--initialize"; Flags: waituntilterminated
Filename: "{app}\LKH-MCP-Enroll\LKH-MCP-Enroll.exe"; Parameters: "--provision"; Flags: runhidden waituntilterminated
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\scripts\install-agent-task.ps1"" -InstallDir ""{app}"" -AgentUser ""{code:GetAgentUser}"" -ProjectAlias ""{code:GetProjectAlias}"" -Repository ""{code:GetRepository}"" -CheckoutPath ""{code:GetCheckoutPath}"""; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "--startup auto --username ""NT AUTHORITY\LocalService"" install"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Service\LKH-MCP-Service.exe"; Parameters: "start"; Flags: runhidden waituntilterminated
Filename: "{app}\LKH-MCP-Tray\LKH-MCP-Tray.exe"; Description: "Start Pixel Pig tray"; Flags: nowait postinstall skipifsilent runasoriginaluser

; Native removal handled by checked [Code] hook; no unchecked automatic uninstall actions.

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

{ One checkbox replaces the former Yes/No branching removal mode selector. }
function SelectUninstallMode(): Boolean;
var
  Form: TSetupForm;
  Description, Hint: TNewStaticText;
  FullRemoval: TNewCheckBox;
  RemoveButton, CancelButton: TNewButton;
begin
  Result := False;
  { Inno Setup 6.6+ requires form size at creation; client size is read-only. }
  Form := CreateCustomForm(460, 184, False, False);
  try
    Form.Caption := 'LKH MCP 제거 옵션';
    Form.Position := poDesktopCenter;

    Description := TNewStaticText.Create(Form);
    Description.Parent := Form;
    Description.Left := ScaleX(14);
    Description.Top := ScaleY(12);
    Description.Width := Form.ClientWidth - ScaleX(28);
    Description.Height := ScaleY(36);
    Description.AutoSize := False;
    Description.Caption := '기본 삭제: 프로그램, Windows 서비스, 작업 스케줄러 및 설정을 제거합니다.' + #13#10 +
      'SQLite 데이터베이스, 로그, 백업은 보존합니다.';

    FullRemoval := TNewCheckBox.Create(Form);
    FullRemoval.Parent := Form;
    FullRemoval.Left := ScaleX(14);
    FullRemoval.Top := ScaleY(59);
    FullRemoval.Width := Form.ClientWidth - ScaleX(28);
    FullRemoval.Height := ScaleY(24);
    FullRemoval.Caption := '완전 삭제 (SQLite DB, 설정, 로그 및 백업까지 삭제)';
    FullRemoval.Checked := False;

    Hint := TNewStaticText.Create(Form);
    Hint.Parent := Form;
    Hint.Left := ScaleX(14);
    Hint.Top := ScaleY(93);
    Hint.Width := Form.ClientWidth - ScaleX(28);
    Hint.Height := ScaleY(39);
    Hint.AutoSize := False;
    Hint.Caption := '완전 삭제를 선택하면 검증된 SQLite 복구 사본을 별도 보호 폴더에' + #13#10 +
      '남긴 뒤 LKH-MCP 데이터 폴더를 제거합니다.';

    RemoveButton := TNewButton.Create(Form);
    RemoveButton.Parent := Form;
    RemoveButton.Width := ScaleX(85);
    RemoveButton.Height := ScaleY(25);
    RemoveButton.Left := Form.ClientWidth - ScaleX(188);
    RemoveButton.Top := Form.ClientHeight - ScaleY(38);
    RemoveButton.Caption := '제거';
    RemoveButton.ModalResult := mrOk;
    RemoveButton.Default := True;

    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Width := ScaleX(85);
    CancelButton.Height := ScaleY(25);
    CancelButton.Left := Form.ClientWidth - ScaleX(94);
    CancelButton.Top := RemoveButton.Top;
    CancelButton.Caption := '취소';
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;

    Form.ActiveControl := FullRemoval;
    if Form.ShowModal <> mrOk then Exit;
    if FullRemoval.Checked then begin
      { Checking the box is the only way to select full removal. }
      if MsgBox('완전 삭제 확인: LKH-MCP 설정, SQLite DB, 로그 및 백업을 삭제합니다.' + #13#10 +
        'SQLite 복구 사본은 보호된 별도 폴더에 보존됩니다.' + #13#10 +
        '완전 삭제를 진행하려면 [확인]을 누르세요.',
        mbCriticalError, MB_OKCANCEL or MB_DEFBUTTON2) <> idOk then Exit;
      RemovalMode := 'all';
    end;
    Result := True;
  finally
    Form.Free();
  end;
end;

function InitializeUninstall(): Boolean;
begin
  RemovalMode := 'settings';
  Result := True;
  { Silent uninstall always keeps SQLite and backups. }
  if not UninstallSilent() then begin
    if not SelectUninstallMode() then begin
      Result := False;
      Exit;
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
