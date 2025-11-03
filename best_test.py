import pyvisa
import time

# --- Configuration ---
RESOURCE_NAME = 'ASRL5::INSTR'  # Your COM5 port
BAUD_RATE = 19200               # CRITICAL: Confirmed 19200 baud
DATA_BITS = 8
PARITY = pyvisa.constants.Parity.none
STOP_BITS = pyvisa.constants.StopBits.one
# --- End Configuration ---

# --- Discovered 4-Byte "Value" Arrays ---
# [Byte1, Byte2] = Magnitude, Byte4 = Sign (00=Neg, 01=Pos)
VALUE_NEG_2_0_A = [0x02, 0x29, 0x00, 0x00] # From packets_22.txt # 553
VALUE_NEG_0_1_A = [0x00, 0x23, 0x00, 0x00] # From packets.txt # 35
VALUE_POS_1_0_A = [0x00, 0xDE, 0x00, 0x01] # From packets_1.txt # 222
VALUE_POS_4_0_A = [0x05, 0x13, 0x00, 0x01] # From packets_4.txt # 1299
# --- End Value Definitions ---

def read_one_byte(instrument):
    """Reads a single byte, returns the integer value or None on timeout."""
    try:
        response = instrument.read_bytes(1)
        # print(f"  READ: 0x{response[0]:02X}")
        return response[0]
    except pyvisa.errors.VisaIOError:
        # print("  READ: Timeout")
        return None

def poll_for_byte(instrument, expected_byte):
    """Keeps reading until a specific byte is found or timeout."""
    # print(f"  Polling for 0x{expected_byte:02X}...")
    try:
        while True: # Loop will be broken by timeout
            response = instrument.read_bytes(1)
            # print(f"    ... got 0x{response[0]:02X}")
            if response[0] == expected_byte:
                return response[0]
    except pyvisa.errors.VisaIOError:
        # print("  Polling Timeout")
        return None

def run_start_sequence(inst, value_bytes):
    """
    Sends the full 10-step START sequence with the provided 4-byte value.
    """
    print(f"\n--- Sending START sequence for value: {[f'0x{b:02X}' for b in value_bytes]} ---")
    
    inst.write_raw(bytes([0x64])); read_one_byte(inst) # Step 1: Ready Check
    inst.write_raw(bytes([0x64])); read_one_byte(inst) # Step 2: Ready Check
    inst.write_raw(bytes([0x1E])); poll_for_byte(inst, 0x12) # Step 3: Start Cmd
    inst.write_raw(bytes([0x64])); read_one_byte(inst) # Step 4: Ready Check
    inst.write_raw(bytes([0x2C])); read_one_byte(inst) # Step 5: "Set Value" cmd
    
    # Steps 6-9: Send the 4-byte value
    inst.write_raw(bytes([value_bytes[0]])); read_one_byte(inst) # Step 6
    inst.write_raw(bytes([value_bytes[1]])); read_one_byte(inst) # Step 7
    inst.write_raw(bytes([value_bytes[2]])); read_one_byte(inst) # Step 8
    inst.write_raw(bytes([value_bytes[3]])); read_one_byte(inst) # Step 9
    
    # Step 10: End Command
    inst.write_raw(bytes([0x00])); poll_for_byte(inst, 0x12)
    
    print("--- START sequence complete ---")

def stop_and_query_field(inst):
    """
    Sends the STOP command (0x2B), then queries the field (0x0A),
    and finishes the stop sequence.
    Returns the decoded field reading.
    """
    print("\n--- Sending STOP and QUERY sequence ---")
    
    # --- Part 1: Send STOP command ---
    inst.write_raw(bytes([0x64])); read_one_byte(inst) # Ready Check
    inst.write_raw(bytes([0x2B])); poll_for_byte(inst, 0x12) # Stop Cmd
    
    # --- Part 2: Send QUERY command (this is the fix) ---
    print("  Querying field...")
    inst.write_raw(bytes([0x0A])) # The query command
    
    byte1 = read_one_byte(inst)
    if byte1 is None: return "Query Failed: No response"
    inst.write_raw(bytes([byte1])) # Echo byte 1
    
    byte2 = read_one_byte(inst)
    if byte2 is None: return "Query Failed: No response"
    inst.write_raw(bytes([byte2])) # Echo byte 2
    
    byte3 = read_one_byte(inst)
    if byte3 is None: return "Query Failed: No response"
    inst.write_raw(bytes([byte3])) # Echo byte 3 (sign?)

    # --- Part 3: Finish the STOP sequence ---
    # This part seems to vary based on the value, but the -0.1A
    # sequence is simple and seems to work as a generic "set zero".
    # We will use the sequence from packets_1.txt 
    # which is slightly different from the -2.0A log.
    
    # This is from packets_1.txt, after the query:
    # WRITE: 4E, READ: 00, WRITE: 00
    inst.write_raw(bytes([0x4E])); read_one_byte(inst) 
    inst.write_raw(bytes([0x00])); # No response in log
    
    inst.write_raw(bytes([0x64])); read_one_byte(inst) # Ready Check
    inst.write_raw(bytes([0x82])); poll_for_byte(inst, 0x12) # End Cmd
    
    print("--- STOP/QUERY sequence complete ---")

    # --- Decode and return the value ---
    try:
        raw_magnitude = (byte1 << 8) | byte2
        scaled_magnitude = raw_magnitude / 10.0 # Our hypothesis
        
        # Hypothesis for sign:
        sign = "Unknown"
        if byte3 == 0x00: sign = "Positive (+)"
        if byte3 == 0x01: sign = "Negative (-)"

        print(f"  Received raw bytes: [0x{byte1:02X}, 0x{byte2:02X}, 0x{byte3:02X}]")
        print(f"  Decoded Magnitude: {raw_magnitude} (~{scaled_magnitude} mT)")
        print(f"  Decoded Sign Flag: 0x{byte3:02X} ({sign})")
        
        final_value = scaled_magnitude if byte3 == 0x00 else -scaled_magnitude
        return final_value
    except Exception as e:
        return f"Query Failed: Error decoding bytes: {e}"

# --- Main Script ---
rm = pyvisa.ResourceManager()

try:
    print(f"Connecting to {RESOURCE_NAME} at {BAUD_RATE} baud...")
    with rm.open_resource(RESOURCE_NAME) as inst:
        
        inst.baud_rate = BAUD_RATE
        inst.data_bits = DATA_BITS
        inst.parity = PARITY
        inst.stop_bits = STOP_BITS
        inst.write_termination = None
        inst.read_termination = None
        inst.timeout = 2000  # 2-second timeout
        
        inst.clear()
        print("Connection successful.")

        # --- Run the -2.0A Test ---
        run_start_sequence(inst, VALUE_NEG_2_0_A)
        
        print("\n*** Current should be -2.0A. Waiting 1 second... ***")
        time.sleep(1.0)
        
        # Stop the current and query the field
        field_reading = stop_and_query_field(inst)
        
        print(f"\n--- Test Finished ---")
        print(f"Final Field Reading: {field_reading} mT")

except pyvisa.errors.VisaIOError as e:
    print(f"\n--- VISA Error ---")
    print(f"Details: {e}")
    print("Please check:")
    print("1. Is the device on COM5?")
    print("2. Is the Holmarc proprietary software CLOSED?")

finally:
    if 'rm' in locals():
        rm.close()
    print("Resource manager closed.")