from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from flask import Blueprint, jsonify, request
from flask_jwt_extended import verify_jwt_in_request

import api.config as config
from api.models import SessionMeta, User
from api.playback_tuner_service import build_playback_manifest, load_playback_payload
from api.track_catalog import get_track_display_name, load_track_layout, resolve_track

race_view_bp = Blueprint('race_view', __name__)

MIN_LAP_OVERLAP_SEC = 15.0
MAX_GROUPS = 8
MAX_MANIFEST_POINTS = 1800
MIN_PLAUSIBLE_GPS_EPOCH = 946684800.0  # 2000-01-01 UTC


def _optional_auth():
    try:
        verify_jwt_in_request(optional=True)
    except Exception:
        pass


def _parse_session_datetime(raw_value: Optional[str]) -> Optional[datetime]:
    if not raw_value:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _session_date_key(raw_value: Optional[str]) -> Optional[str]:
    dt = _parse_session_datetime(raw_value)
    if dt:
        return dt.date().isoformat()
    if raw_value and len(raw_value) >= 10:
        return raw_value[:10]
    return None


def _session_start_epoch(raw_value: Optional[str]) -> Optional[float]:
    dt = _parse_session_datetime(raw_value)
    if not dt:
        return None
    return dt.timestamp()


def _resolve_start_epoch(session_meta: SessionMeta, payload: Optional[Dict] = None) -> Optional[float]:
    payload_meta = (payload or {}).get('meta') if isinstance(payload, dict) else {}
    payload_start = _session_start_epoch((payload_meta or {}).get('start_time'))
    if payload_start is not None:
        return payload_start
    return _session_start_epoch(session_meta.start_time)


def _resolve_start_value(session_meta: SessionMeta, payload: Optional[Dict] = None) -> Optional[str]:
    payload_meta = (payload or {}).get('meta') if isinstance(payload, dict) else {}
    return (payload_meta or {}).get('start_time') or session_meta.start_time


def _resolve_timestamp_source(session_meta: SessionMeta, payload: Optional[Dict] = None) -> str:
    payload_meta = (payload or {}).get('meta') if isinstance(payload, dict) else {}
    timestamp_source = str((payload_meta or {}).get('timestamp_source') or '').strip()
    if timestamp_source:
        return timestamp_source
    start_epoch = _resolve_start_epoch(session_meta, payload)
    if start_epoch is not None and start_epoch >= MIN_PLAUSIBLE_GPS_EPOCH:
        return 'legacy_gps_epoch'
    return 'relative_fallback'


def _has_race_view_timestamp(session_meta: SessionMeta, payload: Optional[Dict] = None) -> bool:
    return _resolve_timestamp_source(session_meta, payload) in ('gps_epoch', 'legacy_gps_epoch')


def _resolve_duration_sec(session_meta: SessionMeta, payload: Optional[Dict] = None) -> float:
    payload_meta = (payload or {}).get('meta') if isinstance(payload, dict) else {}
    try:
        payload_duration = float((payload_meta or {}).get('duration_sec') or 0.0)
    except Exception:
        payload_duration = 0.0
    if payload_duration > 0:
        return payload_duration
    return float(session_meta.duration_sec or 0.0)


def _session_end_epoch(session_meta: SessionMeta, payload: Optional[Dict] = None) -> Optional[float]:
    start_epoch = _resolve_start_epoch(session_meta, payload)
    duration = _resolve_duration_sec(session_meta, payload)
    if start_epoch is None or duration <= 0:
        return None
    return start_epoch + duration


def _session_ref(user_id: int, session_id: str) -> str:
    return f'{int(user_id)}:{session_id}'


