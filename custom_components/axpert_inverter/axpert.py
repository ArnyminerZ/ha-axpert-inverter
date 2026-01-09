import logging
import os
import time
import threading

_LOGGER = logging.getLogger(__name__)

class AxpertInverter:
    """Class to communicate with the Axpert Inverter via HID."""

    def __init__(self, device_path: str):
        """Initialize the inverter interface."""
        self._device_path = device_path
        self._lock = threading.Lock()
        self._last_command_time = 0

    def _get_crc(self, cmd: str | bytes) -> bytes:
        """Calculate CRC16-XMODEM."""
        crc = 0
        if isinstance(cmd, str):
            da = bytearray(cmd, 'utf8')
        else:
            da = bytearray(cmd)
        
        for byte in da:
            crc ^= byte << 8
            for _ in range(8):
                if (crc & 0x8000):
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        
        low = crc & 0xFF
        high = (crc >> 8) & 0xFF

        # Fix for control characters in CRC (from Voltronic protocol)
        # If CRC bytes match ( (0x28), CR (0x0d), LF (0x0a), increment them
        if low in (0x28, 0x0d, 0x0a):
            low += 1
        
        if high in (0x28, 0x0d, 0x0a):
            high += 1

        return bytes([high, low])

    def send_command(self, command: str) -> str:
        """Send a command to the inverter and return the response."""
        with self._lock:
            # Ensure at least 500ms between commands
            time_since_last = time.time() - self._last_command_time
            if time_since_last < 0.5:
                time.sleep(0.5 - time_since_last)

            for attempt in range(2):
                fd = None
                try:
                    # Open device for reading and writing, non-blocking
                    fd = os.open(self._device_path, os.O_RDWR | os.O_NONBLOCK)
                    
                    # Prepare command
                    crc = self._get_crc(command)
                    full_command = command.encode() + crc + b'\r'
                    
                    # Write command
                    # For HID devices, we might need to write in chunks or just once.
                    _LOGGER.debug(f'Sending command: {command} ({full_command})')
                    os.write(fd, full_command)
                    time.sleep(0.1) # Wait a bit for processing
    
                    # Read response
                    response = b""
                    retries = 50 # 5 seconds timeout
                    while retries > 0:
                        try:
                            chunk = os.read(fd, 256)
                            if chunk:
                                response += chunk
                                if b'\r' in response:
                                    break
                            else:
                                time.sleep(0.1)
                                retries -= 1
                        except BlockingIOError:
                            time.sleep(0.1)
                            retries -= 1
                        except Exception as e:
                            _LOGGER.error(f"Error reading from device: {e}")
                            break
                    
                    if not response:
                        raise Exception("No response from inverter")
    
                    # Process response bytes (before decoding)
                    # Strip trailing CR
                    if response.endswith(b'\r'):
                        response = response[:-1]
                    
                    # Check for ACK/NAK (simple cases)
                    if response == b'(ACK' or response == b'ACK':
                        return 'ACK'
                    if response == b'(NAK' or response == b'NAK':
                        if attempt == 0:
                            _LOGGER.warning(f"Got NAK for command {command}, retrying in 1s...")
                            time.sleep(1)
                            continue
                        raise Exception(f"Command \"{command}\" not supported")

                    # Extract CRC and Data
                    # Format: (DATA<CRC>
                    # CRC is last 2 bytes
                    
                    # Valid characters in response: A-Z, 0-9, space, ., -, (, :
                    # We use this to help separate CRC from data if there is trailing garbage
                    valid_chars = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 (.-:")
                    
                    if len(response) > 2:
                        # Strategy 1: Standard Split (Last 2 bytes are CRC)
                        std_data = response[:-2]
                        std_crc_received = response[-2:]
                        std_crc_calc = self._get_crc(std_data)
                        
                        if std_crc_calc == std_crc_received:
                            # Perfect match, use it
                            raw_data = std_data
                        else:
                            # Strategy 2: Smart Scan
                            # Check if the standard split failed because of trailing garbage?
                            # Or because of corruption?
                            # We scan for a valid data prefix that checksums correctly.
                            
                            found_smart = False
                            # We iterate backwards from len-2 down to 0? Or forwards?
                            # Usually data is long, garbage is short.
                            # But valid chars might mask CRC. 
                            # Let's check prefixes that consist ONLY of valid chars.
                            
                            # Optimized scan: Only check split points where data bytes are all valid
                            # But checking all bytes repeatedly is slow.
                            # Just check if std_data was all valid. If so, and CRC failed, maybe actual data is shorter?
                            # Scan from length 1 to len-2
                            
                            for i in range(len(response)-2, 0, -1):
                                candidate_data = response[:i]
                                # Check if ALL chars in candidate are valid
                                # This filter is crucial to avoid matching random binary data
                                if all(b in valid_chars for b in candidate_data):
                                    candidate_crc = response[i:i+2]
                                    if self._get_crc(candidate_data) == candidate_crc:
                                        # Found a match!
                                        _LOGGER.debug(f"Smart CRC scan recovered data for {command}. Garbage detected at end of response.")
                                        raw_data = candidate_data
                                        found_smart = True
                                        break
                                        
                            if not found_smart:
                                _LOGGER.warning(f"CRC mismatch for {command}: Recv {std_crc_received.hex()} vs Calc {std_crc_calc.hex()}. Smart scan failed to recover.")
                                # Fallback to standard split even if invalid, as we can't do better
                                raw_data = std_data

                    else:
                        raw_data = response

                    try:
                        # Decode with ignore to handle garbage bytes
                        decoded_response = raw_data.decode('iso-8859-1', errors='ignore')
                        
                        # Strip null bytes and whitespace (if any left)
                        decoded_response = decoded_response.replace('\x00', '').strip()
                    except Exception:
                        decoded_response = raw_data.decode('utf-8', errors='ignore').replace('\x00', '').strip()

                    # Find the start of the response (usually '(')
                    if '(' in decoded_response:
                        decoded_response = decoded_response[decoded_response.find('(')+1:]

                    _LOGGER.debug(f'Response from inverter: {decoded_response}')
                    
                    return decoded_response
    
                except Exception as e:
                    if attempt == 1:
                        _LOGGER.error(f"Failed to communicate with inverter after retries: {e}")
                        raise e
                    else:
                        _LOGGER.warning(f"Failed to communicate with inverter: {e}")
                    if fd is not None:
                        os.close(fd)
                        fd = None
                    # Wait a bit before retry?
                    time.sleep(0.5)
                finally:
                    if fd is not None:
                        os.close(fd)
                    self._last_command_time = time.time()

    def get_general_status(self) -> dict:
        """Get general status parameters (QPIGS)."""
        raw = self.send_command("QPIGS")
        # Log raw response for debugging if parsing fails
        if not raw:
             return {}

        # Example from user log cleaned: 
        # 000.0 00.0 230.0 50.0 0046 0002 000 371 53.20 001 080 0026 0001 089.9 53.13 00000 00110110 ...
        parts = raw.split()
        if len(parts) < 16: # Need at least up to status
            _LOGGER.warning(f"QPIGS response too short: {raw}")
            return {}
        
        try:
            data = {
                "grid_voltage": float(parts[0]),
                "grid_frequency": float(parts[1]),
                "ac_output_voltage": float(parts[2]),
                "ac_output_frequency": float(parts[3]),
                "ac_output_apparent_power": int(parts[4]),
                "ac_output_active_power": int(parts[5]),
                "output_load_percent": int(parts[6]),
                "bus_voltage": int(parts[7]), # 371 (likely Bus Voltage)
                "battery_voltage": float(parts[8]), # 53.20
                "battery_charging_current": int(parts[9]), # 001
                "battery_capacity": int(parts[10]), # 080
                "heat_sink_temperature": int(parts[11]), # 0026 (Wait, 0026 is 26 deg?)
                "pv_input_current": float(parts[12]), # 0001 -> This might be 1A or a different scaling?
                # User log: 0001. Usually PV current is XXX or XX.X
                # If it is 0001, it is likely 1 Amp.
                
                "pv_input_voltage": float(parts[13]), # 089.9
                "scc_voltage": float(parts[14]), # 53.13
                "battery_discharge_current": int(parts[15]), # 00000
                "status_binary": parts[16], # 00110110
            }
            
            # Additional fields (not present in all firmwares)
            # ... QQ VV MMMMM ...
            # 17: Battery voltage offset?
            # 18: EEPROM version?
            # 19: PV Charging Power (MMMMM)
            
            if len(parts) > 16:
                # Supports extended QPIGS
                data["pv_charging_power"] = int(parts[19])
            
            return data
        except (ValueError, IndexError) as e:
            _LOGGER.error(f"Error parsing QPIGS data: {e} | Raw: {raw}")
            return {}

    def get_warnings(self) -> str:
        """Get warning status (QPIWS)."""
        try:
            return self.send_command("QPIWS")
        except Exception as e:
            _LOGGER.error(f"Error getting warnings: {e}")
            return ""

    def get_mode(self) -> str:
        """Get Device Mode (QMOD)."""
        # Response: (M<CRC><cr>  where M is P, S, L, B, F, H, D
        return self.send_command("QMOD")

    def get_device_id(self) -> str:
        """Get Device ID (QID)."""
        return self.send_command("QID")
    
    def set_ac_input_range(self, mode_code: str) -> bool:
        """Set AC Input Range. PGR00 or PGR01."""
        resp = self.send_command(mode_code)
        return "ACK" in resp
        
    def get_rated_information(self) -> dict:
        """Get Rated Information (QPIRI)."""
        raw = self.send_command("QPIRI")
        if not raw:
            return {}
            
        parts = raw.split()
        if len(parts) < 17:
             _LOGGER.warning(f"QPIRI response too short: {raw}")
             return {}

        try:
            # According to docs:
            # ...
            # 16: Output Source Priority (0:Utility, 1:Solar, 2:SBU)
            # 17: Charger Source Priority (0:Utility, 1:Solar, 2:Solar+Utility, 3:Only Solar)
            
            data = {}
            if len(parts) > 16:
                data["output_source_priority"] = parts[16]
            
            if len(parts) > 17:
                data["charger_source_priority"] = parts[17]
                
            return data
        except Exception as e:
            _LOGGER.error(f"Error parsing QPIRI: {e}")
            return {}

    def set_output_source_priority(self, priority: str) -> bool:
        """Set Output Source Priority. 00/01/02."""
        # POP00, POP01, POP02
        return "ACK" in self.send_command(f"POP{priority}")

    def set_charger_source_priority(self, priority: str) -> bool:
        """Set Charger Source Priority. 00/01/02/03."""
        # PCP00, PCP01, PCP02, PCP03
        return "ACK" in self.send_command(f"PCP{priority}")
    
    def get_firmware_version(self) -> str:
        """Get Main CPU Firmware Version (QVFW)."""
        # Response: (VERFW:XXXXX.XX<CRC><cr> or just (VERFW:00052.30
        try:
            raw = self.send_command("QVFW")
            if "VERFW:" in raw:
                return raw.split("VERFW:")[1]
            return raw
        except Exception:
            return "Unknown"

    def get_model_name(self) -> str:
        """Get Model Name (QGMN)."""
        try:
            raw = self.send_command("QGMN")
            # Raw response is usually (NNN, e.g., (001.
            # Clean it up
            code = raw.replace('(', '').strip()
            
            # Mapping from protocol documentation
            mapping = {
                "001": "VP-5000",
                "002": "VM-5000",
                "003": "VP-3000",
                "004": "VM-3000",
                "005": "MKS+-2000-48-LV-LY",
                "006": "Axpert MLV 3K-24",
                "007": "Axpert PLV 3K-24",
                "008": "Axpert MKS 3KP",
                "009": "Axpert KS 3KP",
                "010": "Axpert MKS 5KP",
                "011": "Axpert KS 5KP",
                "012": "Axpert MKS 4K/5K 64VDC",
                "013": "Axpert KS 4K/5K 64VDC",
                "014": "Axpert MKS 4K/5K",
                "015": "Axpert KS 4K/5K",
                "016": "ALFA M-5000",
                "017": "ALFA P-5000",
                "018": "Axpert Plus Duo/Tri 5KVA",
                "019": "Axpert EPS 5KW",
                "020": "Axpert EPS M-5KW",
                "021": "Axpert EPS 33-5KW",
                "022": "Axpert MKS II 5KW",
                "023": "AXPERT KING 5KW",
                "024": "AXPERT KING 3KW",
                "025": "APT MKS II 5KW (Feed-in grid)",
                "026": "Axpert MLV 5KW-48V",
                "027": "AXPERT VMIII",
                "028": "APT VMIII 3.2KW (Feed-in grid)",
                "029": "AXPERT VMII",
                "030": "Fusion VMII (Feed-in grid)",
                "031": "Phocos MKS II 5KW",
                "032": "Axpert MKS Zero LV 0.7KW",
                "033": "Axpert MKS Zero LV 1.4KW",
                "034": "Axpert MKS Zero LV 2.6KW",
                "035": "AXPERT KING 5KW (Energy)",
                "036": "AXPERT KING 3KW (Energy)",
                "037": "AXPERT VMIII (Energy)",
                "038": "Phocos MKS II 5KW (Energy)",
                "039": "Phocos MKS II 5KW LV",
                "040": "Axpert SE 3.5K",
                "041": "Axpert SE 5.5K",
                "042": "AXPERT MKS III 5KW",
                "043": "MAX 3.6K",
                "044": "MAX 7.2K",
                "045": "MAX 5K LV",
            }
            
            return mapping.get(code, code)
        except Exception:
            return "Unknown"
