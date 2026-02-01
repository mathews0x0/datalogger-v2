"""
MicroPython driver for SD cards using SPI bus.

Requires an SPI bus and a CS pin.  Provides readblocks and writeblocks
methods so the device can be mounted as a filesystem.

Example usage:

    import machine, os
    import sdcard

    # Initialize SPI
    spi = machine.SPI(1, baudrate=10000000, polarity=0, phase=0, sck=machine.Pin(18), mosi=machine.Pin(23), miso=machine.Pin(19))
    
    # Initialize SD Card
    sd = sdcard.SDCard(spi, machine.Pin(5))
    
    # Mount filesystem
    os.mount(sd, '/sd')
"""

from micropython import const
import time

_CMD_TIMEOUT = const(1000)

_R1_IDLE_STATE = const(1 << 0)
_R1_ERASE_RESET = const(1 << 1)
_R1_ILLEGAL_COMMAND = const(1 << 2)
_R1_COM_CRC_ERROR = const(1 << 3)
_R1_ERASE_SEQUENCE_ERROR = const(1 << 4)
_R1_ADDRESS_ERROR = const(1 << 5)
_R1_PARAMETER_ERROR = const(1 << 6)
_TOKEN_CMD25 = const(0xFC)
_TOKEN_STOP_TRAN = const(0xFD)
_TOKEN_DATA = const(0xFE)

