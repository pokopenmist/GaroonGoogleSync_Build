@echo off
echo ========================================
echo Garoon-Google Sync GUI - EXE Build
echo ========================================
echo.

python --version
if errorlevel 1 (
    echo ERROR: Python is not installed
    pause
    exit /b 1
)

echo.
echo Step 1: Creating virtual environment...
if exist venv rmdir /s /q venv
python -m venv venv
call venv\Scripts\activate.bat

echo.
echo Step 2: Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Step 3: Installing required libraries...
pip install requests
pip install google-api-python-client
pip install google-auth-httplib2
pip install google-auth-oauthlib
pip install python-dateutil
pip install pyinstaller

echo.
echo Step 4: Building EXE...
pyinstaller --onefile --noconsole --name GaroonGoogleSync garoon_google_sync_gui.py

echo.
echo Step 5: Checking build result...
if not exist "dist\GaroonGoogleSync.exe" (
    echo.
    echo ========================================
    echo ERROR: Build failed!
    echo EXE file was not created.
    echo Check the error messages above.
    echo ========================================
    call deactivate
    pause
    exit /b 1
)

echo.
echo Step 6: Creating dist_package folder...
if not exist dist_package mkdir dist_package
copy /Y dist\GaroonGoogleSync.exe dist_package\
if exist README_*.txt copy /Y README_*.txt dist_package\README.txt
if exist *.txt copy /Y タスクスケジューラ設定.txt dist_package\ 2>nul

call deactivate

echo.
echo ========================================
echo BUILD COMPLETE
echo ========================================
echo.
echo Output: dist_package\GaroonGoogleSync.exe
echo.
dir dist_package
echo.
echo Add credentials.json to dist_package folder.
echo.
pause
