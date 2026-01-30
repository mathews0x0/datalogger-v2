# Minimal NMEA Parser for ESP32
# Handles GNRMC (Position/Speed) and GNGGA (Altitude/Satellites)

class GPS:
    def __init__(self, uart):
        self.uart = uart
        self.last_fix = {
            'lat': None,
            'lon': None,
            'speed_kmh': 0.0,
            'satellites': 0,
            'timestamp': None,
            'valid': False
        }
        
    def send_ubx(self, msg_class, msg_id, payload):
        """Send a UBX binary command with automatic checksum calculation"""
        header = b'\xb5\x62'
        length = len(payload).to_bytes(2, 'little')
        msg = bytes([msg_class, msg_id]) + length + payload
        
        # Calculate Checksum
        ck_a, ck_b = 0, 0
        for b in msg:
            ck_a = (ck_a + b) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
            
        full_msg = header + msg + bytes([ck_a, ck_b])
        self.uart.write(full_msg)

    def set_baudrate(self, baud):
        """Configure GPS module UART baud rate (CFG-PRT)"""
        # Pre-calculated for common rates
        if baud == 115200:
            payload = b'\x01\x00\x00\x00\xd0\x08\x00\x00\x00\xc2\x01\x00\x07\x00\x03\x00\x00\x00\x00\x00'
        elif baud == 38400:
            payload = b'\x01\x00\x00\x00\xd0\x08\x00\x00\x00\x96\x00\x00\x07\x00\x03\x00\x00\x00\x00\x00'
        else:
            payload = b'\x01\x00\x00\x00\xd0\x08\x00\x00'
            payload += baud.to_bytes(4, 'little')
            payload += b'\x07\x00\x03\x00\x00\x00\x00\x00'
        
        self.send_ubx(0x06, 0x00, payload)

    def set_rate(self, hz):
        """Configure GPS measurement rate (CFG-RATE) and disable unused messages"""
        interval = int(1000 / hz)
        # measRate, navRate=1, timeRef=1(UTC)
        payload = interval.to_bytes(2, 'little') + b'\x01\x00\x01\x00'
        self.send_ubx(0x06, 0x08, payload)
        
        # Disable GSV, GLL, VTG, GSA to save UART bandwidth
        # CFG-MSG: [Class, ID, Rate]
        self.send_ubx(0x06, 0x01, b'\xf0\x03\x00') # GSV
        self.send_ubx(0x06, 0x01, b'\xf0\x01\x00') # GLL
        self.send_ubx(0x06, 0x01, b'\xf0\x05\x00') # VTG
        self.send_ubx(0x06, 0x01, b'\xf0\x02\x00') # GSA

    def update(self):
        """Read all available data from UART and parse. Don't block."""
        while self.uart.any():
            try:
                line = self.uart.readline()
                if not line: break
                
                # Convert bytes to string (ignoring errors)
                try:
                    line_str = line.decode('utf-8').strip()
                except:
                    continue
                    
                if line_str.startswith('$'):
                    self._parse_nmea(line_str)
            except Exception:
                pass 
                
        return self.last_fix

    def _chk(self, line):
        """Verify NMEA Checksum"""
        try:
            pt = line.split('*')
            if len(pt) != 2: return False
            content = pt[0][1:] # Skip $
            checksum_received = int(pt[1], 16)
            
            calc = 0
            for char in content:
                calc ^= ord(char)
                
            return calc == checksum_received
        except:
            return False

    def _parse_nmea(self, line):
        if not self._chk(line):
            return 
            
        parts = line.split(',')
        msg_id = parts[0][3:] # Remove $GN or $GP
        
        # RMC: Recommended Minimum Data (Time, Lat, Lon, Speed, Date)
        if msg_id == 'RMC':
            # $GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A
            # Index: 1=Time, 2=Status(A=OK), 3=Lat, 4=N, 5=Lon, 6=E, 7=Speed(Knots)
            if len(parts) < 10: return
            
            # Update timestamp regardless of fix validy (shows UART is working)
            if parts[1]:
                self.last_fix['timestamp'] = parts[1]
            
            valid = parts[2] == 'A'
            self.last_fix['valid'] = valid
            
            if valid:
                self.last_fix['lat'] = self._dm_to_dd(parts[3], parts[4])
                self.last_fix['lon'] = self._dm_to_dd(parts[5], parts[6])
                
                try:
                    knots = float(parts[7] or 0)
                    self.last_fix['speed_kmh'] = knots * 1.852
                except:
                    pass

        # GGA: Fix Data (Satellites, Altitude)
        elif msg_id == 'GGA':
            # $GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
            # Index: 6=FixType, 7=Sats
            if len(parts) < 8: return
            
            try:
                self.last_fix['satellites'] = int(parts[7] or 0)
            except:
                pass

    def _dm_to_dd(self, val, hemi):
        """Convert DegMin (ddmm.mmmm) to Decimal Degrees"""
        if not val or not hemi: return None
        try:
            dot = val.find('.')
            if dot == -1: return None
            
            degrees = float(val[:dot-2])
            minutes = float(val[dot-2:])
            calc = degrees + (minutes / 60.0)
            
            if hemi == 'S' or hemi == 'W':
                calc = -calc
                
            return calc
        except:
            return None
