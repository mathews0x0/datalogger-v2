# lib/wifi_manager.py - Local Access Point Manager
import network
import time

def start_ap_mode():
    """Start Access Point for Phone Proxy"""
    # Disable STA mode
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    
    # Enable AP mode
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid="Racesense-Pit", password="password123", authmode=3)  # WPA2
    
    # Wait for AP to be active
    for _ in range(10):
        if ap.active():
            break
        time.sleep(0.5)
    
    ip = ap.ifconfig()[0]
    print(f"AP Mode Active!")
    print(f"  SSID: Racesense-Pit")
    print(f"  Password: password123")
    print(f"  IP: {ip}")
    
    return "AP", ip

def connect_or_ap():
    """Always return AP mode for Phone Proxy architecture"""
    return start_ap_mode()
