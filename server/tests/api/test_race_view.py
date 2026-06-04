import json

import api.config as config
from api.models import GlobalTrack, SessionMeta, User, db
from api.blueprints.race_view import _build_groups, _has_race_view_timestamp


def _write_global_layout(track_id, folder_name):
    track_dir = config.get_global_track_dir(folder_name)
    layout_payload = {
        "svg_data_url": "data:image/svg+xml;base64,PHN2Zy8+",
        "preview_svg_data_url": "data:image/svg+xml;base64,PHN2Zy8+",
        "layout_width": 1000,
        "layout_height": 700,
        "geo_reference": {
            "lat0": 11.0,
            "lon0": 77.0,
            "metersPerDegLat": 111320.0,
            "metersPerDegLon": 109000.0,
        },
        "auto_align": {
            "scale": 1.0,
            "rotationDeg": 0.0,
            "translateX": 0.0,
            "translateY": 0.0,
        },
        "sampled_points": [
            {"canonical": {"x": 0, "y": 0}, "localMeters": {"x": 0, "y": 0}},
            {"canonical": {"x": 100, "y": 0}, "localMeters": {"x": 100, "y": 0}},
            {"canonical": {"x": 100, "y": 100}, "localMeters": {"x": 100, "y": 100}},
            {"canonical": {"x": 0, "y": 100}, "localMeters": {"x": 0, "y": 100}},
        ],
        "affine_fit": {
            "x_coeffs": [1, 0, 0],
            "y_coeffs": [0, 1, 0],
        },
    }
    track_json = {
        "track_id": track_id,
        "track_name": "Test Global Track",
        "sectors": [],
        "start_line": None,
        "centerline": [],
    }
    (track_dir / "layout_metadata.json").write_text(json.dumps(layout_payload))
    (track_dir / "track.json").write_text(json.dumps(track_json))


def _write_playback(user_id, session_id, lat_offset):
    return _write_playback_with_laps(
        user_id,
        session_id,
        lat_offset,
        laps=[{"lap_number": 1, "start_time": 0.0, "end_time": 120.0, "lap_time": 120.0}],
    )


def _write_playback_with_laps(user_id, session_id, lat_offset, laps):
    payload = {
        "meta": {
            "start_time": "2026-05-31T14:00:00+05:30",
            "duration_sec": 120.0,
            "timestamp_source": "gps_epoch",
        },
        "config": {},
        "laps": laps,
        "rows": [
            {
                "time": 0.0,
                "display_lat": 11.0 + lat_offset,
                "display_lon": 77.0,
                "aligned_lat": 11.0 + lat_offset,
                "aligned_lon": 77.0,
                "lap_number": 1,
            },
            {
                "time": 60.0,
                "display_lat": 11.0001 + lat_offset,
                "display_lon": 77.0001,
                "aligned_lat": 11.0001 + lat_offset,
                "aligned_lon": 77.0001,
                "lap_number": 1,
            },
            {
                "time": 120.0,
                "display_lat": 11.0002 + lat_offset,
                "display_lon": 77.0002,
                "aligned_lat": 11.0002 + lat_offset,
                "aligned_lon": 77.0002,
                "lap_number": 1,
            },
        ],
    }
    sessions_dir = config.get_user_sessions_dir(user_id)
    (sessions_dir / f"{session_id}_playback.json").write_text(json.dumps(payload))


def _write_playback_payload(user_id, session_id, payload):
    sessions_dir = config.get_user_sessions_dir(user_id)
    (sessions_dir / f"{session_id}_playback.json").write_text(json.dumps(payload))


