# lib/uploader.py - High-Speed Persistent Uploader for RS-Core
import json
import os
import gc
import time

DEVICE_CONFIG_PATH = '/data/metadata/device.json'
CHUNK_SIZE = 64 * 1024  # Ambitious 64KB chunks for maximum throughput
MAX_RETRIES = 3
RETRY_DELAY_MS = 2000
TIMEOUT = 30  # Increased for larger chunks


def _load_config():
    """Load device config."""
    try:
        with open(DEVICE_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}


def _validate_session(filepath):
    """Check if a session file has a valid CSV header."""
    try:
        with open(filepath, 'r') as f:
            header = f.readline().strip()
        return header.startswith('tick_ms,') or header.startswith('gps_time,') or header.startswith('time,')
    except:
        return False


def _upload_file_chunked(filepath, fname, api_url, token, led=None, wdt=None, lock=None):
    """
    Stream a file using a PERSISTENT SSL socket to eliminate per-chunk handshakes.
    Manually constructs HTTP POST requests.
    """
    import socket
    import ssl

    stat = os.stat(filepath)
    total_size = stat[6]
    if total_size == 0: return True, 0

    # Parse URL
    try:
        # Expected: https://domain.com/api
        proto, _, host_port, path = api_url.split('/', 3)
        port = 443 if proto == 'https:' else 80
        if ':' in host_port:
            host, port = host_port.split(':')
            port = int(port)
        else:
            host = host_port
        chunk_path = '/' + path.rstrip('/') + '/chunk'
    except Exception as e:
        print(f"[Sync] URL Parse Error: {e}")
        return False, 0

    chunk_index = 0
    bytes_sent = 0
    total_chunks = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    # Establish Persistent Connection
    s = None
    ss = None
    locked = False
    
    try:
        # Acquire network lock for the entire file duration to prevent heartbeat interference
        if lock: locked = lock.acquire(True)
        gc.collect()
        
        # 1. Open Raw Socket
        ai = socket.getaddrinfo(host, port)[0]
        s = socket.socket(ai[0], ai[1], ai[2])
        s.settimeout(TIMEOUT)
        
        # 2. SSL Handshake (ONCE PER FILE)
        print(f"[Sync] Handshake: {fname} ({total_size} bytes)")
        s.connect(ai[-1])
        ss = ssl.wrap_socket(s, server_hostname=host)
        
        # Set background animation state once
        if led: led.set_state("SYNC_UPLOADING")

        with open(filepath, 'rb') as f:
            while True:
                data = f.read(CHUNK_SIZE)
                if not data: break
                
                content_len = len(data)
                # Build Raw HTTP Request
                # Using Connection: keep-alive to signal the server
                # Build Raw HTTP Request
                request = "POST " + chunk_path + " HTTP/1.1\r\n"
                request += "Host: " + host + "\r\n"
                request += "Authorization: Bearer " + token + "\r\n"
                request += "Content-Type: application/octet-stream\r\n"
                request += "Content-Length: " + str(content_len) + "\r\n"
                request += "X-Filename: " + fname + "\r\n"
                request += "X-Chunk-Index: " + str(chunk_index) + "\r\n"
                request += "X-Total-Size: " + str(total_size) + "\r\n"
                request += "X-Total-Chunks: " + str(total_chunks) + "\r\n"
                request += "Connection: keep-alive\r\n\r\n"
                request = request.encode()

                sent = False
                for attempt in range(MAX_RETRIES):
                    try:
                        if wdt: wdt.feed()
                        
                        # Send Headers + Data
                        ss.write(request)
                        ss.write(data)
                        
                        # Read Response
                        status_line = ss.readline().decode()
                        if "200" in status_line:
                            # 1. Drain Headers and find Content-Length
                            resp_content_len = 0
                            while True:
                                h_line = ss.readline().decode()
                                if not h_line or h_line == "\r\n": break
                                if h_line.lower().startswith("content-length:"):
                                    resp_content_len = int(h_line.split(":")[1].strip())
                            
                            # 2. Consume the Body (CRITICAL for persistent sockets)
                            if resp_content_len > 0:
                                ss.read(resp_content_len)
                            
                            sent = True
                            print(f'[Sync] Fast Sent: {chunk_index}')
                            break
                        else:
                            print(f'[Sync] HTTP Status Error: {status_line.strip()}')
                            return False, chunk_index
                    except Exception as chunk_e:
                        print(f'[Sync] Socket Error at chunk {chunk_index}: {chunk_e}')
                        return False, chunk_index # Socket died, abort file
                
                if not sent: 
                    return False, chunk_index
                
                bytes_sent += content_len
                chunk_index += 1
                gc.collect()

        return True, chunk_index

    except Exception as e:
        print(f"[Sync] Persistent Conn Error: {e}")
        return False, chunk_index
    finally:
        if ss: ss.close()
        if s: s.close()
        if locked: lock.release()
        gc.collect()


def _finalize_upload(fname, api_url, token, total_chunks, led=None, wdt=None, lock=None):
    """Finalize using standard urequests (one-off)."""
    import urequests
    complete_url = api_url.rstrip('/') + '/complete'
    payload = json.dumps({'filename': fname, 'total_chunks': total_chunks})
    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}

    for attempt in range(MAX_RETRIES):
        resp = None
        locked = False
        if lock: locked = lock.acquire(True)
        try:
            if wdt: wdt.feed()
            gc.collect()
            resp = urequests.post(complete_url, data=payload, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                return True
        except Exception as e:
            print(f'[Sync] Finalize Error: {e}')
        finally:
            if resp: resp.close()
            if locked: lock.release()
            gc.collect()
    return False


def sync_all(session_mgr, led=None, wdt=None, lock=None):
    """Upload all pending files using persistent sockets."""
    config = _load_config()
    token = config.get('token', '')
    api_url = config.get('api_url', '')

    if not token or not api_url: return False

    files = session_mgr.list_sessions()
    if not files: return True

    print(f'[Sync] High-Speed Mode: {len(files)} files pending')
    success_count = 0
    
    for fname in files:
        try:
            filepath = session_mgr.active_dir + '/' + fname
            if not _validate_session(filepath):
                session_mgr.delete_session(fname)
                success_count += 1
                continue

            ok, chunks_sent = _upload_file_chunked(filepath, fname, api_url, token, led, wdt, lock)

            if ok and chunks_sent > 0:
                if _finalize_upload(fname, api_url, token, chunks_sent, led, wdt, lock):
                    print(f'[Sync] Done: {fname}')
                    session_mgr.delete_session(fname)
                    success_count += 1
                else:
                    print(f'[Sync] Failed finalize: {fname}')
            elif ok and chunks_sent == 0:
                session_mgr.delete_session(fname)
                success_count += 1
            
            gc.collect()
        except Exception as e:
            print(f'[Sync] Error {fname}: {e}')
            
    return success_count == len(files)
