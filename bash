python retina_metadata_tagger.py
pip install opencv-python pydicom numpy pillow
python retina_metadata_gui.py
pyinstaller --onefile --windowed --add-data "retina_metadata_log.csv;." --name "RetinaLogixPro" retina_metadata_gui_plus.py
pyinstaller build.spec
pyinstaller --onefile --windowed --name "RetinaLogixPro" retina_metadata_gui_plus.py
