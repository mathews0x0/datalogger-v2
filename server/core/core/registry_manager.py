import json
import os
import re
from typing import Dict, List, Optional
from datetime import datetime

class RegistryManager:
    """
    Manages the output/registry.json file.
    
    Core Principles:
    - track_id: Numeric, immutable identity
    - track_name: String, mutable, drives folder name
    - folder_name: Always synchronized with track_name
    
    Registry Format:
    {
      "next_id": 3,
      "tracks": [
        {
          "track_id": 1,
          "track_name": "kari_motor_speedway",
          "folder_name": "kari_motor_speedway",
          "created": "2025-12-25T13:05:30"
        },
        {
          "track_id": 2,
          "track_name": "test_track",
          "folder_name": "test_track",
          "created": "2025-12-25T14:00:00"
        }
      ]
    }
    """
    
    def __init__(self, registry_path: str = None):
        import src.config as config
        self.registry_path = registry_path or config.REGISTRY_FILE
        self.registry = self._load()
    
    def _load(self) -> Dict:
        if not os.path.exists(self.registry_path):
            return {"next_id": 1, "tracks": []}
        
        try:
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
                # Ensure next_id exists
                if "next_id" not in data:
                    data["next_id"] = len(data.get("tracks", [])) + 1
                return data
        except (json.JSONDecodeError, IOError):
            print(f"[RegistryManager] Warning: Could not load registry from {self.registry_path}")
            return {"next_id": 1, "tracks": []}
    
    def _save(self):
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        try:
            with open(self.registry_path, 'w') as f:
                json.dump(self.registry, f, indent=2)
        except IOError as e:
            print(f"[RegistryManager] Error saving registry: {e}")
    
    def register_track(self, track_id: int, track_name: str, folder_name: str = None):
        """
        Add or update track entry in registry.
        folder_name defaults to sanitized track_name if not provided.
        """
        if folder_name is None:
            folder_name = self.sanitize_name(track_name)
        
        # Check if track already exists
        for track in self.registry["tracks"]:
            if track["track_id"] == track_id:
                # Update existing
                track["track_name"] = track_name
                track["folder_name"] = folder_name
                track["last_updated"] = datetime.now().isoformat()
                self._save()
                return
        
        # Add new track
        self.registry["tracks"].append({
            "track_id": track_id,
            "track_name": track_name,
            "folder_name": folder_name,
            "created": datetime.now().isoformat()
        })
        
        # Update next_id if needed
        if track_id >= self.registry["next_id"]:
            self.registry["next_id"] = track_id + 1
        
        self._save()
        print(f"[RegistryManager] Registered track ID {track_id}: {track_name} -> {folder_name}/")
    
    def get_next_track_id(self) -> int:
        """Returns next available numeric track ID."""
        next_id = self.registry["next_id"]
        self.registry["next_id"] = next_id + 1
        self._save()
        return next_id
    
    def get_track_by_id(self, track_id: int) -> Optional[Dict]:
        """Get track entry by numeric ID."""
        for track in self.registry["tracks"]:
            if track["track_id"] == track_id:
                return track
        return None
    
    def get_track_by_folder(self, folder_name: str) -> Optional[Dict]:
        """Get track entry by folder name."""
        for track in self.registry["tracks"]:
            if track["folder_name"] == folder_name:
                return track
        return None
    
    def get_folder_name(self, track_id: int) -> Optional[str]:
        """Get folder name for a track ID."""
        track = self.get_track_by_id(track_id)
        return track["folder_name"] if track else None
    
    def list_tracks(self) -> List[Dict]:
        """Get all registered tracks."""
        return self.registry["tracks"]
    
    def update_track_name(self, track_id: int, new_name: str, new_folder: str = None):
        """
        Update track name and folder name.
        Used by rename utility.
        """
        if new_folder is None:
            new_folder = self.sanitize_name(new_name)
        
        for track in self.registry["tracks"]:
            if track["track_id"] == track_id:
                track["track_name"] = new_name
                track["folder_name"] = new_folder
                track["last_updated"] = datetime.now().isoformat()
                self._save()
                return True
        return False

    def delete_track(self, track_id: int) -> bool:
        """Remove track from registry."""
        for i, track in enumerate(self.registry["tracks"]):
            if track["track_id"] == track_id:
                del self.registry["tracks"][i]
                self._save()
                print(f"[RegistryManager] Deleted track ID {track_id}")
                return True
        return False
    
    @staticmethod
    def sanitize_name(name: str) -> str:
        """
        Convert human name to safe folder name.
        - Lowercase
        - Spaces → underscores
        - Remove special chars
        """
        # Lowercase
        name = name.lower()
        # Spaces to underscores
        name = name.replace(" ", "_")
        # Remove non-alphanumeric except underscores
        name = re.sub(r'[^a-z0-9_]', '', name)
        # Collapse multiple underscores
        name = re.sub(r'_+', '_', name)
        # Strip leading/trailing underscores
        name = name.strip('_')
        
        return name or "unnamed_track"

