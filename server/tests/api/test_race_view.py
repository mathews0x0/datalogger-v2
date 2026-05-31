import json

import api.config as config
from api.models import GlobalTrack, SessionMeta, User, db


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
    payload = {
        "meta": {},
        "config": {},
        "laps": [{"lap_number": 1, "start_time": 0.0, "end_time": 120.0, "lap_time": 120.0}],
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
    assert sorted(groups[0]["session_ids"]) == ["sess_a", "sess_b"]

    detail_resp = client.get("/api/race-view/detail?session_ids=sess_a,sess_b")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()
    assert detail["track"]["track_id"] == 1000001
    assert len(detail["participants"]) == 2
    assert "time_epoch" in detail["participants"][0]["playback"]["columns"]
