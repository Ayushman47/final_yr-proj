[Setup]
AppName=Health Assist
AppVersion=1.0.0
AppPublisher=Ayushman
AppPublisherURL=https://github.com/Ayushman47
DefaultDirName={autopf}\Health Assist
DefaultGroupName=Health Assist
OutputDir=dist
OutputBaseFilename=HealthAssist_Setup
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=compiler:SetupClassicIcon.ico
UninstallDisplayIcon={app}\HealthAssist.exe
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The main executable
Source: "dist\HealthAssist\HealthAssist.exe"; DestDir: "{app}"; Flags: ignoreversion
; All other files in the folder build
Source: "dist\HealthAssist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Health Assist"; Filename: "{app}\HealthAssist.exe"
Name: "{group}\{cm:UninstallProgram,Health Assist}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Health Assist"; Filename: "{app}\HealthAssist.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HealthAssist.exe"; Description: "{cm:LaunchProgram,Health Assist}"; Flags: nowait postinstall skipifsilent

[Dirs]
; Create models folder inside the app directory with full permissions so users can download models
Name: "{app}"; Permissions: users-modify
Name: "{app}\models"; Permissions: users-modify
Name: "{app}\ollama_bin"; Permissions: users-modify
