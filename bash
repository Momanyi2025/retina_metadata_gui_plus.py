python retina_metadata_tagger.py
pip install opencv-python pydicom numpy pillow
python retina_metadata_gui.py
pyinstaller --onefile --windowed --add-data "retina_metadata_log.csv;." --name "RetinaLogixPro" retina_metadata_gui_plus.py
pyinstaller build.spec
pyinstaller --onefile --windowed --name "RetinaLogixPro" retina_metadata_gui_plus.py
pip install opencv-python pydicom numpy pillow pyinstaller
python retina_metadata_gui_plus.py
pyinstaller --onefile --windowed --name "RetinaLogixPro" retina_metadata_gui_plus.py
RetinaLogixPro_Setup.exe /SILENT
pyupdater build --app-version=1.1.0 retina_metadata_gui_plus.py --name RetinaLogixPro
pyupdater pkg --process --sign
pyupdater init
 ➤ Enter your company name: YourClinic
 ➤ Enter your app name: RetinaLogixPro
 ➤ Enter your app version: 1.0.0
 ➤ Enter your update URL: https://github.com/yourusername/retinalogix/releases/download/
 ➤ Is the url above correct?: y
 ➤ Would you like to use a symmetric cipher?: n
 ➤ Would you like to setup a client config?: y
