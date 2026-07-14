
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
    """
    Grupları iç içe halkalar halinde gösterir.

    Mantık:
    - Her ana bölge bir çeyrek daireyi temsil eder:
      A = sol üst, B = sol alt, C = sağ alt, D = sağ üst
    - Alt grup numarası halkanın seviyesidir:
      1 = merkezdeki halka, 4 = en dış halka
    - Aktif kombinasyondaki sektörler bölge renginde vurgulanır.
    - Haritadan eczane seçildikçe ilgili sektör yeşil çerçeve alır.
    """
    width, height = 1180, 820
    cx, cy = 590, 420

    region_colors = {
        "A": "#0EA5E9",
        "B": "#22C55E",
        "C": "#F9A8D4",
        "D": "#A855F7",
    }

    # SVG yay dilimi oluşturucu.
    def polar(center_x: float, center_y: float, radius: float, angle_deg: float):
        angle = math.radians(angle_deg)
        return (
            center_x + radius * math.cos(angle),
            center_y + radius * math.sin(angle),
        )

    def annular_sector_path(
        center_x: float,
        center_y: float,
        inner_r: float,
        outer_r: float,
        start_angle: float,
        end_angle: float,
    ) -> str:
        x1, y1 = polar(center_x, center_y, outer_r, start_angle)
        x2, y2 = polar(center_x, center_y, outer_r, end_angle)
        x3, y3 = polar(center_x, center_y, inner_r, end_angle)
        x4, y4 = polar(center_x, center_y, inner_r, start_angle)

        large_arc = 1 if (end_angle - start_angle) > 180 else 0

        return (
            f"M {x1:.2f},{y1:.2f} "
            f"A {outer_r},{outer_r} 0 {large_arc} 1 {x2:.2f},{y2:.2f} "
            f"L {x3:.2f},{y3:.2f} "
            f"A {inner_r},{inner_r} 0 {large_arc} 0 {x4:.2f},{y4:.2f} Z"
        )

    # Saat yönünde:
    # A sol üst, B sol alt, C sağ alt, D sağ üst
    region_angles = {
        "A": (180, 270),
        "B": (90, 180),
        "C": (0, 90),
        "D": (270, 360),
    }

    inner_start = 58
    ring_width = 58
    ring_gap = 0

    active_set = set(active_combo)

    background = []
    active_shapes = []
    labels = []
    selected_overlays = []

    # Merkez daire.
    background.append(
        f'<circle cx="{cx}" cy="{cy}" r="{inner_start}" fill="#FFFFFF" '
        f'stroke="#111827" stroke-width="3"/>'
    )

    # Ana eksen çizgileri.
    axis_r = inner_start + 4 * ring_width
    background.extend([
        f'<line x1="{cx-axis_r}" y1="{cy}" x2="{cx+axis_r}" y2="{cy}" stroke="#111827" stroke-width="2.5"/>',
        f'<line x1="{cx}" y1="{cy-axis_r}" x2="{cx}" y2="{cy+axis_r}" stroke="#111827" stroke-width="2.5"/>',
    ])

    # Halkalar ve sektörler.
    for subgroup_no in range(1, 5):
        inner_r = inner_start + (subgroup_no - 1) * ring_width
        outer_r = inner_r + ring_width

        background.append(
            f'<circle cx="{cx}" cy="{cy}" r="{outer_r}" fill="none" '
            f'stroke="#111827" stroke-width="2.5"/>'
        )

        for region, (start_angle, end_angle) in region_angles.items():
            group_name = f"{region}{subgroup_no}"
            path = annular_sector_path(
                cx,
                cy,
                inner_r,
                outer_r,
                start_angle,
                end_angle,
            )

            if group_name in active_set:
                active_shapes.append(
                    f'<path d="{path}" fill="{region_colors[region]}" '
                    f'fill-opacity="0.93" stroke="#111827" stroke-width="2"/>'
                )

            if group_name in selected_by_group:
                selected_overlays.append(
                    f'<path d="{path}" fill="none" stroke="#16A34A" '
                    f'stroke-width="7" opacity="0.98"/>'
                )

            # Etiket konumu sektörün ortasında.
            mid_angle = (start_angle + end_angle) / 2
            mid_radius = (inner_r + outer_r) / 2
            tx, ty = polar(cx, cy, mid_radius, mid_angle)

            is_active = group_name in active_set
            label_color = "#FFFFFF" if is_active else "#344054"

            labels.append(
                f'<text x="{tx:.2f}" y="{ty+5:.2f}" text-anchor="middle" '
                f'font-size="15" font-weight="800" fill="{label_color}">{group_name}</text>'
            )

            count = int((pharmacies["group"] == group_name).sum())
            count_radius = mid_radius + 16
            c_tx, c_ty = polar(cx, cy, count_radius, mid_angle)

            labels.append(
                f'<text x="{c_tx:.2f}" y="{c_ty+20:.2f}" text-anchor="middle" '
                f'font-size="10" fill="{"#FFFFFF" if is_active else "#667085"}">'
                f'{count} eczane</text>'
            )

            if group_name in selected_by_group:
                pid = selected_by_group[group_name]
                name_series = pharmacies.loc[
                    pharmacies["pharmacy_id"] == pid,
                    "pharmacy_name",
                ]
                if not name_series.empty:
                    name_radius = outer_r + 18
                    n_tx, n_ty = polar(cx, cy, name_radius, mid_angle)
                    labels.append(
                        f'<text x="{n_tx:.2f}" y="{n_ty:.2f}" text-anchor="middle" '
                        f'font-size="12" font-weight="800" fill="#15803D">'
                        f'{escape(name_series.iloc[0])}</text>'
                    )

    # Bölge başlıkları.
    region_title_positions = {
        "A": (cx - 255, cy - 255),
        "B": (cx - 255, cy + 275),
        "C": (cx + 255, cy + 275),
        "D": (cx + 255, cy - 255),
    }

    region_titles = []
    for region, (tx, ty) in region_title_positions.items():
        region_titles.append(
            f'<text x="{tx}" y="{ty}" text-anchor="middle" '
            f'font-size="22" font-weight="900" fill="{region_colors[region]}">'
            f'{region} BÖLGESİ</text>'
        )

    # Aktif kombinasyonu merkezde göster.
    combo_text = "  •  ".join(active_combo)
    center_text = f"""
      <text x="{cx}" y="{cy-8}" text-anchor="middle"
            font-size="13" font-weight="700" fill="#667085">AKTİF</text>
      <text x="{cx}" y="{cy+14}" text-anchor="middle"
            font-size="14" font-weight="900" fill="#123B6D">{combo_text}</text>
    """

    # Sağ panel: seçilen eşlenikler.
    selected_cards = []
    panel_x = 920
    panel_y = 170

    selected_cards.append(
        f'<rect x="{panel_x}" y="{panel_y}" width="225" height="420" rx="18" '
        f'fill="#F8FAFC" stroke="#D0D5DD" stroke-width="1.5"/>'
    )
    selected_cards.append(
        f'<text x="{panel_x+112}" y="{panel_y+38}" text-anchor="middle" '
        f'font-size="18" font-weight="900" fill="#123B6D">Canlı Eşlenik Seçimi</text>'
    )

    card_y = panel_y + 72
    for group_name in active_combo:
        selected_pid = selected_by_group.get(group_name)
        selected_name = "Henüz seçilmedi"

        if selected_pid is not None:
            selected_name_series = pharmacies.loc[
                pharmacies["pharmacy_id"] == selected_pid,
                "pharmacy_name",
            ]
            if not selected_name_series.empty:
                selected_name = selected_name_series.iloc[0]

        selected = selected_pid is not None
        card_color = "#ECFDF3" if selected else "#FFFFFF"
        border_color = "#16A34A" if selected else "#D0D5DD"

        selected_cards.append(
            f'<rect x="{panel_x+18}" y="{card_y}" width="189" height="62" rx="12" '
            f'fill="{card_color}" stroke="{border_color}" stroke-width="2"/>'
        )
        selected_cards.append(
            f'<circle cx="{panel_x+48}" cy="{card_y+31}" r="18" '
            f'fill="{region_colors[group_name[0]]}"/>'
        )
        selected_cards.append(
            f'<text x="{panel_x+48}" y="{card_y+36}" text-anchor="middle" '
            f'font-size="13" font-weight="900" fill="#FFFFFF">{group_name}</text>'
        )
        selected_cards.append(
            f'<text x="{panel_x+78}" y="{card_y+25}" '
            f'font-size="13" font-weight="800" fill="#344054">'
            f'{escape(selected_name)}</text>'
        )
        selected_cards.append(
            f'<text x="{panel_x+78}" y="{card_y+44}" '
            f'font-size="11" fill="{"#15803D" if selected else "#98A2B3"}">'
            f'{"Seçim tamamlandı" if selected else "Haritadan eczane seçin"}</text>'
        )
        card_y += 76

    svg = f"""
    <div style="
      width:100%;
      background:white;
      border:1px solid #E4E7EC;
      border-radius:18px;
      padding:8px;
      overflow:hidden;">
      <svg width="100%" viewBox="0 0 {width} {height}"
           xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" rx="18" fill="#FFFFFF"/>

        <text x="{cx}" y="42" text-anchor="middle"
              font-size="28" font-weight="900" fill="#123B6D">
          AYÇA Çembersel Grup ve Eşlenik Simülasyonu
        </text>
        <text x="{cx}" y="70" text-anchor="middle"
              font-size="14" fill="#667085">
          İç halkadan dış halkaya: 1 → 2 → 3 → 4 alt grupları
        </text>

        {''.join(active_shapes)}
        {''.join(background)}
        {''.join(selected_overlays)}
        {''.join(labels)}
        {''.join(region_titles)}
        {center_text}
        {''.join(selected_cards)}

        <g transform="translate(58,760)">
          <rect x="0" y="-15" width="26" height="18" rx="4"
                fill="#0EA5E9" opacity="0.93"/>
          <text x="36" y="0" font-size="13" fill="#344054">
            Aktif grup sektörü
          </text>

          <rect x="180" y="-15" width="26" height="18" rx="4"
                fill="none" stroke="#16A34A" stroke-width="4"/>
          <text x="216" y="0" font-size="13" fill="#344054">
            Eczane seçimi tamamlanan grup
          </text>
        </g>
      </svg>
    </div>
    """
    return svg
