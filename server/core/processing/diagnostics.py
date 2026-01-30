
import statistics
from typing import List, Dict, Optional, Any
from src.analysis.core.models import Session, Lap

class DiagnosticsEngine:
    """
    Phase 8.1: Diagnostic Intelligence Engine.
    Calculates statistical variance and consistency metrics for a session.
    Strict Adherence to 'Truth-First' (no coaching advice).
    """

    def analyze_session(self, session: Session, track_info: Dict = None) -> Dict:
        """
        Generates a diagnostic report for the session.
        """
        if not session.laps:
            return self._empty_report()

        # 1. Extract Valid Sector Data
        # We need to group times by sector index (S1, S2...)
        # Structure: { 0: [t1, t2...], 1: [...] }
        sector_collections: Dict[int, List[float]] = {}
        
        # Determine sector count
        sector_count = 0
        if track_info and 'sectors' in track_info:
            sector_count = len(track_info['sectors'])
        else:
            # Fallback helper if track_info not provided (infer from max key)
            for l in session.laps:
                for k in l.sector_times.keys():
                    if k.startswith('S') and k[1:].isdigit():
                        idx = int(k[1:]) - 1 # 0-indexed
                        sector_count = max(sector_count, idx + 1)

        # Initialize collections
        for i in range(sector_count):
            sector_collections[i] = []

        # Populate
        valid_laps = [l for l in session.laps if getattr(l, 'valid', True)]
        if len(valid_laps) < 2:
            return self._empty_report(reason="Insufficient valid laps (need 2+)")

        for lap in valid_laps:
            # Sort keys to map to 0-indices or use direct 'S{i+1}' lookup
            for i in range(sector_count):
                key = f"S{i+1}"
                val = lap.sector_times.get(key)
                if val is not None:
                    sector_collections[i].append(val)

        # 2. Calculate Stats per Sector
        sector_stats = []
        cv_scores = [] # Coefficient of Variation list for overall score

        for i in range(sector_count):
            values = sector_collections[i]
            stat = self._compute_stats(values)
            stat['sector_index'] = i
            stat['sector_label'] = f"Sector {i+1}"
            sector_stats.append(stat)
            
            if stat['cv'] is not None:
                cv_scores.append(stat['cv'])

        # 3. Overall Consistency Score
        # Simple metric: 100% - Average CV? 
        # If Average CV is 5% (0.05), Consistency is 95%.
        # If Average CV is 20% (0.20), Consistency is 80%.
        # Cap at 0.
        session_cv = statistics.mean(cv_scores) if cv_scores else 0.0
        consistency_score = max(0.0, 1.0 - session_cv) * 100.0

        # 4. Identify Variance Hotspots
        # Sort by CV descending (Highest variance first)
        sorted_by_variance = sorted(
            [s for s in sector_stats if s['cv'] is not None],
            key=lambda x: x['cv'],
            reverse=True
        )
        
        # Top 3 Hotspots
        hotspots = []
        for s in sorted_by_variance[:3]:
            hotspots.append({
                "sector_index": s['sector_index'],
                "sector_label": s['sector_label'],
                "cv_percent": round(s['cv'] * 100, 1),
                "std_dev": s['std_dev']
            })

        return {
            "version": "1.0",
            "consistency_score": round(consistency_score, 1),
            "consistency_label": self._classify_consistency(consistency_score),
            "sector_stats": sector_stats,
            "variance_hotspots": hotspots,
            "meta": {
                "valid_laps_analyzed": len(valid_laps)
            }
        }

    def _compute_stats(self, values: List[float]) -> Dict:
        """
        Calculates n, mean, stdev, cv for a list of floats.
        Safe for empty lists.
        """
        count = len(values)
        if count < 2:
            return {
                "count": count,
                "mean": None,
                "std_dev": None,
                "cv": None,
                "min": min(values) if values else None,
                "max": max(values) if values else None
            }
        
        mean_val = statistics.mean(values)
        stdev_val = statistics.stdev(values)
        
        # Coefficient of Variation (CV) = StDev / Mean
        # Avoid divide by zero
        cv_val = (stdev_val / mean_val) if mean_val > 0 else 0.0
        
        return {
            "count": count,
            "mean": round(mean_val, 3),
            "std_dev": round(stdev_val, 3),
            "cv": round(cv_val, 4), # Keep precision for internal calc
            "min": round(min(values), 3),
            "max": round(max(values), 3)
        }

    def _classify_consistency(self, score: float) -> str:
        """
        Returns a neutral label for the consistency score.
        Phase 8.3: Consistency Classification.
        """
        if score >= 98.0: return "Very Stable"
        if score >= 95.0: return "Stable"
        if score >= 90.0: return "Variable"
        return "Highly Variable"

    def _empty_report(self, reason: str = "No Data") -> Dict:
        return {
            "version": "1.0",
            "consistency_score": None,
            "sector_stats": [],
            "variance_hotspots": [],
            "meta": {"error": reason}
        }
