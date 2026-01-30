import unittest
from src.analysis.processing.geo import haversine_distance

class TestGeoMath(unittest.TestCase):
    def test_haversine_distance(self):
        """Test Haversine distance between two known points."""
        # Point A: New York City (40.7128, -74.0060)
        # Point B: London (51.5074, -0.1278)
        # Expected Distance: ~5570 km
        
        lat1, lon1 = 40.7128, -74.0060
        lat2, lon2 = 51.5074, -0.1278
        
        dist_km = haversine_distance(lat1, lon1, lat2, lon2)
        
        # Allow small margin of error for standard earth radius diffs
        self.assertAlmostEqual(dist_km, 5570.0, delta=20.0)

    def test_zero_distance(self):
        """Distance to self should be 0."""
        dist = haversine_distance(10.0, 10.0, 10.0, 10.0)
        self.assertEqual(dist, 0.0)

    def test_small_distance(self):
        """Test small movement (1 degree lat ~= 111km)."""
        dist = haversine_distance(0, 0, 1.0, 0)
        self.assertAlmostEqual(dist, 111.0, delta=1.0)

if __name__ == '__main__':
    unittest.main()
