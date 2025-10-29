import base64
import json
import os
import math
import qrcode
import sys
import tkinter as tk
from PIL import Image, ImageTk
import threading
import argparse
import queue
import time

# --- Configuration ---
# Set the size of the data chunk (in bytes)
# This *must* match the receiver script
CHUNK_SIZE_BYTES = 2048
# ---------------------

def get_file_chunks(file_path):
    """Reads a file and yields binary chunks of it."""
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                yield chunk
    except FileNotFoundError:
        print(f"Error: Source file '{file_path}' not found.")
        return None
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        return None

def generate_qr_image(data, box_size=6):
    """Generates a single QR code image in memory."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img

class QRPresenter:
    """
    A Tkinter GUI class to display images from a queue.
    """
    def __init__(self, root, image_queue, total_parts):
        self.root = root
        self.image_queue = image_queue
        self.total_parts = total_parts
        self.current_part = 0
        
        self.root.title("QR Code Broadcaster")
        # Set window size and position (1200x1200 at top-left corner)
        self.root.geometry("1200x1200+0+0")
        
        # Configure the window to not be resizable
        self.root.resizable(False, False)
        
        # Set a black background
        self.root.configure(bg='black')

        self.label = tk.Label(root, bg='black')
        # Use expand=True to center the label in the window
        self.label.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.check_for_image()

    def check_for_image(self):
        """
        Checks the queue for a new image and displays it.
        This is the main GUI loop.
        """
        try:
            # Get an image from the queue (non-blocking)
            img = self.image_queue.get_nowait()
            
            # A 'None' object is the signal to stop
            if img is None:
                self.show_end_message()
                return

            # Convert the PIL image to a PhotoImage
            self.photo = ImageTk.PhotoImage(img)
            self.label.config(image=self.photo)
            
            self.current_part += 1
            self.root.title(f"QR Code Broadcaster - Part {self.current_part}/{self.total_parts}")

            # Schedule the next check (100ms = 10 FPS)
            self.root.after(100, self.check_for_image)

        except queue.Empty:
            # If the queue is empty, check again in 10ms
            # This allows the generator to catch up
            self.root.after(10, self.check_for_image)

    def show_end_message(self):
        """Displays a 'Finished' message."""
        # Clear the image
        self.label.config(image=None, text="All parts sent.", font=("Arial", 30), fg="white")
        self.root.title("QR Code Broadcaster - Finished")

def generation_thread(file_path, remediation_parts, image_queue):
    """
    This runs in a background thread.
    It reads the file and generates QR codes "just-in-time".
    It puts the generated images into the image_queue.
    """
    try:
        file_size = os.path.getsize(file_path)
        total_parts = math.ceil(file_size / CHUNK_SIZE_BYTES)
        
        print(f"Total parts to generate: {total_parts}")
        
        # Get the filename to embed in the payload
        file_name = os.path.basename(file_path)

        for part_number, chunk_data in enumerate(get_file_chunks(file_path), 1):
            
            # --- Remediation Logic ---
            # If a remediation list is provided,
            # skip parts that are NOT in the list.
            if remediation_parts and part_number not in remediation_parts:
                continue
            
            print(f"  > Broadcasting part {part_number}/{total_parts}")

            # Encode the binary chunk to a Base64 string
            base64_data = base64.b64encode(chunk_data).decode('utf-8')
            
            # Create the JSON payload
            payload = {
                "p": part_number,
                "t": total_parts,
                "f": file_name,
                "d": base64_data
            }
            json_string = json.dumps(payload)
            
            # Generate the QR code image
            img = generate_qr_image(json_string, box_size=6)
            
            # Put the image into the queue.
            # This will block if the queue is full (size=1),
            # forcing this thread to wait until the GUI
            # has consumed the previous image.
            image_queue.put(img)

        # Send a 'None' signal to tell the GUI thread we are done
        image_queue.put(None)

    except Exception as e:
        print(f"Error in generation thread: {e}")
        image_queue.put(None) # Ensure the GUI stops

def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Broadcast a file as a series of QR codes.")
    parser.add_argument("file", help="The path to the file you want to send.")
    parser.add_argument("--remediate", help="Path to a 'missing_parts.json' file for remediation.")
    
    args = parser.parse_args()

    # --- Remediation Logic ---
    remediation_parts = None
    if args.remediate:
        try:
            with open(args.remediate, 'r') as f:
                remediation_data = json.load(f)
                remediation_parts = set(remediation_data.get("missing", []))
            if not remediation_parts:
                print("Error: Remediation file is empty or invalid.")
                return
            print(f"--- REMEDIATION MODE ---")
            print(f"Only sending {len(remediation_parts)} missing parts: {sorted(list(remediation_parts))}")
        except FileNotFoundError:
            print(f"Error: Remediation file not found at '{args.remediate}'")
            return
        except json.JSONDecodeError:
            print(f"Error: Could not parse remediation file '{args.remediate}'.")
            return
    # -------------------------

    # Check if the main file exists
    if not os.path.exists(args.file):
        print(f"Error: Source file '{args.file}' not found.")
        return

    # This queue has a max size of 1.
    # This creates a "producer-consumer" model where the
    # generation thread (producer) waits for the GUI (consumer)
    # to be ready for the next frame.
    image_queue = queue.Queue(maxsize=1)

    # Calculate total parts for the GUI title
    file_size = os.path.getsize(args.file)
    total_parts = math.ceil(file_size / CHUNK_SIZE_BYTES)
    
    if remediation_parts:
        display_total = len(remediation_parts)
    else:
        display_total = total_parts

    # Start the Tkinter GUI
    root = tk.Tk()
    app = QRPresenter(root, image_queue, display_total)

    # Start the background thread for QR generation
    gen_thread = threading.Thread(
        target=generation_thread,
        args=(args.file, remediation_parts, image_queue),
        daemon=True
    )
    gen_thread.start()

    # Start the Tkinter main loop
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nBroadcast stopped by user.")
    finally:
        print("Closing application.")

if __name__ == "__main__":
    main()