def test_race_view_groups_and_detail(client, app):
    with app.app_context():
        user_a = User(email="a@example.com", name="Akhil", password_hash="x")
        user_b = User(email="b@example.com", name="Bharath", password_hash="x")
        db.session.add_all([user_a, user_b])
        db.session.flush()

        global_track = GlobalTrack(
            track_id=1000001,
            slug="test_global_track",
            track_name="Test Global Track",
            folder_name="test_global_track",
            package_version=1,
            layout_width=1000,
            layout_height=700,
            has_canonical_layout=True,
        )
        db.session.add(global_track)

        session_a = SessionMeta(
            session_id="sess_a",
            user_id=user_a.id,
            track_id=global_track.track_id,
            start_time="2026-05-31T14:00:00+05:30",
            duration_sec=900,
            total_laps=6,
            best_lap_time=108.2,
            is_public=True,
        )
        session_b = SessionMeta(
            session_id="sess_b",
            user_id=user_b.id,
            track_id=global_track.track_id,
            start_time="2026-05-31T14:05:00+05:30",
            duration_sec=780,
            total_laps=5,
            best_lap_time=107.9,
            is_public=True,
        )
        db.session.add_all([session_a, session_b])
        db.session.commit()

        _write_global_layout(global_track.track_id, global_track.folder_name)
        _write_playback(user_a.id, "sess_a", 0.0)
        _write_playback(user_b.id, "sess_b", 0.0003)

    groups_resp = client.get("/api/race-view/groups?track_id=1000001&date=2026-05-31")
    assert groups_resp.status_code == 200
    groups = groups_resp.get_json()
    assert len(groups) == 1
    assert groups[0]["rider_count"] == 2
    assert groups[0]["session_count"] == 2
    assert groups[0]["session_refs"] == [f"{user_a.id}:sess_a", f"{user_b.id}:sess_b"]
    assert sorted(groups[0]["session_ids"]) == ["sess_a", "sess_b"]
    assert [participant["owner_label"] for participant in groups[0]["participants"]] == ["Akhil", "Bharath"]

    detail_resp = client.get(f"/api/race-view/detail?session_refs={user_a.id}:sess_a,{user_b.id}:sess_b")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()
    assert detail["track"]["track_id"] == 1000001
    assert detail["rider_count"] == 2
    assert detail["session_count"] == 2
    assert len(detail["participants"]) == 2
    assert [participant["owner_label"] for participant in detail["participants"]] == ["Akhil", "Bharath"]
    assert "time_epoch" in detail["participants"][0]["playback"]["columns"]


def test_race_view_disambiguates_duplicate_owner_names(client, app):
    with app.app_context():
        user_a = User(email="dup-a@example.com", name="RaceSense Admin", password_hash="x")
        user_b = User(email="dup-b@example.com", name="RaceSense Admin", password_hash="x")
        db.session.add_all([user_a, user_b])
        db.session.flush()

        global_track = GlobalTrack(
            track_id=1000002,
            slug="duplicate_name_track",
            track_name="Duplicate Name Track",
            folder_name="duplicate_name_track",
            package_version=1,
            layout_width=1000,
            layout_height=700,
            has_canonical_layout=True,
        )
        db.session.add(global_track)

        session_a = SessionMeta(
            session_id="dup_sess_a",
            user_id=user_a.id,
            track_id=global_track.track_id,
            start_time="2026-05-31T15:00:00+05:30",
            duration_sec=900,
            total_laps=6,
            best_lap_time=91.961,
            is_public=True,
        )
        session_b = SessionMeta(
            session_id="dup_sess_b",
            user_id=user_b.id,
            track_id=global_track.track_id,
            start_time="2026-05-31T15:02:00+05:30",
            duration_sec=840,
            total_laps=6,
            best_lap_time=93.291,
            is_public=True,
        )
        db.session.add_all([session_a, session_b])
        db.session.commit()

        _write_global_layout(global_track.track_id, global_track.folder_name)
        _write_playback(user_a.id, "dup_sess_a", 0.0)
        _write_playback(user_b.id, "dup_sess_b", 0.0003)

    groups_resp = client.get("/api/race-view/groups?track_id=1000002&date=2026-05-31")
    assert groups_resp.status_code == 200
    groups = groups_resp.get_json()
    assert len(groups) == 1
    assert groups[0]["rider_count"] == 2
    assert [participant["owner_label"] for participant in groups[0]["participants"]] == [
        "RaceSense Admin 1",
        "RaceSense Admin 2",
    ]

    detail_resp = client.get(f"/api/race-view/detail?session_refs={user_a.id}:dup_sess_a,{user_b.id}:dup_sess_b")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()
    assert [participant["owner_label"] for participant in detail["participants"]] == [
        "RaceSense Admin 1",
        "RaceSense Admin 2",
    ]


