; packaging/windows/orrin.iss — Inno Setup script for the Orrin Windows installer (I5).
;
; We ship a raw .zip today; this produces a real Setup.exe: per-user install (no admin
; prompt), Start-Menu + optional desktop shortcut, clean uninstall, and it bundles the
; WebView2 evergreen bootstrapper and runs it silently when the runtime is missing (the
; native window needs WebView2 — present on most Win10/11, but we guarantee it).
;
; Build (on a Windows runner, after pyinstaller produces dist\Orrin\):
;   iscc /DMyAppVersion=%ORRIN_VERSION% packaging\windows\orrin.iss
; Output: dist\Orrin-Setup-windows-x64.exe
;
; Code-signing (clears SmartScreen) is the blocked part — sign the output .exe with a
; Windows code-signing cert before distribution.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "Orrin"
#define MyAppExeName "Orrin.exe"
#define MyAppPublisher "Orrin"

[Setup]
; A stable AppId so upgrades replace in place rather than installing side-by-side.
AppId={{B6F4E1C2-2D9A-4E77-9C3F-1A2B3C4D5E6F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Orrin
DefaultGroupName=Orrin
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir={#SourcePath}\..\..\dist
OutputBaseFilename=Orrin-Setup-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Per-user install → no UAC elevation (also less SmartScreen friction).
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; The whole frozen folder app.
Source: "{#SourcePath}\..\..\dist\Orrin\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; WebView2 bootstrapper — downloaded into this folder by CI before iscc runs.
Source: "{#SourcePath}\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\Orrin"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Orrin"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Install the WebView2 evergreen runtime silently, only if it isn't already present.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
  Check: WebView2Missing; StatusMsg: "Installing the WebView2 runtime…"; Flags: waituntilterminated
; Offer to launch after a non-silent install.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Orrin"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Missing(): Boolean;
var
  v: String;
const
  // Well-known GUID of the WebView2 Evergreen Runtime in EdgeUpdate's client list.
  WV2 = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
begin
  // Registered per-machine (WOW6432Node) or per-user when present.
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WV2, 'pv', v) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WV2, 'pv', v)
  );
end;
