# lib/wifi_manager.py - WiFi Manager with STA + Unique AP Fallback
import network
import time
import json
import ubinascii

DEVICE_CONFIG_PATH = '/data/metadata/device.json'


def _get_unique_ap_name():
    """Generate unique AP name from MAC address: RS-Core-XXXX"""
    ap = network.WLAN(network.AP_IF)
    mac = ubinascii.hexlify(ap.config('mac')).decode()
    return 'RS-Core-' + mac[-4:].upper()


def load_device_config():
    """Load saved device configuration (WiFi + token)."""
    try:
        with open(DEVICE_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}


def connect_or_ap():
    """
    Try to connect to saved WiFi. If no config or connection fails,
    fall back to AP mode with a unique SSID for captive portal setup.
    
    Returns: (mode, ip)
        mode: 'STA' or 'AP'
        ip: IP address string
    """
    config = load_device_config()
    ssid = config.get('ssid', '')
    password = config.get('password', '')
    
    if ssid:
        # Try STA mode
        print(f'[WiFi] Connecting to: {ssid}')
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        sta.connect(ssid, password)
        
        # Wait up to 15 seconds
        for i in range(30):
            if sta.isconnected():
                ip = sta.ifconfig()[0]
                print(f'[WiFi] Connected! IP: {ip}')
                # Disable AP if it was on
                ap = network.WLAN(network.AP_IF)
                ap.active(False)
                return ('STA', ip)
            time.sleep(0.5)
        
        print('[WiFi] STA connection failed, falling back to AP mode')
        sta.active(False)
    
    # AP Mode fallback
    return start_ap_mode()


def start_ap_mode():
    """Start Access Point with unique name derived from MAC."""
    # Disable STA
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    
    ap_name = _get_unique_ap_name()
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=ap_name, password='racesense', authmode=3)  # WPA2
    
    # Wait for AP to be active
    for _ in range(10):
        if ap.active():
            break
        time.sleep(0.5)
    
    ip = ap.ifconfig()[0]
    print(f'[WiFi] AP Mode: {ap_name} | IP: {ip} | Password: racesense')
    return ('AP', ip)
