# lib/miniserver.py - Minimal HTTP Server for ESP32
import socket
import os
import json
import gc

class MiniServer:
    VERSION = "1.1.0"

    def __init__(self, session_mgr, led=None, gps_state=None, track_engine=None):
        self.sm = session_mgr
        self.led = led
        self.gps_state = gps_state
        self.track_engine = track_engine  # TrackEngine instance
        self.sock = None
        self.running = False
        
    def start(self, port=80):
        import time
        addr = socket.getaddrinfo('0.0.0.0', port)[0][-1]
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Retry bind
        for i in range(3):
            try:
                self.sock.bind(addr)
                break
            except OSError as e:
                print(f"Bind Error {e}, retrying...")
                time.sleep(1)
        
        self.sock.listen(5)
        self.sock.settimeout(0.01) # Reduced from 0.1 for faster loop
        self.running = True
        print("Server listening on port " + str(port))
        
        while self.running:
            self.poll()
            time.sleep(0.01)

    def poll(self):
        if not self.running:
            return
        
        try:
            cl, addr = self.sock.accept()
        except OSError:
            return
        
        try:
            cl.settimeout(5.0)
            if self.led:
                self.led.value(not self.led.value())
            
            request = cl.recv(1024)
            if not request:
                cl.close()
                return
            
            req_str = request.decode('utf-8', 'ignore')
            first_line = req_str.split('\r\n')[0]
            parts = first_line.split(' ')
            
            if len(parts) < 2:
                self.send_response(cl, 400, '{"error": "Bad Request"}')
                cl.close()
                return
            
            method = parts[0]
            path = parts[1]
            
            if method == 'OPTIONS':
                self.send_cors_preflight(cl)
            elif method == 'GET':
                self.handle_get(cl, path)
            elif method == 'POST':
                # Read full body for POST (OTA files can be large)
                body = ""
                if '\r\n\r\n' in req_str:
                    body = req_str.split('\r\n\r\n', 1)[1]
                
                # Check for Content-Length to ensure we got everything
                cl_header = "Content-Length: "
                idx = req_str.find(cl_header)
                if idx == -1:
                    idx = req_str.lower().find(cl_header.lower())
                
                if idx != -1:
                    try:
                        end_idx = req_str.find('\r\n', idx)
                        length = int(req_str[idx + len(cl_header):end_idx].strip())
                        while len(body.encode()) < length:
                            chunk = cl.recv(1024)
                            if not chunk: break
                            body += chunk.decode('utf-8', 'ignore')
                    except Exception as e:
                        print("Body read error:", e)

                self.handle_post(cl, path, body)
            else:
                self.send_response(cl, 405, '{"error": "Method Not Allowed"}')
            
            cl.close()
            gc.collect()
            
        except Exception as e:
            print("Server Error: " + str(e))
            try:
                cl.close()
            except:
                pass

    def handle_get(self, cl, path):
        if path == '/status':
            self.handle_status(cl)
        elif path == '/wifi/list':
            self.handle_wifi_list(cl)
        elif path == '/list':
            self.handle_session_list(cl)
        elif path.startswith('/download/'):
            fname = path.split('/download/', 1)[1]
            self.handle_download(cl, fname)
        elif path.startswith('/delete/'):
            fname = path.split('/delete/', 1)[1]
            self.handle_delete(cl, fname)
        elif path == '/track/status':
            self.handle_track_status(cl)
        elif path == '/':
            self.send_response(cl, 200, '{"message": "Datalogger ESP32 API"}')
        else:
            self.send_response(cl, 404, '{"error": "Not Found"}')

    def handle_post(self, cl, path, body):
        if path == '/wifi/add':
            self.handle_wifi_add(cl, body)
        elif path == '/wifi/remove':
            self.handle_wifi_remove(cl, body)
        elif path == '/track/set':
            self.handle_track_set(cl, body)
        elif path == '/update':
            self.handle_update(cl, body)
        elif path == '/reboot':
            self.handle_reboot(cl)
        else:
            self.send_response(cl, 404, '{"error": "Not Found"}')

    def send_cors_preflight(self, cl):
        h = "HTTP/1.1 200 OK\r\n"
        h += "Access-Control-Allow-Origin: *\r\n"
        h += "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
        h += "Access-Control-Allow-Headers: Content-Type\r\n"
        h += "Access-Control-Max-Age: 86400\r\n"
        h += "Content-Length: 0\r\n"
        h += "\r\n"
        cl.send(h.encode())

    def send_response(self, cl, code, content, ctype="application/json"):
        status_map = {200: 'OK', 400: 'Bad Request', 404: 'Not Found', 500: 'Error'}
        status = status_map.get(code, 'OK')
        
        h = "HTTP/1.1 " + str(code) + " " + status + "\r\n"
        h += "Content-Type: " + ctype + "\r\n"
        h += "Content-Length: " + str(len(content)) + "\r\n"
        h += "Access-Control-Allow-Origin: *\r\n"
        h += "Connection: close\r\n"
        h += "\r\n"
        
        cl.send(h.encode())
        cl.send(content.encode())

    def handle_status(self, cl):
        from lib import wifi_manager
        creds = wifi_manager.load_credentials()
        
        # Get storage info
        try:
            stat = os.statvfs('/')
            block_size = stat[0]
            total_blocks = stat[2]
            free_blocks = stat[3]
            
            total_kb = (total_blocks * block_size) // 1024
            free_kb = (free_blocks * block_size) // 1024
            used_kb = total_kb - free_kb
            used_pct = int((used_kb * 100) / total_kb) if total_kb > 0 else 0
        except:
            total_kb = 0
            used_kb = 0
            free_kb = 0
            used_pct = 0
        
        status = {
            "version": self.VERSION,
            "storage": "FLASH",
            "status": "running",
            "wifi_mode": "AP" if not creds else "STA",
            "networks_stored": len(creds),
            "storage_total_kb": total_kb,
            "storage_used_kb": used_kb,
            "storage_free_kb": free_kb,
            "storage_used_pct": used_pct,
            "active_track": self.track_engine.track.get('id') if self.track_engine and self.track_engine.track else None,
            "track_identified": self.track_engine.track_identified if self.track_engine else False
        }

        # Add GPS info if available
        if self.gps_state:
            # Support both dict and object
            if isinstance(self.gps_state, dict):
                gps = self.gps_state.get('gps')
                if gps:
                    status["gps_lat"] = gps.last_fix.get('lat')
                    status["gps_lon"] = gps.last_fix.get('lon')
            elif hasattr(self.gps_state, 'last_fix'):
                status["gps_lat"] = self.gps_state.last_fix.get('lat')
                status["gps_lon"] = self.gps_state.last_fix.get('lon')

        self.send_response(cl, 200, json.dumps(status))

    def handle_wifi_list(self, cl):
        from lib import wifi_manager
        creds = wifi_manager.load_credentials()
        ssids = [c.get('ssid', '') for c in creds]
        self.send_response(cl, 200, json.dumps({"networks": ssids}))

    def handle_wifi_add(self, cl, body):
        try:
            if not body:
                self.send_response(cl, 400, '{"error": "No body"}')
                return
            
            data = json.loads(body)
            ssid = data.get('ssid', '')
            password = data.get('password', '')
            
            if not ssid:
                self.send_response(cl, 400, '{"error": "SSID required"}')
                return
            
            from lib import wifi_manager
            if wifi_manager.add_credential(ssid, password):
                resp = {"success": True, "message": "Added " + ssid}
                self.send_response(cl, 200, json.dumps(resp))
                
                import machine
                import time
                time.sleep(1)
                machine.reset()
            else:
                self.send_response(cl, 500, '{"error": "Failed to save"}')
                
        except Exception as e:
            self.send_response(cl, 500, '{"error": "' + str(e) + '"}')

    def handle_wifi_remove(self, cl, body):
        try:
            if not body:
                self.send_response(cl, 400, '{"error": "No body"}')
                return
            
            data = json.loads(body)
            ssid = data.get('ssid', '')
            
            if not ssid:
                self.send_response(cl, 400, '{"error": "SSID required"}')
                return
            
            from lib import wifi_manager
            if wifi_manager.remove_credential(ssid):
                self.send_response(cl, 200, '{"success": true}')
            else:
                self.send_response(cl, 500, '{"error": "Failed"}')
                
        except Exception as e:
            self.send_response(cl, 500, '{"error": "' + str(e) + '"}')

    def handle_session_list(self, cl):
        try:
            # Stop logging when sync process starts (requested by user)
            if self.gps_state and isinstance(self.gps_state, dict):
                self.gps_state['logging_active'] = False
                print("[Server] Sync requested: Stopping Logging Thread")
            
            files = self.sm.list_sessions()
            self.send_response(cl, 200, json.dumps({"files": files}))
        except Exception as e:
            self.send_response(cl, 500, '{"error": "' + str(e) + '"}')

    def handle_download(self, cl, filename):
        filepath = self.sm.active_dir + "/" + filename
        
        try:
            size = os.stat(filepath)[6]
            h = "HTTP/1.1 200 OK\r\n"
            h += "Content-Type: text/csv\r\n"
            h += "Content-Length: " + str(size) + "\r\n"
            h += "Access-Control-Allow-Origin: *\r\n"
            h += "Connection: close\r\n"
            h += "\r\n"
            cl.send(h.encode())
            
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(512)
                    if not chunk:
                        break
                    cl.send(chunk)
        except OSError:
            self.send_response(cl, 404, '{"error": "File not found"}')

    def handle_delete(self, cl, filename):
        if self.sm.delete_session(filename):
            self.send_response(cl, 200, '{"success": true}')
        else:
            self.send_response(cl, 500, '{"error": "Delete failed"}')

    def handle_update(self, cl, body):
        try:
            data = json.loads(body)
            filename = data.get('filename')
            content = data.get('content')
            
            if not filename or content is None:
                self.send_response(cl, 400, '{"error": "Missing filename or content"}')
                return
            
            # Simple path safety
            if '..' in filename or filename.startswith('/'):
                if not filename.startswith('/lib/') and not filename.startswith('/drivers/') and filename not in ['boot.py', 'main.py']:
                     self.send_response(cl, 400, '{"error": "Invalid filename path"}')
                     return
            
            # Write file (use 'w' for text contents)
            with open(filename, 'w') as f:
                f.write(content)
                
            print(f"OTA Updated: {filename}")
            self.send_response(cl, 200, '{"success": true, "filename": filename}')
        except Exception as e:
            self.send_response(cl, 500, json.dumps({"error": str(e)}))

    def handle_reboot(self, cl):
        self.send_response(cl, 200, '{"message": "Rebooting..."}')
        import time
        import machine
        time.sleep(1)
        machine.reset()

    def handle_track_set(self, cl, body):
        """
        POST /track/set - Save track metadata from app.
        Expected body: {id, name, start_line, sectors, tbl}
        """
        try:
            if not body:
                self.send_response(cl, 400, '{"error": "No body"}')
                return
            
            data = json.loads(body)
            
            # Validate required fields
            if 'id' not in data or 'start_line' not in data:
                self.send_response(cl, 400, '{"error": "Missing id or start_line"}')
                return
            
            if self.track_engine:
                if self.track_engine.save_track(data):
                    resp = {"success": True, "track_name": data.get('name', 'Unknown')}
                    self.send_response(cl, 200, json.dumps(resp))
                else:
                    self.send_response(cl, 500, '{"error": "Failed to save track"}')
            else:
                self.send_response(cl, 500, '{"error": "Track engine not initialized"}')
                
        except Exception as e:
            self.send_response(cl, 500, json.dumps({"error": str(e)}))

    def handle_track_status(self, cl):
        """GET /track/status - Return current track state."""
        if self.track_engine:
            status = self.track_engine.get_status()
            self.send_response(cl, 200, json.dumps(status))
        else:
            self.send_response(cl, 200, '{"track_loaded": false}')
