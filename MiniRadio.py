#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
# import os # For path manipulation (No longer needed if script_dir is removed)
import serial  # For serial communication
import serial.tools.list_ports # To list serial ports
from guizero import App, PushButton, Text, Combo, Window, Box, ListBox, TextBox # Picture and Box import removed, Window and Box added
# from PIL import Image # For image manipulation (No longer needed)
from guizero import CheckBox # Checkbox added (capitalization corrected)

# --- Matplotlib for Spectrum Analyzer ---
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- Configuration ---
# BAUD_RATE is replaced by dynamic selection
DEFAULT_BAUD_RATE = 115200

# --- Global variable for the serial connection ---
ser = None
connected_port = None # Stores the name of the currently connected port
log_mode_active = False # Now controlled by the checkbox
spectrum_window_instance = None
memory_viewer_window_instance = None # Renamed
current_radio_frequency_khz = None
current_radio_band_name = None
current_radio_step_size_str = None
current_radio_mode_str = None

# --- Constants for battery calculation ---
MIN_BATTERY_VOLTAGE = 3.2
MAX_BATTERY_VOLTAGE = 4.2
MAX_VOLUME = 63
# PERCENTAGE_MULTIPLIER = 100 # Used directly in the code

# --- Band Data for Spectrum Analyzer ---
# Keys should match the band_name string reported by the radio (parts[4])
BANDS_DATA = {
    "VHF": {"min_khz": 64000, "max_khz": 108000, "default_mode": "FM"},
    "ALL": {"min_khz": 150, "max_khz": 30000, "default_mode": "AM"},
    "11M": {"min_khz": 25600, "max_khz": 26100, "default_mode": "AM"},
    "13M": {"min_khz": 21500, "max_khz": 21900, "default_mode": "AM"},
    "15M": {"min_khz": 18900, "max_khz": 19100, "default_mode": "AM"}, # Shortwave Broadcast 15M
    "16M": {"min_khz": 17500, "max_khz": 18100, "default_mode": "AM"},
    "19M": {"min_khz": 15100, "max_khz": 15900, "default_mode": "AM"},
    "22M": {"min_khz": 13500, "max_khz": 13900, "default_mode": "AM"},
    "25M": {"min_khz": 11000, "max_khz": 13000, "default_mode": "AM"},
    "31M": {"min_khz": 9000, "max_khz": 11000, "default_mode": "AM"},
    "41M": {"min_khz": 7000, "max_khz": 9000, "default_mode": "AM"}, # Note: Overlaps with 40M Ham band
    "49M": {"min_khz": 5000, "max_khz": 7000, "default_mode": "AM"},
    "60M": {"min_khz": 4000, "max_khz": 5100, "default_mode": "AM"},
    "75M": {"min_khz": 3500, "max_khz": 4000, "default_mode": "AM"}, # Note: Overlaps with 80M Ham band
    "90M": {"min_khz": 3000, "max_khz": 3500, "default_mode": "AM"},
    "MW3": {"min_khz": 1700, "max_khz": 3500, "default_mode": "AM"}, # Assuming radio might report these
    "MW2": {"min_khz": 495, "max_khz": 1701, "default_mode": "AM"},
    "MW1": {"min_khz": 150, "max_khz": 1800, "default_mode": "AM"},
    "160M": {"min_khz": 1800, "max_khz": 2000, "default_mode": "LSB"},
    "80M": {"min_khz": 3500, "max_khz": 4000, "default_mode": "LSB"},
    "40M": {"min_khz": 7000, "max_khz": 7300, "default_mode": "LSB"},
    "30M": {"min_khz": 10000, "max_khz": 10200, "default_mode": "LSB"},
    "20M": {"min_khz": 14000, "max_khz": 14400, "default_mode": "USB"},
    "17M": {"min_khz": 18000, "max_khz": 18200, "default_mode": "USB"}, # Ham Radio 17M
    "15M HAM": {"min_khz": 21000, "max_khz": 21500, "default_mode": "USB"}, # Distinguish from SW Broadcast 15M
    "12M": {"min_khz": 24800, "max_khz": 25000, "default_mode": "USB"},
    "10M": {"min_khz": 28000, "max_khz": 29700, "default_mode": "USB"},
    "CB": {"min_khz": 25000, "max_khz": 30000, "default_mode": "AM"},
}


def toggle_connection():
    """Toggles the serial connection (connects if disconnected, disconnects if connected)."""
    global ser, connected_port, log_mode_active # log_mode_active added

    # If already connected, disconnect
    if ser and ser.is_open:
        print("INFO: Disconnecting from serial port...")
        if log_mode_active:
            print("INFO: Attempting to disable radio logging before disconnecting.")
            # We don't strictly need to check the return of send_serial_command_internal here,
            # as we are disconnecting anyway.
            send_serial_command_internal('t')
        
        ser.close()
        ser = None
        connected_port = None
        log_mode_active = False
        if hasattr(app, 'connect_button'):
            app.connect_button.text = "Connect"
            app.connect_button.text_color = dark_theme_text_color # Reset to default
        if hasattr(app, 'enable_cyclic_reading'):
            app.enable_cyclic_reading.value = 0
        reset_status_display() # Reset status fields
        print("INFO: Disconnected.")
        return

    # If not connected, try to connect
    try:
        selected_port = app.port_selector.value # Read port from dropdown
        if not selected_port or selected_port == "No ports found": # Changed German string
            print("No valid port selected.") # Changed German string
            if hasattr(app, 'connect_button'): # Nur aktualisieren, wenn Button existiert
                app.connect_button.text = "No port\nselected!" # Zeilenumbruch hinzugefügt
                app.connect_button.text_color = "#FFA726" # Orange
            return

        selected_baud_rate_str = app.baud_rate_selector.value
        try:
            selected_baud_rate = int(selected_baud_rate_str)
        except ValueError:
            print(f"Invalid baud rate selected: {selected_baud_rate_str}. Using default.")
            selected_baud_rate = DEFAULT_BAUD_RATE # Fallback to default

        print(f"Attempting connection to {selected_port} at {selected_baud_rate} baud...")
        ser = serial.Serial(selected_port, selected_baud_rate, timeout=1)
        connected_port = selected_port # Store connected port
        print(f"Successfully connected to {connected_port}.")
        if hasattr(app, 'connect_button'): # Check if button exists before updating
            app.connect_button.text = "Disconnect" # Button now shows "Disconnect"
            app.connect_button.text_color = "#66BB6A" # Grün

        # --- Enhanced logic to handle cyclic reading on connect ---
        ser.reset_input_buffer() # Clear any stale data, as suggested by community
        print("INFO: Serial input buffer cleared.")

        initial_radio_state_is_on = False
        original_timeout = ser.timeout
        ser.timeout = 0.3  # Short timeout (300ms) to check for existing data stream
        print(f"INFO: Temporarily set serial timeout to {ser.timeout}s to check for radio data.")

        try:
            line_bytes = ser.readline()
            if line_bytes:
                initial_radio_state_is_on = True
                print("INFO: Radio logging appears to be initially ON (data received).")
                # Optionally, try to parse this first line for immediate status update
                try:
                    log_line = line_bytes.decode('ascii', errors='ignore').strip()
                    if log_line:
                        print(f"INFO: Initial data line: {log_line}")
                        parse_and_update_radio_status(log_line)
                except Exception as e_parse:
                    print(f"WARN: Could not parse initial data line: {e_parse}")
            else:
                print("INFO: Radio logging appears to be initially OFF (no data received quickly).")
        except Exception as e_check:
            print(f"WARN: Error checking initial radio log state: {e_check}")
        finally:
            ser.timeout = original_timeout # Restore original timeout
            print(f"INFO: Serial timeout restored to {ser.timeout}s.")

        if initial_radio_state_is_on:
            # Radio is already sending data. App should reflect this.
            log_mode_active = True
            if hasattr(app, 'enable_cyclic_reading'):
                app.enable_cyclic_reading.value = 1
            print("INFO: Cyclic reading confirmed ON (was already active on radio).")
        else:
            # Radio logging was OFF, or we couldn't confirm. Try to turn it ON.
            print("INFO: Attempting to enable cyclic reading on radio via 't' command.")
            if send_serial_command_internal('t'):
                log_mode_active = True
                if hasattr(app, 'enable_cyclic_reading'):
                    app.enable_cyclic_reading.value = 1
                print("INFO: Cyclic reading enabled via 't' command.")
            else:
                log_mode_active = False # Ensure it's false if command failed
                if hasattr(app, 'enable_cyclic_reading'):
                    app.enable_cyclic_reading.value = 0 # Ensure box is unchecked
                print("WARN: Failed to enable cyclic reading via 't' command. Please use the checkbox.")

    except serial.SerialException as e:
        print(f"ERROR: Error opening serial port {selected_port}: {e}")
        if hasattr(app, 'connect_button'):
            app.connect_button.text = "Connection\nfailed!" # Zeilenumbruch hinzugefügt
            app.connect_button.text_color = "#EF5350" # Red
        ser = None # Ensure ser is None if connection fails
        if hasattr(app, 'enable_cyclic_reading'): app.enable_cyclic_reading.value = 0 # Uncheck if connection fails
        log_mode_active = False # Ensure log mode is off
        reset_status_display() # Reset status fields on connection error
    except Exception as e: # Other unexpected errors
        print(f"ERROR: Unexpected error during serial initialization ({selected_port}): {e}")
        if hasattr(app, 'connect_button'):
            app.connect_button.text = "Unexpected\nerror!" # Zeilenumbruch hinzugefügt
            app.connect_button.text_color = "#EF5350" # Red
        ser = None
        if hasattr(app, 'enable_cyclic_reading'): app.enable_cyclic_reading.value = 0
        log_mode_active = False
        reset_status_display() # Reset status fields on unexpected error
        print("INFO: Log mode deactivated due to unexpected initialization error.")