def _lap_windows(payload: Dict, start_epoch: float) -> List[Dict]:
    laps = list((payload or {}).get('laps') or [])
    windows = []
    for lap in laps:
        try:
            lap_number = int(lap.get('lap_number') or 0)
        except Exception:
            lap_number = 0
        try:
            lap_start = float(lap.get('start_time'))
        except Exception:
            continue
        lap_end_raw = lap.get('end_time')
        try:
            lap_end = float(lap_end_raw) if lap_end_raw is not None else (lap_start + float(lap.get('lap_time') or 0.0))
        except Exception:
            continue
        if lap_end <= lap_start:
            continue
        windows.append({
            'lap_number': lap_number,
            'start_epoch': start_epoch + lap_start,
            'end_epoch': start_epoch + lap_end,
            'lap_time': lap_end - lap_start,
        })
    return windows


def _lap_overlap_windows(a: Dict, b: Dict, min_overlap_sec: float = MIN_LAP_OVERLAP_SEC) -> List[Dict]:
    left = list(a.get('lap_windows') or [])
    right = list(b.get('lap_windows') or [])
    overlaps = []
    right_index = 0

    for left_lap in left:
        while right_index < len(right) and right[right_index]['end_epoch'] <= left_lap['start_epoch']:
            right_index += 1
        probe_index = right_index
        while probe_index < len(right) and right[probe_index]['start_epoch'] < left_lap['end_epoch']:
            right_lap = right[probe_index]
            overlap_start = max(left_lap['start_epoch'], right_lap['start_epoch'])
            overlap_end = min(left_lap['end_epoch'], right_lap['end_epoch'])
            overlap_sec = overlap_end - overlap_start
            if overlap_sec >= min_overlap_sec:
                overlaps.append({
                    'start_epoch': overlap_start,
                    'end_epoch': overlap_end,
                    'overlap_sec': overlap_sec,
                    'left_lap_number': left_lap.get('lap_number'),
                    'right_lap_number': right_lap.get('lap_number'),
                })
            probe_index += 1
    return overlaps


def _rider_count(rows: List[Dict]) -> int:
    return len({row.get('user_id') for row in rows if row.get('user_id') is not None})


def _apply_owner_labels(rows: List[Dict]) -> List[Dict]:
    by_name = defaultdict(list)
    for row in rows:
        display_name = str(row.get('owner_name') or '').strip() or f"Rider {row.get('user_id')}"
        row['owner_name'] = display_name
        by_name[display_name].append(row)

    for owner_name, bucket in by_name.items():
        if len(bucket) == 1:
            bucket[0]['owner_label'] = owner_name
            continue

        bike_counts = defaultdict(int)
        for item in bucket:
            bike_label = str(item.get('bike_info') or '').strip()
            if bike_label:
                bike_counts[bike_label] += 1

        ordered = sorted(
            bucket,
            key=lambda item: (
                float(item.get('start_epoch') or 0.0),
                str(item.get('session_id') or ''),
            ),
        )
        for index, item in enumerate(ordered, start=1):
            bike_label = str(item.get('bike_info') or '').strip()
            if bike_label and bike_counts.get(bike_label) == 1:
                item['owner_label'] = f'{owner_name} · {bike_label}'
            else:
                item['owner_label'] = f'{owner_name} {index}'
    return rows


