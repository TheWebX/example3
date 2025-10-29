import base64
import json
import os
import cv2  # OpenCV for image reading
from pyzbar import pyzbar # For QR decoding

# --- Configuration ---
QR_CODE_DIR = 'qr_series_output' # Folder where the QR images are
# ---------------------

def reassemble_from_qrs():
    chunks = {} # Use a dictionary to store parts (handles out-of-order)
    total_parts = None
    output_filename = None

    print(f"Reading QR codes from '{QR_CODE_DIR}'...\n")
    
    # Find all PNG files in the directory
    try:
        image_files = [f for f in os.listdir(QR_CODE_DIR) if f.endswith('.png')]
        image_files.sort() # Sort to read in order (e.g., 001, 002...)
    except FileNotFoundError:
        print(f"Error: Directory '{QR_CODE_DIR}' not found.")
        return

    # 1. Read and decode all QR codes
    for img_file in image_files:
        image_path = os.path.join(QR_CODE_DIR, img_file)
        
        # Read the image
        img = cv2.imread(image_path)
        
        # Find and decode QR codes
        decoded_objects = pyzbar.decode(img)
        
        if not decoded_objects:
            print(f"Warning: Could not find a QR code in {img_file}.")
            continue
            
        # Get the data from the first QR code found
        qr_data_string = decoded_objects[0].data.decode('utf-8')
        
        # 2. Parse the JSON data
        try:
            payload = json.loads(qr_data_string)
            part_num = payload['p']
            
            # Store the Base64 data, keyed by its part number
            chunks[part_num] = payload['d']
            
            # Set total parts and filename (will be the same in all QRs)
            if total_parts is None:
                total_parts = payload['t']
                output_filename = payload['f']
                
            print(f"Read part {part_num}/{total_parts} from {img_file}")
            
        except (json.JSONDecodeError, KeyError):
            print(f"Error: Invalid data in {img_file}. Skipping.")
            
    # 3. Check for completeness and reassemble
    if not output_filename or not total_parts:
        print("Error: No valid QR codes were found.")
        return

    if len(chunks) != total_parts:
        print("\n--- ERROR: MISSING PARTS ---")
        print(f"Found {len(chunks)} parts, but expected {total_parts}.")
        expected = set(range(1, total_parts + 1))
        found = set(chunks.keys())
        print(f"Missing part numbers: {sorted(list(expected - found))}")
        return

    print(f"\nAll {total_parts} parts found. Reassembling file...")

    # 4. Write the reassembled file
    restored_filename = f"RESTORED_{output_filename}"
    
    with open(restored_filename, 'wb') as f_out:
        for i in range(1, total_parts + 1):
            # Get the Base64 data for this chunk
            base64_data = chunks[i]
            
            # Decode the Base64 back into binary
            binary_chunk = base64.b64decode(base64_data)
            
            # Write the binary chunk to the file
            f_out.write(binary_chunk)

    print(f"\nSuccess! File reassembled as '{restored_filename}'.")

if __name__ == "__main__":
    reassemble_from_qrs()
