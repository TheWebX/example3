import base64
import json
import time
from PIL import ImageGrab
from pyzbar.pyzbar import decode

def main_scanner():
    """
    Scans the screen for a series of QR codes, one by one,
    and reassembles the file when all parts are found.
    """
    
    print("--- Live QR Code Scanner Started ---")
    print("Please show the QR codes to your screen, one by one.")
    print("Waiting for the first part...")

    # Dictionary to store the data chunks, e.g., {1: "base64data", 2: "..."}
    chunks = {}
    
    total_parts = None
    output_filename = None
    
    # Keep track of the last message to avoid spamming the console
    last_message = ""

    try:
        while True:
            # 1. Capture the entire screen
            screen_image = ImageGrab.grab()

            # 2. Try to find and decode QR codes in the screenshot
            #    This is the most time-consuming part
            try:
                decoded_objects = decode(screen_image)
            except Exception as e:
                print(f"Error decoding image: {e}")
                time.sleep(1) # Wait a bit if decoding fails
                continue

            if not decoded_objects:
                # No QR codes found on screen, try again
                time.sleep(0.5) # 500ms delay
                continue

            # 3. Process the first QR code found
            qr_data_string = decoded_objects[0].data.decode('utf-8')

            try:
                # 4. Attempt to parse the QR data as our expected JSON
                payload = json.loads(qr_data_string)
                
                part_num = payload['p']
                base64_data = payload['d']
                
                # 5. Check if this is a new part
                if part_num not in chunks:
                    
                    # If this is the very first part, set up the job
                    if total_parts is None:
                        total_parts = payload['t']
                        output_filename = payload['f']
                        print("\n--- Found First Part! ---")
                        print(f"Target file: {output_filename}")
                        print(f"Total parts to find: {total_parts}")

                    # Store the new chunk
                    chunks[part_num] = base64_data
                    
                    progress_message = f"Captured part {part_num}/{total_parts}. Progress: [{len(chunks)} of {total_parts}]"
                    print(progress_message)
                    last_message = progress_message

            except (json.JSONDecodeError, KeyError, TypeError):
                # The QR code found was not in our expected JSON format.
                # It's probably a different QR code (e.g., Wi-Fi, URL).
                if last_message != "Found an unrelated QR code. Ignoring...":
                    last_message = "Found an unrelated QR code. Ignoring..."
                    print(last_message)
                pass # Ignore it and continue scanning

            # 6. Check for completion
            if total_parts is not None and len(chunks) == total_parts:
                print("\n--- All Parts Found! ---")
                print("Reassembling file...")
                
                restored_filename = f"RESTORED_{output_filename}"
                
                try:
                    with open(restored_filename, 'wb') as f_out:
                        # Reassemble in the correct order
                        for i in range(1, total_parts + 1):
                            base64_data = chunks[i]
                            binary_chunk = base64.b64decode(base64_data)
                            f_out.write(binary_chunk)
                            
                    print(f"\nSUCCESS! File reassembled as '{restored_filename}'.")
                    print("Terminating script.")
                    break # Exit the while loop and end the program

                except Exception as e:
                    print(f"FATAL ERROR: Could not write file. {e}")
                    break
            
            # Wait before the next screen capture
            time.sleep(0.5) # 500ms delay

    except KeyboardInterrupt:
        print("\nScan cancelled by user.")

if __name__ == "__main__":
    main_scanner()