def _eligible_public_sessions(track_id: Optional[int] = None, date: Optional[str] = None) -> List[Dict]:
    query = SessionMeta.query.filter(
        SessionMeta.is_public.is_(True),
        SessionMeta.track_id.isnot(None),
        SessionMeta.duration_sec.isnot(None),
        SessionMeta.duration_sec > 0,
    )
    if track_id:
        query = query.filter(SessionMeta.track_id == int(track_id))
    sessions = []
    user_cache: Dict[int, Optional[User]] = {}
    track_cache: Dict[int, Dict] = {}

    for meta in query.order_by(SessionMeta.start_time.asc()).all():
        playback_file = config.get_user_sessions_dir(meta.user_id) / f"{meta.session_id}_playback.json"
        payload = load_playback_payload(playback_file)
        if payload is None:
            continue
        if not _has_race_view_timestamp(meta, payload):
            continue
        start_epoch = _resolve_start_epoch(meta, payload)
        end_epoch = _session_end_epoch(meta, payload)
        if start_epoch is None or end_epoch is None or end_epoch <= start_epoch:
            continue

        resolved_track = track_cache.get(meta.track_id)
        if resolved_track is None:
            resolved_track = resolve_track(meta.track_id)
            track_cache[meta.track_id] = resolved_track
        if not resolved_track or resolved_track.get('track_scope') != 'global' or not resolved_track.get('has_canonical_layout'):
            continue

        owner = user_cache.get(meta.user_id)
        if owner is None and meta.user_id not in user_cache:
            owner = User.query.get(meta.user_id)
            user_cache[meta.user_id] = owner
        else:
            owner = user_cache.get(meta.user_id)

        lap_windows = _lap_windows(payload, start_epoch)
        if not lap_windows:
            continue
        resolved_start_time = _resolve_start_value(meta, payload)
        date_key = _session_date_key(resolved_start_time)
        if not date_key or (date and date_key != date):
            continue

        sessions.append({
            'session_id': meta.session_id,
            'session_ref': _session_ref(meta.user_id, meta.session_id),
            'user_id': meta.user_id,
            'owner_name': owner.name if owner and owner.name else f'Rider {meta.user_id}',
            'bike_info': owner.bike_info if owner else '',
            'track_id': meta.track_id,
            'track_name': get_track_display_name(meta.track_id, user_id=meta.user_id),
            'best_lap_time': meta.best_lap_time,
            'total_laps': meta.total_laps,
            'start_time': resolved_start_time,
            'date_key': date_key,
            'start_epoch': start_epoch,
            'end_epoch': end_epoch,
            'duration_sec': _resolve_duration_sec(meta, payload),
            'timestamp_source': _resolve_timestamp_source(meta, payload),
            'lap_windows': lap_windows,
        })
    return sessions


def _select_interval_sessions(bucket_by_ref: Dict[str, Dict], active_windows: List[Dict]) -> List[Dict]:
    scores = defaultdict(float)
    for window in active_windows:
        scores[window['left_ref']] += window['overlap_sec']
        scores[window['right_ref']] += window['overlap_sec']

    selected_by_user = {}
    for session_ref, score in scores.items():
        row = bucket_by_ref[session_ref]
        user_id = row['user_id']
        candidate = (score, -float(row['start_epoch']), session_ref, row)
        existing = selected_by_user.get(user_id)
        if existing is None or candidate[:3] > existing[:3]:
            selected_by_user[user_id] = candidate
    return sorted((candidate[3] for candidate in selected_by_user.values()), key=lambda row: row['start_epoch'])


def _interval_groups(bucket: List[Dict]) -> List[Dict]:
    bucket_by_ref = {row['session_ref']: row for row in bucket}
    overlap_windows = []
    for index, left in enumerate(bucket):
        for right in bucket[index + 1:]:
            if int(left.get('user_id') or 0) == int(right.get('user_id') or 0):
                continue
            for overlap in _lap_overlap_windows(left, right):
                overlap_windows.append({
                    **overlap,
                    'left_ref': left['session_ref'],
                    'right_ref': right['session_ref'],
                })
    if not overlap_windows:
        return []

    boundaries = sorted({
        boundary
        for window in overlap_windows
        for boundary in (window['start_epoch'], window['end_epoch'])
    })
    intervals = []
    for index in range(len(boundaries) - 1):
        start_epoch = boundaries[index]
        end_epoch = boundaries[index + 1]
        if end_epoch <= start_epoch:
            continue
        active_windows = [
            window for window in overlap_windows
            if window['start_epoch'] < end_epoch and window['end_epoch'] > start_epoch
        ]
        selected = _select_interval_sessions(bucket_by_ref, active_windows)
        if len(selected) < 2:
            continue
        selected_refs = tuple(row['session_ref'] for row in selected)
        if intervals and intervals[-1]['session_refs'] == selected_refs and intervals[-1]['end_epoch'] == start_epoch:
            intervals[-1]['end_epoch'] = end_epoch
            intervals[-1]['overlap_window_count'] += len(active_windows)
        else:
            intervals.append({
                'start_epoch': start_epoch,
                'end_epoch': end_epoch,
                'session_refs': selected_refs,
                'overlap_window_count': len(active_windows),
            })
    return intervals


