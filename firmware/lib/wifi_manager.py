# lib/wifi_manager.py - WiFi Manager with STA + Unique AP Fallback
import network
import time
import json
import ubinascii
import ntptime

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


def connect_or_ap(led=None):
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
        if led: led.update_onboard_led("CONNECTING")
        
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        sta.connect(ssid, password)
        
        # Wait up to 30 seconds (300 * 0.1s)
        for i in range(300):
            if led: led.update_onboard_led("CONNECTING") # Keep blinking
            if sta.isconnected():
                ip = sta.ifconfig()[0]
                print(f'[WiFi] Connected! IP: {ip}')
                if led: led.update_onboard_led("CONNECTED")
                
                # Sync time for HTTPS certificates
                try:
                    print('[WiFi] Syncing time via NTP...')
                    ntptime.settime()
                    print(f'[WiFi] Time synced: {time.gmtime()}')
                except Exception as e:
                    print(f'[WiFi] NTP Sync failed: {e}')

                # Disable AP if it was on
                ap = network.WLAN(network.AP_IF)
                ap.active(False)
                return ('STA', ip)
            time.sleep(0.1)
        
        print('[WiFi] STA connection failed, falling back to AP mode')
        sta.active(False)
    
    # AP Mode fallback
    if led: led.update_onboard_led("PAIRING")
    return start_ap_mode(led)


def start_ap_mode(led=None):
    """Start Access Point with unique name derived from MAC."""
    # Reset radio for clean state
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.active(False)
    time.sleep(0.1)
    
    ap_name = _get_unique_ap_name()
    ap.active(True)
    
    # Explicit config for better visibility/compatibility
    # authmode 3 is WPA2-PSK
    ap.config(essid=ap_name, password='racesense', authmode=3)
    
    # Wait for AP to be active with high-freq LED updates
    print(f'[WiFi] Starting AP: {ap_name}...')
    for _ in range(50): # 5 seconds
        if led: led.update_onboard_led("PAIRING")
        if ap.active():
            break
        time.sleep(0.1)
    
    ip = ap.ifconfig()[0]
    print(f'[WiFi] AP Mode Active: {ap_name} | IP: {ip}')
    return ('AP', ip)
