import os
import re
import csv
import json
from datetime import datetime
from pathlib import Path

# ===== CONFIG =====
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp'}
METADATA_LOG_FILE = 'retina_metadata_log.csv'
DEVICE_PROFILE = {
    "camera_model": "TOPCON TRC-NW6S + Nikon D70s",
    "default_fov_deg": 45,
    "non_mydriatic": True,
    "sensor_info": {
        "model": "Nikon D70s",
        "resolution_px": [3008, 2000],
        "sensor_mm": [23.7, 15.6]
    }
}

# ===== HELPER FUNCTIONS =====
def parse_filename(filename):
    """
    Try to extract PatientID, Eye, Date from filename.
    Supports patterns like:
      - PAT123_OD_20250405.jpg
      - ABC_OS_20241201.png
      - 12345_OD.jpg
    """
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
            # Convert YYYYMMDD to readable date if present
            if 'date' in 
                try:
                    dt = datetime.strptime(data['date'], '%Y%m%d')
                    data['capture_date'] = dt.strftime('%Y-%m-%d')
                    del data['date']
                except:
                    data['capture_date'] = data['date']
            return data
    return {}

def get_user_input_for_image(filename):
    """Prompt user to enter metadata manually"""
    print(f"\n--- Tagging: {filename} ---")
    patient_id = input("Patient ID (e.g., PAT123): ").strip() or "UNKNOWN"
    eye = input("Eye (OD=right, OS=left, OU=both) [OD/OS/OU]: ").strip().upper()
    while eye not in {'OD', 'OS', 'OU'}:
        eye = input("Invalid. Enter OD, OS, or OU: ").strip().upper()
    capture_date = input("Capture Date (YYYY-MM-DD) or press Enter for today: ").strip()
    if not capture_date:
        capture_date = datetime.today().strftime('%Y-%m-%d')
    diagnosis = input("Diagnosis/Tags (e.g., DR, Glaucoma, Normal): ").strip() or "Not assessed"
    notes = input("Notes: ").strip() or ""
    
    return {
        'patient_id': patient_id,
        'eye': eye,
        'capture_date': capture_date,
        'diagnosis_tags': diagnosis,
        'notes': notes
    }

def save_metadata_to_csv(metadata_list, csv_path):
    """Save all metadata to CSV log"""
    fieldnames = [
        'filename', 'full_path', 'patient_id', 'eye', 'capture_date',
        'diagnosis_tags', 'notes', 'device', 'fov_deg', 'processed_at'
    ]
    
    file_exists = os.path.isfile(csv_path)
    
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for meta in metadata_list:
            writer.writerow(meta)

def save_metadata_to_json(metadata, image_path):
    """Save metadata as sidecar .json file (same name as image)"""
    json_path = str(image_path).rsplit('.', 1)[0] + '.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f" → Saved metadata to {json_path}")

def rename_file_to_standard(image_path, metadata):
    """Optional: Rename file to standard format: PATIENT_EYE_DATE.jpg"""
    new_name = f"{metadata['patient_id']}_{metadata['eye']}_{metadata['capture_date'].replace('-', '')}{image_path.suffix}"
    new_path = image_path.parent / new_name
    image_path.rename(new_path)
    print(f" → Renamed to {new_name}")
    return new_path

# ===== MAIN FUNCTION =====
def main():
    print("🩺 Retina Image Metadata Tagger (TOPCON TRC-NW6S + Nikon D70s)")
    print("="*60)
    
    folder = input("Enter folder path with retinal images: ").strip()
    folder_path = Path(folder)
    
    if not folder_path.exists():
        print("❌ Folder not found!")
        return
    
    # Find image files
    image_files = [f for f in folder_path.iterdir() 
                   if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
    
    if not image_files:
        print("❌ No image files found!")
        return
    
    print(f"\nFound {len(image_files)} images. Processing...\n")
    
    all_metadata = []
    
    for img_path in image_files:
        print(f"\n📄 Processing: {img_path.name}")
        
        # Try auto-parse from filename
        meta = parse_filename(img_path.name)
        
        if meta:
            print(f" → Auto-parsed: {meta}")
            # Fill in missing fields
            meta.setdefault('diagnosis_tags', 'Auto-parsed')
            meta.setdefault('notes', 'From filename')
        else:
            print(" → No auto-parse pattern matched. Manual input required.")
            meta = get_user_input_for_image(img_path.name)
        
        # Add system fields
        meta.update({
            'filename': img_path.name,
            'full_path': str(img_path.resolve()),
            'device': DEVICE_PROFILE['camera_model'],
            'fov_deg': DEVICE_PROFILE['default_fov_deg'],
            'processed_at': datetime.now().isoformat()
        })
        
        # Ask if user wants to rename
        rename = input("Rename file to standard format? (y/N): ").strip().lower()
        if rename == 'y':
            img_path = rename_file_to_standard(img_path, meta)
            meta['filename'] = img_path.name
            meta['full_path'] = str(img_path.resolve())
        
        # Save sidecar JSON
        save_metadata_to_json(meta, img_path)
        
        all_metadata.append(meta)
    
    # Save to master CSV
    save_metadata_to_csv(all_metadata, METADATA_LOG_FILE)
    print(f"\n✅ All done! Metadata saved to '{METADATA_LOG_FILE}'")
    print(f"📁 Processed {len(all_metadata)} images.")

if __name__ == "__main__":
    main()
