from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import copy
import math
import random
from typing import Iterable

import pandas as pd

DEMO_LAYOUT_VERSION = 6

CITY_CONFIG = {
    "Uşak": {"lat": 38.6742, "lon": 29.4058, "default_pharmacy_count": 100, "layout": "Dairesel", "profile": "İç Ege şehir profili"},
    "Giresun": {"lat": 40.9170, "lon": 38.3895, "default_pharmacy_count": 100, "layout": "Kıyı odaklı", "profile": "Karadeniz kıyı profili"},
    "Erzurum": {"lat": 39.9043, "lon": 41.2679, "default_pharmacy_count": 154, "layout": "Geniş merkez", "profile": "Doğu Anadolu şehir profili"},
    "Kahramanmaraş": {"lat": 37.5753, "lon": 36.9228, "default_pharmacy_count": 150, "layout": "Çok merkezli", "profile": "Büyükşehir profili"},
    "Sivas": {"lat": 39.7505, "lon": 37.0150, "default_pharmacy_count": 125, "layout": "Dairesel", "profile": "İç Anadolu şehir profili"},
    "Tokat": {"lat": 40.3167, "lon": 36.5500, "default_pharmacy_count": 100, "layout": "Dairesel", "profile": "Orta Karadeniz profili"},
    "Amasya": {"lat": 40.6539, "lon": 35.8331, "default_pharmacy_count": 75, "layout": "Vadi odaklı", "profile": "Vadi şehir profili"},
    "Ordu": {"lat": 40.9565, "lon": 37.8764, "default_pharmacy_count": 125, "layout": "Kıyı odaklı", "profile": "Karadeniz kıyı profili"},
    "Trabzon": {"lat": 40.9740, "lon": 39.7178, "default_pharmacy_count": 175, "layout": "Kıyı odaklı", "profile": "Büyük kıyı şehir profili"},
    "Rize": {"lat": 40.9920, "lon": 40.5234, "default_pharmacy_count": 100, "layout": "Kıyı odaklı", "profile": "Karadeniz kıyı profili"},
}

DEMO_CENTER_LAT = CITY_CONFIG["Uşak"]["lat"]
DEMO_CENTER_LON = CITY_CONFIG["Uşak"]["lon"]

REGION_ANGLES = {
    "A": (90.0, 180.0),
    "B": (180.0, 270.0),
    "C": (270.0, 360.0),
    "D": (0.0, 90.0),
}

RING_LIMITS_KM = {
    1: (0.35, 1.45),
    2: (1.45, 2.45),
    3: (2.45, 3.45),
    4: (3.45, 4.45),
}

SECTOR_MARGIN_DEG = 10.0
RING_MARGIN_KM = 0.12

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
    return KOMB_ABC[int(day_index) % len(KOMB_ABC)]


def region_angles_for_city(city_name: str) -> dict[str, tuple[float, float]]:
    """Giresun gibi kıyı şehirlerinde görünümü kuzeye taşıyan açısal profil."""
    if city_name in {"Giresun", "Ordu", "Trabzon", "Rize"}:
        return {
            "A": (55.0, 145.0),
            "B": (145.0, 235.0),
            "C": (235.0, 325.0),
            "D": (325.0, 415.0),
        }
    return REGION_ANGLES.copy()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


@dataclass
class SimulationState:
    last_duty_by_id: dict[int, date | None] = field(default_factory=dict)
    assignment_count_by_id: dict[int, int] = field(default_factory=dict)

    @classmethod
    def from_dataframe(cls, pharmacies: pd.DataFrame) -> "SimulationState":
        last_duty: dict[int, date | None] = {}
        counts: dict[int, int] = {}
        for row in pharmacies.itertuples():
            pid = int(row.pharmacy_id)
            raw = getattr(row, "last_duty_date", None)
            parsed_date = None
            if raw is not None and not pd.isna(raw) and str(raw).strip():
                parsed = pd.to_datetime(raw, errors="coerce")
                if not pd.isna(parsed):
                    parsed_date = parsed.date()
            last_duty[pid] = parsed_date
            counts[pid] = int(getattr(row, "assignment_count", 0) or 0)
        return cls(last_duty, counts)

    def copy(self) -> "SimulationState":
        return copy.deepcopy(self)

    def apply_assignment(self, pharmacy_id: int, duty_date: date) -> None:
        pid = int(pharmacy_id)
        self.last_duty_by_id[pid] = duty_date
        self.assignment_count_by_id[pid] = self.assignment_count_by_id.get(pid, 0) + 1


