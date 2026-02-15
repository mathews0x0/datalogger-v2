# lib/wifi_manager.py - Multi-Network WiFi Manager
import network
import time
import json
import os

CREDENTIALS_FILE = '/data/metadata/wifi.json'

def load_credentials():
    """Load all stored WiFi credentials"""
    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_credentials(credentials):
    """Save WiFi credentials list to file"""
    try:
        # Ensure directory exists
        parts = CREDENTIALS_FILE.split('/')
        path = ""
        for i in range(1, len(parts)-1):
            path += "/" + parts[i]
            try:
                os.mkdir(path)
            except:
                pass
                
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(credentials, f)
        return True
    except Exception as e:
        print(f"Error saving credentials: {e}")
        return False

def add_credential(ssid, password):
    """Add or update a WiFi credential"""
    credentials = load_credentials()
    
    # Check if SSID already exists, update password
    for cred in credentials:
        if cred.get('ssid') == ssid:
            cred['password'] = password
            save_credentials(credentials)
            return True
    
    # Add new credential
    credentials.append({'ssid': ssid, 'password': password})
    return save_credentials(credentials)

def remove_credential(ssid):
    """Remove a WiFi credential by SSID"""
    credentials = load_credentials()
    credentials = [c for c in credentials if c.get('ssid') != ssid]
    return save_credentials(credentials)

def connect_or_ap():
    """
    Scans for available networks and tries to connect using stored credentials.
    Falls back to AP mode if no known network is found.
    Returns: (mode_string, ip_address)
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Disable power saving for better stability
    try:
        wlan.config(pm=0xa11140) # Disable power management
    except:
        pass

    # Set hostname for easier discovery
    try:
        wlan.config(dhcp_hostname="datalogger")
    except:
        pass
    
    # Load stored credentials
    credentials = load_credentials()
    
    if not credentials:
        print("[WiFi] No credentials stored. Starting AP mode...")
        return start_ap_mode()
    
    print(f"[WiFi] Loaded {len(credentials)} stored network(s)")
    
    # Scan available networks (Retry up to 3 times)
    available_ssids = []
    for attempt in range(3):
        print(f"[WiFi] Scanning for networks (attempt {attempt+1})...")
        try:
            available_networks = wlan.scan()
            available_ssids = [n[0].decode() for n in available_networks]
            if available_ssids:
                break
        except Exception as e:
            print(f"[WiFi] Scan error: {e}")
            time.sleep(1)
            
    print(f"[WiFi] Found networks: {available_ssids}")
    
    # Try to connect to any known network, prioritized by what's visible
    matched_creds = [c for c in credentials if c.get('ssid') in available_ssids]
    
    # If no match in scan, try all stored ones anyway (sometimes hidden or missed)
    if not matched_creds:
        matched_creds = credentials

    for cred in matched_creds:
        ssid = cred.get('ssid', '')
        password = cred.get('password', '')
        
        print(f"[WiFi] Attempting to connect to: {ssid}")
        
        try:
            wlan.disconnect()
            time.sleep_ms(200)
            wlan.connect(ssid, password)
            
            # Wait for connection (20 sec timeout for slow routers)
            for i in range(20):
                if wlan.isconnected():
                    ip = wlan.ifconfig()[0]
                    print(f"[WiFi] Connected to {ssid}! IP: {ip}")
                    return "STA", ip
                time.sleep(1)
                if i % 5 == 4:
                    print(f"[WiFi] Still connecting to {ssid}... ({i+1}/20)")
            
            print(f"[WiFi] Failed to connect to {ssid}")
            wlan.disconnect()
        except Exception as e:
            print(f"[WiFi] Connection error: {e}")
    
    # No known network worked
    print("[WiFi] All connection attempts failed. Falling back to AP mode...")
    return start_ap_mode()

def start_ap_mode():
    """Start Access Point for configuration"""
    # Disable STA mode
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    
    # Enable AP mode
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid="Datalogger-Setup", password="password123", authmode=3)  # WPA2
    
    # Wait for AP to be active
    for _ in range(10):
        if ap.active():
            break
        time.sleep(0.5)
    
    ip = ap.ifconfig()[0]
    print(f"AP Mode Active!")
    print(f"  SSID: Datalogger-Setup")
    print(f"  Password: password123")
    print(f"  IP: {ip}")
    
    return "AP", ip
