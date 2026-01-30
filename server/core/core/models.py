from dataclasses import dataclass
from typing import List, Optional
import bisect

@dataclass(frozen=True)
class GPSSample:
    lat: float
    lon: float
    speed: float    # km/h
    sats: int

@dataclass(frozen=True)
class IMUSample:
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: Optional[float] = None
    gyro_y: Optional[float] = None
    gyro_z: Optional[float] = None

@dataclass(frozen=True)
class EnvSample:
    temp: float
    pressure: float

@dataclass(frozen=True)
class Sample:
    timestamp: float # Unix Epoch
    gps: GPSSample
    imu: IMUSample
    env: EnvSample

class Session:
    """
    A container for a continuous sequence of Samples.
    """
    def __init__(self, description: str = "", samples: List[Sample] = None):
        self.description = description
        self.samples: List[Sample] = samples if samples else []

    def add_sample(self, sample: Sample):
        self.samples.append(sample)

    @property
    def start_time(self) -> float:
        return self.samples[0].timestamp if self.samples else 0.0

    @property
    def end_time(self) -> float:
        return self.samples[-1].timestamp if self.samples else 0.0

    @property
    def duration(self) -> float:
        if not self.samples:
            return 0.0
        return self.end_time - self.start_time

    def __len__(self):
        return len(self.samples)

    def slice(self, start_ts: float, end_ts: float) -> 'Session':
        """
        Returns a new Session containing samples within [start_ts, end_ts].
        Uses binary search for efficiency.
        """
        if not self.samples:
            return Session(description=f"Slice of {self.description}")

        # Extract timestamps for searching (optimization: could be cached)
        timestamps = [s.timestamp for s in self.samples]
        
        start_idx = bisect.bisect_left(timestamps, start_ts)
        end_idx = bisect.bisect_right(timestamps, end_ts)
        
        subset = self.samples[start_idx:end_idx]
        return Session(description=f"Slice of {self.description}", samples=subset)

class Lap(Session):
    """
    A specific slice of a Session representing one circuit.
    """
    def __init__(self, session: Session, start_index: int, end_index: int, number: int):
        # Initialize with the subset of samples
        super().__init__(
            description=f"Lap {number} of {session.description}",
            samples=session.samples[start_index:end_index]
        )
        self.lap_number = number
        self.sector_times = {} # {'s1': 23.4, 's2': 45.1}

