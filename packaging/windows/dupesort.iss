; Inno Setup script for the Windows installer (DupeSort-<version>-Windows-Setup.exe).
; Build the app first (pyinstaller dupesort.spec), then from the project root:
;   iscc /DAppVersion=0.1.0 packaging\windows\dupesort.iss
; packaging\build_windows.ps1 does both steps.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "DupeSort"
#define AppExe "DupeSort.exe"

[Setup]
; Keep this AppId the same in every release so upgrades replace the old version.
AppId={{6F3B2A0E-5C1D-4E8B-9A47-2D9C8B1E7F45}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
AppComments=Find, relocate and organize duplicate music, photos, videos and documents.
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Install for the current user by default (no admin prompt); allow all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\..\dist
OutputBaseFilename=DupeSort-{#AppVersion}-Windows-Setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\DupeSort\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; In-app updates run this installer with /SILENT: start the new version afterwards.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

; Settings and undo history live in %LOCALAPPDATA%\DupeSort and are kept on
; uninstall, so reinstalling keeps the user's folders, API keys and history.
