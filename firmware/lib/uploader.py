# lib/uploader.py - High-Speed Batch Uploader for RS-Core
import json
import os
import gc
import time
from lib.memory_profile import get_memory_profile, recommended_stream_chunk_size

DEVICE_CONFIG_PATH = '/data/metadata/device.json'
CHUNK_SIZE = 4 * 1024        # Legacy non-PSRAM ceiling
PSRAM_CHUNK_SIZE = 32 * 1024 # Faster PSRAM-backed read size without overpushing weak links
BATCH_SIZE = 1 * 1024 * 1024 # 1MB per HTTP request to balance speed and stability
MIN_CHUNK_SIZE = 1024        # 1KB floor for badly fragmented heaps
MAX_RETRIES = 3
RETRY_DELAY_MS = 2000
TIMEOUT = 45
GC_EVERY_N = 8               # Only gc.collect() every Nth read
RESPONSE_READ_SIZE = 1024
MAX_JSON_BODY = 4096


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
    """Pick a read size that leaves heap headroom for TLS/socket buffers."""
    try:
        chunk_size = recommended_stream_chunk_size()
        if chunk_size <= 0:
            return MIN_CHUNK_SIZE
        return chunk_size
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


def _read_http_response(sock, max_body_bytes=0):
    """Read HTTP response with bounded body buffering."""
    status_line = sock.readline().decode().strip()
    headers = {}
    while True:
        line = sock.readline().decode()
        if not line or line == "\r\n":
            break
        if ':' in line:
            key, value = line.split(':', 1)
            headers[key.strip().lower()] = value.strip()

    body = bytearray() if max_body_bytes > 0 else None
    content_len = int(headers.get("content-length", "0") or "0")
    while content_len > 0:
        chunk = sock.read(min(RESPONSE_READ_SIZE, content_len))
        if not chunk:
            break
        if body is not None and len(body) < max_body_bytes:
            remaining = max_body_bytes - len(body)
            body.extend(chunk[:remaining])
        content_len -= len(chunk)
    if body is None:
        return status_line, headers, b""
    return status_line, headers, bytes(body)


def _query_status_on_socket(ss, fname, host, status_path, token):
    """Query upload status using an EXISTING SSL socket (no new handshake)."""
    # URL encode spaces to prevent malformed HTTP request line
    encoded_fname = fname.replace(' ', '%20')
    req = "GET " + status_path + "?filename=" + encoded_fname + " HTTP/1.1\r\n"
    req += "Host: " + host + "\r\n"
    req += "Authorization: Bearer " + token + "\r\n"
    req += "Connection: keep-alive\r\n\r\n"
    ss.write(req.encode())
    status_line, _, body = _read_http_response(ss, max_body_bytes=MAX_JSON_BODY)
    if "200" in status_line and body:
        data = json.loads(body)
        return (
            int(data.get('received_bytes', 0) or 0),
            int(data.get('next_chunk', 0) or 0),
            int(data.get('chunk_size', 0) or 0),
        )
    return 0, 0, 0