class SDCard:
    def __init__(self, spi, cs, baudrate=1320000):
        self.spi = spi
        self.cs = cs

        self.cmdbuf = bytearray(6)
        self.dummybuf = bytearray(512)
        self.tokenbuf = bytearray(1)
        for i in range(512):
            self.dummybuf[i] = 0xFF
        self.dummybuf_memoryview = memoryview(self.dummybuf)

        # Init CS pin
        self.cs.init(self.cs.OUT, value=1)

        # Init SPI
        # self.init_spi(baudrate)

        # Drive for 80 clock cycles
        self.cs.init(self.cs.OUT, value=1)
        for i in range(16):
            self.spi.write(b'\xff')

        # CMD0: init card; should return _R1_IDLE_STATE (0x01)
        # or 0x00 if already initialized
        # CMD0: init card; should return _R1_IDLE_STATE (0x01)
        # or 0x00 if already initialized
        res = self.cmd(0, 0, 0x95)
        if res != _R1_IDLE_STATE and res != 0x00:
            print(f"[SD_DEBUG] CMD0 Failed. Response: {hex(res)}")
            raise OSError("no SD card")


        # CMD8: SEND_IF_COND
        # 0x1AA: VHS=1 (2.7-3.6V), Check Pattern=0xAA
        if self.cmd(8, 0x1AA, 0x87, 4) == _R1_IDLE_STATE:
            self.init_card_v2()
        else:
            self.init_card_v1()

        # CMD16: SET_BLOCKLEN
        if self.cmd(16, 512, 0) != 0:
            raise OSError("can't set 512 block size")

        # self.init_spi(400000) # 400kHz for stability

    def init_spi(self, baudrate):
        try:
            master = self.spi.MASTER
        except AttributeError:
            # on ESP8266 or SoftSPI
            self.spi.init(baudrate=baudrate, phase=0, polarity=0)
        else:
            # on ESP32 HardSPI
            self.spi.init(master, baudrate=baudrate, phase=0, polarity=0)

    def init_card_v1(self):
        for i in range(_CMD_TIMEOUT):
            self.cmd(55, 0, 0)
            if self.cmd(41, 0, 0) == 0:
                self.cdv = 512
                # print("[SDCard] v1 card")
                return
        raise OSError("timeout waiting for v1 card")

    def init_card_v2(self):
        for i in range(_CMD_TIMEOUT):
            time.sleep_ms(50)
            self.cmd(58, 0, 0, 4)
            self.cmd(55, 0, 0)
            if self.cmd(41, 0x40000000, 0) == 0:
                self.cmd(58, 0, 0, 4)
                self.cdv = 1
                # print("[SDCard] v2 card")
                return
        raise OSError("timeout waiting for v2 card")

    def ioctl(self, op, arg):
        if op == 4:  # get number of blocks
            return 0 # simplified
        if op == 5:  # get block size
            return 512


    def cmd(self, cmd, arg, crc, final=0, release=True, skip1=False):
        self.cs(0)

        # create and send the command
        buf = self.cmdbuf
        buf[0] = 0x40 | cmd
        buf[1] = arg >> 24
        buf[2] = arg >> 16
        buf[3] = arg >> 8
        buf[4] = arg
        buf[5] = crc
        self.spi.write(buf)

        if skip1:
            self.spi.readinto(self.tokenbuf, 0xFF)

        # wait for the response (response[7] == 0)
        for i in range(_CMD_TIMEOUT):
            self.spi.readinto(self.tokenbuf, 0xFF)
            response = self.tokenbuf[0]
            # print(f"DEBUG: {hex(response)}") # Trace every byte
            if not (response & 0x80):
                # this could be a r1 or a r2 response
                # for a r2, response, we have 16 bits, which is the 1st byte (status)
                # plus the 2nd byte (which is 0).
                if cmd == 13:
                    self.spi.readinto(self.tokenbuf, 0xFF)
                # for r3 and r7, we have 5 bytes (status + 4 data bytes)
                if final > 0:
                    self.spi.readinto(self.tokenbuf, 0xFF)
                    if final > 1:
                        self.spi.readinto(self.tokenbuf, 0xFF)
                        if final > 2:
                            self.spi.readinto(self.tokenbuf, 0xFF)
                            if final > 3:
                                self.spi.readinto(self.tokenbuf, 0xFF)
                if release:
                    self.cs(1)
                    self.spi.write(b'\xff')
                # print(f"  CMD{cmd} -> {hex(response)}") # Cleaned up logs
                return response


        # timeout
        self.cs(1) # Re-enable if needed for debug
        self.spi.write(b'\xff')
        return -1

    def readblocks(self, block_num, buf):
        nblocks = len(buf) // 512
        assert nblocks and not len(buf) % 512, 'Buffer length is invalid'
        if nblocks == 1:
            # CMD17: READ_SINGLE_BLOCK
            if self.cmd(17, block_num * self.cdv, 0, release=False) != 0:
                return 1
            # wait for the start block token
            for i in range(100000): # Extremely high persistence
                self.spi.readinto(self.tokenbuf, 0xFF)
                if self.tokenbuf[0] == _TOKEN_DATA:
                    break
            else:
                self.cs(1)
                raise OSError("timeout waiting for response")



            # read the data
            self.spi.readinto(buf)
            # read CRC checksum (2 bytes)
            self.spi.write(b'\xff')
            self.spi.write(b'\xff')
            self.cs(1)
            self.spi.write(b'\xff')
            return 0
        else:
            # CMD18: READ_MULTIPLE_BLOCK
            if self.cmd(18, block_num * self.cdv, 0, release=False) != 0:
                return 1
            offset = 0
            while nblocks:
                # wait for the start block token
                for i in range(100000):
                    self.spi.readinto(self.tokenbuf, 0xFF)
                    if self.tokenbuf[0] == _TOKEN_DATA:
                        break
                else:
                    self.cs(1)
                    raise OSError("timeout waiting for response")
                # read the data
                self.spi.readinto(buf[offset : offset + 512])
                offset += 512
                nblocks -= 1
                # read CRC checksum (2 bytes)
                self.spi.write(b'\xff')
                self.spi.write(b'\xff')
            # CMD12: STOP_TRANSMISSION
            if self.cmd(12, 0, 0xFF, skip1=True) != 0:
                raise OSError("CMD12 failed")
            self.cs(1)
            self.spi.write(b'\xff')
            return 0

    def writeblocks(self, block_num, buf):
        nblocks = len(buf) // 512
        assert nblocks and not len(buf) % 512, 'Buffer length is invalid'
        if nblocks == 1:
            # CMD24: WRITE_BLOCK
            if self.cmd(24, block_num * self.cdv, 0, release=False) != 0:
                return 1
            # send the token
            self.spi.write(bytearray([_TOKEN_DATA]))
            # send the data
            self.spi.write(buf)
            # send CRC checksum (2 bytes)
            self.spi.write(b'\xff')
            self.spi.write(b'\xff')
            # check the response
            if (self.spi.read(1)[0] & 0x1F) != 0x05:
                self.cs(1)
                self.spi.write(b'\xff')
                return 1
            # wait for write to finish
            while not self.spi.read(1)[0]:
                pass
            self.cs(1)
            self.spi.write(b'\xff')
            return 0
        else:
            # CMD25: WRITE_MULTIPLE_BLOCK
            if self.cmd(25, block_num * self.cdv, 0, release=False) != 0:
                return 1
            # send the data
            offset = 0
            while nblocks:
                self.spi.write(bytearray([_TOKEN_CMD25]))
                self.spi.write(buf[offset : offset + 512])
                offset += 512
                nblocks -= 1
                self.spi.write(b'\xff')
                self.spi.write(b'\xff')
                if (self.spi.read(1)[0] & 0x1F) != 0x05:
                    self.cs(1)
                    self.spi.write(b'\xff')
                    return 1
                while not self.spi.read(1)[0]:
                    pass
            # stop transmission token
            self.spi.write(bytearray([_TOKEN_STOP_TRAN]))
            # wait for write to finish
            while not self.spi.read(1)[0]:
                pass
            self.cs(1)
            self.spi.write(b'\xff')
            return 0
    def ioctl(self, op, arg):
        if op == 4:  # get number of blocks
            return self.sectors
        if op == 5:  # get block size
            return 512
