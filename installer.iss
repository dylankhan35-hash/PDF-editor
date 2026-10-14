; Inno Setup script for PDF Editor.
; 1) Run build_windows.bat first (creates dist\PDFEditor\)
; 2) Open this file in Inno Setup (free, jrsoftware.org) and press Compile (Ctrl+F9)
; 3) Your installer appears in installer\PDFEditor-Setup.exe

[Setup]
AppName=PDF Editor
AppVersion=0.1.0
AppPublisher=PDF Editor
DefaultDirName={autopf}\PDF Editor
DefaultGroupName=PDF Editor
UninstallDisplayIcon={app}\PDFEditor.exe
OutputDir=installer
OutputBaseFilename=PDFEditor-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "openwith"; Description: "Add PDF Editor to the ""Open with"" list for PDF files"; Flags: unchecked

[Files]
Source: "dist\PDFEditor\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\PDF Editor"; Filename: "{app}\PDFEditor.exe"
Name: "{group}\Uninstall PDF Editor"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PDF Editor"; Filename: "{app}\PDFEditor.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\PDFEditor.pdf"; ValueType: string; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\PDFEditor.pdf\shell\open\command"; ValueType: string; ValueData: """{app}\PDFEditor.exe"" ""%1"""; Tasks: openwith
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueName: "PDFEditor.pdf"; ValueType: string; ValueData: ""; Flags: uninsdeletevalue; Tasks: openwith

[Run]
Filename: "{app}\PDFEditor.exe"; Description: "Launch PDF Editor"; Flags: nowait postinstall skipifsilent
