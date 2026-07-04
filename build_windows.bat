pyinstaller --onefile --name snbt-tr main.py
pyinstaller --onefile --windowed --name snbt-tr-gui main.py
"%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" setup.iss
