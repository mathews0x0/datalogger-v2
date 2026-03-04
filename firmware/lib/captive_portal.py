# lib/captive_portal.py - Universal Stealth Provisioning for RS-Core
import socket
import json
import os
import gc
import time
import machine

DEVICE_CONFIG_PATH = '/data/metadata/device.json'

# --- PREMIUM RACESENSE UI ---
SETUP_HTML = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RS-Core Setup</title>
<style>
:root {{ --orange: #ff6b35; --bg: #121212; --card: #1e1e1e; --text: #e0e0e0; --border: #333; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text); display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 1.5rem; }}
.container {{ background: var(--card); width: 100%; max-width: 400px; padding: 2rem; border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
h1 {{ color: var(--orange); font-size: 1.5rem; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 1px; text-align: center; }}
.sub {{ font-size: 0.85rem; color: #888; margin-bottom: 1.5rem; text-align: center; line-height: 1.4; }}
label {{ display: block; font-size: 0.75rem; font-weight: 700; color: #aaa; text-transform: uppercase; margin-top: 1.2rem; margin-bottom: 0.4rem; }}
input {{ width: 100%; padding: 0.9rem; border: 1px solid var(--border); border-radius: 10px; background: #2a2a2a; color: #fff; font-size: 1rem; transition: border-color 0.2s; }}
input:focus {{ outline: none; border-color: var(--orange); }}
button {{ width: 100%; padding: 1rem; margin-top: 2rem; border: none; border-radius: 12px; background: var(--orange); color: #fff; font-size: 1rem; font-weight: 800; cursor: pointer; text-transform: uppercase; }}
button:active {{ transform: scale(0.98); background: #e55a2b; }}
.footer {{ font-size: 0.7rem; color: #555; text-align: center; margin-top: 1.5rem; }}
.footer a {{ color: var(--orange); text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
    <h1>🏎️ RS-Core Setup</h1>
    <p class="sub">Provisioning detected. Review and Save.</p>
    <form method="POST" action="/setup">
        <label>Hotspot Name (SSID)</label>
        <input name="ssid" value="{SSID}" required placeholder="e.g. My Phone">
        
        <label>Hotspot Password</label>
        <input name="password" type="password" value="{PASS}" placeholder="Leave blank if open">
        
        <label>Device Token</label>
        <input name="token" value="{TOKEN}" required placeholder="rsk_xxxxxxxx">
        
        <input type="hidden" name="api_url" value="{API_URL}">
        
        <button type="submit">Verify & Connect</button>
    </form>
    <div class="footer">RaceSense Datalogger V2 &bull; <a href="https://racesense.in">racesense.in</a></div>
</div>
</body>
</html>"""

SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Setup Complete</title>
<style>
body {{ font-family: sans-serif; background: #121212; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; text-align: center; margin: 0; }}
.card {{ padding: 2.5rem; background: #1e1e1e; border-radius: 20px; border: 2px solid #4caf50; max-width: 90%; }}
.icon {{ font-size: 4rem; color: #4caf50; margin-bottom: 1rem; }}
h2 {{ color: #4caf50; margin-bottom: 0.5rem; }}
p {{ color: #aaa; margin-bottom: 1.5rem; font-size: 1.1rem; }}
.countdown {{ font-size: 2.5rem; font-weight: 800; color: #ff6b35; }}
.action {{ margin-top: 2rem; background: #ff6b35; padding: 1rem; border-radius: 10px; font-weight: 700; animation: blink 1s infinite; }}
@keyframes blink {{ 0% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} 100% {{ opacity: 1; }} }}
</style>
</head>
<body>
    <div class="card">
        <div class="icon">✓</div>
        <h2>Credentials Linked!</h2>
        <p>RS-Core will reboot in:</p>
        <div class="countdown" id="cd">15</div>
        <div class="action">TURN ON YOUR HOTSPOT NOW</div>
    </div>
    <script>
        var c = 15;
        setInterval(function(){{
            c--; if(c<0) c=0;
            document.getElementById('cd').innerText = c;
        }}, 1000);
    </script>
</body>
</html>"""

def save_device_config(ssid, password, token, api_url):
    """Save device configuration to flash."""
    try:
        try: os.mkdir('/data')
        except: pass
        try: os.mkdir('/data/metadata')
        except: pass
        
        config = {'ssid': ssid, 'password': password, 'token': token, 'api_url': api_url}
        with open(DEVICE_CONFIG_PATH, 'w') as f:
            json.dump(config, f)
        return True
    except Exception as e:
        print("[Portal] Save error:", e)
        return False

def _parse_params(raw_str):
    """Parse params from query string or POST body."""
    params = {}
    if not raw_str: return params
    for pair in raw_str.split('&'):
        if '=' in pair:
            k, v = pair.split('=', 1)
            # Basic URL Decode
            v = v.replace('+', ' ').replace('%3A', ':').replace('%2F', '/').replace('%40', '@')
            v = v.replace('%3F', '?').replace('%3D', '=').replace('%26', '&').replace('%23', '#')
            params[k] = v
    return params

def _send_response(cl, code, body, content_type='text/html'):
    """Helper to send HTTP response."""
    try:
        header = f'HTTP/1.1 {code}\r\nContent-Type: {content_type}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'
        cl.send(header.encode())
        if body:
            cl.send(body.encode())
    except: pass

def start_captive_portal(led=None, ap_ip='192.168.4.1'):
    """Launch portal with Universal Stealth support and LED feedback."""
    import _thread
    
    # 1. Start DNS Hijack
    _thread.start_new_thread(_dns_server, (ap_ip,))
    
    # 2. Start HTTP Server
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(2)
    s.settimeout(0.1) # Shorter timeout for smoother LED blinking
    
    print('[Portal] Universal Magic Portal listening on port 80')
    
    while True:
        if led: led.update_onboard_led("PAIRING")
        
        try:
            cl, addr = s.accept()
        except OSError: 
            # Timeout - loop back to update LED
            continue
            
        try:
            cl.settimeout(3.0)
            req = cl.recv(1500).decode('utf-8', 'ignore')
            if not req: 
                cl.close()
                continue
            
            lines = req.split('\r\n')
            if not lines:
                cl.close()
                continue
            
            first_line = lines[0]
            parts = first_line.split(' ')
            if len(parts) < 2:
                cl.close()
                continue
                
            method = parts[0]
            path_full = parts[1]
            
            # --- STEALTH PROBE SUPPRESSION ---
            # Apple (iOS/macOS)
            if 'hotspot-detect.html' in path_full or 'success.html' in path_full:
                print('[Portal] Suppressing Apple probe')
                _send_response(cl, '200 OK', '<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>')
                cl.close()
                continue
            
            # Android
            if 'generate_204' in path_full:
                print('[Portal] Suppressing Android probe')
                _send_response(cl, '204 No Content', '')
                cl.close()
                continue
            
            # Windows
            if 'connecttest.txt' in path_full:
                print('[Portal] Suppressing Windows probe')
                _send_response(cl, '200 OK', 'Microsoft Connect Test', 'text/plain')
                cl.close()
                continue
            
            # Extract query params from path
            query_str = ""
            if '?' in path_full:
                path, query_str = path_full.split('?', 1)
            else:
                path = path_full
            
            params = _parse_params(query_str)
            
            # Handle POST data
            if method == 'POST':
                body = req.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in req else ''
                params.update(_parse_params(body))
            
            # PROVISIONING LOGIC
            ssid = params.get('ssid', '')
            pw = params.get('password', params.get('pass', ''))
            token = params.get('token', '')
            api = params.get('api_url', 'https://racesense.in/api/upload')
            
            if method == 'POST' or (ssid and token):
                # Magic Link or Form Submit: Save and Reboot
                if ssid and token:
                    save_device_config(ssid, pw, token, api)
                    _send_response(cl, '200 OK', SUCCESS_HTML)
                    cl.close()
                    print(f'[Portal] PROVISIONED! SSID: {ssid}, Token: {token[:8]}...')
                    
                    # Countdown with LED
                    start_wait = time.ticks_ms()
                    while time.ticks_diff(time.ticks_ms(), start_wait) < 15000:
                        if led: led.update_onboard_led("PAIRING") # Keep blinking
                        time.sleep(0.1)
                        
                    machine.reset()
            
            # Display current form (pre-filled with URL params if any)
            html = SETUP_HTML.format(
                SSID=ssid,
                PASS=pw,
                TOKEN=token,
                API_URL=api
            )
            _send_response(cl, '200 OK', html)
            cl.close()
            gc.collect()
            
        except Exception as e:
            try: cl.close()
            except: pass

def _dns_server(ip):
    """Simple DNS hijack: all queries -> AP IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 53))
    ip_bytes = bytes([int(x) for x in ip.split('.')])
    while True:
        try:
            data, addr = s.recvfrom(512)
            if len(data) < 12: continue
            resp = data[:2] + b'\x81\x80' + data[4:6] + data[4:6] + b'\x00\x00\x00\x00' + data[12:]
            resp += b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04' + ip_bytes
            s.sendto(resp, addr)
        except: pass
