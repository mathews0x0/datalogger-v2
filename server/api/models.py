from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_bcrypt import Bcrypt
import uuid

from sqlalchemy import MetaData

convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

db = SQLAlchemy(metadata=MetaData(naming_convention=convention))
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
    subscription_tier = db.Column(db.String(20), default='free')
    subscription_expires_at = db.Column(db.DateTime, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    active_track_id = db.Column(db.Integer, nullable=True)
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
            "subscription_tier": self.subscription_tier,
            "subscription_expires_at": self.subscription_expires_at.isoformat() if self.subscription_expires_at else None,
            "is_admin": self.is_admin,
            "is_approved": self.is_approved,
            "active_track_id": self.active_track_id,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class SessionMeta(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint('session_id', 'user_id', name='_session_user_uc'),
    )
    track_id = db.Column(db.Integer)
    session_name = db.Column(db.String(255))
    start_time = db.Column(db.String(100)) # Storing as string to match existing JSON format for now
    duration_sec = db.Column(db.Float)
    total_laps = db.Column(db.Integer)
    best_lap_time = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # New fields for Phase 2: Privacy
    is_public = db.Column(db.Boolean, default=False)
    share_token = db.Column(db.String(100), unique=True, nullable=True)
    share_expires_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "track_id": self.track_id,
            "session_name": self.session_name,
            "start_time": self.start_time,
            "duration_sec": self.duration_sec,
            "total_laps": self.total_laps,
            "best_lap_time": self.best_lap_time,
            "is_public": self.is_public,
            "share_token": self.share_token,
            "share_expires_at": self.share_expires_at.isoformat() if self.share_expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class TrackMeta(db.Model):
    __tablename__ = 'tracks'
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint('track_id', 'user_id', name='_track_user_uc'),
    )
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

class Follow(db.Model):
    __tablename__ = 'follows'
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    following_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Team(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    logo_url = db.Column(db.String(255))
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "logo_url": self.logo_url,
            "owner_id": self.owner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class TeamMember(db.Model):
    __tablename__ = 'team_members'
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    role = db.Column(db.String(20), default='rider') # 'owner', 'coach', 'rider'
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "team_id": self.team_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None
        }

class TeamInvite(db.Model):
    __tablename__ = 'team_invites'
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Annotation(db.Model):
    __tablename__ = 'annotations'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lap_number = db.Column(db.Integer)
    sector_number = db.Column(db.Integer)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "author_id": self.author_id,
            "lap_number": self.lap_number,
            "sector_number": self.sector_number,
            "text": self.text,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class DeviceToken(db.Model):
    __tablename__ = 'device_tokens'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)  # rsk_<uuid4>
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_name = db.Column(db.String(100), default='RS-Core')
    revoked = db.Column(db.Boolean, default=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)  # Optional expiration
    last_sync = db.Column(db.DateTime, nullable=True)
    auto_analyse = db.Column(db.Boolean, default=True)
    
    # Telemetry data from heartbeat
    device_uid = db.Column(db.String(100), nullable=True)
    vbatt_sense = db.Column(db.Float, nullable=True)
    storage_sd_free = db.Column(db.Integer, nullable=True) # MB
    storage_sd_total = db.Column(db.Integer, nullable=True) # MB
    storage_flash_free = db.Column(db.Integer, nullable=True) # KB
    storage_flash_total = db.Column(db.Integer, nullable=True) # KB

    # Sync progress tracking
    is_syncing = db.Column(db.Boolean, default=False)
    last_sync_filename = db.Column(db.String(255), nullable=True)
    last_sync_chunk = db.Column(db.Integer, default=0)
    last_sync_total = db.Column(db.Integer, default=0)
    
    # Global batch tracking
    sync_global_current = db.Column(db.BigInteger, default=0)
    sync_global_total = db.Column(db.BigInteger, default=0)
    sync_total_files = db.Column(db.Integer, default=0)
    sync_current_file_index = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "token": self.token,
            "device_name": self.device_name,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at.isoformat() + 'Z' if self.revoked_at else None,
            "created_at": self.created_at.isoformat() + 'Z' if self.created_at else None,
            "last_sync": self.last_sync.isoformat() + 'Z' if self.last_sync else None,
            "expires_at": self.expires_at.isoformat() + 'Z' if self.expires_at else None,
            "device_uid": self.device_uid,
            "vbatt_sense": self.vbatt_sense,
            "storage_sd_free": self.storage_sd_free,
            "storage_sd_total": self.storage_sd_total,
            "storage_flash_free": self.storage_flash_free,
            "storage_flash_total": self.storage_flash_total,
            "is_syncing": self.is_syncing,
            "sync_filename": self.last_sync_filename,
            "sync_chunk": self.last_sync_chunk,
            "sync_total": self.last_sync_total,
            "sync_global_current": self.sync_global_current,
            "sync_global_total": self.sync_global_total,
            "sync_total_files": self.sync_total_files,
            "sync_current_file_index": self.sync_current_file_index,
            "auto_analyse": self.auto_analyse
        }

class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False) # e.g., 'analysis'
    status = db.Column(db.String(20), default='queued') # queued, running, complete, failed
    input_data = db.Column(db.Text) # JSON string
    result = db.Column(db.Text) # JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    error = db.Column(db.Text)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "status": self.status,
            "input_data": json.loads(self.input_data) if self.input_data else None,
            "result": json.loads(self.result) if self.result else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error
        }
