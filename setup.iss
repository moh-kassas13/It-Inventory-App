[Setup]
AppName=IT Warehouse Inventory
AppVersion=1.0.0
DefaultDirName={autopf}\IT Warehouse
DefaultGroupName=IT Warehouse
OutputDir=Output
OutputBaseFilename=IT_Warehouse_Setup_v1.0.0
Compression=lzma2
SolidCompression=yes

SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\assets\app_icon.ico

[Files]
; Main application binaries & assets
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

; Bundle ODBC Driver installer
Source: "installers\msodbcsql17.msi"; DestDir: "{tmp}"; Flags: deleteafterinstall ignoreversion skipifsourcedoesntexist

; Bundle SQL Server Express installer (Packages it into Setup.exe)
Source: "installers\SQLEXPR_x64_ENU.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\IT Warehouse"; Filename: "{app}\main.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\app_icon.ico"
Name: "{autodesktop}\IT Warehouse"; Filename: "{app}\main.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\app_icon.ico"

[Run]
; 1. Install ODBC Driver silently
Filename: "msiexec.exe"; Parameters: "/i ""{tmp}\msodbcsql17.msi"" /qn IACCEPTMSODBCSQLLICENSETERMS=YES"; Flags: waituntilterminated; StatusMsg: "Installing SQL Server ODBC Driver..."; Check: FileExists(ExpandConstant('{tmp}\msodbcsql17.msi'))

; 2. Install SQL Server Express silently if bundled (Creates SQLEXPRESS instance automatically)
Filename: "{tmp}\SQLEXPR_x64_ENU.exe"; Parameters: "/Q /IACCEPTSQLSERVERLICENSETERMS /ACTION=Install /FEATURES=SQLEngine /INSTANCENAME=SQLEXPRESS /SQLSYSADMINACCOUNTS=""Builtin\Administrators"""; Flags: waituntilterminated; StatusMsg: "Installing SQL Server Express engine (this may take 5-10 minutes)..."; Check: FileExists(ExpandConstant('{tmp}\SQLEXPR_x64_ENU.exe'))

; 3. Launch Application
Filename: "{app}\main.exe"; Description: "{cm:LaunchProgram,IT Warehouse}"; Flags: nowait postinstall skipifsilent