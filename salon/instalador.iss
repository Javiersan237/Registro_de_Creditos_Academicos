; Instalador de la versión del salón · Registro de créditos (TecNM Matehuala). Lo compila salon\construir.py.
#define Nombre "Registro de créditos TecNM"
#define Version "1.3.0"
#ifndef Origen
  #error Falta /DOrigen=<carpeta de PyInstaller>
#endif

[Setup]
AppId={{B98D00E0-9C65-42BB-9C1A-F9DA5F573E4C}
AppName={#Nombre}
AppVersion={#Version}
AppPublisher=Renueva TI (prototipo escolar para el TecNM Campus Matehuala)
DefaultDirName={autopf}\RegistroCreditosTecNM
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
OutputBaseFilename=Instalar_RegistroCreditos_TecNM
SetupIconFile={#Origen}\_internal\salon\icono.ico
UninstallDisplayIcon={app}\RegistroCreditos.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Nombre}"; Filename: "{app}\RegistroCreditos.exe"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\RegistroCreditos.exe"; Tasks: escritorio

[Run]
; Permite que los celulares de la red entren al servidor. La regla es por PROGRAMA (no por puerto): si el 8000
; está ocupado, la app usa el siguiente libre y sigue permitida. Primero se borra la regla de una versión anterior.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Registro de creditos TecNM"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Registro de creditos TecNM"" dir=in action=allow program=""{app}\RegistroCreditos.exe"" protocol=TCP enable=yes profile=any"; Flags: runhidden; StatusMsg: "Configurando el firewall..."
Filename: "{app}\RegistroCreditos.exe"; Description: "Abrir {#Nombre}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Registro de creditos TecNM"""; Flags: runhidden; RunOnceId: "QuitarFirewall"

[Messages]
es.WelcomeLabel2=Se instalará el Registro de créditos complementarios del Congreso Académico (Instituto Tecnológico de Matehuala).%n%nTus datos y la sesión de WhatsApp se guardan en tu usuario, no en esta carpeta.
