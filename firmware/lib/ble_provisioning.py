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
                # No longer scanning networks in Proxy mode
                self.ble.gatts_write(self._h_networks, b"[]")

    def _handle_write(self, value):
        print(f"[BLE] Received command: {value}")
        # WiFi and Proxy commands are obsolete since the ESP32 is a persistent AP.
        # We can safely ignore "SCAN", "START_AP", and credentials here.

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
