@echo off
echo 🐍 Building EXE with PyInstaller...
pyinstaller --onefile --windowed --name "RetinaLogixPro" retina_metadata_gui_plus.py

echo 📦 Building Installer with Inno Setup...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" RetinaLogixProInstaller.iss

echo 🎉 Done! Installer is in Output folder.
pause
