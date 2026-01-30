import os
import requests
import json
from pathlib import Path

class UpdateManager:
    def __init__(self, firmware_dir):
        """
        :param firmware_dir: Path to firmware/esp32 directory containing main.py, boot.py, lib/
        """
        self.firmware_dir = Path(firmware_dir)
        
    def get_file_list(self):
        """List all core files that should be synced to ESP32."""
        files = []
        
        # 1. Root files
        for f in self.firmware_dir.glob("*.py"):
            if f.name == "secrets.py": continue # Don't overwrite secrets unless needed?
            files.append({
                "local_path": f,
                "remote_path": f.name
            })
            
        # 2. Lib files
        lib_dir = self.firmware_dir / "lib"
        if lib_dir.exists():
            for f in lib_dir.glob("*.py"):
                files.append({
                    "local_path": f,
                    "remote_path": f"lib/{f.name}"
                })
                
        # 3. Drivers
        drivers_dir = self.firmware_dir / "drivers"
        if drivers_dir.exists():
            for f in drivers_dir.glob("*.py"):
                files.append({
                    "local_path": f,
                    "remote_path": f"drivers/{f.name}"
                })
                
        return files

    def push_update(self, device_ip, progress_callback=None):
        """Push all firmware files to device via WiFi."""
        files = self.get_file_list()
        total = len(files)
        success_count = 0
        failed = []
        
        for i, f_info in enumerate(files):
            try:
                local_path = f_info['local_path']
                remote_path = f_info['remote_path']
                
                if progress_callback:
                    progress_callback(i, total, f"Uploading {remote_path}...")
                
                with open(local_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # OTA POST to ESP32
                url = f"http://{device_ip}/update"
                data = {
                    "filename": remote_path,
                    "content": content
                }
                
                resp = requests.post(url, json=data, timeout=10)
                if resp.status_code == 200:
                    success_count += 1
                else:
                    failed.append(f"{remote_path}: {resp.status_code}")
            except Exception as e:
                failed.append(f"{f_info['remote_path']}: {str(e)}")
                
        # Finally reboot
        if success_count > 0:
            try:
                requests.post(f"http://{device_ip}/reboot", timeout=2)
            except:
                pass # Expected timeout during reboot
                
        return {
            "success": success_count == total,
            "total": total,
            "success_count": success_count,
            "failed": failed
        }
