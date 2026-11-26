#define AppVersion "0.1.0"
#define AppDisplayName "电机测试台"

[Setup]
AppId={{05A8DC60-8DD4-43EB-95A6-6024E4CF6296}
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppPublisher=RP27-EC
AppPublisherURL=https://github.com/RP27-EC/Motor-Test-Bench
DefaultDirName={localappdata}\Programs\MotorBench
DefaultGroupName={#AppDisplayName}
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=MotorBench-Setup-Windows-x64
SetupIconFile=..\src\motorbench.ico
UninstallDisplayIcon={app}\MotorBench.exe
WizardStyle=modern
ShowLanguageDialog=no
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "zh"; MessagesFile: "ChineseSimplified.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\MotorBench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\MotorBench 电机测试台"; Filename: "{app}\MotorBench.exe"; WorkingDir: "{app}"
Name: "{group}\{#AppDisplayName}"; Filename: "{app}\MotorBench.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\MotorBench.exe"; Description: "{cm:LaunchProgram,{#AppDisplayName}}"; Flags: nowait postinstall skipifsilent