def send_serial_command_internal(command_char):
    """Sends a single character as a command to the serial interface."""
    global ser, log_mode_active # Declare log_mode_active here to set it on errors
    if not ser or not ser.is_open:
        print("WARN: Serial port not open. Please use 'Connect' button.")
        if hasattr(app, 'connect_button'):
            app.connect_button.text = "Not\nconnected!" # Zeilenumbruch hinzugefügt
            app.connect_button.text_color = "#FFA726"
        return False # Indicate failure, do not attempt to connect here

    if ser and ser.is_open:
        try:
            ser.write(command_char.encode('ascii')) # Commands are single ASCII characters
            print(f"Command sent: {command_char}")
        except serial.SerialException as e_write:
            print(f"ERROR: Error writing to serial port: {e_write}")
            if hasattr(app, 'connect_button'):
                app.connect_button.text = "Write\nerror!" # Zeilenumbruch hinzugefügt
                app.connect_button.text_color = "#EF5350" # Red
            # Do NOT close the port or change log_mode_active on a simple write error.
            return False
        except Exception as e_generic_send: # Other unexpected errors
            print(f"ERROR: Unexpected error sending command '{command_char}': {e_generic_send}")
            if hasattr(app, 'connect_button'):
                app.connect_button.text = "Send\nerror!" # Zeilenumbruch hinzugefügt
                app.connect_button.text_color = "#EF5350" # Red
            # Do NOT close the port or change log_mode_active on a generic send error.
            return False
        return True # Indicate success
    # This print should ideally not be reached if the initial check for ser and ser.is_open is done.
    print(f"WARN: Command '{command_char}' not sent, serial port state unexpected.")
    return False # Indicate failure

def send_serial_command(command_char): # Wrapper for external calls
    send_serial_command_internal(command_char)

def cleanup():
    """Cleanup tasks when closing the application."""
    global ser, connected_port, log_mode_active, spectrum_window_instance, memory_viewer_window_instance
    print("INFO: Application is closing.")
    # Ensure app.tk exists before trying to access winfo_exists
    # and also ensure app itself is not None
    app_exists = app and hasattr(app, 'tk') and app.tk

    if ser and ser.is_open:
        # If logging was active, try to turn it off on the radio before closing port
        if log_mode_active:
            print("INFO: Attempting to disable radio logging before closing port...")
            try:
                ser.write('t'.encode('ascii')) # Send 't' to toggle logging off
                # A short delay might be beneficial for the command to be processed by the radio
                # However, time.sleep() in a GUI app's main thread during cleanup can be tricky.
                # For now, just send and hope for the best, or make it non-blocking if issues arise.
                print("INFO: 't' command sent to attempt disabling radio logging.")
            except Exception as e_cleanup_write:
                print(f"WARN: Could not send 't' command during cleanup: {e_cleanup_write}")
        ser.close()
        print(f"Serial port {connected_port} closed.")
        connected_port = None
    if spectrum_window_instance and spectrum_window_instance.window.tk.winfo_exists():
        spectrum_window_instance.window.destroy()
    if memory_viewer_window_instance and memory_viewer_window_instance.window.tk.winfo_exists(): # Renamed
        memory_viewer_window_instance.window.destroy()

    if app_exists and app.tk.winfo_exists(): # Check if the window still exists
        app.destroy()
    sys.exit(0) # Clean exit

# --- Helper functions for display formatting ---
def format_agc_display(agc_value_str):
    try:
        agc_idx = int(agc_value_str)
        if agc_idx == 0: return "Auto"
        # Assumption: agc_idx=1 means Att 0dB, agc_idx=2 means Att 1dB etc.
        return f"Manual (Att {agc_idx -1}dB)"
    except ValueError:
        return "---" # Fallback if conversion fails

def format_battery_display(voltage_str):
    try:
        voltage = float(voltage_str)
        clamped_v = max(MIN_BATTERY_VOLTAGE, min(voltage, MAX_BATTERY_VOLTAGE))
        percentage = 0
        denominator = MAX_BATTERY_VOLTAGE - MIN_BATTERY_VOLTAGE
        if denominator > 0: # Avoid division by zero
            percentage = ((clamped_v - MIN_BATTERY_VOLTAGE) / denominator) * 100
        else: # If MIN_BATTERY_VOLTAGE == MAX_BATTERY_VOLTAGE
            percentage = 100 if voltage >= MAX_BATTERY_VOLTAGE else 0
        percentage = max(0, min(100, round(percentage))) # Ensure it's between 0 and 100
        return f"{voltage:.2f}V ({percentage}%)"
    except ValueError: # If voltage_str cannot be converted to float
        return f"{voltage_str}V (?%)" # Show raw value with question mark

def format_volume_display(volume_value):
    try:
        vol = int(volume_value)
        # Basic validation for volume range
        if not (0 <= vol <= MAX_VOLUME):
            print(f"WARN: Volume value {vol} out of expected range (0-{MAX_VOLUME}).")
            # Decide how to handle out-of-range: show error, clamp, or show raw
            return f"{volume_value} (ERR)" # Example: show error
        percentage = round((vol / MAX_VOLUME) * 100) if MAX_VOLUME > 0 else 0
        return f"{vol} ({percentage}%)"
    except ValueError:
        return f"{volume_value} (--%)"

def parse_and_update_radio_status(log_string):
    """Parses the log string from the radio and updates GUI elements."""
    global current_radio_frequency_khz, current_radio_band_name, current_radio_step_size_str, current_radio_mode_str
    # If not connected, don't try to update the GUI with potentially stale data
    if not (ser and ser.is_open):
        # This check helps prevent updates if data arrives after a disconnect
        # or if this function is somehow called when not connected.
        # The main reset of the display happens in toggle_connection.
        print("WARN: parse_and_update_radio_status called but not connected. Skipping update.")
        return

    try:
        parts = log_string.split(',')
        if len(parts) < 15:
            print(f"WARN: Incomplete log string: {log_string} (expected 15 parts, got {len(parts)})")
            return

        # Extracting some key values (indices are 0-based) - comments for clarity
        fw_version = parts[0]
        
        # Store raw values for potential use by other modules like spectrum analyzer
        current_radio_frequency_khz = int(parts[1])
        current_radio_band_name = parts[4].strip()
        current_radio_step_size_str = parts[6]
        current_radio_mode_str = parts[5].strip() # Store current mode
        current_frequency_khz = int(parts[1])
        try:
            current_bfo_hz = int(parts[2])
            current_cal_hz = int(parts[3])
        except ValueError: # Handles empty string or non-integer
            current_bfo_hz = 0
            current_cal_hz = 0
        band_name = parts[4] # Band name
        current_mode = parts[5] # Current mode
        volume_str = parts[9] # Volume (as string for format_volume_display)
        step_size = parts[6] # New for Step Size
        bandwidth = parts[7] # New for Bandwidth
        agc_value_str = parts[8] # New for AGC Status (as string for format_agc_display)
        rssi = int(parts[10]) # RSSI value
        # Ensure band_name is not empty before using
        if not band_name:
            band_name = "Unknown" # Fallback for empty band name
        snr = int(parts[11])
        battery_voltage_str = parts[13] # Neu für Batteriespannung (als String)
        
        # Update GUI elements (assuming they exist and are named app.status_frequency etc.)
        # Frequency display logic: FM in MHz, AM/SSB and others in kHz
        if current_mode == "FM":
            # FM: currentFrequency is in 10 kHz units, display in MHz
            display_frequency_mhz = (current_frequency_khz * 10) / 1000.0
            app.status_frequency.value = f"{display_frequency_mhz:.2f}MHz"
        elif current_mode in ["LSB", "USB"]:
            # SSB: Display Frequency (Hz) = (currentFrequency kHz * 1000) + currentBFO Hz
            # current_frequency_khz is already in kHz for SSB
            actual_freq_khz = current_frequency_khz + (current_bfo_hz / 1000.0)
            app.status_frequency.value = f"{actual_freq_khz:.1f}kHz (Calibration: {current_cal_hz}Hz)"
        else:
            # AM and other modes: currentFrequency is in 1 kHz units, display in kHz
            display_frequency_khz = current_frequency_khz
            app.status_frequency.value = f"{display_frequency_khz}kHz"

        if hasattr(app, 'status_fw_version'):
            fw_display_text = "---"  # Default value if fw_version is empty or invalid
            
            # fw_version is the value from parts[0]
            if isinstance(fw_version, str) and fw_version.strip():
                raw_fw = fw_version.strip()
                # Specific case for format "201" -> "2.01"
                if len(raw_fw) == 3 and raw_fw.isdigit():
                    major = raw_fw[0]
                    minor = raw_fw[1:]
                    fw_display_text = f"{major}.{minor}" # "v" removed
                else:
                    # Remove "v" or "V" from the beginning, if present
                    if raw_fw.lower().startswith('v'):
                        fw_display_text = raw_fw[1:]
                    else:
                        fw_display_text = raw_fw
            app.status_fw_version.value = fw_display_text # "v" removed
        if hasattr(app, 'status_mode_band'): # Order changed to Band/Mode
            app.status_mode_band.value = f"{band_name}/{current_mode}"
        if hasattr(app, 'status_volume'): # Now uses format_volume_display
            app.status_volume.value = format_volume_display(volume_str)
        if hasattr(app, 'status_step'):
            app.status_step.value = f"{step_size}"
        if hasattr(app, 'status_bw'):
            app.status_bw.value = f"{bandwidth}"
        if hasattr(app, 'status_agc'):
            app.status_agc.value = format_agc_display(agc_value_str)
        if hasattr(app, 'status_battery'):
            app.status_battery.value = format_battery_display(battery_voltage_str)
        if hasattr(app, 'status_signal'):
            app.status_signal.value = f"RSSI: {rssi}dBuV, SNR: {snr}dB"

        # If spectrum window is open and sweeping, pass data to it
        # global spectrum_window_instance # Already declared global at module level
        if spectrum_window_instance is not None and spectrum_window_instance.sweeping_active:
            # current_frequency_khz is int(parts[1]) - base VFO frequency
            # current_mode is parts[5]
            # current_bfo_hz is int(parts[2]) - BFO in Hz
            # rssi is also numeric
            spectrum_window_instance.add_data_point(
                current_frequency_khz, current_mode, current_bfo_hz, rssi
            )

    except ValueError as e:
        print(f"ERROR: Error parsing numeric value in log string: {log_string} - {e}")
    except IndexError as e:
        print(f"ERROR: Index error parsing log string (not enough parts?): {log_string} - {e}")
    except Exception as e:
        print(f"ERROR: Unexpected error parsing radio status '{log_string}': {e}")

