from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
bcrypt = Bcrypt()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100))
    profile_photo = db.Column(db.String(255))
    bike_info = db.Column(db.String(255))
    home_track = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "profile_photo": self.profile_photo,
            "bike_info": self.bike_info,
            "home_track": self.home_track,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class SessionMeta(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    track_id = db.Column(db.Integer)
    session_name = db.Column(db.String(255))
    start_time = db.Column(db.String(100)) # Storing as string to match existing JSON format for now
    duration_sec = db.Column(db.Float)
    total_laps = db.Column(db.Integer)
    best_lap_time = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TrackMeta(db.Model):
    __tablename__ = 'tracks'
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    track_name = db.Column(db.String(255))
    folder_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TrackDayMeta(db.Model):
    __tablename__ = 'trackdays'
    id = db.Column(db.Integer, primary_key=True)
    trackday_id = db.Column(db.String(100), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(255))
    date = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
