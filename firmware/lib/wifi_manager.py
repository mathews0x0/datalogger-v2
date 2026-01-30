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
    # Set hostname for easier discovery
    try:
        wlan.config(dhcp_hostname="datalogger")
    except:
        pass
    
    # Load stored credentials
    credentials = load_credentials()
    
    if not credentials:
        print("No WiFi credentials stored. Starting AP mode...")
        return start_ap_mode()
    
    print(f"Loaded {len(credentials)} stored network(s)")
    
    # Scan available networks
    print("Scanning for networks...")
    try:
        available_networks = wlan.scan()
        available_ssids = [n[0].decode() for n in available_networks]
        print(f"Found networks: {available_ssids}")
    except Exception as e:
        print(f"Scan error: {e}")
        return start_ap_mode()
    
    # Try to connect to any known network
    for cred in credentials:
        ssid = cred.get('ssid', '')
        password = cred.get('password', '')
        
        if ssid in available_ssids:
            print(f"Found known network: {ssid}. Connecting...")
            
            try:
                wlan.connect(ssid, password)
                
                # Wait for connection (10 sec timeout)
                for i in range(10):
                    if wlan.isconnected():
                        ip = wlan.ifconfig()[0]
                        print(f"Connected to {ssid}! IP: {ip}")
                        return "STA", ip
                    time.sleep(1)
                    print(f"Waiting... ({i+1}/10)")
                
                print(f"Failed to connect to {ssid}")
                wlan.disconnect()
            except Exception as e:
                print(f"Connection error: {e}")
    
    # No known network worked
    print("No known networks available. Starting AP mode...")
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
