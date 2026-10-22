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
rem truststore: verify the corporate proxy certificate via the Windows certificate store
python -m pip install --use-feature=truststore --upgrade pip

echo.
echo Step 3: Installing required libraries...
python -m pip install --use-feature=truststore requests google-auth-oauthlib python-dateutil pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install libraries
    call deactivate
    pause
    exit /b 1
)

echo.
echo Step 4: Building EXE (onedir / UPX disabled)...
if exist dist\GaroonGoogleSync rmdir /s /q dist\GaroonGoogleSync
pyinstaller --noconfirm GaroonGoogleSync.spec

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
