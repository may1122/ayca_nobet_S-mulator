from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import copy
import math
import random

import pandas as pd


# ==========================================================
# DEMO COĞRAFİ YERLEŞİM SABİTLERİ
# ==========================================================
DEMO_LAYOUT_VERSION = 2
DEMO_CENTER_LAT = 38.6742
DEMO_CENTER_LON = 29.4058

# Dört ana bölge tam 90 derecelik sektörlerdir.
# A: kuzeybatı, B: güneybatı, C: güneydoğu, D: kuzeydoğu.
REGION_ANGLES = {
    "A": (90.0, 180.0),
    "B": (180.0, 270.0),
    "C": (270.0, 360.0),
    "D": (0.0, 90.0),
}

# Haritada çizilen ve veri üretiminde kullanılan ortak halka sınırları.
RING_LIMITS_KM = {
    1: (0.35, 1.45),
    2: (1.45, 2.45),
    3: (2.45, 3.45),
    4: (3.45, 4.45),
}

# Eczaneler sektör kenarlarına yapışmasın diye iç marj.
SECTOR_MARGIN_DEG = 12.0
RING_MARGIN_KM = 0.16


# 8 günlük dengeli eşlenik rotasyon.
KOMB_ABC = [
    ("A1", "B2", "C3", "D4"),
    ("A2", "B3", "C4", "D1"),
    ("A3", "B4", "C1", "D2"),
    ("A4", "B1", "C2", "D3"),
    ("A1", "B4", "C2", "D3"),
    ("A2", "B1", "C3", "D4"),
    ("A3", "B2", "C4", "D1"),
    ("A4", "B3", "C1", "D2"),
]


