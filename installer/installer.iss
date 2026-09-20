; Inno Setup script — NMS Tracker (Shadowskeep LLC)
; Build with:  ISCC.exe installer\installer.iss      (build.bat does this for you)
; Input:  dist\NMS Tracker\   (PyInstaller output)
; Output: dist\installer\NMSTracker-Setup-<version>.exe

#define AppName      "NMS Tracker"
#define AppPublisher "Shadowskeep LLC"
#define AppExe       "NMS Tracker.exe"
#define SourceDir    "..\dist\NMS Tracker"
; Version comes from the built exe so there is one source of truth (version_info.txt)
#define AppVersion   GetVersionNumbersString(SourceDir + "\" + AppExe)
#define CerFile      "ShadowskeepLLC-CodeSigning.cer"

; Written by tools\sign.ps1: CertThumb + CertSelfSigned. The "trust our certificate"
; option only exists for a self-signed certificate; a purchased one is trusted already.
#ifexist "cert.iss.inc"
  #include "cert.iss.inc"
#endif
#ifndef CertSelfSigned
  #define CertSelfSigned 0
#endif

[Setup]
; Never change AppId: it is how Windows recognises upgrades of the same app.
AppId={{B2D94A61-7C3E-4F18-A5D2-91E6C4F0A37B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoVersion={#AppVersion}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

; Per-user install by default (no admin prompt); the dialog lets the user pick "all users",
; which installs to C:\Program Files and asks for elevation.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

OutputDir=..\dist\installer
OutputBaseFilename=NMSTracker-Setup-{#AppVersion}
SetupIconFile=..\app\static\img\icon.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes

; The app lives in the system tray, so make sure a running copy is closed before upgrading.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

#if CertSelfSigned
; Opt-in and unchecked by default: adding a root certificate changes what this PC trusts,
; so the person installing has to choose it. Per-user installs also get Windows' own
; confirmation prompt; that prompt is deliberate and cannot (and should not) be bypassed.
Name: "trustcert"; Description: "Trust the {#AppPublisher} signing certificate (shows ""Verified publisher"" for this app and its future updates)"; GroupDescription: "Security:"; Flags: unchecked
#endif

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#if CertSelfSigned
Source: "{#CerFile}"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
#if CertSelfSigned
; Machine-wide stores for an "all users" install, per-user stores otherwise.
Filename: "{sys}\certutil.exe"; Parameters: "-f -addstore Root ""{app}\{#CerFile}"""; Tasks: trustcert; Check: IsAdminInstallMode; Flags: runhidden waituntilterminated; StatusMsg: "Trusting the signing certificate..."
Filename: "{sys}\certutil.exe"; Parameters: "-f -addstore TrustedPublisher ""{app}\{#CerFile}"""; Tasks: trustcert; Check: IsAdminInstallMode; Flags: runhidden waituntilterminated
Filename: "{sys}\certutil.exe"; Parameters: "-user -f -addstore Root ""{app}\{#CerFile}"""; Tasks: trustcert; Check: not IsAdminInstallMode; Flags: runhidden waituntilterminated; StatusMsg: "Trusting the signing certificate (Windows will ask you to confirm)..."
Filename: "{sys}\certutil.exe"; Parameters: "-user -f -addstore TrustedPublisher ""{app}\{#CerFile}"""; Tasks: trustcert; Check: not IsAdminInstallMode; Flags: runhidden waituntilterminated
#endif
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
#if CertSelfSigned
; Always clean up the trust we may have added (harmless if it was never added).
Filename: "{sys}\certutil.exe"; Parameters: "-delstore Root {#CertThumb}"; Check: IsAdminInstallMode; Flags: runhidden; RunOnceId: "UntrustRootM"
Filename: "{sys}\certutil.exe"; Parameters: "-delstore TrustedPublisher {#CertThumb}"; Check: IsAdminInstallMode; Flags: runhidden; RunOnceId: "UntrustPubM"
Filename: "{sys}\certutil.exe"; Parameters: "-user -delstore Root {#CertThumb}"; Check: not IsAdminInstallMode; Flags: runhidden; RunOnceId: "UntrustRootU"
Filename: "{sys}\certutil.exe"; Parameters: "-user -delstore TrustedPublisher {#CertThumb}"; Check: not IsAdminInstallMode; Flags: runhidden; RunOnceId: "UntrustPubU"
#endif

[UninstallDelete]
; PyInstaller/Qt may leave caches behind; the folder only ever contains our files.
Type: filesandordirs; Name: "{app}\_internal"
Type: dirifempty; Name: "{app}"

[Code]
// Save data lives in %LOCALAPPDATA%\ShadowskeepLLC\NMSTracker and is kept on
// uninstall unless the user explicitly chooses to delete it.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // The app keeps running in the tray, and its Qt WebEngine helper processes hold
    // files open. Close the whole process tree and give Windows a moment to release them.
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM "{#AppExe}"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(2000);
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    // Saved progress is NEVER deleted by a silent uninstall (upgrades, scripts, winget):
    // only a person who is asked, and says Yes, can remove it.
    if UninstallSilent then
      exit;
    DataDir := ExpandConstant('{localappdata}\ShadowskeepLLC\NMSTracker');
    if DirExists(DataDir) then
      if MsgBox('Also delete your saved inventory, goals and ships?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Choose No to keep them for a future reinstall.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
        RemoveDir(ExpandConstant('{localappdata}\ShadowskeepLLC'));
      end;
  end;
end;
