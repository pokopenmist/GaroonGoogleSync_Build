#define MyAppName "Garoon Google Calendar 同期ツール"
#define MyAppVersion "1.0.2"
#define MyAppExeName "GaroonGoogleSync.exe"
#define MyAppSourceDir "dist\GaroonGoogleSync"

[Setup]
AppId={{FC5BAA65-FCA7-45C3-B999-E42A57B616D2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={localappdata}\GaroonGoogleSync
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=release
OutputBaseFilename=GaroonGoogleSync_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
InfoAfterFile=installer_note.txt

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成する"; GroupDescription: "追加タスク:"

[Files]
; アプリケーション本体
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; ドキュメント
Source: "README_使用ガイド.txt"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion
Source: "タスクスケジューラ設定.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; インストール先フォルダを開く（credentials.json の配置場所を確認できる）
Filename: "{app}"; Description: "インストール先フォルダを開く（credentials.json をここに配置）"; Flags: postinstall shellexec skipifsilent
; アプリを起動する
Filename: "{app}\{#MyAppExeName}"; Description: "セットアップ完了後に {#MyAppName} を起動する"; Flags: nowait postinstall skipifsilent
