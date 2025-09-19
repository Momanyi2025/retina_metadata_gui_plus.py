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
    "assumed_disc_diameter_mm": 1.5
}

class RetinaMetadataApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🩺 RetinaLogix Pro — DICOM + Calibration + Measurement")
        self.root.geometry("1200x800")
        self.current_image_path = None
        self.current_image_cv = None
        self.current_image_tk = None
        self.calibration_px_per_mm = None
        self.metadata = {}
        self.click_points = []
        self.measurement_lines = []  # [(x1,y1,x2,y2,mm), ...]
        self.scale_factor = 1.0  # for display resizing

        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Folder Selection
        folder_frame = ttk.Frame(main_frame)
        folder_frame.pack(fill=tk.X, pady=5)
        ttk.Button(folder_frame, text="📂 Select Image Folder", command=self.select_folder).pack(side=tk.LEFT)
        self.folder_label = ttk.Label(folder_frame, text="No folder selected")
        self.folder_label.pack(side=tk.LEFT, padx=10)

        # Image List + Viewer
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

        # Canvas for Image + Drawings
        self.canvas = tk.Canvas(right_frame, bg='gray', width=800, height=600, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=5)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Motion>", self.on_mouse_move)

        # Status bar
        self.status_label = ttk.Label(right_frame, text="Ready")
        self.status_label.pack(fill=tk.X, pady=2)

        # Tool Buttons
        tool_frame = ttk.Frame(right_frame)
        tool_frame.pack(fill=tk.X, pady=5)

        ttk.Button(tool_frame, text="🔍 Auto-Calibrate (Disc)", command=self.auto_calibrate).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="📏 Manual Calibration", command=self.start_manual_calibration).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="✏️ Measure Tool", command=self.toggle_measure_mode).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="🗑️ Clear Measurements", command=self.clear_measurements).pack(side=tk.LEFT, padx=2)

        self.calib_label = ttk.Label(tool_frame, text="Not calibrated")
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

        # Export Buttons
        btn_frame = ttk.Frame(form_frame)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="💾 Save Metadata", command=self.save_metadata).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📤 Export as DICOM", command=self.export_dicom).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🖼️ Save Sidecar JSON", command=self.save_json).pack(side=tk.LEFT, padx=5)

        self.measure_mode = False
        self.measure_start = None

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder with Retinal Images")
        if not folder:
            return
        self.folder_path = Path(folder)
        self.folder_label.config(text=str(self.folder_path))

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

        self.current_image_cv = cv2.imread(str(self.current_image_path))
        if self.current_image_cv is None:
            messagebox.showerror("Error", "Could not load image")
            return

        self.display_image(self.current_image_cv)
        self.clear_measurements()

        meta = self.parse_filename(filename)
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, meta.get(key, ""))

        self.calibration_px_per_mm = None
        self.calib_label.config(text="Not calibrated")

    def display_image(self, img_cv):
        img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        img_width, img_height = img_pil.size

        scale_w = canvas_width / img_width
        scale_h = canvas_height / img_height
        self.scale_factor = min(scale_w, scale_h)

        new_size = (int(img_width * self.scale_factor), int(img_height * self.scale_factor))
        img_pil = img_pil.resize(new_size, Image.LANCZOS)

        self.tk_image = ImageTk.PhotoImage(img_pil)
        self.canvas.delete("all")
        x_offset = (canvas_width - new_size[0]) // 2
        y_offset = (canvas_height - new_size[1]) // 2
        self.canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.tk_image)

        # Redraw measurements
        self.redraw_measurements(x_offset, y_offset)

        self.image_offsets = (x_offset, y_offset)

    def redraw_measurements(self, x_offset, y_offset):
        for line in self.measurement_lines:
            x1, y1, x2, y2, mm = line
            sx1 = x_offset + int(x1 * self.scale_factor)
            sy1 = y_offset + int(y1 * self.scale_factor)
            sx2 = x_offset + int(x2 * self.scale_factor)
            sy2 = y_offset + int(y2 * self.scale_factor)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="yellow", width=2, tags="measure")
            mid_x = (sx1 + sx2) // 2
            mid_y = (sy1 + sy2) // 2
            self.canvas.create_text(mid_x, mid_y - 10, text=f"{mm:.2f}mm", fill="yellow", font=("Arial", 10, "bold"), tags="measure")

    def on_canvas_click(self, event):
        if not hasattr(self, 'image_offsets'):
            return

        x_offset, y_offset = self.image_offsets
        # Convert click to original image coordinates
        img_x = int((event.x - x_offset) / self.scale_factor)
        img_y = int((event.y - y_offset) / self.scale_factor)

        # Ignore clicks outside image
        if img_x < 0 or img_y < 0 or img_x >= self.current_image_cv.shape[1] or img_y >= self.current_image_cv.shape[0]:
            return

        if self.measure_mode:
            if self.measure_start is None:
                self.measure_start = (img_x, img_y)
                self.status_label.config(text=f"Measure: Start point ({img_x}, {img_y})")
            else:
                end_point = (img_x, img_y)
                if self.calibration_px_per_mm:
                    # Calculate distance in mm
                    dx = end_point[0] - self.measure_start[0]
                    dy = end_point[1] - self.measure_start[1]
                    pixels = np.sqrt(dx*dx + dy*dy)
                    mm = pixels / self.calibration_px_per_mm
                    self.measurement_lines.append((*self.measure_start, *end_point, mm))
                    self.status_label.config(text=f"Measured: {mm:.2f}mm")
                else:
                    messagebox.showwarning("Warning", "Please calibrate first!")
                self.measure_start = None
                self.display_image(self.current_image_cv)  # redraw with measurement
        else:
            # For manual calibration
            self.click_points.append((img_x, img_y))
            self.status_label.config(text=f"Point {len(self.click_points)}: ({img_x}, {img_y})")
            if len(self.click_points) == 2:
                self.complete_manual_calibration()

    def on_mouse_move(self, event):
        if not hasattr(self, 'image_offsets') or self.current_image_cv is None:
            return
        x_offset, y_offset = self.image_offsets
        img_x = int((event.x - x_offset) / self.scale_factor)
        img_y = int((event.y - y_offset) / self.scale_factor)
        if 0 <= img_x < self.current_image_cv.shape[1] and 0 <= img_y < self.current_image_cv.shape[0]:
            self.status_label.config(text=f"Position: ({img_x}, {img_y}) | Calibration: {self.calibration_px_per_mm or 'None'} px/mm")

    def auto_calibrate(self):
        if self.current_image_cv is None:
            messagebox.showwarning("Warning", "No image loaded")
            return

        gray = cv2.cvtColor(self.current_image_cv, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        gray = clahe.apply(gray)

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
            x, y, r = circles[0]

            output = self.current_image_cv.copy()
            cv2.circle(output, (x, y), r, (0, 255, 0), 4)
            cv2.circle(output, (x, y), 2, (0, 0, 255), 3)

            self.calibration_px_per_mm = (2 * r) / DEVICE_PROFILE["assumed_disc_diameter_mm"]
            self.calib_label.config(text=f"✅ Auto-Calibrated: {self.calibration_px_per_mm:.1f} px/mm")
            self.display_image(output)
            messagebox.showinfo("Calibration", f"Optic disc detected!\nDiameter: {2*r}px ≈ 1.5mm\nScale: {self.calibration_px_per_mm:.1f} px/mm")
        else:
            messagebox.showwarning("Calibration Failed", "Could not detect optic disc. Try manual calibration.")

    def start_manual_calibration(self):
        self.click_points = []
        self.status_label.config(text="Click two points on a known distance (e.g., optic disc edges)")
        messagebox.showinfo("Manual Calibration", "Click two points on the image that represent a known real-world distance (e.g., 1.5mm for optic disc diameter).")

    def complete_manual_calibration(self):
        if len(self.click_points) != 2:
            return

        p1, p2 = self.click_points
        pixel_distance = np.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
        
        real_distance = simpledialog.askfloat("Calibration", "Enter real-world distance between points (mm):", initialvalue=1.5)
        if real_distance and real_distance > 0:
            self.calibration_px_per_mm = pixel_distance / real_distance
            self.calib_label.config(text=f"✅ Manual Calibration: {self.calibration_px_per_mm:.1f} px/mm")
            self.status_label.config(text=f"Calibrated: {real_distance}mm = {pixel_distance:.1f}px → {self.calibration_px_per_mm:.1f} px/mm")
            
            # Visual feedback
            output = self.current_image_cv.copy()
            cv2.line(output, p1, p2, (255, 0, 0), 2)
            cv2.circle(output, p1, 5, (0, 0, 255), -1)
            cv2.circle(output, p2, 5, (0, 0, 255), -1)
            self.display_image(output)
        else:
            messagebox.showwarning("Invalid Input", "Please enter a valid distance > 0")

        self.click_points = []

    def toggle_measure_mode(self):
        self.measure_mode = not self.measure_mode
        if self.measure_mode:
            self.status_label.config(text="📏 Measure Mode: Click start and end points")
            self.canvas.config(cursor="tcross")
        else:
            self.status_label.config(text="Measure mode off")
            self.canvas.config(cursor="cross")
            self.measure_start = None

    def clear_measurements(self):
        self.measurement_lines = []
        self.measure_start = None
        if self.current_image_cv is not None:
            self.display_image(self.current_image_cv)
        self.status_label.config(text="Measurements cleared")

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
                if 'date' in data:  # ← FIXED HERE
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
            'px_per_mm': self.calibration_px_per_mm,
            'measurements_mm': [round(line[4], 2) for line in self.measurement_lines] if self.measurement_lines else []
        }
        for key, entry in self.entries.items():
            meta[key] = entry.get().strip() or "UNKNOWN"
        return meta

    def save_metadata(self):
        if not self.current_image_path:
            messagebox.showwarning("Warning", "No image selected")
            return

        meta = self.get_metadata_from_form()
        self.save_to_csv([meta])

        if messagebox.askyesno("Rename", "Rename file to standard format?"):
            new_name = f"{meta['patient_id']}_{meta['eye']}_{meta['capture_date'].replace('-', '')}{self.current_image_path.suffix}"
            new_path = self.current_image_path.parent / new_name
            self.current_image_path.rename(new_path)
            self.current_image_path = new_path
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

        img = cv2.imread(str(self.current_image_path))
        if img is None:
            messagebox.showerror("Error", "Could not read image for DICOM")
            return

        if len(img.shape) == 3:
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            img_gray = img

        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.77.1.5.1'
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

        ds.Rows = img_gray.shape[0]
        ds.Columns = img_gray.shape[1]
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.SamplesPerPixel = 1
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.PixelData = img_gray.tobytes()

        if self.calibration_px_per_mm:
            ds.PixelSpacing = [1.0 / self.calibration_px_per_mm, 1.0 / self.calibration_px_per_mm]

        dicom_path = str(self.current_image_path).rsplit('.', 1)[0] + '.dcm'
        ds.save_as(dicom_path, write_like_original=False)
        messagebox.showinfo("Success", f"DICOM saved to {dicom_path}")

    def save_to_csv(self, metadata_list):
        fieldnames = [
            'filename', 'full_path', 'patient_id', 'eye', 'capture_date',
            'diagnosis_tags', 'notes', 'device', 'fov_deg', 'px_per_mm',
            'measurements_mm', 'processed_at'
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
