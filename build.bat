@echo off
REM Build ElaStarter with PyInstaller
REM Using --noupx to avoid compression issues with large ICU library files

call venv\Scripts\activate.bat

pyinstaller --clean ^
    --onefile ^
    --windowed ^
    --noupx ^
    --icon=ela.ico ^
    --add-data "config.json;." ^
    --add-data "background.png;." ^
    --add-data "ela.ico;." ^
    --name ElaStarter ^
    app.py

echo Build complete! Executable at: dist\ElaStarter.exe
