@echo off
setlocal
cd /d "%~dp0"

echo SYSTEM root: %CD%

if not exist "config\system.json" (
  echo ERROR: config\system.json not found in %CD%
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -m venv .venv
  if errorlevel 1 (
    echo ERROR: failed to create .venv - install Python 3.11+
    pause
    exit /b 1
  )
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

echo.
echo Starting run_live.py ...
python run_live.py
set EXIT_CODE=%ERRORLEVEL%
echo.
echo Exit code: %EXIT_CODE%
pause
exit /b %EXIT_CODE%
