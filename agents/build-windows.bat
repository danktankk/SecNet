@echo off
REM Build secnet-agent.exe — run from agents\ directory
REM Requires: pip install pyinstaller psutil requests pywin32

echo Building secnet-agent.exe ...
pyinstaller --onefile --name secnet-agent --clean ^
  --hidden-import=win32timezone ^
  --hidden-import=win32serviceutil ^
  --hidden-import=win32service ^
  --hidden-import=win32event ^
  --hidden-import=servicemanager ^
  secnet-agent.py

if %ERRORLEVEL% NEQ 0 (
    echo BUILD FAILED
    exit /b 1
)

echo.
echo SUCCESS: dist\secnet-agent.exe
echo.
echo Next steps (run as Administrator):
echo   dist\secnet-agent.exe setup --url http://YOUR_SECNET:8088 --key YOUR_KEY
echo   dist\secnet-agent.exe install
echo   dist\secnet-agent.exe start
