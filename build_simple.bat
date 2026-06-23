@echo off
echo ========================================
echo Garoon-Google Sync GUI - Simple Build
echo ========================================
echo.

python --version
if errorlevel 1 (
    echo ERROR: Python is not installed
    pause
    exit /b 1
)

echo.
echo Installing libraries (this may take a few minutes)...
pip install requests
pip install google-api-python-client
pip install google-auth-httplib2
pip install google-auth-oauthlib
pip install python-dateutil
pip install pyinstaller

echo.
echo Building EXE...
pyinstaller --onefile --noconsole --name GaroonGoogleSync garoon_google_sync_gui.py

echo.
if exist "dist\GaroonGoogleSync.exe" (
    echo ========================================
    echo BUILD SUCCESS!
    echo ========================================
    echo.
    if not exist dist_package mkdir dist_package
    copy /Y dist\GaroonGoogleSync.exe dist_package\
    copy /Y README_*.txt dist_package\README.txt 2>nul
    echo.
    echo Output: dist_package\GaroonGoogleSync.exe
    dir dist_package\GaroonGoogleSync.exe
) else (
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    echo Check error messages above.
)
echo.
pause
