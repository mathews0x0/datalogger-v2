"""Tests for chunked upload endpoints (/api/upload/chunk + /api/upload/complete)."""
import pytest
import os
import sys
import json
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from flask_jwt_extended import create_access_token
from api.models import db, User, DeviceToken
import api.config as config


@pytest.fixture
def upload_client(app):
    """Client with a device token for upload auth."""
    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(email='upload@racesense.in', name='Upload User', is_approved=True)
        user.set_password('Pass123!')
        db.session.add(user)
        db.session.commit()

        # Create a device token
        dt = DeviceToken(user_id=user.id, token='rsk_testtoken123')
        db.session.add(dt)
        db.session.commit()

        user_id = str(user.id)

    with app.test_client() as client:
        client._user_id = user_id
        client._token = 'rsk_testtoken123'
        yield client

    # Cleanup
    with app.app_context():
        try:
            learning_dir = config.get_user_learning_dir(user_id)
            chunks_dir = learning_dir / '.chunks'
            if chunks_dir.exists():
                shutil.rmtree(str(chunks_dir))
            for f in learning_dir.glob('*.csv'):
                f.unlink()
        except:
            pass
        db.session.remove()
        db.drop_all()



def _auth_headers(client, content_type='application/octet-stream'):
    """Build standard auth + chunk headers."""
    return {
        'Authorization': f'Bearer {client._token}',
        'Content-Type': content_type,
    }


# --- Single chunk upload ---

