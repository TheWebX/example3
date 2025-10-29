import base64
import json
import os
import math
import qrcode

# --- Configuration ---
SOURCE_FILE = 'my_file.zip'  # The file you want to split
OUTPUT_DIR = 'qr_series_output' # Folder to save the images
# This is the size of the *original binary* data per chunk.
# 1024 bytes (1KB) is a safe, scannable size.
# Base64 encoding will make this ~1366 bytes, which fits
# well within a QR code's limits.
CHUNK_SIZE_BYTES = 1024
# ---------------------

def create_qr_series():
    # 1. Create output directory
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: {OUTPUT_DIR}")

    # 2. Read the source file as binary
    try:
        with open(SOURCE_FILE, 'rb') as f:
            file_data = f.read()
    except FileNotFoundError:
        print(f"Error: Source file '{SOURCE_FILE}' not found.")
        return

    total_size = len(file_data)
    total_parts = math.ceil(total_size / CHUNK_SIZE_BYTES)
    
    print(f"Source file: '{SOURCE_FILE}' ({total_size} bytes)")
    print(f"Chunk size: {CHUNK_SIZE_BYTES} bytes")
    print(f"Total QR codes to generate: {total_parts}\n")

    # 3. Loop through the data and create a QR code for each chunk
    for i in range(total_parts):
        part_number = i + 1
        start_byte = i * CHUNK_SIZE_BYTES
        end_byte = (i + 1) * CHUNK_SIZE_BYTES
        
        # Get the binary chunk
        chunk_data = file_data[start_byte:end_byte]
        
        # 4. Encode the binary chunk to a Base64 string
        # We must decode('utf-8') to make it a JSON-safe string
        base64_data = base64.b64encode(chunk_data).decode('utf-8')
        
        # 5. Create the JSON payload
        # 'p' = part, 't' = total, 'f' = filename, 'd' = data
        payload = {
            "p": part_number,
            "t": total_parts,
            "f": SOURCE_FILE,
            "d": base64_data
        }
        
        json_string = json.dumps(payload)
        
        # 6. Generate the QR code image
        qr = qrcode.QRCode(
            version=None, # Auto-detect version
            error_correction=qrcode.constants.ERROR_CORRECT_L, # Low error correction for max data
            box_size=10,
            border=4,
        )
        qr.add_data(json_string)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 7. Save the image
        # Use 3-digit padding for correct file sorting (e.g., 001, 002, ...)
        file_name = f"{SOURCE_FILE}_part_{part_number:03d}_of_{total_parts:03d}.png"
        img.save(os.path.join(OUTPUT_DIR, file_name))
        
        print(f"Generated {file_name} (Part {part_number}/{total_parts})")

    print(f"\nSuccess! Created {total_parts} QR codes in '{OUTPUT_DIR}'.")

if __name__ == "__main__":
    create_qr_series()
