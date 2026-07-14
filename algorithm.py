from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import asin, cos, radians, sin, sqrt
import math
from html import escape

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

REGION_COLORS = {
    "A": "#2563EB",
    "B": "#16A34A",
    "C": "#F59E0B",
    "D": "#7C3AED",
}

def generate_pharmacies(seed: int = 42, total: int = 112) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    pid = 1
    per_group = total // len(GROUPS)

    for group in GROUPS:
        center_lat, center_lon = GROUP_CENTERS[group]

        for _ in range(per_group):
            rows.append(
                {
                    "pharmacy_id": pid,
                    "pharmacy_name": f"Eczane {pid}",
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
        "selected": [29, 78, 216, 235],
        "selectable": [22, 163, 74, 215],
        "distance_blocked": [220, 38, 38, 215],
        "gap_blocked": [245, 158, 11, 220],
        "inactive": [124, 58, 237, 80],
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

def build_group_svg(
    pharmacies: pd.DataFrame,
    active_combo: tuple[str, str, str, str],
    selected_by_group: dict[str, int],
) -> str:
    width, height = 1100, 720
    cx, cy = width / 2, height / 2 + 10
    main_r = 250
    subgroup_r = 46

    # main region centers
    region_positions = {
        "A": (cx, cy - 225),
        "B": (cx + 285, cy),
        "C": (cx, cy + 225),
        "D": (cx - 285, cy),
    }

    subgroup_positions = {}
    for region, (rx, ry) in region_positions.items():
        angle_start = {"A": 200, "B": 110, "C": 20, "D": -70}[region]
        for idx in range(1, 5):
            angle = math.radians(angle_start + (idx - 1) * 38)
            subgroup_positions[f"{region}{idx}"] = (
                rx + math.cos(angle) * 115,
                ry + math.sin(angle) * 115,
            )

    all_combo_lines = []
    for combo in KOMB_ABC:
        pts = [subgroup_positions[g] for g in combo]
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts + [pts[0]])
        all_combo_lines.append(
            f'<polyline points="{path}" fill="none" stroke="#CBD5E1" stroke-width="1.4" opacity="0.45"/>'
        )

    active_pts = [subgroup_positions[g] for g in active_combo]
    active_path = " ".join(f"{x:.1f},{y:.1f}" for x, y in active_pts + [active_pts[0]])
    active_line = (
        f'<polyline points="{active_path}" fill="none" stroke="#123B6D" '
        f'stroke-width="5" opacity="0.95" stroke-linejoin="round"/>'
    )

    region_shapes = []
    subgroup_shapes = []

    for region, (rx, ry) in region_positions.items():
        region_color = REGION_COLORS[region]
        region_shapes.append(
            f'<circle cx="{rx}" cy="{ry}" r="150" fill="{region_color}" opacity="0.08" '
            f'stroke="{region_color}" stroke-width="3"/>'
        )
        region_shapes.append(
            f'<text x="{rx}" y="{ry-122}" text-anchor="middle" '
            f'font-size="22" font-weight="800" fill="{region_color}">{region} BÖLGESİ</text>'
        )

    for group, (gx, gy) in subgroup_positions.items():
        active = group in active_combo
        region_color = REGION_COLORS[group[0]]
        fill = region_color if active else "#FFFFFF"
        text_color = "#FFFFFF" if active else region_color
        stroke_width = 4 if active else 2

        subgroup_shapes.append(
            f'<circle cx="{gx}" cy="{gy}" r="{subgroup_r}" fill="{fill}" '
            f'stroke="{region_color}" stroke-width="{stroke_width}"/>'
        )
        subgroup_shapes.append(
            f'<text x="{gx}" y="{gy+6}" text-anchor="middle" '
            f'font-size="18" font-weight="800" fill="{text_color}">{group}</text>'
        )

        count = int((pharmacies["group"] == group).sum())
        subgroup_shapes.append(
            f'<text x="{gx}" y="{gy+67}" text-anchor="middle" '
            f'font-size="12" fill="#475467">{count} eczane</text>'
        )

        if group in selected_by_group:
            pid = selected_by_group[group]
            name = pharmacies.loc[pharmacies["pharmacy_id"] == pid, "pharmacy_name"]
            if not name.empty:
                subgroup_shapes.append(
                    f'<text x="{gx}" y="{gy-58}" text-anchor="middle" '
                    f'font-size="12" font-weight="700" fill="#123B6D">{escape(name.iloc[0])}</text>'
                )

    legend = """
    <g transform="translate(40,650)">
      <line x1="0" y1="0" x2="52" y2="0" stroke="#123B6D" stroke-width="5"/>
      <text x="62" y="5" font-size="14" fill="#344054">Aktif eşlenik kombinasyonu</text>
      <line x1="300" y1="0" x2="352" y2="0" stroke="#CBD5E1" stroke-width="2"/>
      <text x="362" y="5" font-size="14" fill="#344054">Diğer olası eşlenikler</text>
    </g>
    """

    svg = f"""
    <div style="width:100%; background:white; border:1px solid #E4E7EC; border-radius:18px; padding:8px;">
      <svg width="100%" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" rx="18" fill="#FFFFFF"/>
        <text x="{cx}" y="38" text-anchor="middle" font-size="26" font-weight="800" fill="#123B6D">
          AYÇA Grup ve Eşlenik Simülasyonu
        </text>
        <text x="{cx}" y="64" text-anchor="middle" font-size="14" fill="#667085">
          Çembersel bölge yapısı ve günlük aktif kombinasyon
        </text>
        {''.join(region_shapes)}
        {''.join(all_combo_lines)}
        {active_line}
        {''.join(subgroup_shapes)}
        {legend}
      </svg>
    </div>
    """
    return svg
