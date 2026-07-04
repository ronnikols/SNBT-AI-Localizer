[Setup]
AppName=SNBT AI Localizer
AppVersion=1.0
DefaultDirName={userappdata}\Programs\SNBT-AI-Localizer
DefaultGroupName=SNBT AI Localizer
OutputDir=.
OutputBaseFilename=setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
ChangesEnvironment=yes

[Files]
Source: "dist\snbt-tr.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\snbt-tr-gui.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SNBT AI Localizer"; Filename: "{app}\snbt-tr-gui.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\SNBT AI Localizer"; Filename: "{app}\snbt-tr-gui.exe"; WorkingDir: "{app}"
Name: "{app}\Uninstall SNBT AI Localizer"; Filename: "{uninstallexe}"; WorkingDir: "{app}"

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: not PathContainsAppDir('{app}')


[Code]
function PathContainsAppDir(Param: string): Boolean;
begin
  Result := Pos(';' + Param + ';', ';' + GetEnv('Path') + ';') > 0;
end;

procedure RemoveAppDirFromPath(AppDir: string);
var
  PathStr: string;
begin
  if RegQueryStringValue(HKCU, 'Environment', 'Path', PathStr) then
  begin
    StringChange(PathStr, ';' + AppDir + ';', ';');
    StringChange(PathStr, AppDir + ';', '');
    StringChange(PathStr, ';' + AppDir, '');
    StringChange(PathStr, ';;', ';');
    RegWriteStringValue(HKCU, 'Environment', 'Path', PathStr);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveAppDirFromPath(ExpandConstant('{app}'));
end;