def check_serial_data():
    """Periodically checks for serial data if log mode is active."""
    global ser, log_mode_active
    # Diagnostic print can be re-enabled if needed:
    # if ser: print(f"CSR: log={log_mode_active}, open={ser.is_open}, wait={ser.in_waiting if ser.is_open else 'N/A'}")

    if log_mode_active and ser and ser.is_open and ser.in_waiting > 0: # Check log_mode_active and connection first
        try:
            log_line = ser.readline().decode('ascii', errors='ignore').strip()
            if log_line:
                # print(f"Radio Log: {log_line}") # For debugging
                parse_and_update_radio_status(log_line) # Ensure this is called
        except Exception as e:
            print(f"Error reading from serial port: {e}")
            # Consider if log_mode_active should be set to False here if reading fails consistently

def toggle_cyclic_reading():
    global log_mode_active, ser
    new_log_state = app.enable_cyclic_reading.value == 1
    print(f"INFO: Checkbox toggled. Requested log state: {new_log_state}")

    if not ser or not ser.is_open:
        print("WARN: Cannot change cyclic reading: Serial port not open.")
        app.enable_cyclic_reading.value = 0
        if hasattr(app, 'connect_button'): # Update connect button with warning
            app.connect_button.text = "Not\nconnected!"
            app.connect_button.text_color = "#FFA726" # Orange
        log_mode_active = False
        return

    # Nur senden, wenn der Status sich wirklich ändert
    if log_mode_active != new_log_state:
        if send_serial_command_internal('t'):
            log_mode_active = new_log_state
            print(f"INFO: Cyclic reading {'enabled' if log_mode_active else 'disabled'} by checkbox.")
        else:
            print("WARN: Failed to toggle log mode. Reverting checkbox.")
            app.enable_cyclic_reading.value = 1 if log_mode_active else 0
    else:
        print("INFO: Log mode already in requested state.")

def parse_step_size_to_khz(step_str):
    step_str = str(step_str).lower().strip()
    val_str = ""
    unit_chars = [] # Collect unit characters

    for char in step_str:
        if char.isdigit() or char == '.':
            val_str += char
        else:
            unit_chars.append(char)
    
    unit = "".join(unit_chars)

    if not val_str: return 1.0 # Default if no numeric part

    try:
        value = float(val_str)
        if "khz" in unit:
            return value
        elif "mhz" in unit or unit == "m": # Handle "MHz" or "M" for step size
            return value * 1000.0
        elif "hz" in unit:
            return value / 1000.0
        else: # Assume kHz if no unit or unknown unit and value seems reasonable for kHz
            if value < 1000: # Heuristic: if it's a small number, assume kHz
                 return value
            else: # If it's a large number without unit, assume Hz
                 return value / 1000.0
    except ValueError:
        print(f"WARN: Could not parse step size: {step_str}")
        return 1.0 # Default step

