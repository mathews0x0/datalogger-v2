# lib/uploader.py - High-Speed Persistent Uploader for RS-Core
import json
import os
import gc
import time

DEVICE_CONFIG_PATH = '/data/metadata/device.json'
CHUNK_SIZE = 64 * 1024       # 64KB ceiling — dynamic sizing scales down if heap is tight
MIN_CHUNK_SIZE = 8 * 1024    # 8KB floor
MAX_RETRIES = 3
RETRY_DELAY_MS = 2000
TIMEOUT = 45
GC_EVERY_N = 8              # Only gc.collect() every Nth chunk


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
        target = free_mem // 4  # More aggressive: 1/4 of free heap (was 1/6)
        if target < MIN_CHUNK_SIZE:
            return MIN_CHUNK_SIZE
        if target > CHUNK_SIZE:
            return CHUNK_SIZE
        return target - (target % 1024)
    except:
        return MIN_CHUNK_SIZE


def _parse_url(api_url):
    """Parse API URL into components. Returns (proto, host, port, base_path) or raises."""
    proto, _, host_port, path = api_url.split('/', 3)
    port = 443 if proto == 'https:' else 80
    if ':' in host_port:
        host, port = host_port.split(':')
        port = int(port)
    else:
        host = host_port
    base_path = '/' + path.rstrip('/')
    return proto, host, port, base_path


def _open_ssl_socket(host, port, proto):
    """Open a raw socket and wrap with SSL if needed. Returns (raw_sock, ssl_sock)."""
    import socket
    import ssl
    ai = socket.getaddrinfo(host, port)[0]
    s = socket.socket(ai[0], ai[1], ai[2])
    s.settimeout(TIMEOUT)
    s.connect(ai[-1])
    gc.collect()  # Maximize heap before TLS buffer allocation (~16KB)
    if proto == 'https:':
        ss = ssl.wrap_socket(s, server_hostname=host)
    else:
        ss = s
    return s, ss


def _read_http_response(sock):
    """Read HTTP response: status line, headers, body."""
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


def _query_status_on_socket(ss, fname, host, status_path, token):
    """Query upload status using an EXISTING SSL socket (no new handshake)."""
    req = "GET " + status_path + "?filename=" + fname + " HTTP/1.1\r\n"
    req += "Host: " + host + "\r\n"
    req += "Authorization: Bearer " + token + "\r\n"
    req += "Connection: keep-alive\r\n\r\n"
    ss.write(req.encode())
    status_line, _, body = _read_http_response(ss)
    if "200" in status_line and body:
        data = json.loads(body)
        return (
            int(data.get('next_chunk', 0) or 0),
            int(data.get('chunk_size', 0) or 0),
        )
    return 0, 0


def _finalize_on_socket(ss, fname, host, complete_path, token, total_chunks, wdt=None):
    """Send finalize request on an EXISTING SSL socket (no new handshake)."""
    payload = json.dumps({'filename': fname, 'total_chunks': total_chunks})
    req = "POST " + complete_path + " HTTP/1.1\r\n"
    req += "Host: " + host + "\r\n"
    req += "Authorization: Bearer " + token + "\r\n"
    req += "Content-Type: application/json\r\n"
    req += "Content-Length: " + str(len(payload)) + "\r\n"
    req += "Connection: keep-alive\r\n\r\n"
    if wdt: wdt.feed()
    ss.write(req.encode() + payload.encode())
    status_line, _, _ = _read_http_response(ss)
    return "200" in status_line


