#!/bin/bash

# Build ElaStarter with PyInstaller
# Using --noupx to avoid compression issues with large ICU library files

source venv/bin/activate

pyinstaller --clean \
    --onefile \
    --noconsole \
    --noupx \
    --icon=ela.ico \
    --add-data "config.json:." \
    --add-data "background.png:." \
    --add-data "ela.ico:." \
    --name ElaStarter \
    app.py

echo "Build complete! Executable at: dist/ElaStarter"
