import os
import re
import csv
import json
import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from datetime import datetime
from pathlib import Path
import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
from PIL import Image, ImageTk

# ===== CONFIG =====
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
METADATA_LOG_FILE = 'retina_metadata_log.csv'
DEVICE_PROFILE = {
    "camera_model": "TOPCON TRC-NW6S + Nikon D70s",
    "default_fov_deg": 45,
    "non_mydriatic": True,
    "sensor_info": {
        "model": "Nikon D70s",
        "resolution_px": [3008, 2000],
        "sensor_mm": [23.7, 15.6]
    },
    "assumed_disc_diameter_mm": 1.5  # Average optic disc size
}

class RetinaMetadataApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🩺 RetinaLogix Legacy — DICOM + Calibration")
        self.root.geometry("1000x700")
        self.current_image_path = None
        self.current_image_cv = None
        self.calibration_px_per_mm = None
        self.metadata = {}

        self.setup_ui()

    def setup_ui(self):
        # Main Frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top: Folder Selection
        folder_frame = ttk.Frame(main_frame)
        folder_frame.pack(fill=tk.X, pady=5)
        ttk.Button(folder_frame, text="📂 Select Image Folder", command=self.select_folder).pack(side=tk.LEFT)
        self.folder_label = ttk.Label(folder_frame, text="No folder selected")
        self.folder_label.pack(side=tk.LEFT, padx=10)

        # Middle: Image List + Viewer
        mid_frame = ttk.Frame(main_frame)
        mid_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Left: Image List
        left_frame = ttk.LabelFrame(mid_frame, text="Images", width=200)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0,5))
        left_frame.pack_propagate(False)

        self.image_listbox = tk.Listbox(left_frame, selectmode=tk.SINGLE)
        self.image_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.image_listbox.bind('<<ListboxSelect>>', self.on_image_select)

        # Right: Image Viewer + Tools
        right_frame = ttk.Frame(mid_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5,0))

        # Image Canvas
        self.canvas = tk.Canvas(right_frame, bg='gray', width=600, height=500)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=5)

        # Calibration Button
        calib_frame = ttk.Frame(right_frame)
        calib_frame.pack(fill=tk.X, pady=5)
        ttk.Button(calib_frame, text="🔍 Auto-Calibrate (Detect Disc)", command=self.auto_calibrate).pack(side=tk.LEFT)
        self.calib_label = ttk.Label(calib_frame, text="Not calibrated")
        self.calib_label.pack(side=tk.LEFT, padx=10)

        # Metadata Form
        form_frame = ttk.LabelFrame(right_frame, text="Metadata", padding=10)
        form_frame.pack(fill=tk.X, pady=5)

        fields = [
            ("Patient ID:", "patient_id"),
            ("Eye (OD/OS/OU):", "eye"),
            ("Date (YYYY-MM-DD):", "capture_date"),
            ("Diagnosis Tags:", "diagnosis_tags"),
            ("Notes:", "notes")
        ]

        self.entries = {}
        for i, (label_text, key) in enumerate(fields):
            ttk.Label(form_frame, text=label_text).grid(row=i, column=0, sticky=tk.W, pady=2)
            entry = ttk.Entry(form_frame, width=40)
            entry.grid(row=i, column=1, sticky=tk.W, pady=2)
            self.entries[key] = entry

        # Buttons
        btn_frame = ttk.Frame(form_frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="💾 Save Metadata", command=self.save_metadata).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📤 Export as DICOM", command=self.export_dicom).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🖼️ Save Sidecar JSON", command=self.save_json).pack(side=tk.LEFT, padx=5)

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder with Retinal Images")
        if not folder:
            return
        self.folder_path = Path(folder)
        self.folder_label.config(text=str(self.folder_path))

        # Load images
        image_files = sorted([f for f in self.folder_path.iterdir()
                            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS])
        self.image_listbox.delete(0, tk.END)
        for f in image_files:
            self.image_listbox.insert(tk.END, f.name)

        if image_files:
            self.image_listbox.selection_set(0)
            self.on_image_select(None)

    def on_image_select(self, event):
        selection = self.image_listbox.curselection()
        if not selection:
            return
        filename = self.image_listbox.get(selection[0])
        self.current_image_path = self.folder_path / filename

        # Load image for OpenCV and Tkinter
        self.current_image_cv = cv2.imread(str(self.current_image_path))
        if self.current_image_cv is None:
            messagebox.showerror("Error", "Could not load image")
            return

        # Display in canvas
        self.display_image(self.current_image_cv)

        # Try to auto-fill metadata from filename
        meta = self.parse_filename(filename)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, meta.get(key, ""))

        # Reset calibration
        self.calibration_px_per_mm = None
        self.calib_label.config(text="Not calibrated")

    def display_image(self, img_cv):
        # Convert BGR to RGB for PIL
        img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)
        
        # Resize to fit canvas while keeping aspect ratio
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        img_width, img_height = img_pil.size
        
        scale = min(canvas_width / img_width, canvas_height / img_height)
        new_size = (int(img_width * scale), int(img_height * scale))
        img_pil = img_pil.resize(new_size, Image.LANCZOS)
        
        # Convert to PhotoImage
        self.tk_image = ImageTk.PhotoImage(img_pil)
        self.canvas.delete("all")
        x = (canvas_width - new_size[0]) // 2
        y = (canvas_height - new_size[1]) // 2
        self.canvas.create_image(x, y, anchor=tk.NW, image=self.tk_image)

    def auto_calibrate(self):
        if self.current_image_cv is None:
            messagebox.showwarning("Warning", "No image loaded")
            return

        # Convert to grayscale
        gray = cv2.cvtColor(self.current_image_cv, cv2.COLOR_BGR2GRAY)
        
        # Apply CLAHE for contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        gray = clahe.apply(gray)
        
        # Detect circles (HoughCircles) — optic disc is roughly circular
        circles = cv2.HoughCircles(
            gray, 
            cv2.HOUGH_GRADIENT, 
            dp=1.2, 
            minDist=100,
            param1=50, 
            param2=30, 
            minRadius=30, 
            maxRadius=150
        )
        
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            # Take the first detected circle (largest or most central)
            x, y, r = circles[0]
            
            # Draw circle on image for feedback
            output = self.current_image_cv.copy()
            cv2.circle(output, (x, y), r, (0, 255, 0), 4)
            cv2.circle(output, (x, y), 2, (0, 0, 255), 3)
            self.display_image(output)
            
            # Calculate px/mm: disc diameter = 2*r pixels = 1.5 mm
            self.calibration_px_per_mm = (2 * r) / DEVICE_PROFILE["assumed_disc_diameter_mm"]
            self.calib_label.config(text=f"✅ Calibrated: {self.calibration_px_per_mm:.1f} px/mm")
            messagebox.showinfo("Calibration", f"Optic disc detected!\nDiameter: {2*r}px ≈ 1.5mm\nScale: {self.calibration_px_per_mm:.1f} px/mm")
        else:
            messagebox.showwarning("Calibration Failed", "Could not detect optic disc. Try manual calibration or adjust image.")

    def parse_filename(self, filename):
        stem = Path(filename).stem
        patterns = [
            r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<eye>OD|OS|OU)_(?P<date>\d{8})$',
            r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<eye>OD|OS|OU)$',
            r'^(?P<patient_id>PAT\d+)$',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, stem)
            if match:
                data = match.groupdict()
                if 'date' in 
                    try:
                        dt = datetime.strptime(data['date'], '%Y%m%d')
                        data['capture_date'] = dt.strftime('%Y-%m-%d')
                    except:
                        data['capture_date'] = data['date']
                return data
        return {"patient_id": "UNKNOWN", "eye": "OD", "capture_date": datetime.today().strftime('%Y-%m-%d')}

    def get_metadata_from_form(self):
        meta = {
            'filename': self.current_image_path.name if self.current_image_path else "",
            'full_path': str(self.current_image_path.resolve()) if self.current_image_path else "",
            'device': DEVICE_PROFILE['camera_model'],
            'fov_deg': DEVICE_PROFILE['default_fov_deg'],
            'processed_at': datetime.now().isoformat(),
            'px_per_mm': self.calibration_px_per_mm
        }
        for key, entry in self.entries.items():
            meta[key] = entry.get().strip() or "UNKNOWN"
        return meta

    def save_metadata(self):
        if not self.current_image_path:
            messagebox.showwarning("Warning", "No image selected")
            return

        meta = self.get_metadata_from_form()
        
        # Save to CSV log
        self.save_to_csv([meta])
        
        # Optional: rename file
        if messagebox.askyesno("Rename", "Rename file to standard format?"):
            new_name = f"{meta['patient_id']}_{meta['eye']}_{meta['capture_date'].replace('-', '')}{self.current_image_path.suffix}"
            new_path = self.current_image_path.parent / new_name
            self.current_image_path.rename(new_path)
            self.current_image_path = new_path
            # Refresh list
            self.select_folder()
            messagebox.showinfo("Success", f"File renamed to {new_name}")

        messagebox.showinfo("Success", "Metadata saved to CSV log.")

    def save_json(self):
        if not self.current_image_path:
            return
        meta = self.get_metadata_from_form()
        json_path = str(self.current_image_path).rsplit('.', 1)[0] + '.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Success", f"Metadata saved to {json_path}")

    def export_dicom(self):
        if not self.current_image_path:
            messagebox.showwarning("Warning", "No image selected")
            return

        meta = self.get_metadata_from_form()

        # Load image
        img = cv2.imread(str(self.current_image_path))
        if img is None:
            messagebox.showerror("Error", "Could not read image for DICOM")
            return

        # Convert to 8-bit grayscale if needed
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Create DICOM dataset
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.77.1.5.1'  # Ophthalmic Photography
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        ds = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)
        ds.PatientName = meta.get('patient_id', 'UNKNOWN')
        ds.PatientID = meta.get('patient_id', 'UNKNOWN')
        ds.StudyDate = meta.get('capture_date', '').replace('-', '')
        ds.SeriesDescription = f"Retinal Photo - {meta.get('eye', 'OD')}"
        ds.Manufacturer = "TOPCON"
        ds.ManufacturerModelName = "TRC-NW6S + Nikon D70s"
        ds.ImageType = ["ORIGINAL", "PRIMARY", "COLOR"]

        # Image data
        ds.Rows = img.shape[0]
        ds.Columns = img.shape[1]
        ds.PhotometricInterpretation = "MONOCHROME2" if len(img.shape) == 2 else "RGB"
        ds.SamplesPerPixel = 1 if len(img.shape) == 2 else 3
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.PixelData = img.tobytes()

        # Add calibration if available
        if self.calibration_px_per_mm:
            ds.PixelSpacing = [1.0 / self.calibration_px_per_mm, 1.0 / self.calibration_px_per_mm]

        # Save
        dicom_path = str(self.current_image_path).rsplit('.', 1)[0] + '.dcm'
        ds.save_as(dicom_path, write_like_original=False)
        messagebox.showinfo("Success", f"DICOM saved to {dicom_path}")

    def save_to_csv(self, metadata_list):
        fieldnames = [
            'filename', 'full_path', 'patient_id', 'eye', 'capture_date',
            'diagnosis_tags', 'notes', 'device', 'fov_deg', 'px_per_mm', 'processed_at'
        ]
        
        file_exists = os.path.isfile(METADATA_LOG_FILE)
        
        with open(METADATA_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for meta in metadata_list:
                writer.writerow(meta)

if __name__ == "__main__":
    root = tk.Tk()
    app = RetinaMetadataApp(root)
    root.mainloop()
