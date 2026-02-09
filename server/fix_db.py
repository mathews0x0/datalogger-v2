
import json
import os
from pathlib import Path
import sys

# Add our paths
sys.path.append('/home/mj/datalogger-v2/server/api')

from main import app, db
from models import SessionMeta
import config

def fix_best_lap_times():
    with app.app_context():
        sessions = SessionMeta.query.all()
        print(f"Checking {len(sessions)} sessions...")
        
        for s in sessions:
            session_file = config.SESSIONS_DIR / f"{s.session_id}.json"
            if session_file.exists():
                try:
                    with open(session_file, 'r') as f:
                        data = json.load(f)
                        best = data.get('aggregates', {}).get('best_lap_time') or data.get('summary', {}).get('best_lap_time')
                        if best and s.best_lap_time is None:
                            print(f"Updating {s.session_id} best lap to {best}")
                            s.best_lap_time = best
                            
                        laps = data.get('summary', {}).get('total_laps') or data.get('aggregates', {}).get('total_laps') or len(data.get('laps', []))
                        if laps and (s.total_laps is None or s.total_laps == 0):
                            print(f"Updating {s.session_id} total laps to {laps}")
                            s.total_laps = laps
                except Exception as e:
                    print(f"Error processing {s.session_id}: {e}")
        
        db.session.commit()
        print("Done!")

if __name__ == "__main__":
    fix_best_lap_times()
