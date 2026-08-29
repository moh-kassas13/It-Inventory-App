[Setup]
AppName=IT Warehouse Inventory
AppVersion=3.0.0
DefaultDirName={autopf}\IT Warehouse
DefaultGroupName=IT Warehouse
OutputDir=Output
OutputBaseFilename=IT_Warehouse_Setup_v3.0.0
Compression=lzma2
SolidCompression=yes

SetupIconFile=assets\logo.ico
UninstallDisplayIcon={app}\InventoryDesk.exe

[Dirs]
Name: "{app}"; Permissions: users-full

[Files]
; Copy all PyInstaller compiled files, DLLs, and bundled assets from the output directory
Source: "dist\InventoryDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\IT Warehouse"; Filename: "{app}\InventoryDesk.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\IT Warehouse"; Filename: "{app}\InventoryDesk.exe"; WorkingDir: "{app}"

[Run]
; Launch Application after setup
Filename: "{app}\InventoryDesk.exe"; Description: "{cm:LaunchProgram,IT Warehouse}"; Flags: nowait postinstall skipifsilent