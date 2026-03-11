# lib/uploader.py - Chunked CSV uploader for RS-Core
# Streams files in small chunks to avoid MemoryError on large sessions.
import json
import os
import gc
import time

DEVICE_CONFIG_PATH = '/data/metadata/device.json'
CHUNK_SIZE = 4 * 1024   # Reverted to 4KB to reduce memory pressure during handshake
MAX_RETRIES = 3
RETRY_DELAY_MS = 2000
TIMEOUT = 20 # Seconds


def _load_config():
    """Load device config (token + API URL)."""
    try:
        with open(DEVICE_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}


def _validate_session(filepath):
    """Check if a session file has a valid CSV header.
    Returns True if the file looks like a valid session.
    """
    try:
        with open(filepath, 'r') as f:
            header = f.readline().strip()
        return header.startswith('tick_ms,') or header.startswith('gps_time,') or header.startswith('time,')
    except:
        return False


def _upload_file_chunked(filepath, fname, api_url, token, led=None, wdt=None, lock=None):
    """
    Stream a file to the server in CHUNK_SIZE pieces.
    Returns (success: bool, chunks_sent: int).
    """
    import urequests

    stat = os.stat(filepath)
    total_size = stat[6]

    if total_size == 0:
        return True, 0

    chunk_url = api_url.rstrip('/') + '/chunk'
    chunk_index = 0
    bytes_sent = 0

    with open(filepath, 'rb') as f:
        while True:
            gc.collect() 
            if wdt:
                wdt.feed()
            if led:
                led.update_sync("SYNC_UPLOADING")

            data = f.read(CHUNK_SIZE)
            if not data:
                break

            headers = {
                'Content-Type': 'application/octet-stream',
                'Authorization': 'Bearer ' + token,
                'X-Filename': fname,
                'X-Chunk-Index': str(chunk_index),
                'X-Total-Size': str(total_size),
            }

            sent = False
            for attempt in range(MAX_RETRIES):
                resp = None
                # Use lock only for the duration of the request
                locked = False
                if lock:
                    locked = lock.acquire(True) # Blocking acquire
                
                try:
                    if led: led.update_sync("SYNC_UPLOADING")
                    
                    # More aggressive GC before SSL handshake
                    gc.collect()
                    
                    resp = urequests.post(chunk_url, data=data, headers=headers, timeout=TIMEOUT)
                    status = resp.status_code

                    if status == 200:
                        sent = True
                        print(f'[Sync] Sent chunk {chunk_index} of {fname}')
                        break
                    else:
                        print(f'[Sync] Chunk {chunk_index} HTTP {status}, retry {attempt + 1}')
                except Exception as e:
                    print(f'[Sync] Chunk {chunk_index} error: {e}, retry {attempt + 1}')
                finally:
                    if resp: resp.close()
                    if locked: lock.release()

                gc.collect()
                if wdt: wdt.feed()
                time.sleep_ms(RETRY_DELAY_MS)

            if not sent:
                print(f'[Sync] FAILED chunk {chunk_index} of {fname} after {MAX_RETRIES} retries')
                return False, chunk_index

            bytes_sent += len(data)
            chunk_index += 1
            time.sleep_ms(50)

    print(f'[Sync] Sent total {chunk_index} chunks ({bytes_sent} bytes) for {fname}')
    return True, chunk_index


def _finalize_upload(fname, api_url, token, total_chunks, led=None, wdt=None, lock=None):
    """Tell server all chunks are sent."""
    import urequests

    complete_url = api_url.rstrip('/') + '/complete'
    payload = json.dumps({'filename': fname, 'total_chunks': total_chunks})
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
    }

    for attempt in range(MAX_RETRIES):
        resp = None
        locked = False
        if lock: locked = lock.acquire(True)
        
        try:
            if wdt: wdt.feed()
            if led: led.update_sync("SYNC_UPLOADING")
            gc.collect()
            resp = urequests.post(complete_url, data=payload, headers=headers, timeout=TIMEOUT)
            status = resp.status_code

            if status == 200:
                return True
            else:
                print(f'[Sync] Finalize HTTP {status}, retry {attempt + 1}')
        except Exception as e:
            print(f'[Sync] Finalize error: {e}, retry {attempt + 1}')
        finally:
            if resp: resp.close()
            if locked: lock.release()
            gc.collect()

        if wdt: wdt.feed()
        time.sleep_ms(RETRY_DELAY_MS)

    return False


def sync_all(session_mgr, led=None, wdt=None, lock=None):
    """Upload all pending session files."""
    config = _load_config()
    token = config.get('token', '')
    api_url = config.get('api_url', '')

    if not token or not api_url:
        print('[Sync] No token or API URL configured')
        return False

    files = session_mgr.list_sessions()
    if not files:
        return True

    print(f'[Sync] Start: {len(files)} file(s)')

    success_count = 0
    for fname in files:
        try:
            filepath = session_mgr.active_dir + '/' + fname
            stat = os.stat(filepath)
            size = stat[6]

            if size == 0:
                print(f'[Sync] Deleting 0-byte: {fname}')
                session_mgr.delete_session(fname)
                success_count += 1
                continue

            if not _validate_session(filepath):
                print(f'[Sync] Skipping corrupt: {fname}')
                session_mgr.delete_session(fname)
                success_count += 1
                continue

            print(f'[Sync] Uploading {fname} ({size} bytes)...')
            if wdt: wdt.feed()

            ok, chunks_sent = _upload_file_chunked(filepath, fname, api_url, token, led, wdt, lock)

            if ok and chunks_sent > 0:
                if _finalize_upload(fname, api_url, token, chunks_sent, led, wdt, lock):
                    print(f'[Sync] Done: {fname}')
                    session_mgr.delete_session(fname)
                    success_count += 1
                else:
                    print(f'[Sync] Finalize failed: {fname}')
            elif ok and chunks_sent == 0:
                session_mgr.delete_session(fname)
                success_count += 1
            else:
                print(f'[Sync] Upload failed: {fname}')

            gc.collect()

        except Exception as e:
            print(f'[Sync] Error {fname}: {e}')
            gc.collect()

    return success_count == len(files)