def _finalize_on_socket(ss, fname, host, complete_path, token, total_size, wdt=None):
    """Send finalize request on an EXISTING SSL socket (no new handshake)."""
    payload = json.dumps({'filename': fname, 'total_size': total_size})
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
                            global_total=0, global_current=0, file_index=0, total_files=1,
                            status_cb=None):
    """
    Upload a file using batched streaming over a SINGLE persistent SSL connection.

    Instead of one HTTP request per small chunk, this streams multiple 32KB
    reads into a single ~512KB HTTP request body.  The server receives each
    batch as one request, cutting round-trips by ~16x.

    Connection layout:
      1. Status query (resume check) — returns byte offset
      2. N batch requests (~512KB each, streamed as 16× 32KB reads)
      3. Finalize
    """
    stat = os.stat(filepath)
    total_size = stat[6]
    if total_size == 0:
        return True, 0, 0

    # Parse URL
    try:
        proto, host, port, base_path = _parse_url(api_url)
        batch_path = base_path + '/batch'
        status_path = base_path + '/status'
        complete_path = base_path + '/complete'
    except Exception as e:
        print(f"[Sync] URL Parse Error: {e}")
        return False, 0, 0

    offset = 0
    s = None
    ss = None
    locked = False

    try:
        # Acquire network lock for the entire file duration
        if lock:
            locked = lock.acquire(True)
        gc.collect()

        # 1. Open persistent SSL connection (ONCE PER FILE)
        print(f"[Sync] Connecting: {fname} ({total_size} bytes, {total_size / (1024 * 1024):.2f} MB)")
        s, ss = _open_ssl_socket(host, port, proto)

        # 2. Query resume status on this connection
        read_size = _pick_chunk_size()
        mem_info = get_memory_profile()
        try:
            resume_bytes, _, _ = _query_status_on_socket(
                ss, fname, host, status_path, token
            )
            if resume_bytes > 0:
                offset = resume_bytes
                print(f'[Sync] Resuming {fname} from byte {offset}')
        except Exception as e:
            print(f'[Sync] Status query failed, starting fresh: {e}')

        total_batches = (total_size - offset + BATCH_SIZE - 1) // BATCH_SIZE
        max_chunk = PSRAM_CHUNK_SIZE if mem_info.get("psram_present") else CHUNK_SIZE
        print(f'[Sync] Uploading: {read_size // 1024}KB reads (cap {max_chunk // 1024}KB), {BATCH_SIZE // 1024}KB batches, ~{total_batches} batches')
        if status_cb:
            try:
                status_cb(
                    "upload_start",
                    filename=fname,
                    file_index=file_index,
                    total_files=total_files,
                    sent_bytes=offset,
                    total_bytes=total_size,
                    global_current=global_current + offset,
                    global_total=global_total,
                )
            except:
                pass

        # Set background animation state once
        if led:
            led.set_state("SYNC_UPLOADING")

        # 3. Stream batches on the same connection
        batch_count = 0
        read_count = 0
        with open(filepath, 'rb') as f:
            if offset > 0:
                f.seek(offset)

            while offset < total_size:
                # Calculate this batch's size
                batch_size = min(BATCH_SIZE, total_size - offset)

                # Build ONE HTTP request for this batch
                request = "POST " + batch_path + " HTTP/1.1\r\n"
                request += "Host: " + host + "\r\n"
                request += "Authorization: Bearer " + token + "\r\n"
                request += "Content-Type: application/octet-stream\r\n"
                request += "Content-Length: " + str(batch_size) + "\r\n"
                request += "X-Filename: " + fname + "\r\n"
                request += "X-Offset: " + str(offset) + "\r\n"
                request += "X-Total-Size: " + str(total_size) + "\r\n"
                # Global progress on every batch
                if global_total > 0:
                    request += "X-Global-Progress: " + str(global_current + offset) + "\r\n"
                    request += "X-Global-Total: " + str(global_total) + "\r\n"
                    request += "X-Total-Files: " + str(total_files) + "\r\n"
                    request += "X-File-Index: " + str(file_index) + "\r\n"
                request += "Connection: keep-alive\r\n\r\n"

                if wdt:
                    wdt.feed()

                ss.write(request.encode())

                # Stream multiple reads into this single request body
                sent_in_batch = 0
                while sent_in_batch < batch_size:
                    to_read = min(read_size, batch_size - sent_in_batch)
                    data = f.read(to_read)
                    if not data:
                        break
                    ss.write(data)
                    sent_in_batch += len(data)
                    read_count += 1

                    if wdt and read_count % 4 == 0:
                        wdt.feed()

                    # GC only every Nth read
                    if read_count % GC_EVERY_N == 0:
                        gc.collect()

                # Read ONE response for the entire batch
                try:
                    status_line, _, _ = _read_http_response(ss)
                    if "200" in status_line:
                        batch_count += 1
                        offset += sent_in_batch
                        print(f'[Sync] Batch {batch_count}/{total_batches}: {offset / 1024:.0f}KB / {total_size / 1024:.0f}KB')
                        if status_cb:
                            try:
                                status_cb(
                                    "upload_progress",
                                    filename=fname,
                                    file_index=file_index,
                                    total_files=total_files,
                                    sent_bytes=offset,
                                    total_bytes=total_size,
                                    global_current=global_current + offset,
                                    global_total=global_total,
                                    batch_count=batch_count,
                                    total_batches=total_batches,
                                )
                            except:
                                pass
                    else:
                        print(f'[Sync] HTTP Error: {status_line.strip()}')
                        return False, offset, offset
                except Exception as batch_e:
                    print(f'[Sync] Socket Error at offset {offset}: {batch_e}')
                    return False, offset, offset

        # 4. Finalize on the SAME connection
        print(f'[Sync] Finalizing {fname} ({batch_count} batches, {offset} bytes)...')
        for attempt in range(MAX_RETRIES):
            try:
                if _finalize_on_socket(ss, fname, host, complete_path, token, total_size, wdt):
                    print(f'[Sync] Done: {fname}')
                    if status_cb:
                        try:
                            status_cb(
                                "upload_done",
                                filename=fname,
                                file_index=file_index,
                                total_files=total_files,
                                sent_bytes=total_size,
                                total_bytes=total_size,
                                global_current=global_current + total_size,
                                global_total=global_total,
                            )
                        except:
                            pass
                    return True, batch_count, offset
                print(f'[Sync] Finalize rejected, retry {attempt + 1}')
            except Exception as fin_e:
                print(f'[Sync] Finalize error: {fin_e}')
            time.sleep_ms(500)

        return False, batch_count, offset

    except Exception as e:
        print(f"[Sync] Connection Error: {e}")
        return False, 0, offset
    finally:
        if ss:
            ss.close()
        if s:
            s.close()
        if locked:
            lock.release()
        gc.collect()


