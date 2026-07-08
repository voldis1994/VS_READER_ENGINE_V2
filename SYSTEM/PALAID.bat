@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"

echo.
echo ========================================
echo  SYSTEM - LIVE START
echo ========================================
echo.
echo SYSTEM root: %ROOT%
echo.

if not exist "%ROOT%\config\system.json" (
  echo ERROR: nav atrasts %ROOT%\config\system.json
  echo.
  echo Pareizais ceļš: C:\VS_READER_ENGINE_V2\SYSTEM
  pause
  exit /b 1
)

if not exist "%ROOT%\run_live.py" (
  echo ERROR: nav atrasts %ROOT%\run_live.py
  pause
  exit /b 1
)

if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo Izveido Python vidi (.venv)...
  py -m venv "%ROOT%\.venv"
  if errorlevel 1 (
    echo ERROR: neizdevas izveidot .venv - instalē Python 3.11+
    pause
    exit /b 1
  )
  call "%ROOT%\.venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  pip install -r "%ROOT%\requirements.txt"
) else (
  call "%ROOT%\.venv\Scripts\activate.bat"
)

echo.
echo Palaižu run_live.py ...
echo.
python "%ROOT%\run_live.py"
set EXIT_CODE=%ERRORLEVEL%
echo.
echo Exit code: %EXIT_CODE%
pause
exit /b %EXIT_CODE%
