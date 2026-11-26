; OmOffice kurulum dosyası. Doğrudan değil, packaging/build.py üzerinden derleyin.
#ifndef AppVersion
  #error "AppVersion tanimli degil"
#endif

[Setup]
AppId={{7C2E5D0A-9B1F-4E63-8A47-3D6F1C92B8E4}
AppName=OmOffice
AppVersion={#AppVersion}
AppVerName=OmOffice {#AppVersion}
AppPublisher=OmOffice
AppPublisherURL=https://github.com/opitmust/omoffice
AppSupportURL=https://github.com/opitmust/omoffice/issues
VersionInfoVersion={#AppVersion}
VersionInfoProductName=OmOffice
VersionInfoDescription=OmOffice Kurulumu
; Yönetici izni istemez; yalnızca bu kullanıcıya kurulur
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\OmOffice
DisableDirPage=yes
DisableProgramGroupPage=yes
ShowLanguageDialog=auto
DefaultGroupName=OmOffice
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=OmOffice-Setup-{#AppVersion}
SetupIconFile=..\omoffice\omoffice.ico
UninstallDisplayIcon={app}\OmOffice.exe
UninstallDisplayName=OmOffice
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Güncellemede önceki sürümün program dosyaları önce silinir: yeni sürümde artık olmayan kitaplıklar
; (ör. 1.0.0'daki Qt TLS eklentileri ve OpenSSL kopyaları) klasörde kalmasın. Bu klasörde yalnızca
; program dosyaları vardır; ayarlar ve kurtarma kopyaları %APPDATA%\OmOffice içindedir.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\OmOffice\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\OmOffice"; Filename: "{app}\OmOffice.exe"
Name: "{userdesktop}\OmOffice"; Filename: "{app}\OmOffice.exe"; Tasks: desktopicon

[Registry]
; Dosyaların varsayılan programını değiştirmez; yalnızca "Birlikte aç" listesine eklenir
Root: HKCU; Subkey: "Software\Classes\Applications\OmOffice.exe"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\OmOffice.exe\shell\open\command"; ValueType: string; ValueData: """{app}\OmOffice.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\OmOffice.exe\SupportedTypes"; ValueType: string; ValueName: ".docx"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Applications\OmOffice.exe\SupportedTypes"; ValueType: string; ValueName: ".odt"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\.docx\OpenWithList\OmOffice.exe"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\.odt\OpenWithList\OmOffice.exe"; Flags: uninsdeletekey

[Run]
Filename: "{app}\OmOffice.exe"; Description: "{cm:LaunchProgram,OmOffice}"; Flags: nowait postinstall skipifsilent

[Code]
{ Kullanıcının belgelerine hiç dokunmaz. Yalnızca programın kendi ayar ve kurtarma verisini, sorarak siler. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if SuppressibleMsgBox('OmOffice ayarları ve kurtarma kopyaları da silinsin mi?' + #13#10 + #13#10 +
         'Kaydettiğiniz belgeler silinmez.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\OmOffice'), True, True, True);
      RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\OmOffice');
    end;
end;
