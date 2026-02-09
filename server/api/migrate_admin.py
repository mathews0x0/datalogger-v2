# server/api/migrate_admin.py
import sys
import os

# Add current directory to path so we can import models and main
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, User
from main import app

with app.app_context():
    # Add column if not exists (SQLite compatible)
    try:
        # Use text() for SQLAlchemy 2.0+ compatibility if needed, 
        # but the plan used db.engine.execute which might be legacy.
        # Let's try the plan's approach first.
        from sqlalchemy import text
        db.session.execute(text('ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0'))
        db.session.commit()
        print("Added is_admin column")
    except Exception as e:
        print(f"Column may already exist or error: {e}")
    
    # Set first user (ID=1) as admin
    user1 = User.query.get(1)
    if user1:
        user1.is_admin = True
        db.session.commit()
        print(f"User {user1.email} (ID=1) is now admin")
    else:
        print("User with ID=1 not found")