class SpectrumWindow:
    def __init__(self, master_app_ref, initial_band_name, initial_freq_khz, initial_step_size_str, band_min_khz, band_max_khz):
        self.master_app = master_app_ref
        self.band_name = initial_band_name # Actual band name like "VHF"

        self.is_vhf = (initial_band_name == "VHF") # True if VHF band
        self.display_unit = "MHz" if self.is_vhf else "kHz" # Unit for display
        self.freq_divisor = 1000.0 if self.is_vhf else 1.0 # Divisor for display unit conversion

        # Convert initial_freq_khz (from radio, parts[1]) to actual kHz for internal use
        # For VHF (FM), radio sends in 10kHz units, so multiply by 10. Others are already in kHz.
        self.current_sweep_freq_khz = float(initial_freq_khz) * 10.0 if self.is_vhf else float(initial_freq_khz)
        
        self.parsed_step_size_khz = float(parse_step_size_to_khz(initial_step_size_str))
        if self.parsed_step_size_khz <= 0:
            print("WARN: Invalid step size for spectrum (<=0), defaulting to 1kHz.")
            self.parsed_step_size_khz = 1.0
        
        self.target_min_freq_khz = float(band_min_khz) # Already in actual kHz
        self.target_max_freq_khz = float(band_max_khz) # Already in actual kHz

        self.spectrum_data = {} # Dictionary: {freq_khz: rssi}
        self.fill_collection = None # To store the fill_between artist
        self.sweeping_active = False

        self.window = Window(self.master_app, title=f"Spectrum Analyzer: {self.band_name}-Band", width=800, height=600)
        self.window.bg = self.master_app.bg # Match theme
        self.window.when_closed = self.on_close
        self.window.tk.resizable(False, False) # Make the spectrum window not resizable

        self.window.tk.config(padx=12, pady=12) # Add padding to the spectrum window
        # Matplotlib Figure and Canvas
        self.fig = Figure(figsize=(7.8, 5), dpi=100, facecolor=self.master_app.bg)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor('#3C3C3C')
        self.ax.tick_params(axis='x', colors=dark_theme_text_color)
        self.ax.tick_params(axis='y', colors=dark_theme_text_color)
        self.ax.xaxis.label.set_color(dark_theme_text_color)
        self.ax.yaxis.label.set_color(dark_theme_text_color)
        self.ax.title.set_color(dark_theme_text_color)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(dark_theme_text_color)
        
        # Display values are derived from actual kHz internal values
        # Step size is now always displayed in kHz
        display_min_freq_title = self.target_min_freq_khz / self.freq_divisor 
        display_max_freq_title = self.target_max_freq_khz / self.freq_divisor 
        
        self.ax.set_xlabel(f"Frequency ({self.display_unit}) - Step: {int(self.parsed_step_size_khz)}kHz")
        self.ax.set_ylabel("RSSI (dBuV)")
        self.ax.set_title(f"Band: {self.band_name} ({display_min_freq_title:.0f} - {display_max_freq_title:.0f}{self.display_unit})")
        self.ax.grid(True, linestyle='--', color='#555555')
        
        # Set initial Y-axis limits
        self.initial_y_min = 0
        self.initial_y_max = 100 # Default max RSSI for initial display or when no data
        self.min_dynamic_y_max = 30 # Minimum upper Y-axis limit when data is present
        self.y_axis_padding = 5     # Padding above max RSSI when data is present
        self.peak_markers = [] # To store matplotlib text objects for peak markers
        self.min_y_axis_range = 30  # Minimum span for the Y-axis (e.g., 30 dBuV)
        self.ABSOLUTE_MIN_PEAK_RSSI = 10  # dBuV, absolute minimum RSSI for a peak
        self.show_peaks_enabled = True # Controls whether peaks are shown
        self.USE_DYNAMIC_THRESHOLD = True # Flag to enable dynamic threshold calculation
        self.DYNAMIC_THRESHOLD_OFFSET_DB = 5 # dBuV, how much above average RSSI for dynamic threshold
        self.LOCAL_AVERAGE_WINDOW_HALF_SIZE = 15 # Number of steps +/- for local average RSSI calculation (Test: increased from 10)
        self.ax.set_ylim(self.initial_y_min, self.initial_y_max)

        # Set initial X-axis limits to exact band limits
        display_min_freq_init = self.target_min_freq_khz / self.freq_divisor
        display_max_freq_init = self.target_max_freq_khz / self.freq_divisor
        self.ax.set_xlim(display_min_freq_init, display_max_freq_init)
        self.line, = self.ax.plot([], [], color="#00FFFF", linestyle='-') # Cyan line, markers removed

        plot_box = Box(self.window, width="fill", height="fill", border=0)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_box.tk) # Use plot_box.tk
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(side="top", fill="both", expand=True)
        self.fig.tight_layout()

        controls_box = Box(self.window, layout="grid", width="fill", align="bottom")
        self.start_button = PushButton(controls_box, text="Start Sweep", command=self.start_sweep, grid=[0,0], align="left")
        self.start_button.bg = dark_theme_button_bg
        self.start_button.text_color = dark_theme_text_color
        self.stop_button = PushButton(controls_box, text="Stop Sweep", command=self.stop_sweep, grid=[1,0], enabled=False, align="left")
        self.stop_button.bg = dark_theme_button_bg
        self.stop_button.text_color = dark_theme_text_color

        # Spacer between buttons and checkbox
        Text(controls_box, text="  ", grid=[2,0]) 

        self.show_peaks_checkbox = CheckBox(controls_box, text="Show Peaks", command=self._toggle_peak_display_command, grid=[3,0], align="left")
        self.show_peaks_checkbox.value = 1 # Checked by default
        self.show_peaks_checkbox.text_color = dark_theme_text_color

        # Add a spacer Text widget before the status label for padding
        Text(controls_box, text="  ", grid=[4,0]) # Spacer, moved one column to the right
        self.status_label = Text(controls_box, text=f"Idle, ready to sweep {self.band_name}-Band!", grid=[5,0], align="left", width="fill") # Moved one column to the right
        self.status_label.text_color = dark_theme_text_color

    def _toggle_peak_display_command(self):
        self.show_peaks_enabled = (self.show_peaks_checkbox.value == 1)
        self.update_plot()

    def start_sweep(self):
        if not (ser and ser.is_open):
            self.status_label.value = "Error: Radio not connected!"
            # self.master_app.warn("Spectrum", "Radio not connected.") # User requested no app.warn
            print("WARN: Spectrum: Radio not connected.")
            return
        if self.sweeping_active:
            return

        self.sweeping_active = True
        # self.clear_peak_markers() # Clear markers when a new sweep starts - update_plot will handle this based on show_peaks_enabled
        self.spectrum_data = {} # Clear previous sweep data
        # Reset current_sweep_freq_khz from global radio status (which is parts[1])
        # Convert to actual kHz if VHF
        if self.is_vhf:
            self.current_sweep_freq_khz = float(current_radio_frequency_khz) * 10.0
        else:
            self.current_sweep_freq_khz = float(current_radio_frequency_khz)
        
        self.status_label.value = f"Sweeping {self.band_name}-Band!"
        self.start_button.enabled = False
        self.stop_button.enabled = True
        self.update_plot() # Clear plot
        self.perform_next_step()

    def stop_sweep(self):
        self.sweeping_active = False
        self.status_label.value = "Sweeping stopped!"
        self.start_button.enabled = True
        self.stop_button.enabled = False

    def perform_next_step(self):
        if not self.sweeping_active:
            return

        # The actual current_sweep_freq_khz will be updated by add_data_point from radio's report
        # This check is more of a pre-condition before sending command
        # We no longer stop at target_max_freq_khz. The sweep is continuous
        # until the user presses "Stop Sweep". The radio handles band wrapping.
        
        send_serial_command_internal('R') # Send "Encoder Rotate Right"

    def add_data_point(self, base_freq_khz_parts1, mode_str, bfo_hz_parts2, rssi):
        if not self.sweeping_active:
            return

        actual_tuned_khz = 0.0
        # base_freq_khz_parts1 is int(parts[1]) from the radio log (base VFO)
        # bfo_hz_parts2 is int(parts[2]) from the radio log (BFO in Hz)
        # mode_str is parts[5] (e.g., "FM", "AM", "LSB", "USB")

        if self.is_vhf: # This is based on initial_band_name. For VHF, mode_str is typically "FM".
                        # Radio sends base_freq_khz_parts1 in 10kHz units for FM.
            actual_tuned_khz = float(base_freq_khz_parts1) * 10.0
            # For FM, bfo_hz_parts2 is usually 0. If it could be non-zero and relevant for actual frequency,
            # it might need to be added, but current main GUI logic for FM doesn't use BFO.
        elif mode_str in ["LSB", "USB"]:
            # For LSB/USB, base_freq_khz_parts1 is base VFO in kHz.
            # bfo_hz_parts2 is BFO offset in Hz.
            actual_tuned_khz = float(base_freq_khz_parts1) + (float(bfo_hz_parts2) / 1000.0)
        else: # AM and other non-VHF modes (e.g., CW if radio reports similarly)
              # base_freq_khz_parts1 is the direct frequency in kHz.
              # bfo_hz_parts2 is often 0 for AM. If non-zero, the main GUI for AM ignores it.
              # To match main GUI AM display, spectrum should also use base VFO.
            actual_tuned_khz = float(base_freq_khz_parts1)
            
        self.current_sweep_freq_khz = actual_tuned_khz # This is now the actual tuned frequency in kHz
        self.spectrum_data[actual_tuned_khz] = rssi # Store/update RSSI for this actual tuned frequency
        
        self.update_plot()
        
        # Status label should reflect the frequency for which data was just plotted
        # self.freq_divisor is 1.0 for SW (kHz display), 1000.0 for VHF (MHz display)
        display_current_freq_status = self.current_sweep_freq_khz / self.freq_divisor # self.current_sweep_freq_khz is already adjusted
        if self.is_vhf:
            freq_format_str = ".2f" # For MHz display
        else: # Not VHF, display in kHz
            if mode_str == "AM": # mode_str is an argument to add_data_point
                freq_format_str = ".0f" # Integer display for AM in kHz
            else: # LSB, USB, etc. on SW
                freq_format_str = ".1f" # One decimal place for SSB etc. in kHz
        self.status_label.value = (
            f"Sweeping {self.band_name}-Band! Last values: {display_current_freq_status:{freq_format_str}}{self.display_unit}, RSSI: {rssi}dBuV." # Use determined freq_format_str
        )
        if self.sweeping_active:
            self.master_app.after(100, self.perform_next_step) # Delay before next step

    def clear_peak_markers(self):
        for marker in self.peak_markers:
            marker.remove()
        self.peak_markers.clear()

    def _add_peak_markers(self, freqs_for_plot, rssis_for_plot):
        self.clear_peak_markers() # Clear previous markers
        # print(f"Debug Peak: _add_peak_markers called. Freqs: {len(freqs_for_plot)}, RSSIs: {len(rssis_for_plot)}")

        if not freqs_for_plot or len(freqs_for_plot) < 3: # Need at least 3 points for local max
            # if freqs_for_plot: print(f"Debug Peak: Not enough data points for peak detection ({len(freqs_for_plot)}).")
            return

        peaks_found_this_run = 0

        # The main loop for peak detection iterates from the second point to the second-to-last point.
        # For each point, we will calculate a local average RSSI if dynamic thresholding is enabled.

        for i in range(1, len(rssis_for_plot) - 1):
            current_rssi = rssis_for_plot[i]
            prev_rssi = rssis_for_plot[i-1]
            next_rssi = rssis_for_plot[i+1]

            # Calculate effective minimum RSSI threshold for the current point i
            effective_min_rssi_for_peak = self.ABSOLUTE_MIN_PEAK_RSSI
            if self.USE_DYNAMIC_THRESHOLD:
                # Define the window for local average calculation
                start_index = max(0, i - self.LOCAL_AVERAGE_WINDOW_HALF_SIZE)
                end_index = min(len(rssis_for_plot), i + self.LOCAL_AVERAGE_WINDOW_HALF_SIZE + 1)
                local_rssis_window = rssis_for_plot[start_index:end_index]

                if local_rssis_window: # Ensure the window is not empty
                    local_average_rssi = sum(local_rssis_window) / len(local_rssis_window)
                    dynamic_threshold = local_average_rssi + self.DYNAMIC_THRESHOLD_OFFSET_DB
                    effective_min_rssi_for_peak = max(self.ABSOLUTE_MIN_PEAK_RSSI, dynamic_threshold)
                    # print(f"Debug Peak @{freqs_for_plot[i]:.1f}{self.display_unit}: LocalAvgRSSI={local_average_rssi:.1f}, DynThresh={dynamic_threshold:.1f}, EffMinRSSI={effective_min_rssi_for_peak:.1f}")

            # New condition for fatter peaks (replaces is_local_max and sufficiently_prominent)
            # A point is a peak if it's >= neighbors and strictly > at least one neighbor (not flat)
            is_fatter_peak = (current_rssi >= prev_rssi and current_rssi >= next_rssi and \
                               (current_rssi > prev_rssi or current_rssi > next_rssi))
            
            above_effective_min_threshold = current_rssi > effective_min_rssi_for_peak

            # if i < 5 or i > len(rssis_for_plot) - 6 : # Print for first/last few points
            marked_this_point = False
            if is_fatter_peak and above_effective_min_threshold:
                peak_freq_display = freqs_for_plot[i]

                if self.is_vhf: # Display unit is MHz
                    marker_text = f"{peak_freq_display:.2f}"
                else: # Display unit is kHz
                    # Use the global current_radio_mode_str for formatting peaks,
                    # as it reflects the mode during which data was collected.
                    if current_radio_mode_str == "AM":
                        marker_text = f"{peak_freq_display:.0f}" # Integer for AM in kHz
                    else: # LSB, USB, etc. on SW
                        marker_text = f"{peak_freq_display:.1f}" # One decimal for SSB etc. in kHz
                
                # print(f"Debug Peak: Adding marker for Freq={peak_freq_display:.2f}, RSSI={current_rssi:.1f}")
                peaks_found_this_run += 1
                text_y_offset = (self.ax.get_ylim()[1] - self.ax.get_ylim()[0]) * 0.035 # 3.5% of y-axis range for offset
                marker = self.ax.text(peak_freq_display, current_rssi + text_y_offset, marker_text,
                                      color='yellow', fontsize=7, ha='center', va='bottom',
                                      bbox=dict(boxstyle="round,pad=0.15", fc="#1A1A1A", ec="yellow", alpha=0.7))
                self.peak_markers.append(marker)
                marked_this_point = True
        
        # if peaks_found_this_run > 0:
        #     print(f"Debug Peak: Added {peaks_found_this_run} markers in this update.")

            # Debugging for high points that are not marked:
            # Only print if the point was above the general RSSI threshold but didn't meet other criteria.
            if not marked_this_point and current_rssi > self.ABSOLUTE_MIN_PEAK_RSSI: # Check against absolute min to reduce noise
                pass # Add pass statement if the block is intentionally empty for now
                # print(f"Debug Peak (High, Not Marked): Freq={freqs_for_plot[i]:.2f}, RSSI={current_rssi:.1f} (Prev={prev_rssi:.1f}, Next={next_rssi:.1f})")
                # print(f"  Conditions: IsFatterPeak={is_fatter_peak}, AboveEffectiveMin={above_effective_min_threshold} (EffectiveMinThresh={effective_min_rssi_for_peak:.1f})")

    def update_plot(self):
        if not self.spectrum_data: # No data or cleared
            self.line.set_data([], [])
            self.clear_peak_markers() # Clear markers if no data
        else:
            # Sort frequencies for a consistent plot line
            sorted_frequencies = sorted(self.spectrum_data.keys())
            freqs_for_plot = [f / self.freq_divisor for f in sorted_frequencies]
            rssis_for_plot = [self.spectrum_data[f] for f in sorted_frequencies]
            self.line.set_data(freqs_for_plot, rssis_for_plot)

            # Remove old fill collection if it exists
            if self.fill_collection:
                self.fill_collection.remove()
                self.fill_collection = None

            # Add new fill_between collection
            if freqs_for_plot and rssis_for_plot: # Ensure there's data to fill
                self.fill_collection = self.ax.fill_between(
                    freqs_for_plot,
                    rssis_for_plot,
                    y2=0,  # Fill down to the 0 dBuV level
                    color="#00FFFF",  # Cyan, same as line color
                    alpha=0.2,       # Adjust transparency as desired
                    zorder=self.line.get_zorder() - 1 # Ensure fill is behind the line
                )
            # Add peak markers if enabled and data exists
            if self.show_peaks_enabled and self.spectrum_data and freqs_for_plot:
                self._add_peak_markers(freqs_for_plot, rssis_for_plot)
            else:
                self.clear_peak_markers() # Clear if peaks disabled OR no data to mark
        
        self.ax.relim()
        self.ax.autoscale_view(scalex=True, scaley=False) # Autoscale X, but not Y initially

        # Set x-axis limits to exact band limits
        display_min_freq = self.target_min_freq_khz / self.freq_divisor
        display_max_freq = self.target_max_freq_khz / self.freq_divisor
        self.ax.set_xlim(display_min_freq, display_max_freq)

        # Adjust Y-axis limits dynamically
        if self.spectrum_data:
            min_rssi_in_data = min(self.spectrum_data.values())
            max_rssi_in_data = max(self.spectrum_data.values())
            
            # Tentative y_min and y_max based on data and padding
            tentative_y_min = min_rssi_in_data - self.y_axis_padding
            tentative_y_max = max_rssi_in_data + self.y_axis_padding
            
            # Ensure y_max is not too low
            final_y_max = max(tentative_y_max, self.min_dynamic_y_max)
            
            # Initial final_y_min
            final_y_min = tentative_y_min
            
            # Ensure minimum range
            if final_y_max - final_y_min < self.min_y_axis_range:
                # Calculate the midpoint of the actual data range
                data_midpoint = (min_rssi_in_data + max_rssi_in_data) / 2.0
                # Expand around data midpoint
                final_y_min = data_midpoint - (self.min_y_axis_range / 2.0)
                final_y_max = data_midpoint + (self.min_y_axis_range / 2.0)
                
                # Re-ensure y_max is not too low after range adjustment
                final_y_max = max(final_y_max, self.min_dynamic_y_max)
                # If y_max was pushed up, ensure y_min maintains the range by adjusting it downwards if necessary
                final_y_min = min(final_y_min, final_y_max - self.min_y_axis_range)

            self.ax.set_ylim(final_y_min, final_y_max)
        else:
            # If no data (e.g., after stop/clear or before first data), stick to initial 0-100 limits
            self.ax.set_ylim(self.initial_y_min, self.initial_y_max)

        self.fig.canvas.draw_idle()
    
    def on_close(self):
        global spectrum_window_instance
        self.stop_sweep()
        self.clear_peak_markers() # Clear markers when closing
        spectrum_window_instance = None
        self.window.destroy()

