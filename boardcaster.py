import base64
import json
import os
import math
import qrcode
import argparse
import tkinter as tk
from PIL import Image, ImageTk

# --- Configuration ---
# This must match the receiver script to be scannable.
# 2048 bytes (2KB) is a safe, scannable size.
CHUNK_SIZE_BYTES = 2048
# ---------------------

class QRPresenter:
    """
    A simple Tkinter app to display a series of QR code images,
    advancing with a key press.
    """
    def __init__(self, root, qr_images, filename):
        self.root = root
        self.qr_images = qr_images
        self.total_parts = len(qr_images)
        self.current_part = 0
        
        # 1. Setup the window
        self.root.title(f"Sending: {filename}")
        
        # 2. Create a label for text (e.g., "Part 1 of 13")
        self.info_label = tk.Label(root, text="", font=("Helvetica", 16))
        self.info_label.pack(pady=10)
        
        # 3. Create a label to hold the QR code image
        self.qr_label = tk.Label(root)
        # Center the label in the available space
        self.qr_label.pack(padx=20, pady=20, expand=True)
        
        # 4. Remove key bindings
        # self.root.bind("<Return>", self.show_next_image)
        # self.root.bind("<space>", self.show_next_image)
        
        # 5. Show the first image and start the automatic loop
        self.show_next_image()

    def show_next_image(self, event=None):
        if self.current_part >= self.total_parts:
            # All parts have been shown
            self.info_label.config(text=f"All {self.total_parts} parts sent.\nYou can close this window.")
            # Optionally, disable the image or close the app
            # self.root.quit()
            return
            
        # Get the next image
        img = self.qr_images[self.current_part]
        
        # Convert the PIL image to a Tkinter-compatible photo image
        tk_img = ImageTk.PhotoImage(img)
        
        # Update the image label
        self.qr_label.config(image=tk_img)
        # Keep a reference to the image to prevent garbage collection
        self.qr_label.image = tk_img
        
        # Update the text label
        part_num = self.current_part + 1
        self.info_label.config(text=f"Part {part_num} of {self.total_parts}\n(Broadcasting automatically...)")
        
        print(f"Showing part {part_num}/{self.total_parts}")
        
        # Increment the counter for the next run
        self.current_part += 1
        
        # Schedule this function to run again after 1000ms (1 second)
        self.root.after(1000, self.show_next_image)

def generate_qr_images(source_file):
    """
    Reads a file, splits it into chunks, and generates a list
    of in-memory QR code Image objects.
    """
    
    # 1. Read the source file as binary
    try:
        with open(source_file, 'rb') as f:
            file_data = f.read()
    except FileNotFoundError:
        print(f"Error: Source file '{source_file}' not found.")
        return None, None
    except Exception as e:
        print(f"Error reading file: {e}")
        return None, None

    total_size = len(file_data)
    total_parts = math.ceil(total_size / CHUNK_SIZE_BYTES)
    
    print(f"Source file: '{source_file}' ({total_size} bytes)")
    print(f"Chunk size: {CHUNK_SIZE_BYTES} bytes")
    print(f"Total QR codes to generate: {total_parts}\n")

    qr_images = []
    
    for i in range(total_parts):
        part_number = i + 1
        start_byte = i * CHUNK_SIZE_BYTES
        end_byte = (i + 1) * CHUNK_SIZE_BYTES
        
        chunk_data = file_data[start_byte:end_byte]
        
        # Encode the binary chunk to a Base64 string
        base64_data = base64.b64encode(chunk_data).decode('utf-8')
        
        # Create the JSON payload (must match receiver's format)
        payload = {
            "p": part_number,
            "t": total_parts,
            "f": os.path.basename(source_file), # Send only the filename
            "d": base64_data
        }
        
        json_string = json.dumps(payload)
        
        # Generate the QR code image in memory
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=6, # Changed from 8 to 6 to better fit in 1000x1000
            border=4,
        )
        qr.add_data(json_string)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        qr_images.append(img)
        
    print(f"Generated {len(qr_images)} QR code images in memory.")
    return qr_images, os.path.basename(source_file)

def main():
    # Setup command-line argument parsing
    parser = argparse.ArgumentParser(description="Display a file as a series of QR codes.")
    parser.add_argument("file", help="The path to the file you want to send.")
    args = parser.parse_args()

    # Generate all QR code images first
    qr_images, filename = generate_qr_images(args.file)
    
    if not qr_images:
        print("Could not generate QR codes. Exiting.")
        return

    # Create the main Tkinter window
    root = tk.Tk()
    # Set the window size
    root.geometry("1500x1500")
    
    # Create the app instance
    app = QRPresenter(root, qr_images, filename)
    
    # Start the GUI event loop
    print("\nStarting QR code display. Broadcasting automatically.")
    root.mainloop()

if __name__ == "__main__":
    main()