def sync_all(session_mgr, led=None, wdt=None, lock=None, status_cb=None):
    """Upload all pending files using persistent sockets with batch streaming."""
    config = _load_config()
    token = config.get('token', '')
    api_url = config.get('api_url', '')

    if not token or not api_url:
        return False

    files = session_mgr.list_sessions()
    if not files:
        return True

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

    print(f'[Sync] Batch Mode: {len(valid_files)} files pending ({global_total_size / (1024 * 1024):.2f} MB total)')
    if status_cb:
        try:
            status_cb("queue", files=valid_files, global_total=global_total_size)
        except:
            pass

    success_count = len(files) - len(valid_files)
    global_current = 0

    for i, fname in enumerate(valid_files):
        try:
            filepath = session_mgr.active_dir + '/' + fname
            ok = False
            file_bytes_sent = 0

            for attempt in range(MAX_RETRIES):
                ok, _, file_bytes_sent = _upload_file_persistent(
                    filepath, fname, api_url, token, led, wdt, lock,
                    global_total=global_total_size,
                    global_current=global_current,
                    file_index=i,
                    total_files=len(valid_files),
                    status_cb=status_cb,
                )
                if ok:
                    break
                print(f'[Sync] Retry file {fname} ({attempt + 1}/{MAX_RETRIES})')
                time.sleep_ms(RETRY_DELAY_MS)
                gc.collect()

            if ok:
                session_mgr.delete_session(fname)
                success_count += 1
            elif status_cb:
                try:
                    status_cb(
                        "upload_failed",
                        filename=fname,
                        file_index=i,
                        total_files=len(valid_files),
                        sent_bytes=file_bytes_sent,
                        total_bytes=os.stat(filepath)[6],
                        global_current=global_current + file_bytes_sent,
                        global_total=global_total_size,
                    )
                except:
                    pass

            global_current += file_bytes_sent
            gc.collect()
        except Exception as e:
            print(f'[Sync] Error {fname}: {e}')

    return success_count == len(files)