# --- Memory Viewer Window ---
class MemoryEditorWindow:
    def __init__(self, master_app_ref):
        self.master_app = master_app_ref
        self.window = Window(self.master_app, title="Memory Editor", width=370, height=330)
        self.window.bg = self.master_app.bg 
        self.window.when_closed = self.on_close
        self.window.tk.resizable(False, False)
        self.window.tk.config(padx=16, pady=16)

        self.memory_slots_data = {}
        self.max_slots = 99

        main_content_box = Box(self.window, align="top", width="fill", height="fill")
        top_controls_box = Box(main_content_box, width="fill", align="top")
        self.load_button = PushButton(
            top_controls_box,
            text="Load Memories from Radio",
            command=self.load_memories,
            width="fill"
        )
        self.load_button.bg = dark_theme_button_bg
        self.load_button.text_color = dark_theme_text_color
        Box(top_controls_box, height=15, width="fill")

        main_box = Box(main_content_box, layout="grid", width="fill", height="fill", align="top")
        main_box.tk.grid_columnconfigure(0, weight=1)
        current_main_row = 0

        # Slot selection row: small input, spacing, OK button to far right
        slot_row_box = Box(main_box, layout="grid", grid=[0, current_main_row], align="left", width="fill")
        slot_row_box.tk.grid_columnconfigure(0, weight=0)
        slot_row_box.tk.grid_columnconfigure(1, weight=0)
        slot_row_box.tk.grid_columnconfigure(2, weight=1)
        slot_row_box.tk.grid_columnconfigure(3, weight=0)
        Text(slot_row_box, text="Slot (1-99):", grid=[0,0], align="left", width=12).text_color = dark_theme_text_color
        self.slot_input = TextBox(slot_row_box, text="1", grid=[1,0], width=4, align="left")
        self.slot_input.bg = dark_theme_combo_bg
        self.slot_input.text_color = dark_theme_combo_text_color
        Box(slot_row_box, width=15, grid=[2,0])  # Abstand zwischen Eingabe und OK
        self.slot_confirm_btn = PushButton(
            slot_row_box,
            text="OK",
            grid=[3,0],
            command=self.confirm_slot_input,
            width=15,
            align="right"
        )
        self.slot_confirm_btn.bg = dark_theme_button_bg
        self.slot_confirm_btn.text_color = dark_theme_text_color
        current_main_row += 1

        Box(main_box, grid=[0, current_main_row], height=6, width="fill")
        current_main_row += 1

        # Edit fields (Frequency, Band, Mode all same width)
        editor_fields_box = Box(main_box, layout="grid", grid=[0, current_main_row], align="left", width="fill")
        editor_fields_box.tk.grid_columnconfigure(0, weight=0)
        editor_fields_box.tk.grid_columnconfigure(1, weight=1)
        field_width = 22
        current_edit_row = 0
        Text(editor_fields_box, text="Frequency:", grid=[0,current_edit_row], align="left", width=12).text_color = dark_theme_text_color
        self.freq_entry = TextBox(editor_fields_box, text="", grid=[1,current_edit_row], align="center", width=24)
        self.freq_entry.bg = dark_theme_combo_bg
        self.freq_entry.text_color = dark_theme_combo_text_color
        current_edit_row+=1
        Text(editor_fields_box, text="Band:", grid=[0,current_edit_row], align="left", width=12).text_color = dark_theme_text_color
        self.band_entry = Combo(editor_fields_box, options=list(BANDS_DATA.keys()), grid=[1,current_edit_row], align="left", width=20)
        self.band_entry.bg = dark_theme_combo_bg
        self.band_entry.text_color = dark_theme_combo_text_color
        current_edit_row+=1
        Text(editor_fields_box, text="Mode:", grid=[0,current_edit_row], align="left", width=12).text_color = dark_theme_text_color
        self.mode_entry = Combo(editor_fields_box, options=["FM","AM","LSB","USB"], grid=[1,current_edit_row], align="left", width=20)
        self.mode_entry.bg = dark_theme_combo_bg
        self.mode_entry.text_color = dark_theme_combo_text_color
        current_edit_row+=1

        Box(main_content_box, height=10, width="fill")
        self.write_all_button = PushButton(
            main_content_box,
            text="Write Memories to Radio",
            command=self.write_all_slots,
            width="fill",
            align="top"
        )
        self.write_all_button.bg = dark_theme_button_bg
        self.write_all_button.text_color = dark_theme_text_color

        Box(main_content_box, height=10, width="fill")
        self.status_label_box = Box(self.window, align="bottom", width="fill")
        self.status_label = Text(self.status_label_box, text="Load memories to view.", align="bottom", width="fill")
        self.status_label.text_color = dark_theme_text_color
        Box(self.status_label_box, height=4, width="fill", align="bottom")

        self.last_selected_slot = None
        self.select_slot(1)
        self.window.height = 320

    def confirm_slot_input(self):
        try:
            slot_num = int(self.slot_input.value)
            max_slot = 99
            if slot_num < 1 or slot_num > max_slot:
                self.status_label.value = f"Slot must be 1-{max_slot}!"
                return
            self.select_slot(slot_num)
        except Exception:
            self.status_label.value = "Invalid slot number!"

    def select_slot(self, slot_num):
        # Save previous slot
        if self.last_selected_slot is not None:
            self.save_current_slot_to_memory(self.last_selected_slot)
        self.last_selected_slot = slot_num
        data = self.memory_slots_data.get(slot_num, None)
        if data:
            freq_hz = data.get("freq_hz", 0)
            mode = data.get("mode", "FM")
            band = data.get("band", "VHF")
            if band == "VHF":
                freq_disp = f"{freq_hz/1_000_000:.1f}M" if freq_hz else ""
            else:
                freq_disp = f"{freq_hz/1_000:.1f}k" if freq_hz else ""
            self.freq_entry.value = freq_disp
            self.band_entry.value = band
            self.mode_entry.value = mode
            self.status_label.value = f"Viewing Slot {slot_num:02d}."
        else:
            self.freq_entry.value = ""
            self.band_entry.value = "VHF"
            self.mode_entry.value = "FM"
            self.status_label.value = f"Slot {slot_num:02d} is empty."

    def load_memories(self):
        if not (ser and ser.is_open):
            self.status_label.value = "Error: Radio not connected."
            # self.master_app.warn("Memory Viewer", "Radio not connected.") # User requested no app.warn
            print("WARN: Memory Viewer: Radio not connected during load_memories.")
            return

        self.status_label.value = "Sending '$' to radio..."
        if not send_serial_command_internal('$'): # Use internal to get return status
            self.status_label.value = "Error: Failed to send '$' command."
            return

        self.status_label.value = "Waiting for memory data!"
        self.master_app.update() # Force GUI update - Corrected method name

        self.memory_slots_data.clear() # Clear previous data
        
        original_timeout = ser.timeout
        ser.timeout = 0.5  # Set a readline timeout (e.g., 500ms)

        lines_processed_count = 0
        
        # Expect up to 99 lines for the memory slots
        for i in range(99): # Iterate 99 times, once for each potential slot
            try:
                line_bytes = ser.readline()
                if not line_bytes: # Timeout, no more data for this slot or end of transmission
                    print(f"MemRead: Timeout waiting for slot {i+1} data.")
                    break 
                
                line = line_bytes.decode('ascii', errors='ignore').strip()
                if not line: # Empty line received
                    print(f"MemRead: Empty line received for slot {i+1}.")
                    continue 

                print(f"MemRead Raw Line {i+1}: {line}") # Debug

                parts = line.split(',')
                
                # Try parsing as: SlotNum,Band,FreqHz,Mode (4 parts)
                if len(parts) == 4:
                    try:
                        slot_num_from_radio_str = parts[0].strip()
                        # Handle potential leading '#' character
                        if slot_num_from_radio_str.startswith('#'):
                            slot_num_from_radio_str = slot_num_from_radio_str[1:]
                        slot_num = int(slot_num_from_radio_str.lstrip('0') if slot_num_from_radio_str.lstrip('0') else "0") # "00" -> 0
                        band = parts[1].strip()
                        freq_hz = int(parts[2].strip())
                        mode = parts[3].strip()

                        if 1 <= slot_num <= 99:
                            if freq_hz != 0 and band: # Freq 0 or empty band means empty slot
                                self.memory_slots_data[slot_num] = {"band": band, "freq_hz": freq_hz, "mode": mode}
                                lines_processed_count +=1
                            else:
                                print(f"MemRead: Slot {slot_num} is empty (freq 0 or no band).")
                        else:
                             print(f"MemRead: Invalid slot number {slot_num} from radio on line: {line}")
                    except ValueError as ve:
                        print(f"MemRead: ValueError parsing 4-part slot data '{line}': {ve}")
                    except IndexError:
                        print(f"MemRead: IndexError parsing 4-part slot data '{line}'.")
                # Try parsing as: Band,FreqHz,Mode (3 parts), slot number is i+1
                elif len(parts) == 3:
                    slot_num = i + 1 # Slot number is implicit by line order
                    try:
                        band = parts[0].strip()
                        freq_hz = int(parts[1].strip())
                        mode = parts[2].strip()
                        if freq_hz != 0 and band:
                             self.memory_slots_data[slot_num] = {"band": band, "freq_hz": freq_hz, "mode": mode}
                             lines_processed_count +=1
                        else:
                            print(f"MemRead: Slot {slot_num} (implicit) is empty (freq 0 or no band).")
                    except ValueError as ve:
                        print(f"MemRead: ValueError parsing 3-part slot data '{line}': {ve}")
                    except IndexError:
                        print(f"MemRead: IndexError parsing 3-part slot data '{line}'.")
                else:
                    print(f"MemRead: Ignoring line with unexpected format ({len(parts)} parts): {line}")

            except serial.SerialException as e:
                self.status_label.value = f"Serial error: {e}"
                print(f"MemRead: SerialException: {e}")
                break 
            except Exception as e: 
                self.status_label.value = f"Error: {e}"
                print(f"MemRead: Exception: {e}")
                break 
        
        ser.timeout = original_timeout # Restore original timeout
        
        # Nach dem Laden: Slot 1 anzeigen
        self.select_slot(1)

        if lines_processed_count > 0:
            self.status_label.value = f"Loaded {lines_processed_count} Memory slot(s)!"
        elif not self.memory_slots_data: 
            self.status_label.value = "No Memory Slots loaded!"
        else: 
             self.status_label.value = "All Memory Slots are empty!"

    def on_slot_selected(self, selected_value):
        # Nicht mehr benötigt, da keine Combo/ListBox mehr
        pass

    def save_current_slot_to_memory(self, slot_num):
        """Speichert die aktuellen Editierfelder in den Speicherarray. Akzeptiert Hz, k, M/m, MHz, khz, etc."""
        try:
            freq_str = self.freq_entry.value.strip().lower().replace(' ','')
            band = self.band_entry.value.strip()
            mode = self.mode_entry.value.strip()
            if not freq_str or not band or not mode:
                # Leerer Slot, nicht speichern
                return
            # Umwandlung: 102.3M, 7100k, 1840k, 1.84m, 7000000, 3500000, 3500k, 3.5m, etc.
            freq_hz = self._parse_freq_to_hz(freq_str)
            if freq_hz is None:
                print(f"Error in save_current_slot_to_memory: invalid frequency '{freq_str}'")
                return
            if freq_hz == 0:
                # Slot löschen
                if slot_num in self.memory_slots_data:
                    del self.memory_slots_data[slot_num]
                return
            # Speichern/Überschreiben
            self.memory_slots_data[slot_num] = {"band": band, "freq_hz": freq_hz, "mode": mode}
        except Exception as e:
            print(f"Error in save_current_slot_to_memory: {e}")

    def _parse_freq_to_hz(self, freq_str):
        """
        Robustly parse frequency strings like 102.3M, 7100k, 1840k, 1.84m, 7000000, 3500000, 3500k, 3.5m, 7880k, 7880,5k, 7.88 MHz, etc. to Hz.
        Accepts case-insensitive units (m, mhz, k, khz, hz), optional whitespace, dot or comma as decimal, and flexible order.
        """
        import re
        try:
            s = freq_str.strip().replace(' ','').replace(',','.')
            s = s.lower()
            # Regex: number (int/float) + optional unit (m, mhz, k, khz, hz)
            match = re.match(r'^([0-9]+\.?[0-9]*)\s*(m|mhz|k|khz|hz)?$', s)
            if match:
                value = float(match.group(1))
                unit = match.group(2) or ''
                if unit in ['m', 'mhz']:
                    return int(value * 1_000_000)
                elif unit in ['k', 'khz']:
                    return int(value * 1_000)
                elif unit == 'hz':
                    return int(value)
                else:
                    # No unit: guess based on value
                    if value > 1_000_000:  # Looks like Hz
                        return int(value)
                    elif value > 10_000:   # Looks like kHz
                        return int(value * 1)
                    elif value > 1000:     # Could be kHz
                        return int(value * 1)
                    elif value > 100:      # Could be MHz (e.g. 102.3)
                        return int(value * 1_000_000)
                    else:                  # e.g. 7.1 (MHz)
                        return int(value * 1_000_000)
            # Try to extract number and unit with more flexible regex (e.g. 7.88MHz, 7880kHz, 7880k, 7880,5k)
            match2 = re.match(r'^([0-9]+[\.,]?[0-9]*)\s*([a-zA-Z]+)?$', freq_str.strip().replace(' ','').replace(',','.'))
            if match2:
                value = float(match2.group(1))
                unit = (match2.group(2) or '').lower()
                if unit in ['m', 'mhz']:
                    return int(value * 1_000_000)
                elif unit in ['k', 'khz']:
                    return int(value * 1_000)
                elif unit == 'hz':
                    return int(value)
                elif unit == '':
                    # No unit: guess
                    if value > 1_000_000:
                        return int(value)
                    elif value > 10_000:
                        return int(value * 1)
                    elif value > 1000:
                        return int(value * 1)
                    elif value > 100:
                        return int(value * 1_000_000)
                    else:
                        return int(value * 1_000_000)
            # Fallback: try to parse as float (Hz)
            return int(float(s))
        except Exception as e:
            print(f"Error in _parse_freq_to_hz: {e} (input: '{freq_str}')")
        return None

    def write_all_slots(self):
        """Sendet alle Slots im Batch ans Radio, leere als #NN,ALL,0,AM. Anzahl Slots = self.max_slots."""
        if not (ser and ser.is_open):
            self.status_label.value = "Error: Radio not connected."
            print("WARN: Write All: Radio not connected.")
            return
        # Vorherigen Slot speichern
        if self.last_selected_slot is not None:
            self.save_current_slot_to_memory(self.last_selected_slot)
        import time
        self.status_label.value = "Writing all slots..."
        slots_written = 0
        for slot_num in range(1, self.max_slots + 1):
            data = self.memory_slots_data.get(slot_num)
            if data:
                band = data.get('band', 'ALL')
                freq_hz = data.get('freq_hz', 0)
                mode = data.get('mode', 'AM')
            else:
                band = 'ALL'
                freq_hz = 0
                mode = 'AM'
            try:
                line = f"#{slot_num:02d},{band},{freq_hz},{mode}\r\n"
                ser.write(line.encode('ascii'))
                ser.flush()
                print(f"WriteAll: {line.strip()}")
                slots_written += 1
                time.sleep(0.03)  # 30 ms Pause nach jeder Zeile
            except Exception as e:
                print(f"WriteAll: Error writing slot {slot_num}: {e}")
        # Abschlusszeile wie im Webtool
        try:
            end_line = "--- All slots sent ---\r\n"
            ser.write(end_line.encode('ascii'))
            ser.flush()
            print(end_line.strip())
        except Exception as e:
            print(f"WriteAll: Error writing end line: {e}")
        self.status_label.value = f"Wrote {self.max_slots} slot(s) to radio."

    def on_close(self):
        global memory_viewer_window_instance # Renamed
        memory_viewer_window_instance = None
        self.window.destroy()

