import bluetooth
import network
import json
import ubinascii
import struct
import time
from micropython import const

# BLE IRQ constants
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_GATTS_READ_REQUEST = const(4)

# Custom UUIDs
SERVICE_UUID = bluetooth.UUID("12345678-1234-5678-1234-567812345678")
# Raw bytes version for advertising (Little Endian)
_SERVICE_UUID_ADV = ubinascii.unhexlify("78563412341278563412785634127856")

CHAR_NETWORKS_UUID = bluetooth.UUID("12345678-1234-5678-1234-567812345001")
CHAR_STATUS_UUID = bluetooth.UUID("12345678-1234-5678-1234-567812345002")
CHAR_CONFIGURE_UUID = bluetooth.UUID("12345678-1234-5678-1234-567812345003")
CHAR_DEVICE_INFO_UUID = bluetooth.UUID("12345678-1234-5678-1234-567812345004")

class BLEProvisioning:
    def __init__(self, wifi_manager=None, session_manager=None):
        self.wifi_mgr = wifi_manager
        self.sm = session_manager
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq_handler)
        
        self._connections = set()
        self._wlan = network.WLAN(network.STA_IF)
        
        # Register services
        self._register_services()
        
        # Get MAC address for advertising name
        mac = ubinascii.hexlify(network.WLAN().config('mac'), ':').decode().replace(':', '')
        self._device_name = "Racesense-Core" # Friendly Name for Paddock visibility
        
        # Initial values
        self._networks_json = b"[]"
        self._status_json = b'{"connected": false, "ssid": "", "ip": "0.0.0.0", "mode": "STA"}'
        self._device_info_json = b'{"version": "1.1.0", "storage_pct": 0.0, "gps_status": "NO_FIX"}'
        
        # Initial state update
        self._update_all_chars()

    def _register_services(self):
        service = (
            SERVICE_UUID,
            (
                (CHAR_NETWORKS_UUID, bluetooth.FLAG_READ),
                (CHAR_STATUS_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY),
                (CHAR_CONFIGURE_UUID, bluetooth.FLAG_WRITE),
                (CHAR_DEVICE_INFO_UUID, bluetooth.FLAG_READ),
            ),
        )
        ((self._h_networks, self._h_status, self._h_configure, self._h_device_info),) = self.ble.gatts_register_services((service,))

    def _update_all_chars(self):
        self.ble.gatts_write(self._h_networks, self._networks_json)
        self.ble.gatts_write(self._h_status, self._status_json)
        self.ble.gatts_write(self._h_device_info, self._device_info_json)

    def _get_adv_data(self):
        # Flags: General Discoverable Mode, BR/EDR Not Supported
        payload = bytearray(b'\x02\x01\x06')
        
        # Service UUID (128-bit Complete List) - CRITICAL for macOS/iOS visibility
        payload += struct.pack('B', len(_SERVICE_UUID_ADV) + 1) + b'\x07' + _SERVICE_UUID_ADV
        
        # Name (Short Local Name to save space in 31-byte packet)
        name = self._device_name.encode()
        payload += struct.pack('B', len(name) + 1) + b'\x08' + name
        return payload

    def _get_resp_data(self):
        # Complete Name in response data
        name = self._device_name.encode()
        payload = struct.pack('B', len(name) + 1) + b'\x09' + name
        return payload

    def start(self):
        try:
            self.stop() # Ensure previous advertising is stopped
            adv = self._get_adv_data()
            resp = self._get_resp_data()
            self.ble.gap_advertise(100000, adv_data=adv, resp_data=resp)
            print(f"[BLE] Advertising as {self._device_name}")
        except Exception as e:
            print(f"[BLE] Start failed: {e}")

    def stop(self):
        try:
            self.ble.gap_advertise(None)
            print("[BLE] Advertising stopped")
        except:
            pass

    def is_connected(self) -> bool:
        return len(self._connections) > 0

    def _irq_handler(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            self._connections.add(conn_handle)
            print(f"[BLE] Cental connected: {conn_handle}")
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            self._connections.discard(conn_handle)
            print(f"[BLE] Cental disconnected: {conn_handle}")
            self.start() # Resume advertising
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            if attr_handle == self._h_configure:
                value = self.ble.gatts_read(self._h_configure)
                self._handle_write(value.decode())
        elif event == _IRQ_GATTS_READ_REQUEST:
            conn_handle, attr_handle = data
            if attr_handle == self._h_networks:
                # Refresh networks on read request
                self._scan_networks()

    def _scan_networks(self):
        print("[BLE] Scanning for WiFi networks...")
        self._wlan.active(True)
        try:
            # Synchronous scan for simplicity in provisioning
            nets = self._wlan.scan()
            # Sort by RSSI
            nets = sorted(nets, key=lambda x: x[3], reverse=True)
            # Take top 10 unique SSIDs
            ssids = []
            for n in nets:
                ssid = n[0].decode().strip()
                if ssid and ssid not in ssids:
                    ssids.append(ssid)
                if len(ssids) >= 10:
                    break
            self._networks_json = json.dumps(ssids).encode()
            self.ble.gatts_write(self._h_networks, self._networks_json)
            print(f"[BLE] Found {len(ssids)} networks")
        except Exception as e:
            print(f"[BLE] Scan error: {e}")

    def _handle_write(self, value):
        print(f"[BLE] Received command: {value}")
        try:
            if value == "SCAN":
                self._scan_networks()
            elif value == "START_AP":
                self.notify_wifi_status(False, "Setup", "192.168.4.1", "AP")
                self._wlan.active(False)
                import network
                ap = network.WLAN(network.AP_IF)
                ap.active(True)
                ap.config(essid="Racesense-Pit", password="password123", authmode=3)
            elif value == "SYNC":
                # Manual trigger if WiFi is already connected
                if self._wlan.isconnected():
                    import _thread
                    import lib.uploader as uploader
                    _thread.start_new_thread(uploader.upload_all, (self.sm,))
            else:
                # Try parsing as JSON: {ssid, password, api_url}
                try:
                    data = json.loads(value)
                    ssid = data.get("ssid")
                    password = data.get("password")
                    api_url = data.get("api_url")
                    if ssid:
                        print(f"[BLE] Provisioning WiFi: {ssid}")
                        import _thread
                        _thread.start_new_thread(self._connect_to_wifi, (ssid, password, api_url))
                except:
                    print(f"[BLE] Unknown command or invalid JSON: {value}")
        except Exception as e:
            print(f"[BLE] Command error: {e}")

    def _connect_to_wifi(self, ssid, password, api_url=None):
        print(f"[BLE] Attempting WiFi connection to {ssid}...")
        self._wlan.active(True)
        self._wlan.connect(ssid, password)
        
        # Poll for 20s
        for i in range(20):
            if self._wlan.isconnected():
                ip = self._wlan.ifconfig()[0]
                print(f"[BLE] WiFi connected to {ssid}, IP: {ip}")
                
                # Store credentials for next boot
                if self.wifi_mgr:
                    try:
                        self.wifi_mgr.add_credential(ssid, password)
                        print(f"[BLE] Saved credentials for {ssid}")
                    except Exception as e:
                        print(f"[BLE] Failed to save credentials: {e}")
                
                self.notify_wifi_status(True, ssid, ip, "STA")
                
                # If we have an api_url, trigger an automatic upload
                if api_url:
                    import lib.uploader as uploader
                    uploader.upload_all(self.sm, api_url=api_url, ble=self)
                return
            time.sleep(1)
            
        print(f"[BLE] WiFi connection timeout to {ssid}")
        self.notify_wifi_status(False, ssid, "0.0.0.0", "STA")
        
        # If connection fails, we don't automatically fall back to AP here 
        # to avoid disconnecting the user's BLE session abruptly if they want to retry.
        # The user can manually trigger "START_AP" from the UI if needed.

    def update_device_info(self, gps_valid: bool, storage_pct: float):
        try:
            info = {
                "version": "1.1.0",
                "storage_pct": round(storage_pct, 1),
                "gps_status": "FIX" if gps_valid else "NO_FIX"
            }
            self._device_info_json = json.dumps(info).encode()
            self.ble.gatts_write(self._h_device_info, self._device_info_json)
        except:
            pass

    def notify_sync_progress(self, progress: int, filename: str):
        # Update the status JSON with progress
        status = json.loads(self._status_json.decode())
        status['sync_progress'] = progress
        status['sync_file'] = filename
        
        self._status_json = json.dumps(status).encode()
        self.ble.gatts_write(self._h_status, self._status_json)
        
        # Notify all connected centrals
        for conn_handle in self._connections:
            try:
                self.ble.gatts_notify(conn_handle, self._h_status)
            except:
                pass

    def notify_wifi_status(self, connected: bool, ssid: str, ip: str, mode: str, progress=None):
        status = {
            "connected": connected,
            "ssid": ssid,
            "ip": ip,
            "mode": mode
        }
        if progress is not None:
            status['sync_progress'] = progress
            
        self._status_json = json.dumps(status).encode()
        self.ble.gatts_write(self._h_status, self._status_json)
        # Notify all connected centrals
        for conn_handle in self._connections:
            try:
                self.ble.gatts_notify(conn_handle, self._h_status)
            except:
                pass
