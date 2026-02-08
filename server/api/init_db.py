import os
import sys
from pathlib import Path

# Add current directory to path so 'import main' works
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from main import app, db, User, SessionMeta, TrackMeta, TrackDayMeta, Follow, Team, TeamMember, TeamInvite, Annotation
import config

def init_db():
    with app.app_context():
        # Create tables
        db.create_all()
        print("Database tables created.")

        # Create default admin user if it doesn't exist
        admin = User.query.filter_by(email='admin').first()
        if not admin:
            admin = User(
                email='admin',
                name='Admin',
                bike_info='System Default',
                home_track='N/A'
            )
            admin.set_password('admin123') # Default password
            db.session.add(admin)
            db.session.commit()
            print(f"Default admin user created with ID: {admin.id}")
        else:
            print(f"Admin user already exists with ID: {admin.id}")

        # Migrate existing tracks from registry.json
        registry_file = config.METADATA_DIR / "registry.json"
        if registry_file.exists():
            import json
            with open(registry_file, 'r') as f:
                registry = json.load(f)
                for track in registry.get('tracks', []):
                    # Check if already migrated
                    existing = TrackMeta.query.filter_by(track_id=track['track_id']).first()
                    if not existing:
                        tm = TrackMeta(
                            track_id=track['track_id'],
                            user_id=admin.id,
                            track_name=track['track_name'],
                            folder_name=track['folder_name']
                        )
                        db.session.add(tm)
            db.session.commit()
            print("Tracks migrated from registry.json")

        # Migrate existing sessions
        sessions_dir = config.SESSIONS_DIR
        if sessions_dir.exists():
            import json
            for filename in os.listdir(sessions_dir):
                if filename.endswith('.json') and not filename.endswith('_telemetry.json'):
                    session_id = filename.replace('.json', '')
                    existing = SessionMeta.query.filter_by(session_id=session_id).first()
                    if not existing:
                        try:
                            with open(sessions_dir / filename, 'r') as f:
                                data = json.load(f)
                                sm = SessionMeta(
                                    session_id=session_id,
                                    user_id=admin.id,
                                    track_id=data.get('track', {}).get('track_id'),
                                    session_name=data.get('meta', {}).get('session_name'),
                                    start_time=data.get('meta', {}).get('start_time'),
                                    duration_sec=data.get('meta', {}).get('duration_sec'),
                                    total_laps=data.get('summary', {}).get('total_laps', len(data.get('laps', []))),
                                    best_lap_time=data.get('summary', {}).get('best_lap_time')
                                )
                                db.session.add(sm)
                        except Exception as e:
                            print(f"Failed to migrate session {filename}: {e}")
            db.session.commit()
            print("Sessions migrated from disk.")

        # Migrate existing trackdays
        trackdays_file = config.DATA_DIR / "trackdays.json"
        if trackdays_file.exists():
            import json
            with open(trackdays_file, 'r') as f:
                trackdays = json.load(f)
                for td in trackdays:
                    existing = TrackDayMeta.query.filter_by(trackday_id=td['id']).first()
                    if not existing:
                        tdm = TrackDayMeta(
                            trackday_id=td['id'],
                            user_id=admin.id,
                            name=td.get('name'),
                            date=td.get('date')
                        )
                        db.session.add(tdm)
            db.session.commit()
            print("Trackdays migrated from trackdays.json")

if __name__ == "__main__":
    init_db()
