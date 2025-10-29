import base64
import json
import os
import math
import qrcode
import argparse
import tkinter as tk
from PIL import Image, ImageTk
import threading
import queue # Added for thread-safe image passing

# --- Configuration ---
# This must match the receiver script to be scannable.
CHUNK_SIZE_BYTES = 2048
# ---------------------

class QRPresenter:
    """
    A simple Tkinter app to display a series of QR code images.
    It loads images from a queue as they are generated in a background thread.
    """
    def __init__(self, root, total_parts, filename, image_queue, remediation_list=None):
        self.root = root
        self.total_parts = total_parts
        self.filename = filename
        self.image_queue = image_queue
        
        # Calculate the number of parts to be sent
        if remediation_list:
            self.parts_to_send = len(remediation_list)
        else:
            self.parts_to_send = total_parts
            
        self.parts_sent = 0
        
        # 1. Setup the window
        self.root.title(f"Sending: {filename}")
        
        # 2. Create a label for text
        self.info_label = tk.Label(root, text=f"Generating Part 1 of {self.parts_to_send}...\nPlease wait.", font=("Helvetica", 16))
        self.info_label.pack(pady=10)
        
        # 3. Create a label to hold the QR code image
        self.qr_label = tk.Label(root)
        # Center the label in the available space
        self.qr_label.pack(padx=20, pady=20, expand=True)
        
        # Start the consumer loop
        self.check_for_image()

    def check_for_image(self):
        """
        Checks the queue for a new image.
        If found, displays it and schedules the next check after 1 sec.
        If not found, schedules a retry in 100ms.
        """
        try:
            # Try to get an image from the queue without blocking
            img, part_num_absolute = self.image_queue.get_nowait()
            
            if img is None:
                # Sentinel value: This means generation is complete
                self.info_label.config(text=f"All {self.parts_to_send} parts sent.\nYou can close this window.")
                return
            
            # We got an image! Increment counter and display it.
            self.parts_sent += 1
            
            # Convert the PIL image to a Tkinter-compatible photo image
            tk_img = ImageTk.PhotoImage(img)
            
            # Update the image label
            self.qr_label.config(image=tk_img)
            # Keep a reference to the image to prevent garbage collection
            self.qr_label.image = tk_img
            
            # Update the text label
            self.info_label.config(text=f"Part {part_num_absolute} of {self.total_parts}\n(Sending {self.parts_sent} of {self.parts_to_send} parts)\n(Broadcasting automatically...)")
            print(f"Showing part {part_num_absolute}/{self.total_parts} (Sent {self.parts_sent}/{self.parts_to_send})")
            
            # Schedule the *next check* after the 1-second display time
            self.root.after(1000, self.check_for_image)

        except queue.Empty:
            # Queue is empty, means generator is still working
            # Schedule a retry in 100ms without incrementing the counter
            self.root.after(100, self.check_for_image)
        
        except Exception as e:
            print(f"Error displaying image: {e}")
            self.info_label.config(text=f"Error displaying part {self.parts_sent + 1}!")


def get_file_info(source_file):
    """Reads file and calculates total parts."""
    try:
        with open(source_file, 'rb') as f:
            file_data = f.read()
    except FileNotFoundError:
        print(f"Error: Source file '{source_file}' not found.")
        return None, None, None
    except Exception as e:
        print(f"Error reading file: {e}")
        return None, None, None

    total_size = len(file_data)
    total_parts = math.ceil(total_size / CHUNK_SIZE_BYTES)
    filename = os.path.basename(source_file)
    
    print(f"Source file: '{filename}' ({total_size} bytes)")
    print(f"Chunk size: {CHUNK_SIZE_BYTES} bytes")
    print(f"Total QR codes to generate: {total_parts}\n")
    
    return file_data, total_parts, filename

