@echo off
setlocal
cd /d "%~dp0"
echo ===================================================
echo  NMS Tracker - Shadowskeep LLC
echo  Build: app -^> sign -^> installer -^> sign
echo ===================================================

set "APP_EXE=dist\NMS Tracker\NMS Tracker.exe"

echo.
echo [1/5] Installing Python dependencies...
pip install -q -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [2/5] Generating app icon and game data...
python tools\make_icon.py
if errorlevel 1 goto :fail
python tools\build_data.py
if errorlevel 1 goto :fail

echo.
echo [3/5] Building the app with PyInstaller...
taskkill /F /IM "NMS Tracker.exe" >nul 2>&1
pyinstaller nms_tracker.spec --clean --noconfirm --log-level WARN
if errorlevel 1 goto :fail

echo.
echo [4/5] Signing the app...
powershell -NoProfile -ExecutionPolicy Bypass -File tools\sign.ps1 "%APP_EXE%"
if errorlevel 1 goto :fail

echo.
echo [5/5] Building and signing the installer...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 not found. Install it with:
  echo     winget install JRSoftware.InnoSetup
  goto :fail
)
"%ISCC%" /Q installer\installer.iss
if errorlevel 1 goto :fail
for %%F in (dist\installer\NMSTracker-Setup-*.exe) do (
  powershell -NoProfile -ExecutionPolicy Bypass -File tools\sign.ps1 "%%F"
  if errorlevel 1 goto :fail
)

echo.
echo ===================================================
echo  Build complete!
echo    App folder : dist\NMS Tracker\
echo    Installer  : dist\installer\
echo ===================================================
if not defined CI pause
exit /b 0

:fail
echo.
echo *** BUILD FAILED - see the errors above. ***
if not defined CI pause
exit /b 1
