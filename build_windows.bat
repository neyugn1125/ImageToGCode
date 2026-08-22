@echo off
setlocal

cd /d "%~dp0"
if %errorlevel% neq 0 exit /b %errorlevel%
python -m pip install -r requirements.txt
if %errorlevel% neq 0 exit /b %errorlevel%
python -m pip install pyinstaller
if %errorlevel% neq 0 exit /b %errorlevel%
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ImageToGCode app.py
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo Build complete: dist\ImageToGCode.exe
endlocal
