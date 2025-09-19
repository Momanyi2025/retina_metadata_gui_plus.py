# ===== AUTO-UPDATE SUPPORT =====
import sys
from client_config import ClientConfig
from pyupdater.client import Client
import threading
import webbrowser

def check_for_updates_async(callback=None):
    def update_check():
        try:
            client = Client(ClientConfig())
            client.refresh()
            app_update = client.update_check("RetinaLogixPro", "1.0.0")  # ← Update version as you release
            if app_update:
                if callback:
                    callback(app_update)
            else:
                if callback:
                    callback(None)
        except Exception as e:
            print("Update check failed:", e)
            if callback:
                callback(None)
    thread = threading.Thread(target=update_check)
    thread.daemon = True
    thread.start()

def download_and_install_update(app_update):
    if messagebox.askyesno("Update Available", "A new version is available. Download and install now?"):
        try:
            app_update.download()
            if app_update.is_downloaded():
                app_update.extract()
                app_update.restart()
            else:
                messagebox.showerror("Update Failed", "Download failed. Please try again later.")
        except Exception as e:
            messagebox.showerror("Update Error", f"Could not install update:\n{str(e)}")
