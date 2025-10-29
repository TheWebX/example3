import base64
import json
import time
import os
from PIL import ImageGrab
from pyzbar.pyzbar import decode

# --- Configuration ---
# This must match the sender script's chunk size
CHUNK_SIZE_BYTES = 2048
# Set how long to wait (in seconds) after the last *new* part is
# found before automatically timing out.
SCAN_TIMEOUT_SECONDS = 5
# ---------------------

def save_draft_and_exit(chunks, total_parts, output_filename):
    """
    Saves a draft file and a missing_parts.json.
    This is called on Ctrl+C or on timeout.
    """
    print("\n--- Saving Draft and Exiting ---")
    
    if total_parts is None or output_filename is None:
        print("No parts were received. Exiting.")
        return

    # 1. Find missing parts
    all_parts = set(range(1, total_parts + 1))
    found_parts = set(chunks.keys())
    missing_parts = sorted(list(all_parts - found_parts))

    if not missing_parts:
        if len(found_parts) == total_parts:
             print("All parts were found, but process was interrupted before final save.")
             print("The final file was not assembled. Please re-run the scanner.")
        else:
            print("Error: No missing parts, but total parts do not match. Exiting.")
        return

    print(f"Found {len(found_parts)} of {total_parts} parts.")
    print(f"Missing {len(missing_parts)} parts: {missing_parts}")

    # 2. Save the missing parts list
    remediation_data = {
        "filename": output_filename,
        "total_parts": total_parts,
        "missing": missing_parts
    }
    json_filename = "missing_parts.json"
    try:
        with open(json_filename, 'w') as f:
            json.dump(remediation_data, f, indent=2)
        print(f"Successfully saved '{json_filename}'.")
    except Exception as e:
        print(f"Error saving missing parts JSON: {e}")

    # 3. Save the DRAFT file
    draft_filename = f"DRAFT_{output_filename}"
    print(f"Saving received parts to '{draft_filename}'...")
    try:
        with open(draft_filename, 'wb') as f_out:
            # Write all chunks *in order*, filling in gaps with null bytes
            for i in range(1, total_parts + 1):
                if i in chunks:
                    # This part exists, decode and write it
                    base64_data = chunks[i]
                    binary_chunk = base64.b64decode(base64_data)
                    f_out.write(binary_chunk)
                else:
                    # This part is missing.
                    # We must write placeholder null bytes to keep the file
                    # offsets correct.
                    
                    # Check if this is the last chunk
                    if i == total_parts:
                        # If it's the last chunk, we don't know the exact
                        # size, so we can't add padding. Just stop.
                        pass
                    else:
                        # If it's not the last chunk, write null bytes
                        # for the full chunk size.
                        f_out.write(b'\0' * CHUNK_SIZE_BYTES)
                        
        print(f"Successfully saved draft file.")
        print("\nTo resume, run the SENDER with the --remediate flag:")
        print(f"python show_qr_series.py {output_filename} --remediate {json_filename}")
        print("Then, re-run this scanner script to capture the missing parts.")

    except Exception as e:
        print(f"Error saving draft file: {e}")

def main_scanner():
    """
    Scans the screen for a series of QR codes, one by one,
    and reassembles the file when all parts are found.
    
    If cancelled with Ctrl+C, it saves the received parts to a
    DRAFT file and creates a 'missing_parts.json' file.
    """
    
    print("--- Live QR Code Scanner Started ---")
    print("Please show the QR codes to your screen, one by one.")
    print("Press Ctrl+C to stop scanning and save a draft.")
    print("Waiting for the first part...")

    # Dictionary to store the data chunks, e.g., {1: "base64data", 2: "..."}
    chunks = {}
    
    total_parts = None
    output_filename = None
    
    # Keep track of the last message to avoid spamming the console
    last_message = ""
    # Initialize the timeout timer
    last_part_found_time = time.time()

    try:
        while True:
            # --- NEW TIMEOUT LOGIC ---
            # Only start checking for a timeout *after* the first part is found
            if total_parts is not None:
                time_since_last_part = time.time() - last_part_found_time
                
                # Check if we are still missing parts AND the timeout has been exceeded
                if len(chunks) < total_parts and time_since_last_part > SCAN_TIMEOUT_SECONDS:
                    print(f"\nScan timed out (no new parts found in {SCAN_TIMEOUT_SECONDS} seconds).")
                    print("Assuming broadcast is complete.")
                    save_draft_and_exit(chunks, total_parts, output_filename)
                    break # Exit the main while loop
            # --- END TIMEOUT LOGIC ---

            # 1. Capture the entire screen
            # This is more robust.
            screen_image = ImageGrab.grab() 


            # 2. Try to find and decode QR codes in the screenshot
            try:
                decoded_objects = decode(screen_image)
            except Exception as e:
                # This can happen on some frames, not a fatal error
                # print(f"Error decoding image: {e}") 
                time.sleep(0.5) # Wait a bit if decoding fails
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
                        
                        # Check if a DRAFT file already exists
                        draft_file = f"DRAFT_{output_filename}"
                        if os.path.exists(draft_file):
                            print(f"Resuming from existing '{draft_file}'.")
                            print("Loading existing parts from draft...")
                            # This logic re-reads the draft file to populate chunks.
                            try:
                                with open(draft_file, 'rb') as f_in:
                                    for i in range(1, total_parts + 1):
                                        chunk = f_in.read(CHUNK_SIZE_BYTES)
                                        if not chunk:
                                            break # End of file
                                        
                                        # Check if chunk is all null bytes
                                        # (b'\0' * len(chunk)) handles the final, shorter chunk
                                        if chunk != (b'\0' * CHUNK_SIZE_BYTES) and chunk != (b'\0' * len(chunk)):
                                            # This is real data
                                            if i not in chunks:
                                                chunks[i] = base64.b64encode(chunk).decode('utf-8')
                                
                                print(f"Loaded {len(chunks)} existing parts.")
                            
                            except Exception as e:
                                print(f"Error reading draft file: {e}")

                    # --- RESET THE TIMEOUT ---
                    # A new part was found, so reset the timer
                    last_part_found_time = time.time()

                    # Store the new chunk
                    chunks[part_num] = base64_data
                    
                    progress_message = f"Captured part {part_num}/{total_parts}. Progress: [{len(chunks)} of {total_parts}]"
                    print(progress_message)
                    last_message = progress_message

            except (json.JSONDecodeError, KeyError, TypeError):
                # The QR code found was not in our expected JSON format.
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
                    
                    # Clean up draft files if they exist
                    draft_file = f"DRAFT_{output_filename}"
                    json_file = "missing_parts.json"
                    
                    if os.path.exists(draft_file):
                        os.remove(draft_file)
                        print(f"Removed draft file: {draft_file}")
                    if os.path.exists(json_file):
                        os.remove(json_file)
                        print(f"Removed remediation file: {json_file}")
                        
                    break # Exit the while loop and end the program

                except Exception as e:
                    print(f"FATAL ERROR: Could not write file. {e}")
                    break
            
            # Wait before the next screen capture
            time.sleep(0.5) # 500ms delay

    except KeyboardInterrupt:
        print("\n--- Scan Cancelled By User ---")
        save_draft_and_exit(chunks, total_parts, output_filename)

if __name__ == "__main__":
    main_scanner()