# --- GUI Setup ---
# Colors for Dark Theme
# Window height adjusted for new status fields
app = App(title="Mini-Radio Control", width=420, height=930, layout="grid") # Height slightly increased
app.bg = '#2E2E2E' # Dark background for Dark Theme
dark_theme_text_color = "#E0E0E0" # Light gray for text
dark_theme_button_bg = "#4A4A4A"  # Medium dark gray for buttons
dark_theme_combo_bg = "#3A3A3A" # Slightly lighter gray for dropdown
dark_theme_combo_text_color = "#E0E0E0" # Light gray for dropdown text

BAUD_RATES = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
# Get detailed information about serial ports
ports_info = list(serial.tools.list_ports.comports())
available_ports = [p.device for p in ports_info]
auto_selected_port = None

if not available_ports:
    available_ports = ["No ports found"] # Fallback if no ports are found
    print("No serial ports found.")
else:
    print(f"Found ports: {available_ports}")
    # Auto-Auswahl Logik
    # Keywords to look for in port description or name
    PORT_KEYWORDS = ["CH340", "CP210", "FTDI", "USB SERIAL", "SERIAL", "ACM", "USB-SERIAL", "UART"] # Auto-selection logic
    for port_obj in ports_info:
        desc = (port_obj.description or "").upper()
        name = (port_obj.name or "").upper() # port.name is usually the base name like 'ttyUSB0' or 'COM3'
        device_path = port_obj.device
        if any(keyword in desc or keyword in name for keyword in PORT_KEYWORDS):
            auto_selected_port = device_path
            print(f"Auto-selected port '{auto_selected_port}' based on keywords in description/name.")
            break # Use the first match

