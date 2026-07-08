@echo off
setlocal

REM Usage: copy_mql4_to_mt4.bat "C:\path\to\MT4\MQL4"
REM Example:
REM   copy_mql4_to_mt4.bat "C:\VS1\VS_STAGE_02_MT4_MANAGER\mt4_template\MQL4"

if "%~1"=="" (
  echo Usage: %~nx0 "C:\path\to\MT4\MQL4"
  exit /b 1
)

set "MT4_ROOT=%~1"
set "SCRIPT_DIR=%~dp0"
set "SYSTEM_ROOT=%SCRIPT_DIR%.."

if not exist "%SYSTEM_ROOT%\mql4\Include\SYSTEM_Execution.mqh" (
  echo SYSTEM source not found at %SYSTEM_ROOT%\mql4
  exit /b 1
)

echo Copying Include...
xcopy /Y /I "%SYSTEM_ROOT%\mql4\Include\SYSTEM_*.mqh" "%MT4_ROOT%\Include\"

echo Copying Experts...
xcopy /Y /I "%SYSTEM_ROOT%\mql4\Experts\SYSTEM_EA.mq4" "%MT4_ROOT%\Experts\"

echo Done. Open MetaEditor, compile SYSTEM_EA.mq4 (F7), not .mqh files.
endlocal