def test_race_view_supports_same_session_id_across_different_users(client, app):
    with app.app_context():
        user_a = User(email="jinoop@example.com", name="Jinoop A", password_hash="x")
        user_b = User(email="admin@example.com", name="RaceSense Admin", password_hash="x")
        db.session.add_all([user_a, user_b])
        db.session.flush()

        global_track = GlobalTrack(
            track_id=1000003,
            slug="shared_session_id_track",
            track_name="Shared Session Id Track",
            folder_name="shared_session_id_track",
            package_version=1,
            layout_width=1000,
            layout_height=700,
            has_canonical_layout=True,
        )
        db.session.add(global_track)

        session_a = SessionMeta(
            session_id="sess_001",
            user_id=user_a.id,
            track_id=global_track.track_id,
            start_time="2026-05-31T16:00:00+05:30",
            duration_sec=900,
            total_laps=8,
            best_lap_time=91.050,
            is_public=True,
        )
        session_b = SessionMeta(
            session_id="sess_001",
            user_id=user_b.id,
            track_id=global_track.track_id,
            start_time="2026-05-31T16:02:00+05:30",
            duration_sec=885,
            total_laps=7,
            best_lap_time=93.291,
            is_public=True,
        )
        db.session.add_all([session_a, session_b])
        db.session.commit()

        _write_global_layout(global_track.track_id, global_track.folder_name)
        _write_playback(user_a.id, "sess_001", 0.0)
        _write_playback(user_b.id, "sess_001", 0.0003)

    groups_resp = client.get("/api/race-view/groups?track_id=1000003&date=2026-05-31")
    assert groups_resp.status_code == 200
    groups = groups_resp.get_json()
    assert len(groups) == 1
    assert groups[0]["rider_count"] == 2
    assert groups[0]["session_count"] == 2
    assert groups[0]["session_ids"] == ["sess_001", "sess_001"]
    assert groups[0]["session_refs"] == [f"{user_a.id}:sess_001", f"{user_b.id}:sess_001"]
    assert [participant["owner_name"] for participant in groups[0]["participants"]] == ["Jinoop A", "RaceSense Admin"]

    detail_resp = client.get(f"/api/race-view/detail?session_refs={user_a.id}:sess_001,{user_b.id}:sess_001")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()
    assert detail["rider_count"] == 2
    assert detail["session_count"] == 2
    assert [participant["owner_name"] for participant in detail["participants"]] == ["Jinoop A", "RaceSense Admin"]
    assert [participant["session_ref"] for participant in detail["participants"]] == [
        f"{user_a.id}:sess_001",
        f"{user_b.id}:sess_001",
    ]


def test_race_view_requires_actual_lap_overlap_between_different_users(client, app):
    with app.app_context():
        user_a = User(email="lap-a@example.com", name="Rider A", password_hash="x")
        user_b = User(email="lap-b@example.com", name="Rider B", password_hash="x")
        db.session.add_all([user_a, user_b])
        db.session.flush()

        global_track = GlobalTrack(
            track_id=1000004,
            slug="lap_overlap_track",
            track_name="Lap Overlap Track",
            folder_name="lap_overlap_track",
            package_version=1,
            layout_width=1000,
            layout_height=700,
            has_canonical_layout=True,
        )
        db.session.add(global_track)

        session_a = SessionMeta(
            session_id="lap_a",
            user_id=user_a.id,
            track_id=global_track.track_id,
            start_time="2026-05-31T17:00:00+05:30",
            duration_sec=600,
            total_laps=2,
            best_lap_time=60.0,
            is_public=True,
        )
        session_b = SessionMeta(
            session_id="lap_b",
            user_id=user_b.id,
            track_id=global_track.track_id,
            start_time="2026-05-31T17:00:30+05:30",
            duration_sec=600,
            total_laps=2,
            best_lap_time=60.0,
            is_public=True,
        )
        db.session.add_all([session_a, session_b])
        db.session.commit()

        _write_global_layout(global_track.track_id, global_track.folder_name)
        _write_playback_with_laps(
            user_a.id,
            "lap_a",
            0.0,
            laps=[
                {"lap_number": 1, "start_time": 0.0, "end_time": 60.0, "lap_time": 60.0},
                {"lap_number": 2, "start_time": 60.0, "end_time": 120.0, "lap_time": 60.0},
            ],
        )
        _write_playback_with_laps(
            user_b.id,
            "lap_b",
            0.0003,
            laps=[
                {"lap_number": 1, "start_time": 300.0, "end_time": 360.0, "lap_time": 60.0},
                {"lap_number": 2, "start_time": 360.0, "end_time": 420.0, "lap_time": 60.0},
            ],
        )

    groups_resp = client.get("/api/race-view/groups?track_id=1000004&date=2026-05-31")
    assert groups_resp.status_code == 200
    groups = groups_resp.get_json()
    assert groups == []