def _upload_file_persistent(filepath, fname, api_url, token, led=None, wdt=None, lock=None,
                            global_total=0, global_current=0, file_index=0, total_files=1):
    """
    Upload a file using a SINGLE persistent SSL connection for:
      1. Status query (resume check)
      2. All chunk uploads
      3. Finalize

    Zero extra SSL handshakes. One connection per file.
    """
    stat = os.stat(filepath)
    total_size = stat[6]
    if total_size == 0:
        return True, 0, 0

    # Parse URL
    try:
        proto, host, port, base_path = _parse_url(api_url)
        chunk_path = base_path + '/chunk'
        status_path = base_path + '/status'
        complete_path = base_path + '/complete'
    except Exception as e:
        print(f"[Sync] URL Parse Error: {e}")
        return False, 0, 0

    chunk_index = 0
    bytes_sent = 0
    s = None
    ss = None
    locked = False

    try:
        # Acquire network lock for the entire file duration
        if lock:
            locked = lock.acquire(True)
        gc.collect()

        # 1. Open persistent SSL connection (ONCE PER FILE)
        print(f"[Sync] Connecting: {fname} ({total_size} bytes)")
        s, ss = _open_ssl_socket(host, port, proto)

        # 2. Query resume status on this connection (no extra SSL handshake)
        start_chunk = 0
        chunk_size = _pick_chunk_size()
        try:
            resume_chunk, resume_chunk_size = _query_status_on_socket(
                ss, fname, host, status_path, token
            )
            if resume_chunk > 0:
                start_chunk = resume_chunk
                print(f'[Sync] Resuming {fname} from chunk {start_chunk}')
            if resume_chunk_size >= MIN_CHUNK_SIZE and resume_chunk_size <= CHUNK_SIZE:
                chunk_size = resume_chunk_size
        except Exception as e:
            print(f'[Sync] Status query failed, starting fresh: {e}')

        chunk_index = start_chunk
        bytes_sent = start_chunk * chunk_size
        total_chunks = (total_size + chunk_size - 1) // chunk_size
        print(f'[Sync] Uploading: {chunk_size // 1024}KB chunks, {total_chunks} total, start={start_chunk}')

        # Set background animation state once
        if led:
            led.set_state("SYNC_UPLOADING")

        # 3. Stream all chunks on the same connection
        with open(filepath, 'rb') as f:
            if bytes_sent > 0:
                f.seek(bytes_sent)
            while True:
                data = f.read(chunk_size)
                if not data:
                    break

                content_len = len(data)

                # Build HTTP request — minimal headers on non-first chunks
                request = "POST " + chunk_path + " HTTP/1.1\r\n"
                request += "Host: " + host + "\r\n"
                request += "Authorization: Bearer " + token + "\r\n"
                request += "Content-Type: application/octet-stream\r\n"
                request += "Content-Length: " + str(content_len) + "\r\n"
                request += "X-Filename: " + fname + "\r\n"
                request += "X-Chunk-Index: " + str(chunk_index) + "\r\n"
                # Send full metadata only on first chunk
                if chunk_index == start_chunk:
                    request += "X-Total-Size: " + str(total_size) + "\r\n"
                    request += "X-Total-Chunks: " + str(total_chunks) + "\r\n"
                # Global progress every 10th chunk or first/last
                if global_total > 0 and (chunk_index == start_chunk or chunk_index % 10 == 0 or content_len < chunk_size):
                    request += "X-Global-Progress: " + str(global_current + bytes_sent) + "\r\n"
                    request += "X-Global-Total: " + str(global_total) + "\r\n"
                    request += "X-Total-Files: " + str(total_files) + "\r\n"
                    request += "X-File-Index: " + str(file_index) + "\r\n"
                request += "Connection: keep-alive\r\n\r\n"
                request = request.encode()

                try:
                    if wdt:
                        wdt.feed()
                    # Send Headers + Data
                    ss.write(request)
                    ss.write(data)
                    # Read Response
                    status_line, _, _ = _read_http_response(ss)
                    if "200" in status_line:
                        if chunk_index % 10 == 0 or content_len < chunk_size:
                            print(f'[Sync] Sent: {chunk_index}/{total_chunks}')
                    else:
                        print(f'[Sync] HTTP Error: {status_line.strip()}')
                        return False, chunk_index, bytes_sent
                except Exception as chunk_e:
                    print(f'[Sync] Socket Error at chunk {chunk_index}: {chunk_e}')
                    return False, chunk_index, bytes_sent

                bytes_sent += content_len
                chunk_index += 1

                # GC only every Nth chunk instead of every chunk
                if chunk_index % GC_EVERY_N == 0:
                    gc.collect()

        # 4. Finalize on the SAME connection (no extra SSL handshake)
        print(f'[Sync] Finalizing {fname} ({chunk_index} chunks)...')
        for attempt in range(MAX_RETRIES):
            try:
                if _finalize_on_socket(ss, fname, host, complete_path, token, chunk_index, wdt):
                    print(f'[Sync] Done: {fname}')
                    return True, chunk_index, bytes_sent
                print(f'[Sync] Finalize rejected, retry {attempt + 1}')
            except Exception as fin_e:
                print(f'[Sync] Finalize error: {fin_e}')
            time.sleep_ms(500)

        return False, chunk_index, bytes_sent

    except Exception as e:
        print(f"[Sync] Connection Error: {e}")
        return False, chunk_index, bytes_sent
    finally:
        if ss:
            ss.close()
        if s:
            s.close()
        if locked:
            lock.release()
        gc.collect()


def sync_all(session_mgr, led=None, wdt=None, lock=None):
    """Upload all pending files using persistent sockets."""
    config = _load_config()
    token = config.get('token', '')
    api_url = config.get('api_url', '')

    if not token or not api_url:
        return False

    files = session_mgr.list_sessions()
    if not files:
        return True

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
                ok, chunks_sent, file_bytes_sent = _upload_file_persistent(
                    filepath, fname, api_url, token, led, wdt, lock,
                    global_total=global_total_size,
                    global_current=global_current,
                    file_index=i,
                    total_files=len(valid_files),
                )
                if ok:
                    break
                print(f'[Sync] Retry file {fname} ({attempt + 1}/{MAX_RETRIES})')
                time.sleep_ms(RETRY_DELAY_MS)
                gc.collect()

            if ok:
                session_mgr.delete_session(fname)
                success_count += 1
            elif chunks_sent == 0 and ok:
                session_mgr.delete_session(fname)
                success_count += 1

            global_current += file_bytes_sent
            gc.collect()
        except Exception as e:
            print(f'[Sync] Error {fname}: {e}')

    return success_count == len(files)
