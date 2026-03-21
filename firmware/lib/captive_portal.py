# lib/captive_portal.py - Universal Stealth Provisioning for RS-Core
import socket
import json
import os
import gc
import time
import machine

_dns_running = False  # Module-level flag for DNS thread shutdown

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
:root {{
    --primary: #ff6b35;
    --primary-dark: #e5501b;
    --secondary: #004e89;
    --background: #050505;
    --surface: rgba(26, 26, 26, 0.88);
    --glass-border: rgba(255, 255, 255, 0.08);
    --text: #ffffff;
    --text-dim: #a0a0a0;
    --success: #00d26a;
    --shadow: 0 20px 60px rgba(0, 0, 0, 0.55);
}}
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: var(--text);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background:
        radial-gradient(circle at top left, rgba(255, 107, 53, 0.18), transparent 34%),
        radial-gradient(circle at bottom right, rgba(0, 78, 137, 0.20), transparent 38%),
        var(--background);
}}
.shell {{
    width: 100%;
    max-width: 430px;
}}
.card {{
    background: var(--surface);
    border: 1px solid var(--glass-border);
    border-radius: 24px;
    box-shadow: var(--shadow);
    overflow: hidden;
}}
.topbar {{
    height: 5px;
    background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%);
}}
.content {{
    padding: 28px 24px 24px;
    text-align: center;
}}
.eyebrow {{
    display: inline-block;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--primary);
    margin-bottom: 14px;
}}
.status-icon {{
    width: 76px;
    height: 76px;
    margin: 0 auto 18px;
    border-radius: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 38px;
    font-weight: 900;
    color: var(--success);
    background: rgba(0, 210, 106, 0.12);
    border: 1px solid rgba(0, 210, 106, 0.28);
    box-shadow: inset 0 0 24px rgba(0, 210, 106, 0.08);
}}
h1 {{
    margin: 0 0 10px;
    font-size: 28px;
    line-height: 1.1;
    letter-spacing: -0.03em;
}}
.lead {{
    margin: 0 auto 22px;
    max-width: 290px;
    color: var(--text-dim);
    font-size: 15px;
    line-height: 1.55;
}}
.countdown-panel {{
    margin: 0 0 18px;
    padding: 18px;
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
}}
.countdown-label {{
    font-size: 12px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 10px;
}}
.countdown {{
    font-size: 52px;
    line-height: 1;
    font-weight: 900;
    color: var(--primary);
}}
.countdown-unit {{
    margin-top: 6px;
    font-size: 13px;
    color: var(--text-dim);
}}
.action {{
    padding: 14px 16px;
    border-radius: 16px;
    background: linear-gradient(135deg, rgba(255, 107, 53, 0.18), rgba(255, 107, 53, 0.08));
    border: 1px solid rgba(255, 107, 53, 0.28);
    font-size: 14px;
    font-weight: 800;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #ffd7ca;
    animation: pulse 1.4s ease-in-out infinite;
}}
.support {{
    margin-top: 18px;
    font-size: 12px;
    color: #7f7f7f;
}}
strong {{
    color: var(--text);
}}
@keyframes pulse {{
    0% {{ transform: scale(1); box-shadow: 0 0 0 rgba(255, 107, 53, 0); }}
    50% {{ transform: scale(0.985); box-shadow: 0 0 18px rgba(255, 107, 53, 0.12); }}
    100% {{ transform: scale(1); box-shadow: 0 0 0 rgba(255, 107, 53, 0); }}
}}
</style>
</head>
<body>
    <div class="shell">
        <div class="card">
            <div class="topbar"></div>
            <div class="content">
                <div class="eyebrow">RaceSense Provisioning</div>
                <div class="status-icon">✓</div>
                <h1>Credentials Linked</h1>
                <p class="lead">Your RS-Core has saved the network details and is about to restart into normal sync behavior.</p>
                <div class="countdown-panel">
                    <div class="countdown-label">Rebooting In</div>
                    <div class="countdown" id="cd">15</div>
                    <div class="countdown-unit">seconds</div>
                </div>
                <div class="action">Turn on your hotspot now</div>
                <div class="support">After reboot, the device will look for the saved network and continue setup automatically.</div>
            </div>
        </div>
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
    _thread.stack_size(8192)
    _thread.start_new_thread(_dns_server, (ap_ip,))
    
    # 2. Start HTTP Server
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(2)
    s.settimeout(0.1) # Shorter timeout for smoother LED blinking
    
    start_time = time.ticks_ms()
    timeout_ms = 60000 # 1 minute default
    
    print('[Portal] Universal Magic Portal listening on port 80')
    
    while True:
        # Safety Timeout: Kill portal if no connection within X minutes
        if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
            print('[Portal] Safety timeout reached. Shutting down WiFi.')
            break

        if led: led.play_pairing()
        
        try:
            cl, addr = s.accept()
            # Reset timeout if someone actually connects
            start_time = time.ticks_ms() 
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
                        if led: led.play_pairing() # Keep blinking
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
        except Exception as e:
            print(f'[Portal] Request error: {e}')
            try: cl.close()
            except: pass
    gc.collect()
    # Signal DNS thread to stop
    global _dns_running
    _dns_running = False
    time.sleep(1.5)  # Give DNS thread time to exit
    # Ensure WiFi is off on exit
    try: s.close()
    except: pass
    from lib.wifi_manager import stop_wifi
    stop_wifi()

def _dns_server(ip):
    """Simple DNS hijack: all queries -> AP IP. Exits when _dns_running is False."""
    global _dns_running
    _dns_running = True
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 53))
    s.settimeout(1.0)  # Non-blocking so we can check the shutdown flag
    ip_bytes = bytes([int(x) for x in ip.split('.')])
    while _dns_running:
        try:
            data, addr = s.recvfrom(512)
            if len(data) < 12: continue
            resp = data[:2] + b'\x81\x80' + data[4:6] + data[4:6] + b'\x00\x00\x00\x00' + data[12:]
            resp += b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04' + ip_bytes
            s.sendto(resp, addr)
        except OSError:
            pass  # Timeout — check flag and loop
        except:
            pass
    try: s.close()
    except: pass
    print('[DNS] Thread exiting cleanly')

def start_background_portal(led=None):
    """Wrapper that starts AP mode and then the portal loop."""
    from lib.wifi_manager import start_ap_mode
    start_ap_mode(led)
    start_captive_portal(led)
