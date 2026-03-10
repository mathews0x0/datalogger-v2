# lib/uploader.py - Chunked CSV uploader for RS-Core
# Streams files in small chunks to avoid MemoryError on large sessions.
import json
import os
import gc
import time

DEVICE_CONFIG_PATH = '/data/metadata/device.json'
CHUNK_SIZE = 8 * 1024   # 8KB per chunk — safe for ESP32 with SSL overhead
MAX_RETRIES = 3
RETRY_DELAY_MS = 2000


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


def _upload_file_chunked(filepath, fname, api_url, token, led=None, wdt=None):
    """
    Stream a file to the server in CHUNK_SIZE pieces.
    Each chunk is sent as a raw-body POST with metadata in headers.
    Returns (success: bool, chunks_sent: int).
    """
    import urequests

    stat = os.stat(filepath)
    total_size = stat[6]

    if total_size == 0:
        return True, 0  # Nothing to send

    # Build the chunk upload URL from the base API URL
    # e.g. https://racesense.in/api/upload -> https://racesense.in/api/upload/chunk
    chunk_url = api_url.rstrip('/') + '/chunk'

    chunk_index = 0
    bytes_sent = 0

    with open(filepath, 'rb') as f:
        while True:
            gc.collect()
            if wdt:
                wdt.feed()

            data = f.read(CHUNK_SIZE)
            if not data:
                break  # EOF

            headers = {
                'Content-Type': 'application/octet-stream',
                'Authorization': 'Bearer ' + token,
                'X-Filename': fname,
                'X-Chunk-Index': str(chunk_index),
                'X-Total-Size': str(total_size),
            }

            # Retry loop for this chunk
            sent = False
            for attempt in range(MAX_RETRIES):
                try:
                    if led:
                        led.update_onboard_led("CONNECTED")

                    resp = urequests.post(chunk_url, data=data, headers=headers)
                    status = resp.status_code
                    resp.close()

                    if status == 200:
                        sent = True
                        break
                    else:
                        print(f'[Sync] Chunk {chunk_index} HTTP {status}, retry {attempt + 1}')
                except Exception as e:
                    print(f'[Sync] Chunk {chunk_index} error: {e}, retry {attempt + 1}')

                gc.collect()
                if wdt:
                    wdt.feed()
                time.sleep_ms(RETRY_DELAY_MS)

            if not sent:
                print(f'[Sync] FAILED chunk {chunk_index} of {fname} after {MAX_RETRIES} retries')
                return False, chunk_index

            bytes_sent += len(data)
            chunk_index += 1

            # Brief pause between chunks to let ESP32 breathe
            time.sleep_ms(50)

    print(f'[Sync] Sent {chunk_index} chunks ({bytes_sent} bytes) for {fname}')
    return True, chunk_index


def _finalize_upload(fname, api_url, token, total_chunks, wdt=None):
    """
    Tell the server all chunks are sent — trigger reassembly.
    Returns True on success.
    """
    import urequests

    complete_url = api_url.rstrip('/') + '/complete'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
    }
    payload = json.dumps({'filename': fname, 'total_chunks': total_chunks})

    if wdt:
        wdt.feed()

    for attempt in range(MAX_RETRIES):
        try:
            resp = urequests.post(complete_url, data=payload, headers=headers)
            status = resp.status_code
            resp.close()
            gc.collect()

            if status == 200:
                return True
            else:
                print(f'[Sync] Finalize HTTP {status}, retry {attempt + 1}')
        except Exception as e:
            print(f'[Sync] Finalize error: {e}, retry {attempt + 1}')

        if wdt:
            wdt.feed()
        time.sleep_ms(RETRY_DELAY_MS)

    return False


def sync_all(session_mgr, led=None, wdt=None):
    """
    Upload all pending session files using chunked streaming.
    Each file is streamed in 8KB chunks, then finalized on the server.
    """
    config = _load_config()
    token = config.get('token', '')
    api_url = config.get('api_url', '')

    if not token or not api_url:
        print('[Sync] No token or API URL configured')
        return False

    files = session_mgr.list_sessions()
    if not files:
        return True  # Nothing to do

    print(f'[Sync] Start: {len(files)} file(s)')

    success_count = 0
    for fname in files:
        try:
            filepath = session_mgr.active_dir + '/' + fname

            stat = os.stat(filepath)
            size = stat[6]

            # Skip empty files
            if size == 0:
                print(f'[Sync] Deleting 0-byte: {fname}')
                session_mgr.delete_session(fname)
                success_count += 1
                continue

            # Integrity check
            if not _validate_session(filepath):
                print(f'[Sync] Skipping corrupt file: {fname}')
                session_mgr.delete_session(fname)
                success_count += 1
                continue

            print(f'[Sync] Uploading {fname} ({size} bytes, ~{size // CHUNK_SIZE + 1} chunks)...')

            if wdt:
                wdt.feed()

            ok, chunks_sent = _upload_file_chunked(filepath, fname, api_url, token, led, wdt)

            if ok and chunks_sent > 0:
                # Finalize — tell server to reassemble
                if _finalize_upload(fname, api_url, token, chunks_sent, wdt):
                    print(f'[Sync] Done: {fname}')
                    session_mgr.delete_session(fname)
                    success_count += 1
                else:
                    print(f'[Sync] Finalize failed: {fname}')
            elif ok and chunks_sent == 0:
                # Empty file that passed validation somehow
                session_mgr.delete_session(fname)
                success_count += 1
            else:
                print(f'[Sync] Upload failed: {fname}')

            gc.collect()

        except Exception as e:
            print(f'[Sync] Error {fname}: {e}')
            gc.collect()

    return success_count == len(files)
