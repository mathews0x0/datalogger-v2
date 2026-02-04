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
        self._device_name = "Datalogger-" + mac[-4:].upper()
        
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
        
        # Name (Complete Local Name)
        name = self._device_name.encode()
        payload += struct.pack('B', len(name) + 1) + b'\x09' + name
        return payload

    def _get_resp_data(self):
        # Service UUID (128-bit Complete List)
        payload = struct.pack('B', len(_SERVICE_UUID_ADV) + 1) + b'\x07' + _SERVICE_UUID_ADV
        return payload

    def start(self):
        try:
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
                # This usually requires reboot or manual trigger in main
                # We notify via status that we are moving to AP
                self.notify_wifi_status(False, "Setup", "192.168.4.1", "AP")
                # Triggering AP mode via wlan
                self._wlan.active(False)
                ap = network.WLAN(network.AP_IF)
                ap.active(True)
                # Note: wifi_manager usually handles specifics, this is generic fallback
            else:
                # Try parsing as JSON: {ssid, password}
                data = json.loads(value)
                ssid = data.get("ssid")
                password = data.get("password")
                if ssid:
                    print(f"[BLE] Configuring WiFi: {ssid}")
                    if self.wifi_mgr:
                        # Save to credentials file
                        self.wifi_mgr.add_credential(ssid, password)
                        # Attempt connection non-blocking for the IRQ handler 
                        # (though IRQs in MicroPython can be messy with networking)
                        # We'll do a quick blocking attempt here but ideally this is handled in main loop
                        self._connect_to_wifi(ssid, password)
        except Exception as e:
            print(f"[BLE] Command error: {e}")

    def _connect_to_wifi(self, ssid, password):
        self._wlan.active(True)
        self._wlan.connect(ssid, password)
        # Quick poll for 10s
        for _ in range(10):
            if self._wlan.isconnected():
                ip = self._wlan.ifconfig()[0]
                print(f"[BLE] WiFi connected to {ssid}, IP: {ip}")
                self.notify_wifi_status(True, ssid, ip, "STA")
                return
            time.sleep(1)
        self.notify_wifi_status(False, ssid, "0.0.0.0", "STA")
        print(f"[BLE] WiFi connection timeout to {ssid}")

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

    def notify_wifi_status(self, connected: bool, ssid: str, ip: str, mode: str):
        status = {
            "connected": connected,
            "ssid": ssid,
            "ip": ip,
            "mode": mode
        }
        self._status_json = json.dumps(status).encode()
        self.ble.gatts_write(self._h_status, self._status_json)
        # Notify all connected centrals
        for conn_handle in self._connections:
            self.ble.gatts_notify(conn_handle, self._h_status)