app.tk.resizable(False, False) # Window size not resizable
app.when_closed = cleanup      # Call cleanup function on closing

# Add uniform padding to the window
app.tk.config(padx=10, pady=10)

# --- Port Selection and Connect ---
current_grid_row = 0 # Start directly with port selection in row 0
Text(app, text="Serial Port:", grid=[0, current_grid_row], align="left").text_color = dark_theme_text_color # Starts now in row 0
app.port_selector = Combo(app, options=available_ports, grid=[1, current_grid_row], width=15, align="left")
app.port_selector.bg = dark_theme_combo_bg
app.port_selector.text_color = dark_theme_combo_text_color

# Port-Vorauswahl
if auto_selected_port and auto_selected_port in available_ports:
    app.port_selector.value = auto_selected_port
elif available_ports and available_ports[0] != "No ports found":
    # Fallback: Select the last port if auto-selection was not successful
    app.port_selector.value = available_ports[-1] # Selects the last port in the list

# Connect button spans two rows and has an increased height
app.connect_button = PushButton(app, text="Connect", command=toggle_connection, grid=[2, current_grid_row, 1, 2], width=9, height=2, align="right")
app.connect_button.bg = dark_theme_button_bg # Standard text color for the button
app.connect_button.text_color = dark_theme_text_color # Standard Textfarbe für den Button
current_grid_row += 1

# --- Baud Rate Selection ---
Text(app, text="Baud Rate:", grid=[0, current_grid_row], align="left").text_color = dark_theme_text_color
app.baud_rate_selector = Combo(app, options=BAUD_RATES, selected=str(DEFAULT_BAUD_RATE), grid=[1, current_grid_row], width=15, align="left")
app.baud_rate_selector.bg = dark_theme_combo_bg
app.baud_rate_selector.text_color = dark_theme_combo_text_color
current_grid_row += 1

# --- Button to Open Spectrum Analyzer ---
Text(app, text="", grid=[0, current_grid_row, 3, 1]) # Spacer
current_grid_row += 1

# Box to hold the Memory Viewer and Spectrum Analyzer buttons side-by-side
action_buttons_box = Box(app, layout="grid", grid=[0, current_grid_row, 3, 1], width="fill", align="top")
action_buttons_box.tk.columnconfigure(0, weight=1)  # First button's column
action_buttons_box.tk.columnconfigure(1, weight=1)  # Second button's column

def open_memory_editor_window():
    global memory_viewer_window_instance
    if not (ser and ser.is_open):
        print("WARN: Memory Editor button pressed but not connected to radio.")
        if hasattr(app, 'connect_button'):
            app.connect_button.text = "Not\nconnected!"
            app.connect_button.text_color = "#FFA726"
        return
    if memory_viewer_window_instance is not None and memory_viewer_window_instance.window.tk.winfo_exists():
        try:
            memory_viewer_window_instance.window.tk.focus_force()
            memory_viewer_window_instance.window.tk.lift()
        except Exception as e:
            print(f"Could not focus/lift memory editor window: {e}")
        return
    memory_viewer_window_instance = MemoryEditorWindow(app)

memory_viewer_button = PushButton(
    action_buttons_box,
    text="Open Memory Editor",
    command=open_memory_editor_window,
    grid=[0, 0],
    width="21"
)
memory_viewer_button.bg = dark_theme_button_bg
memory_viewer_button.text_color = dark_theme_text_color
memory_viewer_button.tk.config(relief="raised", borderwidth=2)

def open_spectrum_analyzer_window():
    global spectrum_window_instance, current_radio_band_name, current_radio_frequency_khz, current_radio_step_size_str, current_radio_mode_str
    # Check for connection first
    if not (ser and ser.is_open):
        print("WARN: Spectrum Analyzer button pressed but not connected to radio.")
        if hasattr(app, 'connect_button'):
            app.connect_button.text = "Not\nconnected!" # Consistent with other buttons
            app.connect_button.text_color = "#FFA726" # Orange warning color
        return
    if spectrum_window_instance is not None and spectrum_window_instance.window.tk.winfo_exists():
        # User requested no app.info
        # print("INFO: Spectrum window is already open.")
        try:
            spectrum_window_instance.window.tk.focus_force() # Bring to front
            spectrum_window_instance.window.tk.lift()
        except Exception as e:
            print(f"Could not focus/lift spectrum window: {e}")
        return

    try:
        if not current_radio_band_name or current_radio_frequency_khz is None or current_radio_step_size_str is None or current_radio_mode_str is None:
            # app.warn("Spectrum Analyzer", "Radio status not fully available. Please wait for an update.") # User requested no app.warn
            print("WARN: Spectrum Analyzer: Radio status not fully available. Please wait for an update.")
            return

        # Determine the band name to display and the key to use for BANDS_DATA
        display_band_name_for_spectrum = current_radio_band_name
        band_data_key = current_radio_band_name

        # Special handling if radio reports "15M"
        if current_radio_band_name == "15M":
            if current_radio_mode_str == "USB":
                band_data_key = "15M HAM" # Use data for 15M HAM
            # If AM or other, band_data_key remains "15M", display name also "15M"
            # display_band_name_for_spectrum remains "15M" for consistency

        selected_band_info = BANDS_DATA.get(band_data_key)
        
       
        
        if not selected_band_info:
            # Fallback: try to find a band that contains the current frequency
            for name, data in BANDS_DATA.items():
                if data["min_khz"] <= current_radio_frequency_khz <= data["max_khz"]:
                    selected_band_info = data
                    display_band_name_for_spectrum = name # Use the inferred band name for display
                    print(f"INFO: Spectrum using inferred band '{name}' based on current frequency.")
                    break
            if not selected_band_info:
                # Use the originally reported band name in the warning if fallback fails
                # app.warn("Spectrum Analyzer", f"No band definition found for '{current_radio_band_name}' (mode: {current_radio_mode_str}) or current frequency. Cannot determine sweep range.") # User requested no app.warn
                print(f"WARN: Spectrum Analyzer: No band definition found for '{current_radio_band_name}' (mode: {current_radio_mode_str}) or current frequency. Cannot determine sweep range.")
                return

        spectrum_window_instance = SpectrumWindow(
            master_app_ref=app,
            initial_band_name=display_band_name_for_spectrum, # This is the name shown in SpectrumWindow
            initial_freq_khz=current_radio_frequency_khz,
            initial_step_size_str=current_radio_step_size_str,
            band_min_khz=selected_band_info["min_khz"],
            band_max_khz=selected_band_info["max_khz"]
        )
    except Exception as e:
        print(f"Error opening spectrum window: {e}")
        # app.error is also a GUI popup, replace with print
        print(f"ERROR: Spectrum Error: Could not open spectrum window: {e}")

