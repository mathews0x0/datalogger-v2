# lib/captive_portal.py - Captive Portal for RS-Core WiFi + Token Setup
import socket
import json
import os
import gc

DEVICE_CONFIG_PATH = '/data/metadata/device.json'

SETUP_HTML = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RS-Core Setup</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,system-ui,sans-serif;background:#1a1a1a;color:#e0e0e0;padding:1.5rem}
h1{font-size:1.4rem;margin-bottom:0.5rem;color:#ff6b35}
.sub{font-size:0.8rem;color:#888;margin-bottom:1.5rem}
label{display:block;font-size:0.85rem;font-weight:600;margin-bottom:0.25rem;margin-top:1rem}
input{width:100%;padding:0.7rem;border:1px solid #333;border-radius:6px;background:#2a2a2a;color:#e0e0e0;font-size:0.95rem}
input:focus{outline:none;border-color:#ff6b35}
button{width:100%;padding:0.8rem;margin-top:1.5rem;border:none;border-radius:8px;background:#ff6b35;color:#fff;font-size:1rem;font-weight:700;cursor:pointer}
button:active{background:#e55a2b}
.info{font-size:0.75rem;color:#666;margin-top:0.5rem}
.status{text-align:center;margin-top:1rem;font-size:0.9rem}
</style>
</head>
<body>
<h1>&#9881; RS-Core Setup</h1>
<p class="sub">Connect your datalogger to WiFi and link your Racesense account.</p>
<form method="POST" action="/setup">
<label>WiFi Network Name (SSID)</label>
<input name="ssid" required placeholder="Your WiFi or Hotspot name">
<label>WiFi Password</label>
<input name="password" type="password" placeholder="Network password">
<label>Upload URL</label>
<input name="api_url" value="https://racesense.com/api/upload" placeholder="https://racesense.com/api/upload">
<p class="info">Change only if using a custom server.</p>
<label>Device Token</label>
<input name="token" required placeholder="rsk_xxxxxxxx (from your dashboard)">
<p class="info">Generate this token at racesense.com &rarr; Settings &rarr; My Devices.</p>
<button type="submit">Save &amp; Connect</button>
</form>
<div class="status" id="st"></div>
</body>
</html>"""

SUCCESS_HTML = """<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RS-Core Setup Complete</title>
<style>
body{font-family:sans-serif;background:#1a1a1a;color:#e0e0e0;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center}
.ok{font-size:3rem;margin-bottom:1rem}
h2{color:#4caf50}
p{color:#888;margin-top:0.5rem}
</style></head>
<body><div><div class="ok">&#10003;</div><h2>Setup Complete!</h2><p>RS-Core is rebooting and connecting to your network...</p></div></body></html>"""


def load_device_config():
    """Load saved device configuration."""
    try:
        with open(DEVICE_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}


def save_device_config(ssid, password, token, api_url):
    """Save device configuration to flash."""
    try:
        os.makedirs('/data/metadata', exist_ok=True)
    except:
        try:
            os.mkdir('/data')
            os.mkdir('/data/metadata')
        except:
            pass
    
    config = {
        'ssid': ssid,
        'password': password,
        'token': token,
        'api_url': api_url
    }
    with open(DEVICE_CONFIG_PATH, 'w') as f:
        json.dump(config, f)
    return True


def _parse_form(body):
    """Parse URL-encoded form data."""
    params = {}
    for pair in body.split('&'):
        if '=' in pair:
            key, val = pair.split('=', 1)
            # URL decode
            val = val.replace('+', ' ').replace('%40', '@').replace('%3A', ':')
            val = val.replace('%2F', '/').replace('%3F', '?').replace('%26', '&')
            val = val.replace('%3D', '=').replace('%25', '%').replace('%23', '#')
            params[key] = val
    return params


def start_captive_portal(ap_ip='192.168.4.1'):
    """Run the captive portal HTTP + DNS server. Blocks until setup is complete."""
    import _thread
    
    # Start DNS hijack in background
    _thread.start_new_thread(_dns_server, (ap_ip,))
    
    # Start HTTP server
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(3)
    s.settimeout(None)
    
    print('[Portal] Captive portal running on port 80')
    
    while True:
        try:
            cl, addr = s.accept()
            cl.settimeout(5.0)
            req = cl.recv(2048).decode('utf-8', 'ignore')
            
            if not req:
                cl.close()
                continue
            
            first_line = req.split('\r\n')[0]
            parts = first_line.split(' ')
            method = parts[0] if len(parts) > 0 else ''
            path = parts[1] if len(parts) > 1 else '/'
            
            if method == 'POST' and path == '/setup':
                # Extract body
                body = ''
                if '\r\n\r\n' in req:
                    body = req.split('\r\n\r\n', 1)[1]
                
                params = _parse_form(body)
                ssid = params.get('ssid', '')
                password = params.get('password', '')
                token = params.get('token', '')
                api_url = params.get('api_url', 'https://racesense.com/api/upload')
                
                if ssid and token:
                    save_device_config(ssid, password, token, api_url)
                    _send_html(cl, SUCCESS_HTML)
                    cl.close()
                    gc.collect()
                    
                    print(f'[Portal] Config saved: SSID={ssid}, Token={token[:8]}...')
                    
                    # Reboot after a short delay
                    import time
                    import machine
                    time.sleep(2)
                    machine.reset()
                else:
                    _send_html(cl, SETUP_HTML)
            else:
                # All other requests get the setup page (captive portal behavior)
                _send_html(cl, SETUP_HTML)
            
            cl.close()
            gc.collect()
        except Exception as e:
            print('[Portal] Error:', e)
            try:
                cl.close()
            except:
                pass


def _send_html(cl, html):
    """Send an HTML response."""
    header = 'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\nConnection: close\r\n\r\n' % len(html)
    cl.send(header.encode())
    cl.send(html.encode())


def _dns_server(ip):
    """DNS hijack: respond to all queries with the AP IP."""
    import struct
    
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 53))
    
    # Pre-build IP response bytes
    ip_parts = [int(x) for x in ip.split('.')]
    ip_bytes = bytes(ip_parts)
    
    print('[DNS] DNS hijack server running')
    
    while True:
        try:
            data, addr = s.recvfrom(512)
            if len(data) < 12:
                continue
            
            # Build DNS response
            # Copy transaction ID, set flags to standard response
            resp = data[:2]  # Transaction ID
            resp += b'\x81\x80'  # Flags: standard response, no error
            resp += data[4:6]   # Questions count
            resp += data[4:6]   # Answers count (same as questions)
            resp += b'\x00\x00\x00\x00'  # Authority + Additional
            resp += data[12:]   # Copy original question
            
            # Add answer: pointer to question name + A record
            resp += b'\xc0\x0c'  # Name pointer to offset 12
            resp += b'\x00\x01'  # Type A
            resp += b'\x00\x01'  # Class IN
            resp += b'\x00\x00\x00\x3c'  # TTL 60s
            resp += b'\x00\x04'  # Data length 4
            resp += ip_bytes     # IP address
            
            s.sendto(resp, addr)
        except:
            pass
