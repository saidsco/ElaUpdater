@echo off
pyinstaller --icon=ela.ico --onefile --windowed --add-data "background.png;." --add-data "config.json;." --add-data "ela.ico;." --name ElaStarter app.py
