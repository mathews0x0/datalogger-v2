import os
import csv
import io
from typing import TextIO, Union
from src.analysis.core.models import Session, Sample, GPSSample, IMUSample, EnvSample

class CSVLoader:
    """
    Decoupled CSV Ingestion for Motorcycle Telemetry.
    Reads standard CSV format and produces a Session object.
    """
    
    def load(self, file_source: Union[str, TextIO], source_name: str = "Unknown") -> Session:
        """
        Load a CSV file into a Session.
        file_source: File path (str) or file-like object (TextIO).
        """
        
        # Handle file paths vs file objects
        should_close = False
        if isinstance(file_source, str):
            f = open(file_source, 'r', newline='')
            should_close = True
            source_name = os.path.basename(file_source)
        else:
            f = file_source # Already open
            
        try:
            reader = csv.DictReader(f)
            session = Session(description=source_name)
            
            for row in reader:
                try:
                    # Parse with defaults for missing columns
                    # 1. Timestamp (Required)
                    ts = float(row.get("timestamp") or row.get("time") or 0)
                    
                    # 2. GPS
                    gps = GPSSample(
                        lat=float(row.get("latitude") or row.get("lat") or 0.0), 
                        lon=float(row.get("longitude") or row.get("lon") or 0.0),
                        speed=float(row.get("speed") or 0.0),
                        sats=int(row.get("satellites") or 0)
                    )
                    
                    # 3. IMU
                    imu = IMUSample(
                        accel_x=float(row.get("imu_x") or row.get("accel_x") or row.get("acc_x") or 0.0),
                        accel_y=float(row.get("imu_y") or row.get("accel_y") or row.get("acc_y") or 0.0),
                        accel_z=float(row.get("imu_z") or row.get("accel_z") or row.get("acc_z") or 0.0),
                        gyro_x=float(row.get("gyro_x") or 0.0),
                        gyro_y=float(row.get("gyro_y") or 0.0),
                        gyro_z=float(row.get("gyro_z") or 0.0)
                    )
                    
                    # 4. Environment
                    # Handle legacy CSVs without temp
                    env = EnvSample(
                        temp=float(row.get("temp", row.get("temperature", 0.0)) or 0.0),
                        pressure=float(row.get("pressure") or 0.0)
                    )
                    
                    session.add_sample(Sample(ts, gps, imu, env))
                    
                except ValueError as e:
                    # Skip malformed rows
                    continue
                    
            return session
            
        finally:
            if should_close:
                f.close()
