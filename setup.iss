[Setup]
AppName=SNBT AI Localizer
AppVersion=1.1.24
DefaultDirName={userappdata}\Programs\SNBT-AI-Localizer
DefaultGroupName=SNBT AI Localizer
OutputDir=.
OutputBaseFilename=snbt-tr-Windows-Installer
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
ChangesEnvironment=yes

[Files]
Source: "dist\snbt-tr.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SNBT AI Localizer"; Filename: "{app}\snbt-tr.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\SNBT AI Localizer"; Filename: "{app}\snbt-tr.exe"; WorkingDir: "{app}"
Name: "{app}\Uninstall SNBT AI Localizer"; Filename: "{uninstallexe}"; WorkingDir: "{app}"

[Code]
function PathContainsAppDir(Param: string): Boolean;
begin
  Result := Pos(';' + Param + ';', ';' + GetEnv('Path') + ';') > 0;
end;

procedure AddAppDirToPath(AppDir: string);
var
  PathStr: string;
begin
  if not PathContainsAppDir(AppDir) then
  begin
    if RegQueryStringValue(HKCU, 'Environment', 'Path', PathStr) then
    begin
      PathStr := PathStr + ';' + AppDir;
      RegWriteStringValue(HKCU, 'Environment', 'Path', PathStr);
    end
    else
    begin
      RegWriteStringValue(HKCU, 'Environment', 'Path', AppDir);
    end;
  end;
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

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    AddAppDirToPath(ExpandConstant('{app}'));
end;