def group_for_day(day_index: int) -> tuple[str, str, str, str]:
    return KOMB_ABC[day_index % len(KOMB_ABC)]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    delta_p = math.radians(lat2 - lat1)
    delta_l = math.radians(lon2 - lon1)

    value = (
        math.sin(delta_p / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(delta_l / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


@dataclass
class SimulationState:
    last_duty_by_id: dict[int, date | None] = field(default_factory=dict)
    assignment_count_by_id: dict[int, int] = field(default_factory=dict)

    @classmethod
    def from_dataframe(cls, pharmacies: pd.DataFrame) -> "SimulationState":
        last_duty = {}
        assignment_count = {}

        for row in pharmacies.itertuples():
            raw_date = getattr(row, "last_duty_date", None)
            parsed_date = None
            if raw_date is not None and not pd.isna(raw_date) and str(raw_date).strip():
                parsed = pd.to_datetime(raw_date, errors="coerce")
                if not pd.isna(parsed):
                    parsed_date = parsed.date()

            pharmacy_id = int(row.pharmacy_id)
            last_duty[pharmacy_id] = parsed_date
            assignment_count[pharmacy_id] = int(
                getattr(row, "assignment_count", 0) or 0
            )

        return cls(
            last_duty_by_id=last_duty,
            assignment_count_by_id=assignment_count,
        )

    def copy(self) -> "SimulationState":
        return copy.deepcopy(self)

    def apply_assignment(self, pharmacy_id: int, duty_date: date) -> None:
        pharmacy_id = int(pharmacy_id)
        self.last_duty_by_id[pharmacy_id] = duty_date
        self.assignment_count_by_id[pharmacy_id] = (
            self.assignment_count_by_id.get(pharmacy_id, 0) + 1
        )


def _destination_point(
    center_lat: float,
    center_lon: float,
    distance_km: float,
    angle_deg: float,
) -> tuple[float, float]:
    angle_rad = math.radians(angle_deg)
    north_km = distance_km * math.sin(angle_rad)
    east_km = distance_km * math.cos(angle_rad)

    lat = center_lat + north_km / 111.32
    lon = center_lon + east_km / (
        111.32 * math.cos(math.radians(center_lat))
    )
    return lat, lon


def _bearing_deg(
    center_lat: float,
    center_lon: float,
    lat: float,
    lon: float,
) -> float:
    north_km = (lat - center_lat) * 111.32
    east_km = (
        (lon - center_lon)
        * 111.32
        * math.cos(math.radians(center_lat))
    )
    return math.degrees(math.atan2(north_km, east_km)) % 360.0


def pharmacy_layout_is_valid(pharmacies: pd.DataFrame) -> bool:
    required_columns = {
        "pharmacy_id",
        "group",
        "region",
        "ring",
        "lat",
        "lon",
        "layout_version",
    }
    if not required_columns.issubset(pharmacies.columns):
        return False

    if pharmacies.empty or len(pharmacies) != 96:
        return False

    try:
        versions = pharmacies["layout_version"].astype(int).unique().tolist()
    except (TypeError, ValueError):
        return False

    if versions != [DEMO_LAYOUT_VERSION]:
        return False

    expected_groups = {
        f"{region}{ring_no}"
        for region in ("A", "B", "C", "D")
        for ring_no in range(1, 5)
    }
    counts = pharmacies.groupby("group").size().to_dict()
    if set(counts) != expected_groups:
        return False
    if any(int(counts[group_name]) != 6 for group_name in expected_groups):
        return False

    tolerance_km = 0.04
    tolerance_deg = 0.8

    for row in pharmacies.itertuples():
        region = str(row.region)
        ring_no = int(row.ring)
        group_name = str(row.group)

        if group_name != f"{region}{ring_no}":
            return False
        if region not in REGION_ANGLES or ring_no not in RING_LIMITS_KM:
            return False

        distance_km = haversine_km(
            DEMO_CENTER_LAT,
            DEMO_CENTER_LON,
            float(row.lat),
            float(row.lon),
        )
        inner_km, outer_km = RING_LIMITS_KM[ring_no]
        if not (
            inner_km + RING_MARGIN_KM - tolerance_km
            <= distance_km
            <= outer_km - RING_MARGIN_KM + tolerance_km
        ):
            return False

        bearing = _bearing_deg(
            DEMO_CENTER_LAT,
            DEMO_CENTER_LON,
            float(row.lat),
            float(row.lon),
        )
        start_angle, end_angle = REGION_ANGLES[region]

        if region == "C" and bearing < 270:
            bearing += 360

        if not (
            start_angle + SECTOR_MARGIN_DEG - tolerance_deg
            <= bearing
            <= end_angle - SECTOR_MARGIN_DEG + tolerance_deg
        ):
            return False

    return True


def generate_pharmacies(
    seed: int = 42,
    center_lat: float = DEMO_CENTER_LAT,
    center_lon: float = DEMO_CENTER_LON,
    pharmacies_per_subgroup: int = 6,
) -> pd.DataFrame:
    """
    96 eczanelik dengeli demo üretir:
    4 ana bölge × 4 halka × 6 eczane.

    Her eczane, ait olduğu sektörün ve halka kuşağının güvenli biçimde
    içinde oluşturulur. Harita ve veri aynı geometrik sabitleri kullanır.
    """
    rng = random.Random(seed)
    rows = []
    pharmacy_id = 1
    reference_date = pd.Timestamp("2026-08-01")

    for region in ("A", "B", "C", "D"):
        sector_start, sector_end = REGION_ANGLES[region]
        usable_start = sector_start + SECTOR_MARGIN_DEG
        usable_end = sector_end - SECTOR_MARGIN_DEG

        for ring_no in range(1, 5):
            subgroup = f"{region}{ring_no}"
            inner_km, outer_km = RING_LIMITS_KM[ring_no]
            safe_inner = inner_km + RING_MARGIN_KM
            safe_outer = outer_km - RING_MARGIN_KM

            for local_index in range(pharmacies_per_subgroup):
                # Altı eczaneyi sektör boyunca düzenli, küçük sapmalarla dağıt.
                fraction = (local_index + 1) / (pharmacies_per_subgroup + 1)
                base_angle = usable_start + (usable_end - usable_start) * fraction
                angle_deg = base_angle + rng.uniform(-1.8, 1.8)

                # Aynı halkada üst üste binmeyi azaltmak için kontrollü uzaklık dağılımı.
                radial_fraction = (
                    ((local_index * 2) % pharmacies_per_subgroup) + 1
                ) / (pharmacies_per_subgroup + 1)
                base_distance = safe_inner + (
                    safe_outer - safe_inner
                ) * radial_fraction
                distance_km = base_distance + rng.uniform(-0.055, 0.055)
                distance_km = min(
                    safe_outer - 0.01,
                    max(safe_inner + 0.01, distance_km),
                )

                lat, lon = _destination_point(
                    center_lat,
                    center_lon,
                    distance_km,
                    angle_deg,
                )

                days_since_last = rng.randint(16, 45)
                historical_load = round(rng.uniform(2.8, 6.8), 1)
                weekend_count = rng.randint(0, 3)
                holiday_count = rng.randint(0, 1)

                rows.append(
                    {
                        "pharmacy_id": pharmacy_id,
                        "pharmacy_name": f"Eczane {pharmacy_id:03d}",
                        "region": region,
                        "ring": ring_no,
                        "group": subgroup,
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "distance_from_center_km": round(distance_km, 3),
                        "bearing_deg": round(angle_deg % 360.0, 2),
                        "layout_version": DEMO_LAYOUT_VERSION,
                        "historical_load": historical_load,
                        "weekend_count": weekend_count,
                        "holiday_count": holiday_count,
                        "assignment_count": rng.randint(2, 5),
                        "last_duty_date": (
                            reference_date - pd.Timedelta(days=days_since_last)
                        ).date().isoformat(),
                    }
                )
                pharmacy_id += 1

    generated = pd.DataFrame(rows)
    if not pharmacy_layout_is_valid(generated):
        raise RuntimeError(
            "Demo eczane yerleşimi doğrulamasını geçemedi."
        )
    return generated


def eligible_candidates(
    pharmacies: pd.DataFrame,
    group_name: str,
    selected_ids: list[int],
    state: SimulationState,
    current_date: date,
    min_distance_km: float,
    min_gap_days: int,
) -> pd.DataFrame:
    selected_ids = [int(value) for value in selected_ids]
    selected_rows = pharmacies[
        pharmacies["pharmacy_id"].astype(int).isin(selected_ids)
    ]

    normalized_group_name = str(group_name).strip().upper()

    result = pharmacies[
        pharmacies["group"].astype(str).str.strip().str.upper()
        == normalized_group_name
    ].copy()

    # Güvenlik kilidi: bu fonksiyon hiçbir koşulda başka gruptan
    # eczane döndürmez.
    if not result.empty:
        result = result[
            result["group"].astype(str).str.strip().str.upper()
            == normalized_group_name
        ].copy()

    distances = []
    gaps = []
    statuses = []
    reasons = []
    selectable_values = []
    scores = []

    for row in result.itertuples():
        pharmacy_id = int(row.pharmacy_id)

        nearest_distance = None
        if not selected_rows.empty:
            nearest_distance = min(
                haversine_km(
                    float(row.lat),
                    float(row.lon),
                    float(selected.lat),
                    float(selected.lon),
                )
                for selected in selected_rows.itertuples()
            )

        last_duty = state.last_duty_by_id.get(pharmacy_id)
        days_since_last = (
            (current_date - last_duty).days
            if last_duty is not None
            else 999
        )

        gap_ok = days_since_last >= min_gap_days
        distance_ok = (
            nearest_distance is None
            or nearest_distance >= min_distance_km
        )

        is_selected = pharmacy_id in selected_ids
        selectable = gap_ok and distance_ok and not is_selected

        if is_selected:
            status = "selected"
            reason = "Bugünkü plan için seçildi"
        elif not gap_ok:
            status = "gap_blocked"
            reason = f"Son nöbetinden yalnızca {days_since_last} gün geçti"
        elif not distance_ok:
            status = "distance_blocked"
            reason = (
                f"Seçili eczaneye {nearest_distance:.2f} km uzaklıkta; "
                f"minimum {min_distance_km:.2f} km gerekli"
            )
        else:
            status = "selectable"
            reason = "Tüm temel kurallara uygun"

        historical_load = float(getattr(row, "historical_load", 0) or 0)
        weekend_count = int(getattr(row, "weekend_count", 0) or 0)
        holiday_count = int(getattr(row, "holiday_count", 0) or 0)
        assignment_count = state.assignment_count_by_id.get(pharmacy_id, 0)

        score = 100.0
        score -= historical_load * 2.4
        score -= weekend_count * 3.2
        score -= holiday_count * 4.5
        score -= assignment_count * 1.3
        score += min(days_since_last, 45) * 0.35

        if nearest_distance is not None:
            score += min(nearest_distance, 4.0) * 1.4

        if not gap_ok:
            score -= 35
        if not distance_ok:
            score -= 40
        if is_selected:
            score = max(score, 85)

        score = max(0.0, min(100.0, score))

        distances.append(nearest_distance)
        gaps.append(days_since_last)
        statuses.append(status)
        reasons.append(reason)
        selectable_values.append(selectable)
        scores.append(round(score, 2))

    result["distance_to_nearest_selected_km"] = distances
    result["days_since_last_duty"] = gaps
    result["status"] = statuses
    result["reason"] = reasons
    result["selectable"] = selectable_values
    result["decision_score"] = scores
    result["requested_group"] = normalized_group_name

    # Son güvenlik kontrolü.
    invalid_group_rows = result[
        result["group"].astype(str).str.strip().str.upper()
        != normalized_group_name
    ]
    if not invalid_group_rows.empty:
        raise ValueError(
            f"{normalized_group_name} aday listesine başka gruptan "
            "eczane karıştı."
        )

    return result


def status_palette() -> dict[str, list[int]]:
    return {
        "selected": [37, 99, 235, 220],
        "selectable": [22, 163, 74, 210],
        "distance_blocked": [220, 38, 38, 190],
        "gap_blocked": [245, 158, 11, 190],
        "inactive": [148, 163, 184, 110],
    }


def build_group_svg(
    pharmacies: pd.DataFrame,
    active_combo: tuple[str, str, str, str],
    selected_by_group: dict,
) -> str:
    width = 980
    height = 720
    cx = 390
    cy = 350
    radii = [72, 132, 196, 260]
    region_colors = {
        "A": "#38A3E1",
        "B": "#16C96F",
        "C": "#F39ACD",
        "D": "#B444ED",
    }

    region_angles = {
        "A": (180, 270),
        "B": (90, 180),
        "C": (0, 90),
        "D": (270, 360),
    }

    def polar(radius: float, angle_deg: float) -> tuple[float, float]:
        angle = math.radians(angle_deg)
        return (
            cx + radius * math.cos(angle),
            cy + radius * math.sin(angle),
        )

    def sector_path(inner_r: float, outer_r: float, start: float, end: float) -> str:
        x1, y1 = polar(outer_r, start)
        x2, y2 = polar(outer_r, end)
        x3, y3 = polar(inner_r, end)
        x4, y4 = polar(inner_r, start)
        large = 1 if (end - start) > 180 else 0
        return (
            f"M {x1:.2f},{y1:.2f} "
            f"A {outer_r},{outer_r} 0 {large},1 {x2:.2f},{y2:.2f} "
            f"L {x3:.2f},{y3:.2f} "
            f"A {inner_r},{inner_r} 0 {large},0 {x4:.2f},{y4:.2f} Z"
        )

    active_set = set(active_combo)
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="390" y="34" text-anchor="middle" font-size="24" font-weight="800" fill="#123B6D">AYÇA Çembersel Grup ve Eşlenik Simülasyonu</text>',
        '<text x="390" y="61" text-anchor="middle" font-size="13" fill="#667085">İç halkadan dış halkaya 1 → 2 → 3 → 4 alt grupları</text>',
    ]

    inner_radius = 0
    for ring_index, outer_radius in enumerate(radii, start=1):
        for region, (start_angle, end_angle) in region_angles.items():
            group_name = f"{region}{ring_index}"
            active = group_name in active_set
            selected = group_name in selected_by_group

            fill = region_colors[region] if active else "#FFFFFF"
            fill_opacity = "0.95" if active else "1"
            stroke = "#079455" if selected else "#101828"
            stroke_width = "4" if selected else "2"

            svg_parts.append(
                f'<path d="{sector_path(inner_radius, outer_radius, start_angle, end_angle)}" '
                f'fill="{fill}" fill-opacity="{fill_opacity}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
            )

            label_radius = (inner_radius + outer_radius) / 2
            label_angle = (start_angle + end_angle) / 2
            lx, ly = polar(label_radius, label_angle)
            text_color = "#FFFFFF" if active else "#123B6D"
            count = int((pharmacies["group"] == group_name).sum())

            svg_parts.append(
                f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="middle" '
                f'font-size="14" font-weight="800" fill="{text_color}">{group_name}</text>'
            )
            svg_parts.append(
                f'<text x="{lx:.2f}" y="{ly + 15:.2f}" text-anchor="middle" '
                f'font-size="9" fill="{text_color}">{count} eczane</text>'
            )

        inner_radius = outer_radius

    svg_parts.extend(
        [
            f'<text x="{cx - 285}" y="{cy - 285}" font-size="20" font-weight="800" fill="#38A3E1">A BÖLGESİ</text>',
            f'<text x="{cx - 285}" y="{cy + 285}" font-size="20" font-weight="800" fill="#16C96F">B BÖLGESİ</text>',
            f'<text x="{cx + 175}" y="{cy + 285}" font-size="20" font-weight="800" fill="#F39ACD">C BÖLGESİ</text>',
            f'<text x="{cx + 175}" y="{cy - 285}" font-size="20" font-weight="800" fill="#B444ED">D BÖLGESİ</text>',
            f'<circle cx="{cx}" cy="{cy}" r="52" fill="white" stroke="#101828" stroke-width="2"/>',
            f'<text x="{cx}" y="{cy - 8}" text-anchor="middle" font-size="11" fill="#667085">AKTİF</text>',
            f'<text x="{cx}" y="{cy + 12}" text-anchor="middle" font-size="15" font-weight="800" fill="#123B6D">{" • ".join(active_combo)}</text>',
        ]
    )

    panel_x = 720
    svg_parts.append(
        f'<rect x="{panel_x}" y="120" width="230" height="430" rx="18" fill="#F8FAFC" stroke="#D0D5DD"/>'
    )
    svg_parts.append(
        f'<text x="{panel_x + 22}" y="160" font-size="17" font-weight="800" fill="#123B6D">Canlı Eşlenik Seçimi</text>'
    )

    for index, group_name in enumerate(active_combo):
        y = 190 + index * 77
        region = group_name[0]
        selected_id = selected_by_group.get(group_name)
        if selected_id is None:
            selected_text = "Henüz seçilmedi"
            sub_text = "Haritadan eczane seçin"
        else:
            match = pharmacies[pharmacies["pharmacy_id"] == int(selected_id)]
            selected_text = (
                str(match.iloc[0]["pharmacy_name"])
                if not match.empty
                else "Seçildi"
            )
            sub_text = "Seçim tamamlandı"

        svg_parts.extend(
            [
                f'<rect x="{panel_x + 18}" y="{y}" width="194" height="62" rx="14" fill="white" stroke="#D0D5DD"/>',
                f'<circle cx="{panel_x + 48}" cy="{y + 31}" r="18" fill="{region_colors[region]}"/>',
                f'<text x="{panel_x + 48}" y="{y + 36}" text-anchor="middle" font-size="12" font-weight="800" fill="white">{group_name}</text>',
                f'<text x="{panel_x + 78}" y="{y + 26}" font-size="12" font-weight="800" fill="#123B6D">{selected_text}</text>',
                f'<text x="{panel_x + 78}" y="{y + 45}" font-size="10" fill="#98A2B3">{sub_text}</text>',
            ]
        )

    svg_parts.append("</svg>")
    return "".join(svg_parts)
