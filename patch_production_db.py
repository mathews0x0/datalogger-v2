import sqlite3
import os

db_path = 'server/data/racesense.db'
if not os.path.exists(db_path):
    print("DB not found")
    exit()

conn = sqlite3.connect(db_path)
cur = conn.cursor()

def patch_table(table_name, create_sql):
    try:
        print(f"Patching {table_name} table...")
        # 1. Backup old data
        cur.execute(f"SELECT * FROM {table_name}")
        rows = cur.fetchall()
        
        # 2. Get column names
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = [c[1] for c in cur.fetchall()]
        col_names = ", ".join(cols)
        placeholders = ", ".join(["?"] * len(cols))
        
        # 3. Drop table
        cur.execute(f"DROP TABLE {table_name}")
        
        # 4. Recreate table
        cur.execute(create_sql)
        
        # 5. Restore data
        cur.executemany(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})", rows)
        print(f"  {table_name} patched successfully.")
    except Exception as e:
        print(f"  Failed to patch {table_name}: {e}")
        raise e

try:
    # 1. Patch sessions (Relax uniqueness to per-user)
    sessions_sql = """
    CREATE TABLE sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id VARCHAR(100) NOT NULL,
        user_id INTEGER NOT NULL,
        track_id INTEGER,
        session_name VARCHAR(255),
        start_time VARCHAR(100),
        duration_sec FLOAT,
        total_laps INTEGER,
        best_lap_time FLOAT,
        created_at DATETIME,
        is_public BOOLEAN,
        share_token VARCHAR(100),
        share_expires_at DATETIME,
        FOREIGN KEY(user_id) REFERENCES users (id),
        UNIQUE (session_id, user_id)
    )
    """
    
    # 2. Patch tracks (Relax uniqueness to per-user)
    tracks_sql = """
    CREATE TABLE tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        track_name VARCHAR(255),
        folder_name VARCHAR(255),
        created_at DATETIME,
        FOREIGN KEY(user_id) REFERENCES users (id),
        UNIQUE (track_id, user_id)
    )
    """

    # 3. Patch annotations (Change link to numeric ID)
    # We need to bridge the session_id string to the numeric id
    print("Patching annotations table...")
    cur.execute("SELECT id, session_id, author_id, lap_number, sector_number, text, created_at FROM annotations")
    old_annos = cur.fetchall()
    
    # Drop and recreate
    cur.execute("DROP TABLE annotations")
    cur.execute("""
    CREATE TABLE annotations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        author_id INTEGER NOT NULL,
        lap_number INTEGER,
        sector_number INTEGER,
        text TEXT NOT NULL,
        created_at DATETIME,
        FOREIGN KEY(session_id) REFERENCES sessions (id),
        FOREIGN KEY(author_id) REFERENCES users (id)
    )
    """)
    
    # Re-insert by looking up the correct numeric session ID
    for a in old_annos:
        a_id, s_str, u_id, lap, sec, text, created = a
        # Find the session record for this user with this string ID
        cur.execute("SELECT id FROM sessions WHERE session_id = ? AND user_id = ?", (s_str, u_id))
        s_row = cur.fetchone()
        if s_row:
            cur.execute("INSERT INTO annotations (session_id, author_id, lap_number, sector_number, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (s_row[0], u_id, lap, sec, text, created))
    
    patch_table('tracks', tracks_sql)
    patch_table('sessions', sessions_sql)
    
    conn.commit()
    print("\nProduction database siloed successfully.")
except Exception as e:
    conn.rollback()
    print(f"\nMigration failed: {e}")
finally:
    conn.close()