def _destination_point(center_lat: float, center_lon: float, distance_km: float, angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    north = distance_km * math.sin(angle)
    east = distance_km * math.cos(angle)
    lat = center_lat + north / 111.32
    lon = center_lon + east / (111.32 * max(0.2, math.cos(math.radians(center_lat))))
    return lat, lon


def _balanced_group_counts(total: int) -> dict[str, int]:
    groups = [f"{r}{i}" for r in "ABCD" for i in range(1, 5)]
    total = max(16, int(total))
    base, remainder = divmod(total, len(groups))
    return {g: base + (1 if i < remainder else 0) for i, g in enumerate(groups)}


def generate_pharmacies(
    seed: int = 42,
    city_name: str = "Uşak",
    center_lat: float = DEMO_CENTER_LAT,
    center_lon: float = DEMO_CENTER_LON,
    total_pharmacies: int = 100,
    realistic: bool = True,
) -> pd.DataFrame:
    total_pharmacies = max(16, int(total_pharmacies))
    rng = random.Random(f"{seed}|{city_name}|{total_pharmacies}|{realistic}")
    counts = _balanced_group_counts(total_pharmacies)
    angles = region_angles_for_city(city_name)
    rows: list[dict] = []
    pid = 1
    reference = date(2026, 8, 1)

    for region in "ABCD":
        start, end = angles[region]
        for ring in range(1, 5):
            group = f"{region}{ring}"
            count = counts[group]
            inner, outer = RING_LIMITS_KM[ring]
            for local_index in range(count):
                fraction = (local_index + 1) / (count + 1)
                angle = start + SECTOR_MARGIN_DEG + (end - start - 2 * SECTOR_MARGIN_DEG) * fraction
                if realistic:
                    angle += rng.uniform(-4.0, 4.0)
                    radial = rng.triangular(inner + RING_MARGIN_KM, outer - RING_MARGIN_KM, (inner + outer) / 2)
                else:
                    angle += rng.uniform(-1.5, 1.5)
                    radial = inner + RING_MARGIN_KM + (outer - inner - 2 * RING_MARGIN_KM) * fraction
                lat, lon = _destination_point(center_lat, center_lon, radial, angle)
                load = round(rng.uniform(1.5, 9.5), 1)
                weekend = rng.randint(0, 3)
                holiday = rng.randint(0, 2)
                days_ago = rng.randint(8, 55)
                rows.append({
                    "pharmacy_id": pid,
                    "pharmacy_name": f"{city_name} Eczanesi {pid:03d}",
                    "city_name": city_name,
                    "group": group,
                    "region": region,
                    "ring": ring,
                    "lat": lat,
                    "lon": lon,
                    "historical_load": load,
                    "weekend_count": weekend,
                    "holiday_count": holiday,
                    "assignment_count": rng.randint(0, 6),
                    "last_duty_date": (reference - timedelta(days=days_ago)).isoformat(),
                    "layout_version": DEMO_LAYOUT_VERSION,
                })
                pid += 1
    return pd.DataFrame(rows)


def pharmacy_layout_is_valid(
    pharmacies: pd.DataFrame,
    center_lat: float = DEMO_CENTER_LAT,
    center_lon: float = DEMO_CENTER_LON,
    expected_total: int = 100,
    city_name: str | None = None,
) -> bool:
    required = {"pharmacy_id", "group", "region", "ring", "lat", "lon", "layout_version"}
    if pharmacies.empty or len(pharmacies) != int(expected_total) or not required.issubset(pharmacies.columns):
        return False
    try:
        if set(pharmacies["layout_version"].astype(int)) != {DEMO_LAYOUT_VERSION}:
            return False
    except Exception:
        return False
    expected_groups = {f"{r}{i}" for r in "ABCD" for i in range(1, 5)}
    if set(pharmacies["group"].astype(str)) != expected_groups:
        return False
    sizes = pharmacies.groupby("group").size()
    return int(sizes.max() - sizes.min()) <= 1


def _nearest_distance(row: pd.Series, selected_rows: pd.DataFrame) -> float | None:
    if selected_rows.empty:
        return None
    return min(
        haversine_km(float(row.lat), float(row.lon), float(s.lat), float(s.lon))
        for s in selected_rows.itertuples()
    )


def eligible_candidates(
    pharmacies: pd.DataFrame,
    group_name: str,
    selected_ids: Iterable[int],
    state: SimulationState,
    current_date: date,
    min_distance_km: float,
    min_gap_days: int,
) -> pd.DataFrame:
    selected_set = {int(x) for x in selected_ids}
    selected_rows = pharmacies[pharmacies["pharmacy_id"].astype(int).isin(selected_set)]
    frame = pharmacies[pharmacies["group"].astype(str).str.upper() == str(group_name).upper()].copy()
    results: list[dict] = []

    for _, row in frame.iterrows():
        pid = int(row["pharmacy_id"])
        last = state.last_duty_by_id.get(pid)
        gap = (current_date - last).days if last else 999
        distance = _nearest_distance(row, selected_rows)
        distance_ok = distance is None or distance >= float(min_distance_km)
        gap_ok = gap >= int(min_gap_days)
        already_selected = pid in selected_set
        selectable = distance_ok and gap_ok and not already_selected

        if already_selected:
            status, reason = "selected", "Bu gün için seçildi"
        elif not distance_ok:
            status, reason = "distance_blocked", f"Seçili eczaneye {distance:.2f} km mesafede"
        elif not gap_ok:
            status, reason = "gap_blocked", f"Son nöbetten yalnızca {gap} gün geçti"
        else:
            status, reason = "selectable", "Tüm temel kurallara uygun"

        historical = float(row.get("historical_load", 0) or 0)
        weekend = int(row.get("weekend_count", 0) or 0)
        holiday = int(row.get("holiday_count", 0) or 0)
        assignment_count = state.assignment_count_by_id.get(pid, int(row.get("assignment_count", 0) or 0))
        score = 100.0
        score -= min(30.0, historical * 2.0)
        score -= min(12.0, weekend * 3.0)
        score -= min(10.0, holiday * 4.0)
        score -= min(14.0, assignment_count * 2.0)
        if gap < 999:
            score += min(12.0, max(0.0, (gap - min_gap_days) * 0.35))
        if distance is not None:
            score += min(8.0, distance * 1.5)
        if not selectable and not already_selected:
            score = min(score, 55.0)
        score = max(0.0, min(100.0, score))

        item = row.to_dict()
        item.update({
            "status": status,
            "reason": reason,
            "selectable": selectable,
            "days_since_last_duty": gap if gap < 999 else None,
            "distance_to_nearest_selected_km": distance,
            "decision_score": round(score, 1),
            "assignment_count": assignment_count,
        })
        results.append(item)
    return pd.DataFrame(results)


def status_palette() -> dict[str, list[int]]:
    return {
        "selected": [47, 107, 255, 220],
        "selectable": [34, 197, 94, 205],
        "distance_blocked": [239, 68, 68, 190],
        "gap_blocked": [245, 158, 11, 190],
        "inactive": [148, 163, 184, 125],
    }


def build_group_svg(pharmacies: pd.DataFrame, active_groups: Iterable[str] | None = None, active_combo: Iterable[str] | None = None, **_: object) -> str:
    active_source = active_groups if active_groups is not None else active_combo
    active = {str(g).upper() for g in (active_source or [])}
    colors = {"A": "#3B82F6", "B": "#22C55E", "C": "#EC4899", "D": "#8B5CF6"}
    cells = []
    x0, y0, size, gap = 18, 18, 122, 12
    for r_idx, region in enumerate("ABCD"):
        for ring in range(1, 5):
            group = f"{region}{ring}"
            x = x0 + (ring - 1) * (size + gap)
            y = y0 + r_idx * (78 + gap)
            count = int((pharmacies["group"] == group).sum()) if "group" in pharmacies else 0
            fill = colors[region] if group in active else "#F8FAFC"
            text = "#FFFFFF" if group in active else "#1B2B48"
            stroke = colors[region]
            cells.append(f'<rect x="{x}" y="{y}" width="{size}" height="78" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
            cells.append(f'<text x="{x+14}" y="{y+30}" font-size="18" font-weight="800" fill="{text}">{group}</text>')
            cells.append(f'<text x="{x+14}" y="{y+55}" font-size="12" fill="{text}">{count} eczane</text>')
    return f'<svg viewBox="0 0 570 380" width="100%" role="img" aria-label="16 alt grup yapısı">{"".join(cells)}</svg>'


def build_simulation_summary(
    pharmacies: pd.DataFrame,
    active_groups: Iterable[str],
    selected_by_group: dict,
    candidates_by_group: dict[str, pd.DataFrame],
) -> dict[str, float | int]:
    candidate_count = sum(len(df) for df in candidates_by_group.values())
    rule_checks = candidate_count * 6
    selected_count = len(selected_by_group)
    combinations = 1
    for group in active_groups:
        df = candidates_by_group.get(group, pd.DataFrame())
        eligible = int(df["selectable"].sum()) if not df.empty and "selectable" in df else 0
        combinations *= max(1, eligible)
    scores = []
    for df in candidates_by_group.values():
        if not df.empty and "decision_score" in df:
            scores.extend(df.loc[df["selectable"], "decision_score"].astype(float).tolist())
    quality = round(sum(sorted(scores, reverse=True)[:4]) / max(1, min(4, len(scores))), 1) if scores else 0.0
    return {
        "pharmacy_count": len(pharmacies),
        "candidate_count": candidate_count,
        "rule_checks": rule_checks,
        "estimated_combinations": combinations,
        "selected_count": selected_count,
        "estimated_seconds": round(max(0.4, candidate_count * 0.018), 1),
        "quality_score": quality,
    }


def build_group_story(
    group_name: str,
    candidates: pd.DataFrame,
    selected_pharmacy_id: int | None = None,
) -> dict:
    if candidates.empty:
        return {"group": group_name, "candidate_count": 0, "blocked_count": 0, "selectable_count": 0, "selected_name": "Aday yok", "selected_score": 0.0, "reasons": []}
    selectable = candidates[candidates["selectable"]]
    selected = pd.DataFrame()
    if selected_pharmacy_id is not None:
        selected = candidates[candidates["pharmacy_id"].astype(int) == int(selected_pharmacy_id)]
    if selected.empty and not selectable.empty:
        selected = selectable.sort_values("decision_score", ascending=False).head(1)
    selected_name = str(selected.iloc[0]["pharmacy_name"]) if not selected.empty else "Uygun aday bulunamadı"
    selected_score = float(selected.iloc[0]["decision_score"]) if not selected.empty else 0.0
    blocked = candidates[~candidates["selectable"]]
    reasons = [
        {"pharmacy_name": str(row.pharmacy_name), "reason": str(row.reason)}
        for row in blocked.head(6).itertuples()
    ]
    return {
        "group": group_name,
        "candidate_count": len(candidates),
        "blocked_count": len(blocked),
        "selectable_count": len(selectable),
        "selected_name": selected_name,
        "selected_score": selected_score,
        "reasons": reasons,
    }
