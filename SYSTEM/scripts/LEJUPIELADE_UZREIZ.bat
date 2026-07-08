@echo off
setlocal EnableExtensions
title SYSTEM - lejuplade uzreiz
color 0A

echo.
echo  ============================================================
echo   SYSTEM - AUTOMATISKA LEJUPIELADE UN UZSTADISANA
echo  ============================================================
echo.
echo   Meprece: C:\SYSTEM
echo   Avots:   GitHub (visi faili + testi)
echo.
echo   Uzgaidiet... (2-5 minutes atkariba no interneta)
echo.

where powershell >nul 2>&1
if errorlevel 1 (
    echo [KLUDA] PowerShell nav atrasts.
    goto :fail
)

set "SCRIPT_URL=https://raw.githubusercontent.com/voldis1994/VS_READER_ENGINE_V2/main/SYSTEM/scripts/install_windows.ps1"
set "SCRIPT_FILE=%TEMP%\system_install_%RANDOM%.ps1"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; ^
   Write-Host 'Lejupielade instalacijas skriptu...' -ForegroundColor Cyan; ^
   Invoke-WebRequest -Uri '%SCRIPT_URL%' -OutFile '%SCRIPT_FILE%' -UseBasicParsing; ^
   if (-not (Test-Path '%SCRIPT_FILE%')) { throw 'Neizdevas lejupieladet skriptu' }"

if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_FILE%" -InstallPath "C:\SYSTEM" %*
set "EXIT_CODE=%ERRORLEVEL%"

del /f /q "%SCRIPT_FILE%" >nul 2>&1

echo.
if %EXIT_CODE% neq 0 (
    echo  [KLUDA] Uzstadisana neizdevas. Exit code: %EXIT_CODE%
    goto :fail
)

echo  ============================================================
echo   GATAVS! Projekts ir: C:\SYSTEM
echo  ============================================================
echo.
echo   Nakamie soļi:
echo     1. Atveriet: C:\SYSTEM\config\system.json
echo     2. Ievadiet savu account_id, symbol, magic
echo     3. MT4: kopējiet C:\SYSTEM\mql4 uz MT4 MQL4 mapi
echo     4. Palaidiet: C:\SYSTEM\.venv\Scripts\activate
echo                 python C:\SYSTEM\run_live.py
echo.
goto :end

:fail
echo.
echo  Nepieciešams: Python 3.11+ no https://www.python.org/downloads/
echo  Instalejiet ar opciju "Add Python to PATH"
echo.

:end
pause
exit /b %EXIT_CODE%
