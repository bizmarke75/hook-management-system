#ifndef AppVersion
  #define AppVersion "3.13"
#endif

#define AppName "Hook Management System"

[Setup]
AppId={{8A461E98-9EE7-4E97-9D68-1537AB9F1591}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=337 West Productions
DefaultDirName={localappdata}\Programs\Hook Management System
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=HMS_v{#AppVersion}_Setup
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\hms_master_gui.exe
WizardStyle=modern

[Files]
Source: "..\dist\hms_master_gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\hms_master_gui.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\hms_master_gui.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