def generate_qr_images_to_queue(file_data, total_parts, filename, image_queue, remediation_list=None):
    """
    (This function runs in a separate thread)
    Generates QR codes one by one and puts them in the queue.
    If remediation_list is provided, it only generates parts from that list.
    """
    try:
        if remediation_list:
            print(f"Starting REMEDIATION. Sending {len(remediation_list)} specific parts...")
            part_iterator = remediation_list
        else:
            print("Starting QR code generation thread...")
            part_iterator = range(1, total_parts + 1)
        
        for part_number in part_iterator:
            # Ensure part_number is an integer
            part_number = int(part_number)
            
            start_byte = (part_number - 1) * CHUNK_SIZE_BYTES
            end_byte = part_number * CHUNK_SIZE_BYTES
            
            chunk_data = file_data[start_byte:end_byte]
            
            # Encode the binary chunk to a Base64 string
            base64_data = base64.b64encode(chunk_data).decode('utf-8')
            
            # Create the JSON payload (must match receiver's format)
            payload = {
                "p": part_number,
                "t": total_parts,
                "f": filename,
                "d": base64_data
            }
            
            json_string = json.dumps(payload)
            
            # Generate the QR code image in memory
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=6, # Fits well in 1200x1200 window
                border=4,
            )
            qr.add_data(json_string)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Add a print statement to show progress
            print(f"  > Generated image {part_number}/{total_parts}")
            
            # Put the generated image in the queue.
            # This will BLOCK if the queue is full (maxsize=1)
            # until the main thread takes the image out.
            # We send a tuple: (image, part_number)
            image_queue.put((img, part_number))
            
        # After loop, put the sentinel value (None, None) to signal the end
        image_queue.put((None, None))

    except Exception as e:
        print(f"\n--- ERROR during QR Generation ---")
        print(e)
        # Put sentinel value to stop the GUI loop on error
        image_queue.put((None, None))


def main():
    # Setup command-line argument parsing
    parser = argparse.ArgumentParser(description="Display a file as a series of QR codes.")
    parser.add_argument("file", help="The path to the file you want to send.")
    parser.add_description = "Path to a JSON file listing missing parts to resend."
    parser.add_argument("--remediate", help="Path to a JSON file listing missing parts to resend.", default=None)
    args = parser.parse_args()

    # 1. Get file info first
    file_data, total_parts, filename = get_file_info(args.file)
    
    if not file_data:
        print("Could not read file. Exiting.")
        return

    # 2. Check for remediation mode
    remediation_list = None
    if args.remediate:
        try:
            with open(args.remediate, 'r') as f:
                remediation_data = json.load(f)
                remediation_list = remediation_data.get("missing")
                
                # Check that the filename matches
                if remediation_data.get("filename") != filename:
                    print(f"Error: The missing parts file is for '{remediation_data.get('filename')}',")
                    print(f"but you are trying to send '{filename}'.")
                    print("Exiting.")
                    return
                    
            if not remediation_list:
                print(f"Error: '{args.remediate}' is not a valid remediation file or has no missing parts.")
                return
        except FileNotFoundError:
            print(f"Error: Remediation file '{args.remediate}' not found.")
            return
        except json.JSONDecodeError:
            print(f"Error: Could not parse remediation file '{args.remediate}'.")
            return

    # 3. Create the main Tkinter window
    root = tk.Tk()
    # Set the window size and position (top-left corner)
    root.geometry("1200x1200+0+0")
    
    # 4. Create a thread-safe queue with a max size of 1.
    # This acts as a buffer, ensuring the generator doesn't
    # get more than one image ahead of the display.
    image_queue = queue.Queue(maxsize=1)
    
    # 5. Create the app instance
    app = QRPresenter(root, total_parts, filename, image_queue, remediation_list)
    
    # 6. Create and start the generation thread
    generation_thread = threading.Thread(
        target=generate_qr_images_to_queue,
        args=(file_data, total_parts, filename, image_queue, remediation_list),
        daemon=True # A daemon thread exits when the main program exits
    )
    
    try:
        generation_thread.start()
        # 7. Start the GUI event loop
        #    This runs *immediately*.
        root.mainloop()
        
    finally:
        # 8. Clean up
        print("\nWindow closed. Exiting.")


if __name__ == "__main__":
    main()