def test_upload_single_chunk(upload_client, app):
    """A single chunk should be saved to the temp directory."""
    with app.app_context():
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = 'sess_001.csv'
        headers['X-Chunk-Index'] = '0'
        headers['X-Total-Size'] = '100'

        resp = upload_client.post('/api/upload/chunk', data=b'hello,world\n', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['received'] is True
        assert data['chunk_index'] == 0

        # Verify chunk file exists on disk
        chunk_path = config.get_user_learning_dir(upload_client._user_id) / '.chunks' / 'sess_001.csv' / 'chunk_0000'
        assert chunk_path.exists()
        assert chunk_path.read_bytes() == b'hello,world\n'


# --- Multi-chunk upload + finalize ---

def test_full_chunked_upload(upload_client, app):
    """Upload 3 chunks and finalize — verify the assembled CSV."""
    with app.app_context():
        filename = 'sess_test.csv'
        chunk_data = [
            b'tick_ms,row_type,acc_x\n',
            b'100,I,0.12\n200,I,0.34\n',
            b'300,G,0.56\n',
        ]

        # Send all chunks
        for i, data in enumerate(chunk_data):
            headers = _auth_headers(upload_client)
            headers['X-Filename'] = filename
            headers['X-Chunk-Index'] = str(i)
            headers['X-Total-Size'] = str(sum(len(d) for d in chunk_data))

            resp = upload_client.post('/api/upload/chunk', data=data, headers=headers)
            assert resp.status_code == 200

        # Finalize
        headers = _auth_headers(upload_client, content_type='application/json')
        resp = upload_client.post('/api/upload/complete',
                                  data=json.dumps({'filename': filename, 'total_chunks': 3}),
                                  headers=headers)
        assert resp.status_code == 200
        result = resp.get_json()
        assert result['success'] is True

        # Verify assembled file
        final_path = config.get_user_learning_dir(upload_client._user_id) / filename
        assert final_path.exists()
        content = final_path.read_text()
        assert content == 'tick_ms,row_type,acc_x\n100,I,0.12\n200,I,0.34\n300,G,0.56\n'

        # Verify chunk dir was cleaned up
        chunk_dir = config.get_user_learning_dir(upload_client._user_id) / '.chunks' / filename
        assert not chunk_dir.exists()


# --- Error: missing chunk on finalize ---

def test_finalize_missing_chunk(upload_client, app):
    """Finalize should fail if not all chunks were uploaded."""
    with app.app_context():
        filename = 'sess_incomplete.csv'

        # Send only chunk 0
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = filename
        headers['X-Chunk-Index'] = '0'
        headers['X-Total-Size'] = '100'
        upload_client.post('/api/upload/chunk', data=b'header\n', headers=headers)

        # Finalize claiming 3 chunks
        headers = _auth_headers(upload_client, content_type='application/json')
        resp = upload_client.post('/api/upload/complete',
                                  data=json.dumps({'filename': filename, 'total_chunks': 3}),
                                  headers=headers)
        assert resp.status_code == 400
        assert 'Missing chunk' in resp.get_json()['error']


# --- Duplicate chunk (idempotent) ---

def test_duplicate_chunk_idempotent(upload_client, app):
    """Re-sending the same chunk index should overwrite, not corrupt."""
    with app.app_context():
        filename = 'sess_dup.csv'

        for attempt in range(3):
            headers = _auth_headers(upload_client)
            headers['X-Filename'] = filename
            headers['X-Chunk-Index'] = '0'
            headers['X-Total-Size'] = '50'
            resp = upload_client.post('/api/upload/chunk',
                                      data=b'final_content\n',
                                      headers=headers)
            assert resp.status_code == 200

        # Should still have exactly one chunk file
        chunk_dir = config.get_user_learning_dir(upload_client._user_id) / '.chunks' / filename
        chunks = list(chunk_dir.iterdir())
        assert len(chunks) == 1
        assert chunks[0].read_bytes() == b'final_content\n'


# --- Auth required ---

def test_chunk_upload_requires_auth(upload_client, app):
    """Upload without a token should be rejected."""
    with app.app_context():
        headers = {
            'Content-Type': 'application/octet-stream',
            'X-Filename': 'sess_001.csv',
            'X-Chunk-Index': '0',
        }
        resp = upload_client.post('/api/upload/chunk', data=b'data', headers=headers)
        assert resp.status_code == 401


def test_complete_requires_auth(upload_client, app):
    """Finalize without a token should be rejected."""
    with app.app_context():
        headers = {'Content-Type': 'application/json'}
        resp = upload_client.post('/api/upload/complete',
                                  data=json.dumps({'filename': 'x.csv', 'total_chunks': 1}),
                                  headers=headers)
        assert resp.status_code == 401


# --- Missing required headers ---

def test_chunk_missing_headers(upload_client, app):
    """Chunk upload without required X-Filename header should 400."""
    with app.app_context():
        headers = _auth_headers(upload_client)
        # Missing X-Filename and X-Chunk-Index
        resp = upload_client.post('/api/upload/chunk', data=b'data', headers=headers)
        assert resp.status_code == 400


def test_complete_missing_body(upload_client, app):
    """Finalize without filename should 400."""
    with app.app_context():
        headers = _auth_headers(upload_client, content_type='application/json')
        resp = upload_client.post('/api/upload/complete',
                                  data=json.dumps({'total_chunks': 1}),
                                  headers=headers)
        assert resp.status_code == 400

# --- Global Sync Headers ---

def test_global_sync_headers(upload_client, app):
    """Test that global sync progress tracks via headers."""
    with app.app_context():
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = 'sess_global.csv'
        headers['X-Chunk-Index'] = '0'
        headers['X-Total-Size'] = '100'
        headers['X-Total-Chunks'] = '1'
        headers['X-Global-Progress'] = '2000'
        headers['X-Global-Total'] = '5000'
        headers['X-Total-Files'] = '3'
        headers['X-File-Index'] = '1'

        resp = upload_client.post('/api/upload/chunk', data=b'data\n', headers=headers)
        assert resp.status_code == 200

        # Verify DB updated
        dt = DeviceToken.query.filter_by(token='rsk_testtoken123').first()
        assert dt.sync_global_current == 2000
        assert dt.sync_global_total == 5000
        assert dt.sync_total_files == 3
        assert dt.sync_current_file_index == 1
        assert dt.is_syncing == True
        
        # Test Complete clears progress
        headers = _auth_headers(upload_client, content_type='application/json')
        upload_client.post('/api/upload/complete',
                           data=json.dumps({'filename': 'sess_global.csv', 'total_chunks': 1}),
                           headers=headers)
                           
        # it shouldn't clear unless index >= total_files - 1 (1 >= 3 - 1 -> False)
        # Therefore, is_syncing should remain True and progress should be kept.
        dt = DeviceToken.query.filter_by(token='rsk_testtoken123').first()
        assert dt.is_syncing == True
        assert dt.sync_global_current == 2000


# ============================================================================
# BATCH UPLOAD TESTS (/api/upload/batch)
# ============================================================================

def test_batch_upload_single(upload_client, app):
    """A single batch should create a .partial file."""
    with app.app_context():
        data = b'tick_ms,row_type,acc_x\n100,I,0.12\n200,I,0.34\n'
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = 'sess_batch.csv'
        headers['X-Offset'] = '0'
        headers['X-Total-Size'] = str(len(data))
        headers['Content-Length'] = str(len(data))

        resp = upload_client.post('/api/upload/batch', data=data, headers=headers)
        assert resp.status_code == 200
        result = resp.get_json()
        assert result['received'] is True
        assert result['offset'] == len(data)
        assert result['bytes'] == len(data)

        # Verify .partial file exists
        partial = config.get_user_learning_dir(upload_client._user_id) / '.chunks' / 'sess_batch.csv.partial'
        assert partial.exists()
        assert partial.read_bytes() == data


def test_batch_upload_multi_and_finalize(upload_client, app):
    """Upload in two batches + finalize — verify assembled CSV."""
    with app.app_context():
        part1 = b'tick_ms,row_type,acc_x\n100,I,0.12\n'
        part2 = b'200,I,0.34\n300,G,0.56\n'
        total = len(part1) + len(part2)

        # Batch 1
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = 'sess_multi.csv'
        headers['X-Offset'] = '0'
        headers['X-Total-Size'] = str(total)
        resp = upload_client.post('/api/upload/batch', data=part1, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()['offset'] == len(part1)

        # Batch 2
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = 'sess_multi.csv'
        headers['X-Offset'] = str(len(part1))
        headers['X-Total-Size'] = str(total)
        resp = upload_client.post('/api/upload/batch', data=part2, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()['offset'] == total

        # Finalize with total_size (batch mode)
        headers = _auth_headers(upload_client, content_type='application/json')
        resp = upload_client.post('/api/upload/complete',
                                  data=json.dumps({'filename': 'sess_multi.csv', 'total_size': total}),
                                  headers=headers)
        assert resp.status_code == 200
        result = resp.get_json()
        assert result['success'] is True

        # Verify assembled file
        final_path = config.get_user_learning_dir(upload_client._user_id) / 'sess_multi.csv'
        assert final_path.exists()
        assert final_path.read_bytes() == part1 + part2


def test_batch_upload_resume(upload_client, app):
    """Send batch at offset 0, then another at correct offset — verify continuity."""
    with app.app_context():
        part1 = b'AAAA' * 128   # 512 bytes
        part2 = b'BBBB' * 128   # 512 bytes

        # Batch 1 at offset 0
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = 'sess_resume.csv'
        headers['X-Offset'] = '0'
        headers['X-Total-Size'] = '1024'
        resp = upload_client.post('/api/upload/batch', data=part1, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()['offset'] == 512

        # Batch 2 at offset 512
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = 'sess_resume.csv'
        headers['X-Offset'] = '512'
        headers['X-Total-Size'] = '1024'
        resp = upload_client.post('/api/upload/batch', data=part2, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()['offset'] == 1024

        # Verify partial file contains both parts
        partial = config.get_user_learning_dir(upload_client._user_id) / '.chunks' / 'sess_resume.csv.partial'
        assert partial.read_bytes() == part1 + part2


def test_batch_upload_auth_required(upload_client, app):
    """Batch upload without a token should be rejected."""
    with app.app_context():
        headers = {
            'Content-Type': 'application/octet-stream',
            'X-Filename': 'sess_noauth.csv',
            'X-Offset': '0',
        }
        resp = upload_client.post('/api/upload/batch', data=b'data', headers=headers)
        assert resp.status_code == 401


def test_batch_status_returns_bytes(upload_client, app):
    """After batch upload, /status should return received_bytes."""
    with app.app_context():
        data = b'X' * 256
        headers = _auth_headers(upload_client)
        headers['X-Filename'] = 'sess_status.csv'
        headers['X-Offset'] = '0'
        headers['X-Total-Size'] = '512'
        upload_client.post('/api/upload/batch', data=data, headers=headers)

        # Check status
        headers = _auth_headers(upload_client)
        resp = upload_client.get('/api/upload/status?filename=sess_status.csv', headers=headers)
        assert resp.status_code == 200
        result = resp.get_json()
        assert result['received_bytes'] == 256
