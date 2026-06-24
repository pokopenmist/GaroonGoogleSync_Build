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
pip install google-auth-oauthlib
pip install python-dateutil
pip install pyinstaller

echo.
echo Step 4: Building EXE (onedir / UPX disabled)...
pyinstaller GaroonGoogleSync.spec

echo.
echo Step 5: Checking build result...
if not exist "dist\GaroonGoogleSync\GaroonGoogleSync.exe" (
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
echo Step 5b: Removing unnecessary Tcl subpackages (reduces AV false positives)...
set TCL_DATA=dist\GaroonGoogleSync\_internal\_tcl_data
for %%D in (tzdata msgs http1.0 opt0.4) do (
    if exist "%TCL_DATA%\%%D" (
        rmdir /s /q "%TCL_DATA%\%%D"
        echo   Removed: %%D
    )
)

echo.
echo Step 6: Creating release package (ZIP)...
if exist release rmdir /s /q release
mkdir release\GaroonGoogleSync

xcopy /E /Y dist\GaroonGoogleSync\* release\GaroonGoogleSync\
if exist README_*.txt (
    copy /Y README_*.txt release\GaroonGoogleSync\README.txt
)
if exist タスクスケジューラ設定.txt (
    copy /Y タスクスケジューラ設定.txt release\GaroonGoogleSync\
)

cd release
python -c "import zipfile, os; z = zipfile.ZipFile('GaroonGoogleSync.zip', 'w', zipfile.ZIP_DEFLATED); [z.write(os.path.join(r,f), os.path.join(r,f)) for r,_,fs in os.walk('GaroonGoogleSync') for f in fs]; z.close(); print('ZIP created:', os.path.getsize('GaroonGoogleSync.zip'), 'bytes')"
cd ..

call deactivate

echo.
echo ========================================
echo BUILD COMPLETE
echo ========================================
echo.
echo Output: release\GaroonGoogleSync.zip
echo.
dir release\GaroonGoogleSync.zip
echo.
echo Next: Upload release\GaroonGoogleSync.zip to GitHub Releases.
echo Users should place credentials.json inside the extracted folder.
echo.
pause
