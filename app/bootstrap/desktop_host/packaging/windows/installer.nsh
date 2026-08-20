!include "LogicLib.nsh"
!include "StrFunc.nsh"
!include "WinMessages.nsh"

!ifndef BUILD_UNINSTALLER
${StrStr}
!else
${UnStrRep}
!endif

!macro customInstall
  SetShellVarContext current
  CreateDirectory "$INSTDIR\bin"
  FileOpen $0 "$INSTDIR\bin\elfienest.cmd" w
  FileWrite $0 "@echo off$\r$\n"
  FileWrite $0 "$\"%~dp0..\resources\management-cli\ElfieNestCli.exe$\" %*$\r$\n"
  FileClose $0
  ReadRegStr $0 HKCU "Environment" "Path"
  ${If} $0 == ""
    WriteRegExpandStr HKCU "Environment" "Path" "$INSTDIR\bin"
  ${Else}
    StrCpy $1 ";$0;"
    ${StrStr} $2 $1 ";$INSTDIR\bin;"
    ${If} $2 == ""
      WriteRegExpandStr HKCU "Environment" "Path" "$0;$INSTDIR\bin"
    ${EndIf}
  ${EndIf}
  SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment"
!macroend

!macro customUnInstall
  SetShellVarContext current
  Call un.ElfieNestRemoveLauncherPath
  Delete "$INSTDIR\bin\elfienest.cmd"
  RMDir "$INSTDIR\bin"
!macroend

!ifdef BUILD_UNINSTALLER
Function un.ElfieNestRemoveLauncherPath
  ReadRegStr $0 HKCU "Environment" "Path"
  ${If} $0 == ""
    Return
  ${EndIf}
  StrCpy $1 ";$0;"
  ${UnStrRep} $2 $1 ";$INSTDIR\bin;" ";"
  StrCpy $3 $2 "" 1
  StrLen $4 $3
  ${If} $4 > 0
    IntOp $4 $4 - 1
    StrCpy $5 $3 1 $4
    ${If} $5 == ";"
      StrCpy $3 $3 $4
    ${EndIf}
  ${EndIf}
  WriteRegExpandStr HKCU "Environment" "Path" "$3"
  SendMessage ${HWND_BROADCAST} ${WM_SETTINGCHANGE} 0 "STR:Environment"
FunctionEnd
!endif