def _session_overlap_components(bucket: List[Dict]) -> List[Dict]:
    bucket_by_ref = {row['session_ref']: row for row in bucket}
    adjacency = defaultdict(set)
    overlap_scores = defaultdict(float)
    overlap_windows = []

    for index, left in enumerate(bucket):
        for right in bucket[index + 1:]:
            if int(left.get('user_id') or 0) == int(right.get('user_id') or 0):
                continue
            pair_overlaps = _lap_overlap_windows(left, right)
            if not pair_overlaps:
                continue
            left_ref = left['session_ref']
            right_ref = right['session_ref']
            adjacency[left_ref].add(right_ref)
            adjacency[right_ref].add(left_ref)
            for overlap in pair_overlaps:
                overlap_windows.append({
                    **overlap,
                    'left_ref': left_ref,
                    'right_ref': right_ref,
                })
                overlap_scores[left_ref] += overlap['overlap_sec']
                overlap_scores[right_ref] += overlap['overlap_sec']

    components = []
    seen = set()
    for session_ref in sorted(adjacency):
        if session_ref in seen:
            continue
        stack = [session_ref]
        component_refs = set()
        while stack:
            current_ref = stack.pop()
            if current_ref in component_refs:
                continue
            component_refs.add(current_ref)
            stack.extend(adjacency[current_ref] - component_refs)
        seen.update(component_refs)

        selected_by_user = {}
        for current_ref in component_refs:
            row = bucket_by_ref[current_ref]
            candidate = (
                overlap_scores[current_ref],
                -float(row.get('start_epoch') or 0.0),
                current_ref,
                row,
            )
            existing = selected_by_user.get(row['user_id'])
            if existing is None or candidate[:3] > existing[:3]:
                selected_by_user[row['user_id']] = candidate

        selected = sorted((candidate[3] for candidate in selected_by_user.values()), key=lambda row: row['start_epoch'])
        if len(selected) < 2:
            continue

        selected_refs = {row['session_ref'] for row in selected}
        selected_windows = [
            window for window in overlap_windows
            if window['left_ref'] in selected_refs and window['right_ref'] in selected_refs
        ]
        if not selected_windows:
            continue

        components.append({
            'session_refs': tuple(row['session_ref'] for row in selected),
            'start_epoch': min(window['start_epoch'] for window in selected_windows),
            'end_epoch': max(window['end_epoch'] for window in selected_windows),
            'overlap_window_count': len(selected_windows),
        })

    return components


def _build_groups(session_rows: List[Dict]) -> List[Dict]:
    by_bucket = defaultdict(list)
    for row in session_rows:
        date_key = row.get('date_key') or _session_date_key(row.get('start_time'))
        if not date_key:
            continue
        by_bucket[(int(row['track_id']), date_key)].append(row)

    groups = []
    for (track_id, date_key), bucket in by_bucket.items():
        if len(bucket) < 2:
            continue
        bucket.sort(key=lambda item: item['start_epoch'])
        bucket_by_ref = {row['session_ref']: row for row in bucket}
        for component_window in _session_overlap_components(bucket):
            component = [bucket_by_ref[session_ref] for session_ref in component_window['session_refs']]
            _apply_owner_labels(component)
            groups.append({
                'group_id': '%s@%.3f' % ('|'.join(sorted(component_window['session_refs'])), component_window['start_epoch']),
                'track_id': track_id,
                'track_name': component[0]['track_name'],
                'date': date_key,
                'rider_count': _rider_count(component),
                'session_count': len(component),
                'session_refs': [row['session_ref'] for row in component],
                'session_ids': [row['session_id'] for row in component],
                'start_epoch': min(row['start_epoch'] for row in component),
                'end_epoch': max(row['end_epoch'] for row in component),
                'focus_start_epoch': component_window['start_epoch'],
                'focus_end_epoch': component_window['end_epoch'],
                'overlap_window_count': component_window['overlap_window_count'],
                'participants': [
                    {
                        'session_id': row['session_id'],
                        'session_ref': row['session_ref'],
                        'user_id': row['user_id'],
                        'owner_name': row['owner_name'],
                        'owner_label': row.get('owner_label') or row['owner_name'],
                        'bike_info': row['bike_info'],
                        'best_lap_time': row['best_lap_time'],
                        'start_time': row['start_time'],
                    }
                    for row in component
                ],
            })

    groups.sort(key=lambda item: (item['focus_start_epoch'] or item['start_epoch'] or 0), reverse=True)
    return groups