spectrum_button = PushButton(
    action_buttons_box, # Parent is the new box
    text="Open Spectrum Analyzer",
    command=open_spectrum_analyzer_window,
    grid=[1, 0], # Column 1, Row 0 within action_buttons_box
    width="21"
)
spectrum_button.bg = dark_theme_button_bg
spectrum_button.text_color = dark_theme_text_color
spectrum_button.tk.config(relief="raised", borderwidth=2) # Example: raised border with width 2

current_grid_row += 1

# Empty line for spacing above the checkbox
Text(app, text="", grid=[0, current_grid_row, 3, 1]) # Span all relevant columns
current_grid_row += 1

# --- Checkbox for Cyclic Reading ---
app.enable_cyclic_reading = CheckBox(app, text="Enable Cyclic Reading", command=toggle_cyclic_reading, grid=[0, current_grid_row, 3, 1], align="left")
app.enable_cyclic_reading.text_color = dark_theme_text_color
current_grid_row += 1

# --- Control Definitions ---
# Structure: (Label Text, Command1, Text Button1, Command2, Text Button2, Type ["pair" or "single"])
# "Encoder Press" is handled separately above the main loop.
controls_data = [
    # ("Encoder Press",       'e', "Press",       None, None,       "single"), # Moved out
    ("Encoder Rotate",      'R', "Right",        'r', "Left",      "pair"), # Band before Mode again
    ("Band",                'B', "Next",    	 'b', "Previous",  "pair"), # Mode after Band again
    ("Mode",               	'M', "Next",    	 'm', "Previous",  "pair"), # Renamed from AGC
    ("Calibration",        	'I', "Up",        	 'i', "Down",      "pair"), # New for Step Size
    ("Step Size",        	'S', "Next",     	 's', "Previous",  "pair"), # New for Bandwidth
    ("Bandwidth",          	'W', "Next",     	 'w', "Previous",  "pair"), # New for AGC Status
    ("AGC/Att",             'A', "Next",         'a', "Previous",  "pair"), # New for Battery Voltage (as string)
    ("Volume",          	'V', "Up",      	 'v', "Down",      "pair"),
    ("Backlight",    		'L', "Brighter",     'l', "Dimmer",    "pair"),
    ("Sleep",               'O', "On",         	 'o', "Off",       "pair"),
    # Add new controls here if needed, they will be added below "Encoder Press"
]

# --- Radio Status Display Area ---
# This will be row 1 (after Port selection in row 0)
status_text_config = {"align": "left", "width": "fill"} # text_color removed, set individually

# Empty line for spacing above the status area
Text(app, text="", grid=[0, current_grid_row, 3, 1]) # Span all relevant columns
current_grid_row += 1

fw_label = Text(app, text="FW Version:", grid=[0, current_grid_row], **status_text_config)
fw_label.text_color = dark_theme_text_color
app.status_fw_version = Text(app, text="---", grid=[1, current_grid_row, 2, 1], **status_text_config) # Spans 2 cols, space removed
app.status_fw_version.text_color = dark_theme_text_color
current_grid_row += 1

battery_label = Text(app, text="Battery:", grid=[0, current_grid_row], **status_text_config)
battery_label.text_color = dark_theme_text_color
app.status_battery = Text(app, text="--- (--%)", grid=[1, current_grid_row, 2, 1], **status_text_config) # Corrected placeholder
app.status_battery.text_color = dark_theme_text_color
current_grid_row += 1

freq_label = Text(app, text="Frequency:", grid=[0, current_grid_row], **status_text_config)
freq_label.text_color = dark_theme_text_color
app.status_frequency = Text(app, text="---", grid=[1, current_grid_row, 2, 1], **status_text_config) # Spans 2 cols, space removed
app.status_frequency.text_color = dark_theme_text_color
current_grid_row += 1

mode_band_label = Text(app, text="Band/Mode:", grid=[0, current_grid_row], **status_text_config)
mode_band_label.text_color = dark_theme_text_color
app.status_mode_band = Text(app, text="---/---", grid=[1, current_grid_row, 2, 1], **status_text_config)
app.status_mode_band.text_color = dark_theme_text_color
current_grid_row += 1

step_label = Text(app, text="Step Size:", grid=[0, current_grid_row], **status_text_config)
step_label.text_color = dark_theme_text_color
app.status_step = Text(app, text="---", grid=[1, current_grid_row, 2, 1], **status_text_config)
app.status_step.text_color = dark_theme_text_color
current_grid_row += 1

bw_label = Text(app, text="Bandwidth:", grid=[0, current_grid_row], **status_text_config)
bw_label.text_color = dark_theme_text_color
app.status_bw = Text(app, text="---", grid=[1, current_grid_row, 2, 1], **status_text_config)
app.status_bw.text_color = dark_theme_text_color
current_grid_row += 1

agc_label = Text(app, text="AGC Status:", grid=[0, current_grid_row], **status_text_config)
agc_label.text_color = dark_theme_text_color
app.status_agc = Text(app, text="---", grid=[1, current_grid_row, 2, 1], **status_text_config)
app.status_agc.text_color = dark_theme_text_color
current_grid_row += 1

signal_label = Text(app, text="Signal:", grid=[0, current_grid_row], **status_text_config)
signal_label.text_color = dark_theme_text_color
app.status_signal    = Text(app, text="RSSI: --, SNR: --", grid=[1, current_grid_row, 2, 1], **status_text_config)
app.status_signal.text_color = dark_theme_text_color
current_grid_row += 1 

volume_label = Text(app, text="Volume:", grid=[0, current_grid_row], **status_text_config)
volume_label.text_color = dark_theme_text_color
app.status_volume    = Text(app, text="-- (--%)", grid=[1, current_grid_row, 2, 1], **status_text_config) # Corrected placeholder
app.status_volume.text_color = dark_theme_text_color
current_grid_row += 1

# Empty line for spacing below the status area
Text(app, text="", grid=[0, current_grid_row, 3, 1]) # Span all relevant columns
current_grid_row += 1 # Increment row for the actual controls to start below status

def reset_status_display():
    """Resets all status display Text widgets to their initial placeholder values."""
    if hasattr(app, 'status_fw_version'): app.status_fw_version.value = "---"
    if hasattr(app, 'status_battery'): app.status_battery.value = "--- (--%)"
    if hasattr(app, 'status_frequency'): app.status_frequency.value = "---"
    if hasattr(app, 'status_mode_band'): app.status_mode_band.value = "---/---"
    if hasattr(app, 'status_step'): app.status_step.value = "---"
    if hasattr(app, 'status_bw'): app.status_bw.value = "---"
    if hasattr(app, 'status_agc'): app.status_agc.value = "---"
    if hasattr(app, 'status_signal'): app.status_signal.value = "RSSI: --, SNR: --"
    if hasattr(app, 'status_volume'): app.status_volume.value = "-- (--%)"
    print("INFO: Status display fields reset.")

# --- Create "Encoder Press" button manually above the other controls --- # This will be the first control row after status
encoder_press_label_text = "Encoder Press"
encoder_press_cmd = 'e'
encoder_press_button_text = "Press"

lbl_encoder_press = Text(app, text=f"{encoder_press_label_text}:", grid=[0, current_grid_row], align="left")
lbl_encoder_press.text_color = dark_theme_text_color

btn_encoder_press = PushButton(
    app,
    text=encoder_press_button_text,
    command=lambda: send_serial_command(encoder_press_cmd),
    grid=[1, current_grid_row, 2, 1],  # Start in column 1, span 2 columns
    width="25",                        # Fill the width of the spanned columns
    align = "right"                    # This align might not do much if width="fill" or a large width is used
)
btn_encoder_press.bg = dark_theme_button_bg
btn_encoder_press.text_color = dark_theme_text_color

# Access the underlying tkinter widget to set relief style
# Common relief styles: 'flat', 'raised', 'sunken', 'groove', 'ridge'
btn_encoder_press.tk.config(relief="raised", borderwidth=2) # Example: raised border with width 2
current_grid_row += 1

# --- Loop to create paired buttons for other controls ---

for label, cmd1, txt1, cmd2, txt2, ctrl_type in controls_data:
    lbl = Text(app, text=f"{label}:", grid=[0, current_grid_row], align="left")
    lbl.text_color = dark_theme_text_color

    # text_color is set after creation
    button_properties = {"width": "11", "align": "right"}

    # Since "Encoder Press" (the only "single" type) is handled separately,
    # all remaining controls in controls_data are expected to be "pair".
    # Decrement button (cmd2, txt2) on the left
    btn_decrement = PushButton(app, text=txt2, command=lambda c=cmd2: send_serial_command(c), grid=[1, current_grid_row], **button_properties)
    btn_decrement.bg = dark_theme_button_bg
    btn_decrement.text_color = dark_theme_text_color

    # Increment button (cmd1, txt1) on the right
    btn_increment = PushButton(app, text=txt1, command=lambda c=cmd1: send_serial_command(c), grid=[2, current_grid_row], **button_properties)
    btn_increment.bg = dark_theme_button_bg
    btn_increment.text_color = dark_theme_text_color

    current_grid_row += 1

# Auto-connect on start attempt (currently commented out)
#app.after(100, init_serial)

# Repeat the check_serial_data function every 200ms
app.repeat(200, check_serial_data)

app.display()