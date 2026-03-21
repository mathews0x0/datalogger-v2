# lib/uploader.py - High-Speed Persistent Uploader for RS-Core
import json
import os
import gc
import time

DEVICE_CONFIG_PATH = '/data/metadata/device.json'
CHUNK_SIZE = 16 * 1024
MIN_CHUNK_SIZE = 4 * 1024
MAX_RETRIES = 3
RETRY_DELAY_MS = 2000
TIMEOUT = 45  # Increased for larger 128KB chunks


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


def _pick_chunk_size():
    """Pick a chunk size that leaves heap headroom for TLS/socket buffers."""
    try:
        free_mem = gc.mem_free()
        if free_mem <= 0:
            return MIN_CHUNK_SIZE
        target = free_mem // 4
        if target < MIN_CHUNK_SIZE:
            return MIN_CHUNK_SIZE
        if target > CHUNK_SIZE:
            return CHUNK_SIZE
        return target - (target % 1024)
    except:
        return MIN_CHUNK_SIZE


def _read_http_response(sock):
    status_line = sock.readline().decode().strip()
    headers = {}
    while True:
        line = sock.readline().decode()
        if not line or line == "\r\n":
            break
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip().lower()] = value.strip()

    body = b""
    content_len = int(headers.get("content-length", "0") or "0")
    while content_len > 0:
        chunk = sock.read(content_len)
        if not chunk:
            break
        body += chunk
        content_len -= len(chunk)
    return status_line, headers, body


def _query_upload_status(fname, api_url, token, wdt=None, lock=None):
    import urequests

    status_url = api_url.rstrip('/') + '/status?filename=' + fname
    headers = {'Authorization': 'Bearer ' + token}
    resp = None
    locked = False
    try:
        if lock:
            locked = lock.acquire(True)
        if wdt:
            wdt.feed()
        gc.collect()
        resp = urequests.get(status_url, headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return (
                int(data.get('next_chunk', 0) or 0),
                int(data.get('chunk_size', 0) or 0),
            )
    except Exception as e:
        print(f'[Sync] Resume status query failed for {fname}: {e}')
    finally:
        if resp:
            resp.close()
        if locked:
            lock.release()
    return 0, 0


def _upload_file_chunked(filepath, fname, api_url, token, led=None, wdt=None, lock=None, 
                         global_total=0, global_current=0, file_index=0, total_files=1,
                         start_chunk=0, chunk_size=None):
    """
    Stream a file using a PERSISTENT SSL socket to eliminate per-chunk handshakes.
    Manually constructs HTTP POST requests.
    """
    import socket
    import ssl

    stat = os.stat(filepath)
    total_size = stat[6]
    if total_size == 0: return True, 0, 0

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
        return False, 0, 0

    chunk_index = 0
    if chunk_size is None or chunk_size < MIN_CHUNK_SIZE or chunk_size > CHUNK_SIZE:
        chunk_size = _pick_chunk_size()
    if chunk_size <= 0:
        chunk_size = MIN_CHUNK_SIZE
    chunk_index = start_chunk
    bytes_sent = start_chunk * chunk_size
    total_chunks = (total_size + chunk_size - 1) // chunk_size
    
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
            if bytes_sent > 0:
                f.seek(bytes_sent)
            while True:
                data = f.read(chunk_size)
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
                if global_total > 0:
                    request += "X-Global-Progress: " + str(global_current + bytes_sent) + "\r\n"
                    request += "X-Global-Total: " + str(global_total) + "\r\n"
                    request += "X-Total-Files: " + str(total_files) + "\r\n"
                    request += "X-File-Index: " + str(file_index) + "\r\n"
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
                        status_line, _, _ = _read_http_response(ss)
                        if "200" in status_line:
                            sent = True
                            print(f'[Sync] Fast Sent: {chunk_index}')
                            break
                        else:
                            print(f'[Sync] HTTP Status Error: {status_line.strip()}')
                            return False, chunk_index, bytes_sent
                    except Exception as chunk_e:
                        print(f'[Sync] Socket Error at chunk {chunk_index}: {chunk_e}')
                        return False, chunk_index, bytes_sent # Socket died, abort file
                
                if not sent: 
                    return False, chunk_index, bytes_sent
                
                bytes_sent += content_len
                chunk_index += 1
                gc.collect()

        return True, chunk_index, bytes_sent

    except Exception as e:
        print(f"[Sync] Persistent Conn Error: {e}")
        return False, chunk_index, bytes_sent
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
    
    # Pre-calculate global total size
    global_total_size = 0
    valid_files = []
    for fname in files:
        filepath = session_mgr.active_dir + '/' + fname
        if _validate_session(filepath):
            try:
                global_total_size += os.stat(filepath)[6]
                valid_files.append(fname)
            except:
                pass
        else:
            session_mgr.delete_session(fname)

    success_count = len(files) - len(valid_files)
    global_current = 0
    
    for i, fname in enumerate(valid_files):
        try:
            filepath = session_mgr.active_dir + '/' + fname
            ok = False
            chunks_sent = 0
            file_bytes_sent = 0

            for attempt in range(MAX_RETRIES):
                resume_chunk, resume_chunk_size = _query_upload_status(fname, api_url, token, wdt, lock)
                print(f'[Sync] Resume state {fname}: next_chunk={resume_chunk} chunk_size={resume_chunk_size}')
                ok, chunks_sent, file_bytes_sent = _upload_file_chunked(
                    filepath, fname, api_url, token, led, wdt, lock,
                    global_total=global_total_size,
                    global_current=global_current,
                    file_index=i,
                    total_files=len(valid_files),
                    start_chunk=resume_chunk,
                    chunk_size=resume_chunk_size or None,
                )
                if ok:
                    break
                print(f'[Sync] Retry file {fname} ({attempt + 1}/{MAX_RETRIES})')
                time.sleep_ms(RETRY_DELAY_MS)
                gc.collect()

            if ok and chunks_sent > 0:
                finalized = False
                for attempt in range(MAX_RETRIES):
                    if _finalize_upload(fname, api_url, token, chunks_sent, led, wdt, lock):
                        finalized = True
                        break
                    print(f'[Sync] Retry finalize {fname} ({attempt + 1}/{MAX_RETRIES})')
                    time.sleep_ms(RETRY_DELAY_MS)
                    gc.collect()
                if finalized:
                    print(f'[Sync] Done: {fname}')
                    session_mgr.delete_session(fname)
                    success_count += 1
                else:
                    print(f'[Sync] Failed finalize: {fname}')
            elif ok and chunks_sent == 0:
                session_mgr.delete_session(fname)
                success_count += 1
            
            global_current += file_bytes_sent
            gc.collect()
        except Exception as e:
            print(f'[Sync] Error {fname}: {e}')
            
    return success_count == len(files)
