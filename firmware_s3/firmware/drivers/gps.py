# Minimal NMEA Parser for ESP32
# Handles GNRMC (Position/Speed) and GNGGA (Altitude/Satellites)

class GPS:
    def __init__(self, uart):
        self.uart = uart
        self.new_fix = False  # True when update() parsed a new RMC sentence
        self.health = {
            'lines_processed': 0,
            'checksum_failures': 0,
            'decode_failures': 0,
            'parse_failures': 0,
            'update_calls': 0,
            'last_lines_processed': 0,
            'max_lines_per_update': 0,
            'rmc_received': 0,
            'gga_received': 0,
        }
        self.last_fix = {
            'lat': None,
            'lon': None,
            'altitude': 0.0,
            'speed_kmh': 0.0,
            'satellites': 0,
            'timestamp': None,
            'date': None,
            'gps_timestamp': '',
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

    def update(self, max_lines=None):
        """Read available data from UART and parse up to max_lines to bound scheduler jitter."""
        self.new_fix = False
        self.health['update_calls'] += 1
        lines_processed = 0
        while self.uart.any():
            if max_lines is not None and lines_processed >= max_lines:
                break
            try:
                line = self.uart.readline()
                if not line: break
                
                # Convert bytes to string (ignoring errors)
                try:
                    line_str = line.decode('utf-8').strip()
                except:
                    self.health['decode_failures'] += 1
                    continue
                    
                if line_str.startswith('$'):
                    self._parse_nmea(line_str)
                    lines_processed += 1
                    self.health['lines_processed'] += 1
            except Exception:
                self.health['parse_failures'] += 1

        self.health['last_lines_processed'] = lines_processed
        if lines_processed > self.health['max_lines_per_update']:
            self.health['max_lines_per_update'] = lines_processed
                
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
            self.health['checksum_failures'] += 1
            return 
            
        parts = line.split(',')
        msg_id = parts[0][3:] # Remove $GN or $GP
        
        # RMC: Recommended Minimum Data (Time, Lat, Lon, Speed, Date)
        if msg_id == 'RMC':
            self.health['rmc_received'] += 1
            # $GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A
            # Index: 1=Time, 2=Status(A=OK), 3=Lat, 4=N, 5=Lon, 6=E, 7=Speed(Knots)
            if len(parts) < 10: return
            
            self.new_fix = True  # Mark that we got a fresh RMC sentence
            
            # Update timestamp regardless of fix validity (shows UART is working)
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
            
            # Parse date (field 9: ddmmyy)
            if len(parts) > 9 and parts[9]:
                self.last_fix['date'] = parts[9]
            
            # Build combined GPS timestamp string for CSV
            if self.last_fix['timestamp'] and self.last_fix['date']:
                # parts[1] is the HHMMSS.SS string. Keep decimals for 10Hz precision.
                self.last_fix['gps_timestamp'] = f"{self.last_fix['date']}_{parts[1]}"

        # GGA: Fix Data (Satellites, Altitude)
        elif msg_id == 'GGA':
            self.health['gga_received'] += 1
            # $GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
            # Index: 6=FixType, 7=Sats
            if len(parts) > 9:
                try:
                    self.last_fix['satellites'] = int(parts[7] or 0)
                except:
                    pass
                # Parse altitude (field 9)
                try:
                    self.last_fix['altitude'] = float(parts[9] or 0)
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

    def get_health(self):
        return self.health
