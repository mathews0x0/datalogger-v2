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

MIN_GROUP_OVERLAP_SEC = 120
MAX_GROUPS = 8
MAX_MANIFEST_POINTS = 1800


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


def _session_end_epoch(session_meta: SessionMeta) -> Optional[float]:
    start_epoch = _session_start_epoch(session_meta.start_time)
    duration = float(session_meta.duration_sec or 0.0)
    if start_epoch is None or duration <= 0:
        return None
    return start_epoch + duration


def _group_overlap(a: Dict, b: Dict) -> float:
    return min(a['end_epoch'], b['end_epoch']) - max(a['start_epoch'], b['start_epoch'])


def _focus_overlap_window(sessions: List[Dict]) -> tuple[Optional[float], Optional[float]]:
    events = []
    for item in sessions:
        events.append((item['start_epoch'], 1))
        events.append((item['end_epoch'], -1))
    if not events:
        return None, None
    events.sort(key=lambda pair: (pair[0], -pair[1]))

    active = 0
    focus_start = None
    focus_end = None
    previous_ts = None

    for ts, delta in events:
        if previous_ts is not None and active >= 2 and ts > previous_ts:
            if focus_start is None:
                focus_start = previous_ts
            focus_end = ts
        active += delta
        previous_ts = ts

    return focus_start, focus_end


def _eligible_public_sessions(track_id: Optional[int] = None, date: Optional[str] = None) -> List[Dict]:
    query = SessionMeta.query.filter(
        SessionMeta.is_public.is_(True),
        SessionMeta.track_id.isnot(None),
        SessionMeta.duration_sec.isnot(None),
        SessionMeta.duration_sec > 0,
    )
    if track_id:
        query = query.filter(SessionMeta.track_id == int(track_id))
    if date:
        query = query.filter(SessionMeta.start_time.like(f"{date}%"))

    sessions = []
    user_cache: Dict[int, Optional[User]] = {}
    track_cache: Dict[int, Dict] = {}

    for meta in query.order_by(SessionMeta.start_time.asc()).all():
        start_epoch = _session_start_epoch(meta.start_time)
        end_epoch = _session_end_epoch(meta)
        if start_epoch is None or end_epoch is None or end_epoch <= start_epoch:
            continue

        playback_file = config.get_user_sessions_dir(meta.user_id) / f"{meta.session_id}_playback.json"
        if not playback_file.exists():
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

        sessions.append({
            'session_id': meta.session_id,
            'user_id': meta.user_id,
            'owner_name': owner.name if owner and owner.name else f'Rider {meta.user_id}',
            'bike_info': owner.bike_info if owner else '',
            'track_id': meta.track_id,
            'track_name': get_track_display_name(meta.track_id, user_id=meta.user_id),
            'best_lap_time': meta.best_lap_time,
            'total_laps': meta.total_laps,
            'start_time': meta.start_time,
            'start_epoch': start_epoch,
            'end_epoch': end_epoch,
            'duration_sec': float(meta.duration_sec or 0.0),
        })
    return sessions


def _build_groups(session_rows: List[Dict], min_overlap_sec: int = MIN_GROUP_OVERLAP_SEC) -> List[Dict]:
    by_bucket = defaultdict(list)
    for row in session_rows:
        date_key = _session_date_key(row.get('start_time'))
        if not date_key:
            continue
        by_bucket[(int(row['track_id']), date_key)].append(row)

    groups = []
    for (track_id, date_key), bucket in by_bucket.items():
        if len(bucket) < 2:
            continue
        bucket.sort(key=lambda item: item['start_epoch'])
        adjacency = {item['session_id']: set() for item in bucket}
        for index, left in enumerate(bucket):
            for right in bucket[index + 1:]:
                if right['start_epoch'] - left['end_epoch'] > min_overlap_sec:
                    break
                if _group_overlap(left, right) >= min_overlap_sec:
                    adjacency[left['session_id']].add(right['session_id'])
                    adjacency[right['session_id']].add(left['session_id'])

        seen = set()
        for item in bucket:
            session_id = item['session_id']
            if session_id in seen or not adjacency[session_id]:
                continue
            stack = [session_id]
            component_ids = []
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                component_ids.append(current)
                stack.extend(adjacency[current] - seen)

            component = [next(row for row in bucket if row['session_id'] == sid) for sid in component_ids]
            component.sort(key=lambda row: row['start_epoch'])
            focus_start, focus_end = _focus_overlap_window(component)
            groups.append({
                'group_id': '|'.join(sorted(component_ids)),
                'track_id': track_id,
                'track_name': component[0]['track_name'],
                'date': date_key,
                'rider_count': len(component),
                'session_ids': [row['session_id'] for row in component],
                'start_epoch': min(row['start_epoch'] for row in component),
                'end_epoch': max(row['end_epoch'] for row in component),
                'focus_start_epoch': focus_start,
                'focus_end_epoch': focus_end,
                'participants': [
                    {
                        'session_id': row['session_id'],
                        'user_id': row['user_id'],
                        'owner_name': row['owner_name'],
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
    raw_session_ids = request.args.get('session_ids', '')
    session_ids = [value.strip() for value in raw_session_ids.split(',') if value.strip()]
    if len(session_ids) < 2:
        return jsonify({'error': 'At least two session_ids are required'}), 400

    metas = SessionMeta.query.filter(
        SessionMeta.is_public.is_(True),
        SessionMeta.session_id.in_(session_ids),
    ).all()
    by_id = {meta.session_id: meta for meta in metas}
    ordered_metas = [by_id[sid] for sid in session_ids if sid in by_id]
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
        start_epoch = _session_start_epoch(meta.start_time)
        end_epoch = _session_end_epoch(meta)
        if start_epoch is None or end_epoch is None:
            continue
        playback_file = config.get_user_sessions_dir(meta.user_id) / f'{meta.session_id}_playback.json'
        payload = load_playback_payload(playback_file)
        if payload is None:
            continue
        manifest = build_playback_manifest(payload, max_points=MAX_MANIFEST_POINTS)
        owner = User.query.get(meta.user_id)
        participants.append({
            'session_id': meta.session_id,
            'user_id': meta.user_id,
            'owner_name': owner.name if owner and owner.name else f'Rider {meta.user_id}',
            'bike_info': owner.bike_info if owner else '',
            'best_lap_time': meta.best_lap_time,
            'total_laps': meta.total_laps,
            'start_time': meta.start_time,
            'start_epoch': start_epoch,
            'end_epoch': end_epoch,
            'duration_sec': float(meta.duration_sec or 0.0),
            'playback': _minimal_manifest(manifest, start_epoch),
        })

    if len(participants) < 2:
        return jsonify({'error': 'Playback data unavailable for enough public sessions'}), 404

    participants.sort(key=lambda item: item['start_epoch'])
    focus_start, focus_end = _focus_overlap_window(participants)

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
        'participants': participants,
    })
