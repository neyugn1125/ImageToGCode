@echo off
setlocal

cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ImageToGCode app.py

if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build complete: dist\ImageToGCode.exe
endlocal
