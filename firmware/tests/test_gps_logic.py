from drivers.gps import GPS


class MockUART:
    def __init__(self, lines):
        self.lines = [line.encode() for line in lines]

    def any(self):
        return len(self.lines)

    def readline(self):
        if not self.lines:
            return None
        return self.lines.pop(0)

    def write(self, data):
        return len(data)


def test_gps_update_budget_and_health():
    uart = MockUART([
        "$GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*74\r\n",
        "$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59\r\n",
        "$GNRMC,123520,V,,,,,,,230394,,,N*53\r\n",
    ])
    gps = GPS(uart)

    fix = gps.update(max_lines=2)
    health = gps.get_health()

    assert health["last_lines_processed"] == 2
    assert health["rmc_received"] >= 1
    assert health["gga_received"] >= 1
    assert fix["lat"] is not None
    assert fix["satellites"] == 8


if __name__ == "__main__":
    test_gps_update_budget_and_health()
    print("GPS logic tests passed")
