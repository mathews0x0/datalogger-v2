# lib/wifi.py - Wireless Connection Manager (Hybrid STA/AP)
import network
import time
import secrets

def connect_or_ap():
    """
    Attempts to connect to configured WiFi.
    If fails or not found, creates an Access Point.
    Returns: (mode_string, ip_address)
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    print(f"Scanning for {secrets.SSID}...")
    found = False
    try:
        nets = wlan.scan()
        for n in nets:
            ssid = n[0].decode()
            if ssid == secrets.SSID:
                found = True
                break
    except Exception as e:
        print(f"Scan error: {e}")
        
    if found:
        print(f"Found known network. Connecting...")
        wlan.connect(secrets.SSID, secrets.PASSWORD)
        
        # Wait for connection (10 sec timeout)
        for _ in range(10):
            if wlan.isconnected():
                ip = wlan.ifconfig()[0]
                print(f"Connected! IP: {ip}")
                return "STA", ip
            time.sleep(1)
            
    # Fallback to AP Mode
    print("WiFi not found or failed. Starting AP Mode...")
    wlan.active(False) 
    
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid="Datalogger-Setup", password="password123")
    
    while not ap.active():
        time.sleep(0.5)
        
    ip = ap.ifconfig()[0]
    print(f"AP Started. SSID: Datalogger-Setup / Pass: password123")
    print(f"IP: {ip}")
    return "AP", ip