def test_race_view_prefers_playback_gps_start_time_over_session_meta(client, app):
    with app.app_context():
        user_a = User(email="gps-a@example.com", name="GPS A", password_hash="x")
        user_b = User(email="gps-b@example.com", name="GPS B", password_hash="x")
        db.session.add_all([user_a, user_b])
        db.session.flush()

        global_track = GlobalTrack(
            track_id=1000005,
            slug="gps_anchor_track",
            track_name="GPS Anchor Track",
            folder_name="gps_anchor_track",
            package_version=1,
            layout_width=1000,
            layout_height=700,
            has_canonical_layout=True,
        )
        db.session.add(global_track)

        session_a = SessionMeta(
            session_id="gps_anchor_a",
            user_id=user_a.id,
            track_id=global_track.track_id,
            start_time="2026-05-30T10:00:00+05:30",
            duration_sec=900,
            total_laps=1,
            best_lap_time=60.0,
            is_public=True,
        )
        session_b = SessionMeta(
            session_id="gps_anchor_b",
            user_id=user_b.id,
            track_id=global_track.track_id,
            start_time="2026-05-30T12:00:00+05:30",
            duration_sec=900,
            total_laps=1,
            best_lap_time=60.0,
            is_public=True,
        )
        db.session.add_all([session_a, session_b])
        db.session.commit()

        _write_global_layout(global_track.track_id, global_track.folder_name)
        _write_playback_payload(
            user_a.id,
            "gps_anchor_a",
            {
                "meta": {
                    "start_time": "2026-05-31T14:00:00+05:30",
                    "duration_sec": 120.0,
                    "timestamp_source": "gps_epoch",
                },
                "config": {},
                "laps": [{"lap_number": 1, "start_time": 0.0, "end_time": 60.0, "lap_time": 60.0}],
                "rows": [
                    {"time": 0.0, "display_lat": 11.0, "display_lon": 77.0, "aligned_lat": 11.0, "aligned_lon": 77.0, "lap_number": 1},
                    {"time": 60.0, "display_lat": 11.0001, "display_lon": 77.0001, "aligned_lat": 11.0001, "aligned_lon": 77.0001, "lap_number": 1},
                ],
            },
        )
        _write_playback_payload(
            user_b.id,
            "gps_anchor_b",
            {
                "meta": {
                    "start_time": "2026-05-31T14:00:20+05:30",
                    "duration_sec": 120.0,
                    "timestamp_source": "gps_epoch",
                },
                "config": {},
                "laps": [{"lap_number": 1, "start_time": 0.0, "end_time": 60.0, "lap_time": 60.0}],
                "rows": [
                    {"time": 0.0, "display_lat": 11.0003, "display_lon": 77.0, "aligned_lat": 11.0003, "aligned_lon": 77.0, "lap_number": 1},
                    {"time": 60.0, "display_lat": 11.0004, "display_lon": 77.0001, "aligned_lat": 11.0004, "aligned_lon": 77.0001, "lap_number": 1},
                ],
            },
        )

    groups_resp = client.get("/api/race-view/groups?track_id=1000005&date=2026-05-31")
    assert groups_resp.status_code == 200
    groups = groups_resp.get_json()
    assert len(groups) == 1
    assert groups[0]["focus_start_epoch"] is not None

    detail_resp = client.get(f"/api/race-view/detail?session_refs={user_a.id}:gps_anchor_a,{user_b.id}:gps_anchor_b")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()
    assert detail["timeline"]["focus_start_epoch"] is not None


def _group_row(session_id, user_id, start_epoch, end_epoch):
    return {
        "session_id": session_id,
        "session_ref": f"{user_id}:{session_id}",
        "user_id": user_id,
        "owner_name": f"Rider {user_id}",
        "bike_info": "",
        "track_id": 1000099,
        "track_name": "Group Track",
        "best_lap_time": 60.0,
        "total_laps": 1,
        "start_time": "2026-05-31T14:00:00+05:30",
        "date_key": "2026-05-31",
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "duration_sec": end_epoch - start_epoch,
        "timestamp_source": "gps_epoch",
        "lap_windows": [{
            "lap_number": 1,
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
            "lap_time": end_epoch - start_epoch,
        }],
    }


def test_race_view_rejects_relative_fallback_timestamps():
    meta = SessionMeta(start_time="1970-01-01T00:00:00+00:00")
    payload = {
        "meta": {
            "start_time": "1970-01-01T00:00:00+00:00",
            "duration_sec": 120.0,
            "timestamp_source": "relative_fallback",
        },
    }

    assert _has_race_view_timestamp(meta, payload) is False


def test_race_view_group_selects_only_one_session_per_rider():
    rows = [
        _group_row("a1", 1, 1000.0, 1100.0),
        _group_row("a2", 1, 1010.0, 1110.0),
        _group_row("b1", 2, 1020.0, 1090.0),
    ]

    groups = _build_groups(rows)

    assert groups
    assert all(group["rider_count"] == group["session_count"] == 2 for group in groups)
    assert all(len({participant["user_id"] for participant in group["participants"]}) == 2 for group in groups)


def test_race_view_collapses_separated_overlap_windows_into_one_session_group():
    rows = [
        _group_row("a1", 1, 1000.0, 1060.0),
        _group_row("b1", 2, 1020.0, 1140.0),
        _group_row("c1", 3, 1120.0, 1180.0),
    ]

    groups = _build_groups(rows)

    assert len(groups) == 1
    assert groups[0]["session_refs"] == ["1:a1", "2:b1", "3:c1"]
    assert groups[0]["start_epoch"] == 1000.0
    assert groups[0]["end_epoch"] == 1180.0
    assert groups[0]["focus_start_epoch"] == 1020.0
    assert groups[0]["focus_end_epoch"] == 1140.0
    assert groups[0]["overlap_window_count"] == 2