def _minimal_manifest(manifest: Dict, start_epoch: float) -> Dict:
    columns = dict((manifest or {}).get('columns') or {})
    rel_times = columns.get('time') or []
    columns['time_epoch'] = [
        round(start_epoch + float(value), 3) if value is not None else None
        for value in rel_times
    ]
    columns['race_lat'] = columns.get('race_lat') or columns.get('lat') or []
    columns['race_lon'] = columns.get('race_lon') or columns.get('lon') or []
    return {
        'kind': manifest.get('kind'),
        'meta': manifest.get('meta') or {},
        'config': manifest.get('config') or {},
        'laps': manifest.get('laps') or [],
        'row_count': manifest.get('row_count') or 0,
        'overview_step': manifest.get('overview_step') or 1,
        'columns': columns,
    }


@race_view_bp.route('/api/race-view/groups')
def list_race_view_groups():
    _optional_auth()
    track_id = request.args.get('track_id', type=int)
    date = request.args.get('date', type=str)
    limit = max(1, min(int(request.args.get('limit', MAX_GROUPS) or MAX_GROUPS), 24))

    groups = _build_groups(_eligible_public_sessions(track_id=track_id, date=date))
    return jsonify(groups[:limit])


@race_view_bp.route('/api/race-view/detail')
def get_race_view_detail():
    _optional_auth()
    raw_session_refs = request.args.get('session_refs', '')
    session_refs = [value.strip() for value in raw_session_refs.split(',') if value.strip()]
    requested_focus_start = request.args.get('focus_start_epoch', type=float)
    requested_focus_end = request.args.get('focus_end_epoch', type=float)
    if (
        (requested_focus_start is None) != (requested_focus_end is None)
        or (
            requested_focus_start is not None
            and requested_focus_end is not None
            and requested_focus_end <= requested_focus_start
        )
    ):
        return jsonify({'error': 'focus_start_epoch and focus_end_epoch must define a valid window'}), 400
    if len(session_refs) < 2:
        return jsonify({'error': 'At least two session_refs are required'}), 400

    requested_pairs = []
    for raw_ref in session_refs:
        user_part, sep, session_part = raw_ref.partition(':')
        if not sep:
            continue
        try:
            requested_pairs.append((int(user_part), session_part))
        except ValueError:
            continue
    if len(requested_pairs) < 2:
        return jsonify({'error': 'At least two valid session_refs are required'}), 400

    metas = SessionMeta.query.filter(
        SessionMeta.is_public.is_(True),
        SessionMeta.user_id.in_([user_id for user_id, _ in requested_pairs]),
        SessionMeta.session_id.in_([session_id for _, session_id in requested_pairs]),
    ).all()
    by_ref = {_session_ref(meta.user_id, meta.session_id): meta for meta in metas}
    ordered_metas = [by_ref[ref] for ref in session_refs if ref in by_ref]

    if len(ordered_metas) < 2:
        return jsonify({'error': 'Race View requires at least two public sessions'}), 404

    track_ids = {meta.track_id for meta in ordered_metas}
    if len(track_ids) != 1:
        return jsonify({'error': 'All sessions must belong to the same track'}), 400
    track_id = ordered_metas[0].track_id

    resolved_track = resolve_track(track_id)
    if not resolved_track or resolved_track.get('track_scope') != 'global' or not resolved_track.get('has_canonical_layout'):
        return jsonify({'error': 'Race View requires a shared canonical track layout'}), 400

    layout = load_track_layout(resolved_track)
    if not layout:
        return jsonify({'error': 'Canonical layout not found'}), 404

    participants = []
    for meta in ordered_metas:
        playback_file = config.get_user_sessions_dir(meta.user_id) / f'{meta.session_id}_playback.json'
        payload = load_playback_payload(playback_file)
        if payload is None:
            continue
        if not _has_race_view_timestamp(meta, payload):
            continue
        start_epoch = _resolve_start_epoch(meta, payload)
        end_epoch = _session_end_epoch(meta, payload)
        if start_epoch is None or end_epoch is None:
            continue
        manifest = build_playback_manifest(payload, max_points=MAX_MANIFEST_POINTS)
        owner = User.query.get(meta.user_id)
        participants.append({
            'session_id': meta.session_id,
            'session_ref': _session_ref(meta.user_id, meta.session_id),
            'user_id': meta.user_id,
            'owner_name': owner.name if owner and owner.name else f'Rider {meta.user_id}',
            'bike_info': owner.bike_info if owner else '',
            'best_lap_time': meta.best_lap_time,
            'total_laps': meta.total_laps,
            'start_time': _resolve_start_value(meta, payload),
            'start_epoch': start_epoch,
            'end_epoch': end_epoch,
            'duration_sec': _resolve_duration_sec(meta, payload),
            'timestamp_source': _resolve_timestamp_source(meta, payload),
            'lap_windows': _lap_windows(payload, start_epoch),
            'playback': _minimal_manifest(manifest, start_epoch),
        })

    if len(participants) < 2:
        return jsonify({'error': 'Playback data unavailable for enough public sessions'}), 404
    if _rider_count(participants) != len(participants):
        return jsonify({'error': 'Race View accepts at most one session per rider'}), 400

    participants.sort(key=lambda item: item['start_epoch'])
    _apply_owner_labels(participants)
    overlap_windows = []
    for index, left in enumerate(participants):
        for right in participants[index + 1:]:
            if int(left.get('user_id') or 0) == int(right.get('user_id') or 0):
                continue
            for overlap in _lap_overlap_windows(left, right):
                overlap_windows.append({
                    **overlap,
                    'left_ref': left['session_ref'],
                    'right_ref': right['session_ref'],
                })
    if requested_focus_start is not None and requested_focus_end is not None:
        overlap_windows = [
            window for window in overlap_windows
            if window['start_epoch'] < requested_focus_end and window['end_epoch'] > requested_focus_start
        ]
    if not overlap_windows:
        return jsonify({'error': 'Race View requires at least one overlapping lap between different public riders'}), 404
    active_refs = {
        session_ref
        for window in overlap_windows
        for session_ref in (window['left_ref'], window['right_ref'])
    }
    if any(item['session_ref'] not in active_refs for item in participants):
        return jsonify({'error': 'All Race View sessions must participate in the selected overlap window'}), 400
    focus_start = requested_focus_start if requested_focus_start is not None else min(window['start_epoch'] for window in overlap_windows)
    focus_end = requested_focus_end if requested_focus_end is not None else max(window['end_epoch'] for window in overlap_windows)
    response_participants = []
    for item in participants:
        response_item = dict(item)
        response_item.pop('lap_windows', None)
        response_participants.append(response_item)

    return jsonify({
        'track': {
            'track_id': track_id,
            'track_name': get_track_display_name(track_id, user_id=ordered_metas[0].user_id),
        },
        'layout': layout,
        'timeline': {
            'start_epoch': min(item['start_epoch'] for item in participants),
            'end_epoch': max(item['end_epoch'] for item in participants),
            'focus_start_epoch': focus_start,
            'focus_end_epoch': focus_end,
        },
        'rider_count': _rider_count(participants),
        'session_count': len(participants),
        'overlap_window_count': len(overlap_windows),
        'participants': response_participants,
    })
