
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Iterable

import numpy as np
import pandas as pd

KOMB_ABC = [
    ("A1", "B2", "C3", "D4"),
    ("A2", "B3", "C4", "D1"),
    ("A3", "B4", "C1", "D2"),
    ("A4", "B1", "C2", "D3"),
    ("A1", "C2", "D3", "B4"),
    ("A2", "C3", "D4", "B1"),
    ("A3", "C4", "D1", "B2"),
    ("A4", "C1", "D2", "B3"),
]

GROUPS = [f"{main}{sub}" for main in "ABCD" for sub in range(1, 5)]

GROUP_CENTERS = {
    "A1": (38.690, 29.370), "A2": (38.700, 29.390),
    "A3": (38.710, 29.410), "A4": (38.695, 29.430),
    "B1": (38.675, 29.375), "B2": (38.680, 29.400),
    "B3": (38.685, 29.425), "B4": (38.670, 29.445),
    "C1": (38.655, 29.380), "C2": (38.660, 29.405),
    "C3": (38.650, 29.430), "C4": (38.655, 29.455),
    "D1": (38.635, 29.385), "D2": (38.635, 29.410),
    "D3": (38.635, 29.435), "D4": (38.635, 29.460),
}

def generate_pharmacies(seed: int = 42, total: int = 104) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    pid = 1
    per_group = total // len(GROUPS)

    for group in GROUPS:
        center_lat, center_lon = GROUP_CENTERS[group]
        count = per_group

        for _ in range(count):
            rows.append(
                {
                    "pharmacy_id": pid,
                    "pharmacy_name": f"Eczane {pid:03d}",
                    "group": group,
                    "region": group[0],
                    "lat": center_lat + rng.normal(0, 0.006),
                    "lon": center_lon + rng.normal(0, 0.008),
                    "historical_load": round(float(rng.uniform(3.0, 11.0)), 2),
                    "weekend_count": int(rng.integers(0, 4)),
                    "holiday_count": int(rng.integers(0, 3)),
                    "last_duty_days_ago": int(rng.integers(5, 45)),
                }
            )
            pid += 1

    return pd.DataFrame(rows)

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))

@dataclass
class SimulationState:
    last_duty_dates: dict[int, date] = field(default_factory=dict)
    duty_counts: dict[int, int] = field(default_factory=dict)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, reference_date: date | None = None) -> "SimulationState":
        reference_date = reference_date or date(2026, 8, 1)
        return cls(
            last_duty_dates={
                int(r.pharmacy_id): reference_date - timedelta(days=int(r.last_duty_days_ago))
                for r in df.itertuples()
            },
            duty_counts={int(r.pharmacy_id): 0 for r in df.itertuples()},
        )

    def copy(self) -> "SimulationState":
        return SimulationState(
            last_duty_dates=dict(self.last_duty_dates),
            duty_counts=dict(self.duty_counts),
        )

    def apply_assignment(self, pharmacy_id: int, duty_date: date) -> None:
        self.last_duty_dates[int(pharmacy_id)] = duty_date
        self.duty_counts[int(pharmacy_id)] = self.duty_counts.get(int(pharmacy_id), 0) + 1

def group_for_day(day_index: int) -> tuple[str, str, str, str]:
    return KOMB_ABC[day_index % len(KOMB_ABC)]

def status_palette() -> dict[str, list[int]]:
    return {
        "selected": [29, 78, 216, 230],
        "selectable": [22, 163, 74, 210],
        "distance_blocked": [220, 38, 38, 210],
        "gap_blocked": [245, 158, 11, 215],
        "inactive": [124, 58, 237, 85],
    }

def eligible_candidates(
    pharmacies: pd.DataFrame,
    group_name: str,
    selected_ids: list[int],
    state: SimulationState,
    current_date: date,
    min_distance_km: float,
    min_gap_days: int,
) -> pd.DataFrame:
    candidates = pharmacies[pharmacies["group"] == group_name].copy()

    selected_rows = pharmacies[pharmacies["pharmacy_id"].isin(selected_ids)]

    statuses = []
    reasons = []
    distances = []
    days_since_last = []
    scores = []
    selectable_flags = []

    for row in candidates.itertuples():
        pid = int(row.pharmacy_id)
        last_date = state.last_duty_dates.get(pid)
        gap = (current_date - last_date).days if last_date else 999
        days_since_last.append(gap)

        nearest = 999.0
        for selected in selected_rows.itertuples():
            if int(selected.pharmacy_id) == pid:
                continue
            dist = haversine_km(row.lat, row.lon, selected.lat, selected.lon)
            nearest = min(nearest, dist)

        distances.append(round(nearest, 2) if nearest < 999 else None)

        if pid in selected_ids:
            status = "selected"
            reason = "Zaten seçildi"
            selectable = True
        elif nearest < min_distance_km:
            status = "distance_blocked"
            reason = f"Seçilen eczaneye {nearest:.2f} km uzaklıkta"
            selectable = False
        elif gap < min_gap_days:
            status = "gap_blocked"
            reason = f"Son nöbetten yalnızca {gap} gün geçti"
            selectable = False
        else:
            status = "selectable"
            reason = "Tüm temel kurallara uygun"
            selectable = True

        score = (
            float(row.historical_load) * 0.70
            + float(row.weekend_count) * 1.50
            + float(row.holiday_count) * 2.00
            + state.duty_counts.get(pid, 0) * 1.25
            - min(gap, 35) * 0.08
        )

        statuses.append(status)
        reasons.append(reason)
        selectable_flags.append(selectable)
        scores.append(round(score, 3))

    candidates["status"] = statuses
    candidates["reason"] = reasons
    candidates["distance_to_nearest_selected_km"] = distances
    candidates["days_since_last_duty"] = days_since_last
    candidates["decision_score"] = scores
    candidates["selectable"] = selectable_flags

    return candidates

def build_demo_schedule(
    pharmacies: pd.DataFrame,
    start_date: date,
    days: int,
    min_distance_km: float = 1.0,
    min_gap_days: int = 14,
) -> pd.DataFrame:
    state = SimulationState.from_dataframe(pharmacies, reference_date=start_date)
    rows = []

    for day_idx in range(days):
        current_date = start_date + timedelta(days=day_idx)
        chosen: list[int] = []

        for group_name in group_for_day(day_idx):
            result = eligible_candidates(
                pharmacies,
                group_name,
                chosen,
                state,
                current_date,
                min_distance_km,
                min_gap_days,
            )
            valid = result[result["selectable"]].sort_values("decision_score")
            if valid.empty:
                continue
            row = valid.iloc[0]
            pid = int(row["pharmacy_id"])
            chosen.append(pid)
            state.apply_assignment(pid, current_date)
            rows.append(
                {
                    "date": current_date,
                    "group": group_name,
                    "pharmacy_id": pid,
                    "pharmacy_name": row["pharmacy_name"],
                    "decision_score": row["decision_score"],
                }
            )

    return pd.DataFrame(rows)
