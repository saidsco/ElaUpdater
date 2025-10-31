

#!/bin/bash

pyinstaller --onefile --noconsole --icon=ela.ico --add-data "config.json:." --add-data "background.png:." --add-data "ela.ico:." --name "ElaStarter" app.py