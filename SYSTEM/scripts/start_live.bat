@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
set "ROOT=%CD%"

echo SYSTEM root: %ROOT%

if not exist "%ROOT%\config\system.json" (
  echo ERROR: config\system.json not found in %ROOT%
  pause
  exit /b 1
)

if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -m venv "%ROOT%\.venv"
  if errorlevel 1 (
    echo ERROR: failed to create .venv - install Python 3.11+
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
echo Starting run_live.py ...
python "%ROOT%\run_live.py"
set EXIT_CODE=%ERRORLEVEL%
echo.
echo Exit code: %EXIT_CODE%
pause
exit /b %EXIT_CODE%
