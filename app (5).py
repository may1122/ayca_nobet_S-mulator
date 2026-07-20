from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from textwrap import dedent
import math
import re

import pandas as pd
import pydeck as pdk
import streamlit as st
import streamlit.components.v1 as components
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

from algorithm import (
    KOMB_ABC,
    DEMO_CENTER_LAT,
    DEMO_CENTER_LON,
    REGION_ANGLES,
    RING_LIMITS_KM,
    SimulationState,
    eligible_candidates,
    generate_pharmacies,
    pharmacy_layout_is_valid,
    group_for_day,
    status_palette,
    build_group_svg,
)

DEMO_CITY_NAME = "Uşak"

st.set_page_config(
    page_title="AYÇA Nöbet | Grup Simülasyonu",
    page_icon="💊",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.1rem; padding-bottom: 2rem;}
        .ayca-title {font-size: 2rem; font-weight: 800; color: #123B6D; margin-bottom: .1rem;}
        .ayca-subtitle {color: #667085; margin-bottom: 1rem;}
        div[data-testid="stMetric"] {
            border: 1px solid #E4E7EC; padding: 12px 14px; border-radius: 14px;
            background: white;
        }
        .legend {
            display:flex; gap:14px; flex-wrap:wrap; font-size:.9rem; color:#475467;
            margin:.4rem 0 1rem 0;
        }
        .legend span {display:flex; align-items:center; gap:6px;}
        .dot {width:11px; height:11px; border-radius:50%; display:inline-block;}
        .small-note {font-size:.88rem; color:#667085;}
        .group-pill {
            display:inline-block; padding:6px 10px; border-radius:999px;
            background:#EAF3FA; color:#123B6D; font-weight:700; margin-right:6px;
        }
        .summary-wrap {
            border: 1px solid #E4E7EC;
            border-radius: 18px;
            background: #FFFFFF;
            padding: 18px 20px;
            margin: 6px 0 18px 0;
            box-shadow: 0 6px 18px rgba(16,24,40,.05);
        }
        .summary-title {
            font-size: 15px;
            font-weight: 800;
            color: #123B6D;
            margin-bottom: 12px;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: 1.15fr 1.45fr 1fr 1fr;
            gap: 12px;
        }
        .summary-item {
            border: 1px solid #EEF2F6;
            border-radius: 14px;
            padding: 14px 16px;
            background: #F8FAFC;
            min-height: 86px;
        }
        .summary-label {
            color: #667085;
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        .summary-value {
            color: #101828;
            font-size: 22px;
            font-weight: 900;
            line-height: 1.15;
        }
        .summary-sub {
            color: #667085;
            font-size: 12px;
            margin-top: 6px;
        }
        .group-row {
            display: flex;
            flex-wrap: wrap;
            gap: 7px;
            margin-top: 2px;
        }
        .group-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 42px;
            height: 34px;
            border-radius: 10px;
            color: white;
            font-weight: 900;
            font-size: 15px;
            padding: 0 10px;
        }
        .status-ready {
            color: #15803D;
            background: #ECFDF3;
            border: 1px solid #BBF7D0;
            border-radius: 999px;
            display: inline-block;
            padding: 6px 10px;
            font-size: 13px;
            font-weight: 800;
            margin-top: 2px;
        }
        @media (max-width: 900px) {
            .summary-grid {grid-template-columns: 1fr 1fr;}
        }

        .plan-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 10px 0 18px 0;
        }

        .plan-card {
            border: 1px solid #E4E7EC;
            border-radius: 16px;
            background: #FFFFFF;
            padding: 15px;
            min-height: 148px;
            box-shadow: 0 6px 18px rgba(16,24,40,.05);
        }

        .plan-card.empty {
            background: #F8FAFC;
            border-style: dashed;
        }

        .plan-group {
            font-size: 12px;
            font-weight: 900;
            color: #667085;
            margin-bottom: 8px;
        }

        .plan-name {
            color: #123B6D;
            font-size: 18px;
            font-weight: 900;
            line-height: 1.2;
            margin-bottom: 8px;
        }

        .plan-detail {
            color: #667085;
            font-size: 12px;
            line-height: 1.5;
        }

        .plan-source {
            display: inline-block;
            margin-top: 10px;
            padding: 5px 9px;
            border-radius: 999px;
            background: #EFF6FF;
            color: #1D4ED8;
            font-size: 11px;
            font-weight: 800;
        }

        .plan-section {
            border: 1px solid #E4E7EC;
            border-radius: 18px;
            background: #FFFFFF;
            padding: 16px;
            box-shadow: 0 6px 18px rgba(16,24,40,.04);
        }

        @media (max-width: 1100px) {
            .plan-grid {grid-template-columns: 1fr 1fr;}
        }

        @media (max-width: 650px) {
            .plan-grid {grid-template-columns: 1fr;}
        }

        /* Harita sütunu masaüstünde kaydırma sırasında görünür kalır. */
        @media (min-width: 901px) {
            div[data-testid="stColumn"]:has(.sticky-map-anchor) {
                position: sticky;
                top: 0.75rem;
                align-self: flex-start;
                z-index: 20;
            }
        }

        .sticky-map-anchor {
            height: 1px;
            width: 1px;
            overflow: hidden;
        }

        .product-header {
            border: 1px solid #E4E7EC;
            border-radius: 20px;
            padding: 20px 24px;
            margin: 4px 0 18px 0;
            background:
                radial-gradient(circle at top right, rgba(37,99,235,.10), transparent 32%),
                linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
            box-shadow: 0 8px 24px rgba(16,24,40,.06);
        }

        .product-kicker {
            color: #2563EB;
            font-size: 12px;
            font-weight: 900;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: 6px;
        }

        .product-title {
            color: #123B6D;
            font-size: 32px;
            line-height: 1.12;
            font-weight: 900;
            margin: 0;
        }

        .product-subtitle {
            color: #667085;
            font-size: 15px;
            margin-top: 8px;
        }

        .product-date {
            display: inline-block;
            margin-top: 13px;
            padding: 7px 11px;
            border-radius: 999px;
            background: #EFF6FF;
            color: #1D4ED8;
            border: 1px solid #BFDBFE;
            font-size: 13px;
            font-weight: 800;
        }

        .timeline-caption {
            color: #667085;
            font-size: 12px;
            margin: 2px 0 8px 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_PATH = Path(__file__).with_name("pharmacies.csv")

@st.cache_data
def load_pharmacies() -> pd.DataFrame:
    """
    CSV yalnızca yeni çembersel yerleşim standardını karşılıyorsa kullanılır.
    Eski veya hatalı koordinatlı CSV otomatik olarak yeniden oluşturulur.
    """
    if DATA_PATH.exists():
        try:
            existing = pd.read_csv(DATA_PATH)
            if pharmacy_layout_is_valid(existing):
                return existing
        except Exception:
            pass

    generated = generate_pharmacies(seed=42)
    generated.to_csv(DATA_PATH, index=False)
    return generated

pharmacies = load_pharmacies()

def pharmacy_group_for_id(pharmacy_id: int | None) -> str | None:
    if pharmacy_id is None:
        return None

    match = pharmacies.loc[
        pharmacies["pharmacy_id"].astype(int) == int(pharmacy_id),
        "group",
    ]
    if match.empty:
        return None

    return str(match.iloc[0]).strip().upper()


def sanitize_selected_by_group(
    selected_by_group: dict,
    allowed_groups: list[str] | tuple[str, ...] | None = None,
) -> dict[str, int]:
    """
    Her grup anahtarında yalnızca aynı gruba ait eczane kalmasını sağlar.
    Örnek: A1 anahtarına B2 eczanesi yazılmışsa seçim silinir.
    """
    allowed = (
        {str(group).strip().upper() for group in allowed_groups}
        if allowed_groups is not None
        else None
    )

    cleaned: dict[str, int] = {}

    for raw_group, raw_pharmacy_id in dict(selected_by_group).items():
        group_name = str(raw_group).strip().upper()

        if allowed is not None and group_name not in allowed:
            continue

        try:
            pharmacy_id = int(raw_pharmacy_id)
        except (TypeError, ValueError):
            continue

        actual_group = pharmacy_group_for_id(pharmacy_id)
        if actual_group == group_name:
            cleaned[group_name] = pharmacy_id

    return cleaned


def group_locked_candidates(
    group_name: str,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """UI tarafında ikinci bir grup kilidi uygular."""
    normalized = str(group_name).strip().upper()

    if candidates.empty:
        return candidates.copy()

    return candidates[
        candidates["group"].astype(str).str.strip().str.upper()
        == normalized
    ].copy()


def marker_color(status: str) -> str:
    return {
        "selected": "blue",
        "selectable": "green",
        "distance_blocked": "red",
        "gap_blocked": "orange",
        "inactive": "gray",
    }.get(status, "gray")


def clicked_pharmacy_id(map_event: dict | None) -> int | None:
    if not map_event:
        return None

    tooltip = map_event.get("last_object_clicked_tooltip")
    if not tooltip:
        return None

    match = re.search(r"PID:(\d+)", str(tooltip))
    return int(match.group(1)) if match else None



def build_decision_engine_card(row: pd.Series, min_gap_days: int, min_distance_km: float) -> str:
    score = float(row.get("decision_score", 0) or 0)
    gap = row.get("days_since_last_duty")
    distance = row.get("distance_to_nearest_selected_km")
    historical_load = float(row.get("historical_load", 0) or 0)
    weekend_count = int(row.get("weekend_count", 0) or 0)
    holiday_count = int(row.get("holiday_count", 0) or 0)
    selectable = bool(row.get("selectable", False))

    checks = [
        ("Grup kontrolü", True, f'{row.get("group", "-")} aktif grupta'),
        (
            "Yakınlık kontrolü",
            distance is None or float(distance) >= min_distance_km,
            "Uygun" if distance is None else f"{float(distance):.2f} km",
        ),
        (
            f"{min_gap_days} gün kontrolü",
            gap is not None and float(gap) >= min_gap_days,
            "-" if gap is None else f"{int(gap)} gün",
        ),
        ("Geçmiş yük dengesi", historical_load <= 8.5, f"{historical_load:.1f} yük"),
        ("Hafta sonu dengesi", weekend_count <= 2, f"{weekend_count} nöbet"),
        ("Bayram dengesi", holiday_count <= 1, f"{holiday_count} nöbet"),
    ]

    rows_html = ""
    for title, passed, detail in checks:
        color = "#16A34A" if passed else "#F59E0B"
        icon = "✓" if passed else "!"
        rows_html += dedent(
            f"""
            <div style="display:flex;align-items:center;justify-content:space-between;
                        padding:9px 0;border-bottom:1px solid #EEF2F6;">
              <div style="display:flex;align-items:center;gap:9px;">
                <span style="width:22px;height:22px;border-radius:50%;background:{color};
                             color:white;display:inline-flex;align-items:center;justify-content:center;
                             font-weight:800;font-size:12px;">{icon}</span>
                <span style="font-weight:700;color:#344054;">{title}</span>
              </div>
              <span style="color:#667085;font-size:12px;">{detail}</span>
            </div>
            """
        ).strip()

    score_color = "#16A34A" if score >= 80 else "#F59E0B" if score >= 60 else "#DC2626"
    result_text = "Nöbete atanabilir" if selectable else "Şu anda atanamaz"
    result_bg = "#ECFDF3" if selectable else "#FEF2F2"
    result_color = "#15803D" if selectable else "#B91C1C"

    return dedent(
        f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            * {{ box-sizing: border-box; }}
            body {{
              margin: 0;
              padding: 2px;
              background: transparent;
              font-family: Arial, Helvetica, sans-serif;
              color: #101828;
            }}
          </style>
        </head>
        <body>
        <div style="border:1px solid #D0D5DD;border-radius:18px;padding:18px;background:#FFFFFF;
                    box-shadow:0 8px 22px rgba(16,24,40,.06);">
      <div style="font-size:19px;font-weight:900;color:#123B6D;margin-bottom:4px;">
        AYÇA Decision Engine
      </div>
      <div style="color:#667085;font-size:13px;margin-bottom:14px;">
        {row.get("pharmacy_name", "Eczane")} için karar analizi
      </div>

      {rows_html}

      <div style="display:flex;align-items:center;justify-content:space-between;margin-top:16px;">
        <div>
          <div style="font-size:12px;color:#667085;">Uygunluk Skoru</div>
          <div style="font-size:34px;font-weight:900;color:{score_color};">{score:.0f}<span style="font-size:16px;">/100</span></div>
        </div>
        <div style="padding:10px 14px;border-radius:12px;background:{result_bg};
                    color:{result_color};font-weight:900;">
          {"✅" if selectable else "⛔"} {result_text}
        </div>
      </div>
        </div>
        </body>
        </html>
        """
    ).strip()


def selection_reason(row: pd.Series) -> str:
    score = float(row.get("decision_score", 0) or 0)
    gap = row.get("days_since_last_duty")
    historical_load = float(row.get("historical_load", 0) or 0)
    weekend_count = int(row.get("weekend_count", 0) or 0)
    holiday_count = int(row.get("holiday_count", 0) or 0)

    gap_text = "-" if gap is None or pd.isna(gap) else f"{int(gap)} gün ara"
    return (
        f"Uygunluk %{score:.0f} · {gap_text} · "
        f"{historical_load:.1f} yük · "
        f"{weekend_count} hafta sonu · {holiday_count} bayram"
    )


def build_plan_cards(
    active_groups: list[str],
    selected_by_group: dict,
    source_by_group: dict,
    candidates_by_group: dict[str, pd.DataFrame],
) -> str:
    cards = []

    for group_name in active_groups:
        pid = selected_by_group.get(group_name)

        if pid is None:
            cards.append(
                f"""
                <div class="plan-card empty">
                  <div class="plan-group">{group_name} GRUBU</div>
                  <div class="plan-name">Henüz seçilmedi</div>
                  <div class="plan-detail">
                    Harita sekmesindeki yeşil adaylardan bir eczane seçin.
                  </div>
                </div>
                """
            )
            continue

        group_df = candidates_by_group.get(group_name, pd.DataFrame())
        match = (
            group_df.loc[group_df["pharmacy_id"] == pid]
            if not group_df.empty
            else pd.DataFrame()
        )

        if match.empty:
            pharmacy_match = pharmacies.loc[pharmacies["pharmacy_id"] == pid]
            if pharmacy_match.empty:
                continue
            row = pharmacy_match.iloc[0].copy()
            row["decision_score"] = 0
            row["days_since_last_duty"] = None
        else:
            row = match.iloc[0]

        source = source_by_group.get(group_name, "Mevcut seçim")

        cards.append(
            f"""
            <div class="plan-card">
              <div class="plan-group">{group_name} GRUBU</div>
              <div class="plan-name">{row["pharmacy_name"]}</div>
              <div class="plan-detail">{selection_reason(row)}</div>
              <div class="plan-source">{source}</div>
            </div>
            """
        )

    return dedent(
        f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            * {{ box-sizing: border-box; }}
            body {{
              margin: 0;
              padding: 2px;
              background: transparent;
              font-family: Arial, Helvetica, sans-serif;
              color: #101828;
            }}
            .plan-grid {{
              display: grid;
              grid-template-columns: repeat(4, minmax(0, 1fr));
              gap: 12px;
            }}
            .plan-card {{
              border: 1px solid #E4E7EC;
              border-radius: 16px;
              background: #FFFFFF;
              padding: 15px;
              min-height: 154px;
              box-shadow: 0 6px 18px rgba(16,24,40,.05);
            }}
            .plan-card.empty {{
              background: #F8FAFC;
              border-style: dashed;
            }}
            .plan-group {{
              font-size: 12px;
              font-weight: 900;
              color: #667085;
              margin-bottom: 8px;
            }}
            .plan-name {{
              color: #123B6D;
              font-size: 18px;
              font-weight: 900;
              line-height: 1.2;
              margin-bottom: 8px;
            }}
            .plan-detail {{
              color: #667085;
              font-size: 12px;
              line-height: 1.5;
            }}
            .plan-source {{
              display: inline-block;
              margin-top: 10px;
              padding: 5px 9px;
              border-radius: 999px;
              background: #EFF6FF;
              color: #1D4ED8;
              font-size: 11px;
              font-weight: 800;
            }}
            @media (max-width: 900px) {{
              .plan-grid {{ grid-template-columns: 1fr 1fr; }}
            }}
          </style>
        </head>
        <body>
          <div class="plan-grid">
            {''.join(cards)}
          </div>
        </body>
        </html>
        """
    ).strip()


def destination_point(
    center_lat: float,
    center_lon: float,
    distance_km: float,
    angle_deg: float,
) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    north_km = distance_km * math.sin(angle)
    east_km = distance_km * math.cos(angle)

    lat = center_lat + north_km / 111.32
    lon = center_lon + east_km / (
        111.32 * math.cos(math.radians(center_lat))
    )
    return lat, lon


def sector_polygon(
    center_lat: float,
    center_lon: float,
    inner_km: float,
    outer_km: float,
    start_angle: float,
    end_angle: float,
    steps: int = 28,
) -> list[tuple[float, float]]:
    outer_points = [
        destination_point(
            center_lat,
            center_lon,
            outer_km,
            start_angle + (end_angle - start_angle) * index / steps,
        )
        for index in range(steps + 1)
    ]

    if inner_km <= 0:
        return [(center_lat, center_lon)] + outer_points

    inner_points = [
        destination_point(
            center_lat,
            center_lon,
            inner_km,
            end_angle - (end_angle - start_angle) * index / steps,
        )
        for index in range(steps + 1)
    ]

    return outer_points + inner_points


def add_circular_group_grid(
    fmap: folium.Map,
    map_df: pd.DataFrame,
    active_groups: list[str],
) -> None:
    center_lat = DEMO_CENTER_LAT
    center_lon = DEMO_CENTER_LON

    region_colors = {
        "A": "#2563EB",
        "B": "#16A34A",
        "C": "#EC4899",
        "D": "#7C3AED",
    }

    region_angles = REGION_ANGLES
    ring_limits = RING_LIMITS_KM

    active_set = set(active_groups)

    # Önce bütün 16 alt grubu silik olarak çiz.
    for region in ("A", "B", "C", "D"):
        start_angle, end_angle = region_angles[region]
        color = region_colors[region]

        for ring_no in range(1, 5):
            inner_km, outer_km = ring_limits[ring_no]
            group_name = f"{region}{ring_no}"
            is_active = group_name in active_set

            folium.Polygon(
                locations=sector_polygon(
                    center_lat,
                    center_lon,
                    inner_km,
                    outer_km,
                    start_angle,
                    end_angle,
                ),
                color=color,
                weight=3 if is_active else 1.2,
                opacity=0.95 if is_active else 0.22,
                dash_array="8, 7" if is_active else "4, 9",
                fill=True,
                fill_color=color,
                fill_opacity=0.14 if is_active else 0.018,
                tooltip=(
                    f"{group_name} · Bugün aktif"
                    if is_active
                    else f"{group_name} · Pasif"
                ),
            ).add_to(fmap)

            label_distance = (inner_km + outer_km) / 2
            label_angle = (start_angle + end_angle) / 2
            label_lat, label_lon = destination_point(
                center_lat,
                center_lon,
                label_distance,
                label_angle,
            )

            if is_active:
                label_html = f"""
                <div style="
                    transform:translate(-50%,-50%);
                    background:{color};
                    color:white;
                    border:2px solid white;
                    border-radius:999px;
                    padding:4px 8px;
                    font-size:11px;
                    font-weight:900;
                    box-shadow:0 3px 9px rgba(16,24,40,.25);">
                    {group_name}
                </div>
                """
            else:
                label_html = f"""
                <div style="
                    transform:translate(-50%,-50%);
                    color:{color};
                    background:rgba(255,255,255,.65);
                    border-radius:999px;
                    padding:1px 4px;
                    font-size:8px;
                    font-weight:700;
                    opacity:.35;">
                    {group_name}
                </div>
                """

            folium.Marker(
                [label_lat, label_lon],
                icon=folium.DivIcon(html=label_html),
                interactive=False,
            ).add_to(fmap)

    # Ortak merkez.
    folium.CircleMarker(
        [center_lat, center_lon],
        radius=6,
        color="#123B6D",
        weight=2,
        fill=True,
        fill_color="#FFFFFF",
        fill_opacity=1,
        tooltip="AYÇA grup merkezi",
    ).add_to(fmap)

    folium.Marker(
        [center_lat, center_lon],
        icon=folium.DivIcon(
            html="""
            <div style="
                transform:translate(-50%,-34px);
                white-space:nowrap;
                background:#123B6D;
                color:white;
                border-radius:8px;
                padding:4px 7px;
                font-size:10px;
                font-weight:800;">
                MERKEZ
            </div>
            """
        ),
        interactive=False,
    ).add_to(fmap)


def build_folium_map(
    map_df: pd.DataFrame,
    selected_df: pd.DataFrame,
    min_distance_km: float,
    active_groups: list[str],
) -> folium.Map:
    center = [DEMO_CENTER_LAT, DEMO_CENTER_LON]
    fmap = folium.Map(
        location=center,
        zoom_start=13,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # Çembersel 4 bölge × 4 halka grup yapısını haritaya ekle.
    add_circular_group_grid(
        fmap=fmap,
        map_df=map_df,
        active_groups=active_groups,
    )

    # Harita görünümünü bütün çembersel yerleşimi kapsayacak şekilde sabitle.
    outer_radius_km = max(value[1] for value in RING_LIMITS_KM.values())
    south_west = destination_point(
        DEMO_CENTER_LAT,
        DEMO_CENTER_LON,
        outer_radius_km * 1.12,
        225,
    )
    north_east = destination_point(
        DEMO_CENTER_LAT,
        DEMO_CENTER_LON,
        outer_radius_km * 1.12,
        45,
    )
    fmap.fit_bounds([south_west, north_east])

    # Seçilen eczanelerin minimum mesafe çemberleri.
    for row in selected_df.itertuples():
        folium.Circle(
            location=[row.lat, row.lon],
            radius=min_distance_km * 1000,
            color="#1D4ED8",
            weight=2,
            fill=True,
            fill_color="#1D4ED8",
            fill_opacity=0.08,
            tooltip=f"{row.pharmacy_name} minimum mesafe alanı",
        ).add_to(fmap)

    # MarkerCluster kullanmadan doğrudan marker ekliyoruz; böylece her marker tıklanabilir.
    for row in map_df.itertuples():
        score_text = "-" if pd.isna(row.decision_score) else f"{float(row.decision_score):.2f}"
        distance_text = (
            "-"
            if pd.isna(row.distance_to_nearest_selected_km)
            else f"{float(row.distance_to_nearest_selected_km):.2f} km"
        )
        tooltip = f"PID:{int(row.pharmacy_id)} | {row.pharmacy_name} | {row.group}"

        popup_html = f"""
        <div style="font-family:Arial; min-width:230px">
          <b style="font-size:15px">{row.pharmacy_name}</b><br>
          <b>Grup:</b> {row.group}<br>
          <b>Durum:</b> {row.status}<br>
          <b>Gerekçe:</b> {row.reason}<br>
          <b>Uygunluk skoru:</b> {score_text}<br>
          <b>En yakın seçili:</b> {distance_text}
        </div>
        """

        folium.CircleMarker(
            location=[row.lat, row.lon],
            radius=9 if row.status == "selected" else 6,
            color="white",
            weight=2,
            fill=True,
            fill_color=marker_color(row.status),
            fill_opacity=0.95,
            tooltip=tooltip,
            popup=folium.Popup(popup_html, max_width=320),
        ).add_to(fmap)

        # Aktif adayların isimleri haritada sürekli görünür.
        if row.status in {"selected", "selectable"}:
            folium.Marker(
                location=[row.lat, row.lon],
                icon=folium.DivIcon(
                    html=f"""
                    <div style="
                      transform: translate(-45%, -30px);
                      white-space: nowrap;
                      font-size: 10px;
                      font-weight: 700;
                      color: #123B6D;
                      text-shadow: 0 0 3px white, 0 0 3px white;">
                      {row.pharmacy_name}
                    </div>
                    """
                ),
                interactive=False,
            ).add_to(fmap)

    return fmap


def generate_multi_day_plan(
    pharmacies: pd.DataFrame,
    state: SimulationState,
    start_date: date,
    days_count: int,
    min_distance_km: float,
    min_gap_days: int,
    rotation_start_date: date,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    schedule_rows = []
    assignments_by_date: dict[str, dict[str, int]] = {}
    temp_state = state.copy()

    start_day_no = (start_date - rotation_start_date).days

    for offset in range(days_count):
        sim_date = start_date + timedelta(days=offset)
        rotation_index = (start_day_no + offset) % len(KOMB_ABC)
        selected_for_day: list[int] = []
        selected_by_group_for_day: dict[str, int] = {}

        for group_name in group_for_day(rotation_index):
            result = eligible_candidates(
                pharmacies=pharmacies,
                group_name=group_name,
                selected_ids=selected_for_day,
                state=temp_state,
                current_date=sim_date,
                min_distance_km=min_distance_km,
                min_gap_days=min_gap_days,
            )

            valid = result[result["selectable"]].sort_values(
                ["decision_score", "distance_to_nearest_selected_km"],
                ascending=[False, False],
            )

            if valid.empty:
                schedule_rows.append(
                    {
                        "Tarih": sim_date.strftime("%d.%m.%Y"),
                        "Gün": sim_date.strftime("%A"),
                        "Grup": group_name,
                        "Eczane": "Uygun aday bulunamadı",
                        "Skor": None,
                        "Eczane ID": None,
                    }
                )
                continue

            selected_row = valid.iloc[0]
            pharmacy_id = int(selected_row["pharmacy_id"])

            selected_for_day.append(pharmacy_id)
            selected_by_group_for_day[group_name] = pharmacy_id
            temp_state.apply_assignment(pharmacy_id, sim_date)

            schedule_rows.append(
                {
                    "Tarih": sim_date.strftime("%d.%m.%Y"),
                    "Gün": sim_date.strftime("%A"),
                    "Grup": group_name,
                    "Eczane": selected_row["pharmacy_name"],
                    "Skor": round(float(selected_row["decision_score"]), 1),
                    "Eczane ID": pharmacy_id,
                }
            )

        assignments_by_date[sim_date.isoformat()] = selected_by_group_for_day

    return pd.DataFrame(schedule_rows), assignments_by_date


# ==========================================================
# SESSION STATE VE PLANLAMA KONTROLLERİ
# ==========================================================

ROTATION_START_DATE = date(2026, 8, 1)

if "state" not in st.session_state:
    st.session_state.state = SimulationState.from_dataframe(pharmacies)

if "selected_by_group" not in st.session_state:
    st.session_state.selected_by_group = {}

if "selection_source_by_group" not in st.session_state:
    st.session_state.selection_source_by_group = {}

if "manual_selected_date" not in st.session_state:
    st.session_state.manual_selected_date = ROTATION_START_DATE

if "manual_date_widget" not in st.session_state:
    st.session_state.manual_date_widget = st.session_state.manual_selected_date

if "auto_plan_ready" not in st.session_state:
    st.session_state.auto_plan_ready = False

if "auto_schedule_df" not in st.session_state:
    st.session_state.auto_schedule_df = pd.DataFrame()

if "auto_assignments_by_date" not in st.session_state:
    st.session_state.auto_assignments_by_date = {}

if "auto_generated_start_date" not in st.session_state:
    st.session_state.auto_generated_start_date = ROTATION_START_DATE

if "auto_generated_days_count" not in st.session_state:
    st.session_state.auto_generated_days_count = 10

if "auto_view_date" not in st.session_state:
    st.session_state.auto_view_date = ROTATION_START_DATE

if "canonical_current_date" not in st.session_state:
    st.session_state.canonical_current_date = st.session_state.manual_selected_date

if "plan_calendar_date" not in st.session_state:
    st.session_state.plan_calendar_date = st.session_state.canonical_current_date

if "plan_calendar_picker" not in st.session_state:
    st.session_state.plan_calendar_picker = st.session_state.plan_calendar_date

state: SimulationState = st.session_state.state


def clear_current_selections() -> None:
    st.session_state.selected_by_group = {}
    st.session_state.selection_source_by_group = {}


def sync_manual_date_from_widget() -> None:
    selected_date = st.session_state.manual_date_widget
    st.session_state.manual_selected_date = selected_date
    st.session_state.canonical_current_date = selected_date
    st.session_state.plan_calendar_date = selected_date
    st.session_state.plan_calendar_picker = selected_date
    clear_current_selections()


def set_manual_date(target_date: date) -> None:
    safe_date = max(ROTATION_START_DATE, target_date)
    st.session_state.manual_selected_date = safe_date
    st.session_state.manual_date_widget = safe_date
    st.session_state.canonical_current_date = safe_date
    st.session_state.plan_calendar_date = safe_date
    st.session_state.plan_calendar_picker = safe_date
    clear_current_selections()


def go_previous_manual_day() -> None:
    set_manual_date(
        st.session_state.manual_selected_date - timedelta(days=1)
    )


def go_next_manual_day() -> None:
    set_manual_date(
        st.session_state.manual_selected_date + timedelta(days=1)
    )


def go_today_manual() -> None:
    set_manual_date(max(ROTATION_START_DATE, date.today()))


def sync_plan_calendar_date() -> None:
    """Takvim, özet, harita ve plan ekranını aynı tarihe geçirir."""
    selected_date = st.session_state.plan_calendar_picker

    st.session_state.plan_calendar_date = selected_date
    st.session_state.canonical_current_date = selected_date
    st.session_state.manual_selected_date = selected_date
    st.session_state.manual_date_widget = selected_date

    # Tarih oluşturulmuş otomatik planın içindeyse otomatik gün
    # gezgini de aynı tarihe taşınır. Plan dışında ise tarih korunur
    # ve o gün için seçim bulunmadığı gösterilir.
    if st.session_state.get("auto_plan_ready", False):
        generated_start = st.session_state.auto_generated_start_date
        generated_days = int(st.session_state.auto_generated_days_count)
        generated_dates = [
            generated_start + timedelta(days=offset)
            for offset in range(generated_days)
        ]
        if selected_date in generated_dates:
            st.session_state.auto_view_date = selected_date
        elif st.session_state.get("planning_mode") == "Otomatik Çok Günlük Plan":
            # Plan dışında bir tarih seçilmişse tarih korunur; plan tablosu
            # o gün için atama olmadığını açıkça gösterir.
            st.session_state.auto_view_date = generated_dates[0]


with st.sidebar:
    st.header("Takvim ve Plan Ayarları")

    planning_mode = st.radio(
        "Çalışma modu",
        options=["Tek Gün / Manuel Seçim", "Otomatik Çok Günlük Plan"],
        key="planning_mode",
    )

    if planning_mode == "Tek Gün / Manuel Seçim":
        st.date_input(
            "Nöbet gününü takvimden seçin",
            min_value=ROTATION_START_DATE,
            max_value=ROTATION_START_DATE + timedelta(days=365),
            format="DD.MM.YYYY",
            key="manual_date_widget",
            on_change=sync_manual_date_from_widget,
        )

        current_date = st.session_state.canonical_current_date
        start_date = ROTATION_START_DATE
        day_no = (current_date - ROTATION_START_DATE).days + 1

        nav_prev, nav_today, nav_next = st.columns(3)

        with nav_prev:
            st.button(
                "←",
                help="Önceki gün",
                use_container_width=True,
                key="manual_previous_day",
                on_click=go_previous_manual_day,
            )

        with nav_today:
            st.button(
                "Bugün",
                use_container_width=True,
                key="manual_today",
                on_click=go_today_manual,
            )

        with nav_next:
            st.button(
                "→",
                help="Sonraki gün",
                use_container_width=True,
                key="manual_next_day",
                on_click=go_next_manual_day,
            )

        st.caption(
            f"Seçilen gün: {current_date.strftime('%d.%m.%Y')} · "
            f"Rotasyon günü: {((day_no - 1) % len(KOMB_ABC)) + 1}"
        )

    else:
        auto_start_date = st.date_input(
            "Plan başlangıç tarihi",
            value=st.session_state.auto_generated_start_date,
            min_value=ROTATION_START_DATE,
            max_value=ROTATION_START_DATE + timedelta(days=365),
            format="DD.MM.YYYY",
            key="auto_plan_start_widget",
        )

        auto_days_count = st.slider(
            "Otomatik oluşturulacak gün sayısı",
            min_value=3,
            max_value=31,
            value=int(st.session_state.auto_generated_days_count),
            key="auto_plan_days_widget",
        )

        current_date = auto_start_date
        start_date = ROTATION_START_DATE
        day_no = (current_date - ROTATION_START_DATE).days + 1

        st.caption(
            f"{auto_start_date.strftime('%d.%m.%Y')} tarihinden başlayarak "
            f"{auto_days_count} günlük plan oluşturulur."
        )

    min_distance_km = st.slider(
        "Minimum eczaneler arası mesafe",
        min_value=0.2,
        max_value=3.0,
        value=1.0,
        step=0.1,
        key="minimum_distance_slider",
    )

    min_gap_days = st.slider(
        "Minimum nöbet aralığı",
        min_value=7,
        max_value=30,
        value=14,
        step=1,
        key="minimum_gap_slider",
    )

    st.divider()

    if planning_mode == "Tek Gün / Manuel Seçim":
        if st.button(
            "Seçimleri Temizle",
            use_container_width=True,
            key="clear_manual_selections",
        ):
            clear_current_selections()
            st.rerun()

        if st.button(
            "Günü Otomatik Tamamla",
            type="primary",
            use_container_width=True,
            key="complete_single_day",
        ):
            active_groups_for_auto = group_for_day(
                (day_no - 1) % len(KOMB_ABC)
            )
            chosen = {}
            temp_state = state.copy()

            for group_name in active_groups_for_auto:
                result = eligible_candidates(
                    pharmacies=pharmacies,
                    group_name=group_name,
                    selected_ids=list(chosen.values()),
                    state=temp_state,
                    current_date=current_date,
                    min_distance_km=min_distance_km,
                    min_gap_days=min_gap_days,
                )

                valid = result[result["selectable"]].sort_values(
                    ["decision_score", "distance_to_nearest_selected_km"],
                    ascending=[False, False],
                    na_position="last",
                )

                if not valid.empty:
                    pharmacy_id = int(valid.iloc[0]["pharmacy_id"])
                    chosen[group_name] = pharmacy_id
                    temp_state.apply_assignment(pharmacy_id, current_date)

            st.session_state.selected_by_group = chosen
            st.session_state.selection_source_by_group = {
                group_name: "AYÇA otomatik öneri"
                for group_name in chosen
            }
            st.rerun()

    else:
        if st.button(
            "Çok Günlük Planı Oluştur",
            type="primary",
            use_container_width=True,
            key="generate_multi_day_plan_button",
        ):
            generated_df, generated_assignments = generate_multi_day_plan(
                pharmacies=pharmacies,
                state=state,
                start_date=auto_start_date,
                days_count=int(auto_days_count),
                min_distance_km=min_distance_km,
                min_gap_days=min_gap_days,
                rotation_start_date=ROTATION_START_DATE,
            )

            st.session_state.auto_schedule_df = generated_df
            st.session_state.auto_assignments_by_date = generated_assignments
            st.session_state.auto_generated_start_date = auto_start_date
            st.session_state.auto_generated_days_count = int(auto_days_count)
            st.session_state.auto_view_date = auto_start_date
            st.session_state.canonical_current_date = auto_start_date
            st.session_state.plan_calendar_date = auto_start_date
            st.session_state.plan_calendar_picker = auto_start_date
            st.session_state.auto_plan_ready = True
            clear_current_selections()
            st.rerun()


# ==========================================================
# AKTİF GÜN VE OTOMATİK PLAN GÖRÜNÜMÜ
# ==========================================================

auto_schedule_df = pd.DataFrame()
auto_assignments_by_date: dict[str, dict[str, int]] = {}

if planning_mode == "Otomatik Çok Günlük Plan":
    if st.session_state.auto_plan_ready:
        auto_schedule_df = st.session_state.auto_schedule_df
        auto_assignments_by_date = (
            st.session_state.auto_assignments_by_date
        )

        generated_start = st.session_state.auto_generated_start_date
        generated_days = int(st.session_state.auto_generated_days_count)

        available_auto_dates = [
            generated_start + timedelta(days=offset)
            for offset in range(generated_days)
        ]

        if st.session_state.auto_view_date not in available_auto_dates:
            st.session_state.auto_view_date = generated_start

        auto_date_index = available_auto_dates.index(
            st.session_state.auto_view_date
        )

        st.markdown("#### Otomatik Plan Günleri")
        st.markdown(
            '<div class="timeline-caption">'
            'Bir güne tıklayın; üst özet, harita, grup yapısı ve plan birlikte değişir.'
            '</div>',
            unsafe_allow_html=True,
        )

        previous_col, date_label_col, next_col = st.columns([1, 3, 1])

        with previous_col:
            if st.button(
                "← Önceki Gün",
                key="auto_previous_date_button",
                use_container_width=True,
                disabled=auto_date_index == 0,
            ):
                new_date = available_auto_dates[auto_date_index - 1]
                st.session_state.auto_view_date = new_date
                st.session_state.canonical_current_date = new_date
                st.session_state.plan_calendar_date = new_date
                st.session_state.plan_calendar_picker = new_date
                st.rerun()

        with date_label_col:
            st.markdown(
                f"### {st.session_state.auto_view_date.strftime('%d.%m.%Y')}"
            )

        with next_col:
            if st.button(
                "Sonraki Gün →",
                key="auto_next_date_button",
                use_container_width=True,
                disabled=auto_date_index >= len(available_auto_dates) - 1,
            ):
                new_date = available_auto_dates[auto_date_index + 1]
                st.session_state.auto_view_date = new_date
                st.session_state.canonical_current_date = new_date
                st.session_state.plan_calendar_date = new_date
                st.session_state.plan_calendar_picker = new_date
                st.rerun()

        # Tarihleri yatay bir zaman çizgisi gibi göster.
        for row_start in range(0, len(available_auto_dates), 7):
            row_dates = available_auto_dates[row_start:row_start + 7]
            row_columns = st.columns(len(row_dates))

            for column, timeline_date in zip(row_columns, row_dates):
                is_selected = (
                    timeline_date == st.session_state.auto_view_date
                )
                button_label = (
                    f"● {timeline_date.day}"
                    if is_selected
                    else str(timeline_date.day)
                )

                with column:
                    if st.button(
                        button_label,
                        key=f"auto_timeline_{timeline_date.isoformat()}",
                        use_container_width=True,
                        type="primary" if is_selected else "secondary",
                        help=timeline_date.strftime("%d.%m.%Y"),
                    ):
                        st.session_state.auto_view_date = timeline_date
                        st.session_state.canonical_current_date = timeline_date
                        st.session_state.plan_calendar_date = timeline_date
                        st.session_state.plan_calendar_picker = timeline_date
                        st.rerun()

        # canonical_current_date; takvim, özet, harita ve planın
        # ortak tarihidir. Otomatik gün seçicisi yalnızca kullanıcı
        # onu değiştirdiğinde bu tarihi günceller.
        current_date = st.session_state.canonical_current_date
        day_no = (current_date - ROTATION_START_DATE).days + 1
        active_groups = group_for_day(
            (day_no - 1) % len(KOMB_ABC)
        )

        selected_by_group_for_map = auto_assignments_by_date.get(
            current_date.isoformat(),
            {},
        )

        locked_auto_selection = sanitize_selected_by_group(
            selected_by_group_for_map,
            allowed_groups=active_groups,
        )
        st.session_state.selected_by_group = locked_auto_selection
        st.session_state.selection_source_by_group = {
            group_name: "AYÇA çok günlük otomatik plan"
            for group_name in locked_auto_selection
        }

    else:
        current_date = auto_start_date
        day_no = (current_date - ROTATION_START_DATE).days + 1
        active_groups = group_for_day(
            (day_no - 1) % len(KOMB_ABC)
        )
        clear_current_selections()
        st.info(
            "Otomatik planı görmek için sol menüden "
            "'Çok Günlük Planı Oluştur' butonuna basın."
        )

else:
    current_date = st.session_state.canonical_current_date
    day_no = (current_date - ROTATION_START_DATE).days + 1
    active_groups = group_for_day(
        (day_no - 1) % len(KOMB_ABC)
    )

# Başka bir tarihten veya eski session state'ten yanlış grup seçimi
# taşınmışsa burada temizlenir.
cleaned_selections = sanitize_selected_by_group(
    st.session_state.selected_by_group,
    allowed_groups=active_groups,
)
if cleaned_selections != st.session_state.selected_by_group:
    st.session_state.selected_by_group = cleaned_selections
    st.session_state.selection_source_by_group = {
        group_name: source
        for group_name, source in st.session_state.selection_source_by_group.items()
        if group_name in cleaned_selections
    }

combination_text = " + ".join(active_groups)
selected_ids = list(st.session_state.selected_by_group.values())


weekday_names = [
    "Pazartesi", "Salı", "Çarşamba", "Perşembe",
    "Cuma", "Cumartesi", "Pazar"
]
weekday_text = weekday_names[current_date.weekday()]

month_names = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
    5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
    9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
}
date_text = f"{current_date.day:02d} {month_names[current_date.month]} {current_date.year}"

mode_text = (
    "Manuel planlama"
    if planning_mode == "Tek Gün / Manuel Seçim"
    else "Otomatik çok günlük plan"
)

st.markdown(
    dedent(
        f"""
        <div class="product-header">
          <div class="product-kicker">AYÇA NÖBET · UŞAK DEMOSU</div>
          <div class="product-title">Uşak Nöbet Planlama Merkezi</div>
          <div class="product-subtitle">
            Harita, grup yapısı ve oluşturulan plan tek tarih üzerinden
            canlı olarak senkronize edilir.
          </div>
          <div class="product-date">
            {date_text} · {weekday_text} · {mode_text}
          </div>
        </div>
        """
    ).strip(),
    unsafe_allow_html=True,
)

group_colors = {
    "A": "#2563EB",
    "B": "#16A34A",
    "C": "#EC4899",
    "D": "#7C3AED",
}
group_chips = "".join(
    [
        f'<span class="group-chip" style="background:{group_colors[g[0]]};">{g}</span>'
        for g in active_groups
    ]
)

assignment_complete = len(selected_ids) == len(active_groups)
status_text = "Plan hazır" if assignment_complete else "Atamalar devam ediyor"
status_icon = "✓" if assignment_complete else "…"

st.markdown(
    dedent(
        f"""
        <div class="summary-wrap">
      <div class="summary-title">Seçilen Günün Nöbet Özeti</div>
      <div class="summary-grid">

        <div class="summary-item">
          <div class="summary-label">Nöbet Tarihi</div>
          <div class="summary-value">{date_text}</div>
          <div class="summary-sub">{weekday_text}</div>
        </div>

        <div class="summary-item">
          <div class="summary-label">Aktif Nöbet Grupları</div>
          <div class="group-row">{group_chips}</div>
          <div class="summary-sub">Her gruptan bir eczane seçilir</div>
        </div>

        <div class="summary-item">
          <div class="summary-label">Görev Alacak</div>
          <div class="summary-value">{len(active_groups)} eczane</div>
          <div class="summary-sub">{len(selected_ids)} atama tamamlandı</div>
        </div>

        <div class="summary-item">
          <div class="summary-label">Plan Durumu</div>
          <div class="status-ready">{status_icon} {status_text}</div>
          <div class="summary-sub">Kurallar canlı olarak kontrol ediliyor</div>
        </div>

      </div>
        </div>
        """
    ).strip(),
    unsafe_allow_html=True,
)

tab_map, tab_groups, tab_plan = st.tabs(
    ["🗺️ Eczane Haritası", "⭕ Grup Yapısı", "📅 Oluşturulan Plan"]
)

with tab_map:
    st.markdown(
        """
        <div class="legend">
          <span><i class="dot" style="background:#1D4ED8"></i> Seçilen</span>
          <span><i class="dot" style="background:#16A34A"></i> Seçilebilir</span>
          <span><i class="dot" style="background:#DC2626"></i> Yakınlık engeli</span>
          <span><i class="dot" style="background:#F59E0B"></i> Nöbet aralığı engeli</span>
          <span><i class="dot" style="background:#7C3AED"></i> Grup dışı / pasif</span>
          <span style="border-bottom:3px dashed #2563EB;padding-bottom:2px;">Grup sınırı</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.65, 1], gap="large")

    all_status_frames = []
    for g in active_groups:
        frame = eligible_candidates(
            pharmacies=pharmacies,
            group_name=g,
            selected_ids=selected_ids,
            state=state,
            current_date=current_date,
            min_distance_km=min_distance_km,
            min_gap_days=min_gap_days,
        )
        all_status_frames.append(frame)

    status_df = pd.concat(all_status_frames, ignore_index=True)

    base_map_df = pharmacies.copy()
    base_map_df["status"] = "inactive"
    base_map_df["reason"] = "Seçilen günün aktif kombinasyonunda değil"
    base_map_df["decision_score"] = None
    base_map_df["distance_to_nearest_selected_km"] = None
    base_map_df["days_since_last_duty"] = None
    base_map_df["selectable"] = False

    lookup = status_df.set_index("pharmacy_id")

    for idx, row in base_map_df.iterrows():
        pid = row["pharmacy_id"]
        if pid in lookup.index:
            info = lookup.loc[pid]
            if isinstance(info, pd.DataFrame):
                info = info.iloc[0]
            base_map_df.at[idx, "status"] = info["status"]
            base_map_df.at[idx, "reason"] = info["reason"]
            base_map_df.at[idx, "decision_score"] = info["decision_score"]
            base_map_df.at[idx, "distance_to_nearest_selected_km"] = info["distance_to_nearest_selected_km"]
            base_map_df.at[idx, "days_since_last_duty"] = info["days_since_last_duty"]
            base_map_df.at[idx, "selectable"] = bool(info["selectable"])

    for group_name, pid in st.session_state.selected_by_group.items():
        base_map_df.loc[base_map_df["pharmacy_id"] == pid, "status"] = "selected"
        base_map_df.loc[base_map_df["pharmacy_id"] == pid, "reason"] = f"{group_name} grubu için seçildi"

    palette = status_palette()
    base_map_df["color"] = base_map_df["status"].map(palette)
    base_map_df["radius"] = base_map_df["status"].map(
        {
            "selected": 180,
            "selectable": 120,
            "distance_blocked": 108,
            "gap_blocked": 108,
            "inactive": 72,
        }
    ).fillna(80)

    with left:
        st.markdown(
            '<div class="sticky-map-anchor"></div>',
            unsafe_allow_html=True,
        )
        st.subheader("Seçilen Gün İçin Eczane Haritası")
        st.caption("Harita dört ana bölge ve merkezden dışa doğru dört halka halinde düzenlenmiştir. Bir eczane işaretine tıklayarak seçim yapın.")

        selected_df = base_map_df[base_map_df["status"] == "selected"].copy()
        fmap = build_folium_map(
            map_df=base_map_df,
            selected_df=selected_df,
            min_distance_km=min_distance_km,
            active_groups=active_groups,
        )

        map_event = st_folium(
            fmap,
            height=610,
            use_container_width=True,
            returned_objects=["last_object_clicked_tooltip"],
            key=f"ayca_map_{day_no}_{len(selected_ids)}",
        )

        clicked_id = clicked_pharmacy_id(map_event)
        if planning_mode == "Otomatik Çok Günlük Plan" and clicked_id is not None:
            st.info(
                "Otomatik çok günlük planda harita inceleme modundadır. "
                "Manuel seçim için 'Tek Gün / Manuel Seçim' moduna geçin."
            )
        elif clicked_id is not None:
            clicked_row = base_map_df.loc[
                base_map_df["pharmacy_id"] == clicked_id
            ].iloc[0]
            clicked_group = str(clicked_row["group"])

            if clicked_group not in active_groups:
                st.warning(
                    f'{clicked_row["pharmacy_name"]}, bugünkü aktif kombinasyonda '
                    f"yer almayan {clicked_group} grubundadır."
                )
            elif clicked_row["status"] == "selected":
                st.info(f'{clicked_row["pharmacy_name"]} zaten seçili.')
            elif bool(clicked_row["selectable"]):
                actual_group = pharmacy_group_for_id(clicked_id)

                if actual_group != clicked_group:
                    st.error(
                        "Eczanenin kayıtlı grubu ile harita grubu uyuşmuyor. "
                        "Seçim yapılmadı."
                    )
                else:
                    previous = st.session_state.selected_by_group.get(clicked_group)
                    if previous != clicked_id:
                        st.session_state.selected_by_group[clicked_group] = int(clicked_id)
                        st.session_state.selection_source_by_group[clicked_group] = "Haritadan manuel seçim"
                        st.toast(
                            f'{clicked_row["pharmacy_name"]}, {clicked_group} grubu için seçildi.',
                            icon="✅",
                        )
                        st.rerun()
            else:
                st.error(
                    f'{clicked_row["pharmacy_name"]} seçilemez: {clicked_row["reason"]}'
                )

        with st.expander("Haritadaki adayları tablo olarak göster"):
            display_cols = [
                "pharmacy_name",
                "group",
                "status",
                "reason",
                "distance_to_nearest_selected_km",
                "days_since_last_duty",
                "historical_load",
                "decision_score",
            ]
            available_cols = [c for c in display_cols if c in base_map_df.columns]
            table_df = (
                base_map_df.loc[
                    base_map_df["group"].isin(active_groups),
                    available_cols,
                ]
                .sort_values(
                    [c for c in ["group", "status", "decision_score"] if c in available_cols],
                    na_position="last",
                )
            )
            st.dataframe(
                table_df,
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.subheader("Grup Bazında Eczane Seçimi")

        if planning_mode == "Otomatik Çok Günlük Plan":
            st.info(
                "Bu ekranda seçilen otomatik plan gününün eczaneleri gösteriliyor. "
                "Başka bir günü görmek için harita günü seçicisini değiştirin."
            )

        for group_name in active_groups:
            candidates = eligible_candidates(
                pharmacies=pharmacies,
                group_name=group_name,
                selected_ids=list(st.session_state.selected_by_group.values()),
                state=state,
                current_date=current_date,
                min_distance_km=min_distance_km,
                min_gap_days=min_gap_days,
            )

            candidates = group_locked_candidates(
                group_name=group_name,
                candidates=candidates,
            )

            selectable = candidates[
                candidates["selectable"]
            ].sort_values("decision_score", ascending=False)
            blocked = candidates[~candidates["selectable"]]

            st.markdown(f"#### {group_name} Grubu")
            c1, c2 = st.columns(2)
            c1.metric("Seçilebilir", len(selectable))
            c2.metric("Elenen", len(blocked))

            current_pid = st.session_state.selected_by_group.get(group_name)

            # Mevcut seçim bu gruba ait değilse kesin olarak temizle.
            if (
                current_pid is not None
                and pharmacy_group_for_id(current_pid)
                != str(group_name).strip().upper()
            ):
                st.session_state.selected_by_group.pop(group_name, None)
                st.session_state.selection_source_by_group.pop(group_name, None)
                current_pid = None

            option_ids = [None] + selectable["pharmacy_id"].astype(int).tolist()

            # Seçili eczane sadece gerçekten bu grubun üyesiyse listeye korunarak eklenir.
            if (
                current_pid is not None
                and pharmacy_group_for_id(current_pid)
                == str(group_name).strip().upper()
                and current_pid not in option_ids
            ):
                option_ids.insert(1, int(current_pid))

            labels = {None: "— Eczane seç —"}
            labels.update(
                {
                    int(r["pharmacy_id"]): (
                        f'{r["pharmacy_name"]} · {r["group"]} | '
                        f'uygunluk %{r["decision_score"]:.0f}'
                    )
                    for _, r in selectable.iterrows()
                }
            )

            if current_pid is not None and current_pid not in labels:
                current_match = pharmacies.loc[
                    pharmacies["pharmacy_id"] == int(current_pid)
                ]
                current_name = (
                    current_match.iloc[0]["pharmacy_name"]
                    if not current_match.empty
                    else f"Eczane {current_pid}"
                )
                labels[int(current_pid)] = f"{current_name} | seçilmiş"

            default_index = option_ids.index(current_pid) if current_pid in option_ids else 0

            chosen = st.selectbox(
                f"{group_name} için nöbetçi",
                options=option_ids,
                format_func=lambda x: labels[x],
                index=default_index,
                key=f"select_{group_name}_{day_no}",
                disabled=planning_mode == "Otomatik Çok Günlük Plan",
            )

            if planning_mode == "Tek Gün / Manuel Seçim":
                if chosen is not None and chosen != current_pid:
                    chosen_group = pharmacy_group_for_id(int(chosen))
                    expected_group = str(group_name).strip().upper()

                    if chosen_group != expected_group:
                        st.error(
                            f"{expected_group} için yalnızca "
                            f"{expected_group} grubundaki eczaneler seçilebilir."
                        )
                    else:
                        st.session_state.selected_by_group[group_name] = int(chosen)
                        st.session_state.selection_source_by_group[group_name] = "Listeden manuel seçim"
                        st.rerun()
                elif chosen is None and current_pid is not None:
                    st.session_state.selected_by_group.pop(group_name, None)
                    st.session_state.selection_source_by_group.pop(group_name, None)
                    st.rerun()

            if current_pid is not None:
                row = base_map_df.loc[
                    base_map_df["pharmacy_id"] == current_pid
                ].iloc[0]
                st.success(f'{row["pharmacy_name"]} seçildi.')
                components.html(
                    build_decision_engine_card(
                        row=row,
                        min_gap_days=min_gap_days,
                        min_distance_km=min_distance_km,
                    ),
                    height=520,
                    scrolling=False,
                )
            elif not selectable.empty:
                preview_row = selectable.iloc[0]
                components.html(
                    build_decision_engine_card(
                        row=preview_row,
                        min_gap_days=min_gap_days,
                        min_distance_km=min_distance_km,
                    ),
                    height=520,
                    scrolling=False,
                )

            with st.expander(f"{group_name} elenme gerekçeleri"):
                st.dataframe(
                    blocked[
                        [
                            "pharmacy_name",
                            "reason",
                            "distance_to_nearest_selected_km",
                            "days_since_last_duty",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

            st.divider()

with tab_groups:
    st.subheader("Nöbet Gruplarının Yapısı")

    selected_rotation = st.selectbox(
        "Eşlenik kombinasyonu",
        options=list(range(1, 9)),
        index=((day_no - 1) % len(KOMB_ABC)),
        format_func=lambda x: f"Gün {x}: {' • '.join(KOMB_ABC[x-1])}",
    )

    active_combo = KOMB_ABC[selected_rotation - 1]
    st.markdown(
        " ".join([f'<span class="group-pill">{g}</span>' for g in active_combo]),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="small-note">Gruplar iç içe halkalar halinde gösterilir. Her çeyrek A, B, C ve D bölgelerini; içten dışa halkalar ise 1, 2, 3 ve 4 alt gruplarını temsil eder. Haritadan eczane seçildikçe ilgili sektör yeşil çerçeveyle canlı güncellenir.</div>',
        unsafe_allow_html=True,
    )

    svg = build_group_svg(
        pharmacies=pharmacies,
        active_combo=active_combo,
        selected_by_group=st.session_state.selected_by_group,
    )
    components.html(svg, height=760, scrolling=False)

    st.subheader("Grup Detayları")
    group_counts = (
        pharmacies.groupby(["region", "group"], as_index=False)
        .agg(
            Eczane_Sayısı=("pharmacy_id", "count"),
            Ortalama_Yük=("historical_load", "mean"),
            Ortalama_Hafta_Sonu=("weekend_count", "mean"),
            Ortalama_Bayram=("holiday_count", "mean"),
        )
    )
    group_counts["Ortalama_Yük"] = group_counts["Ortalama_Yük"].round(2)
    group_counts["Ortalama_Hafta_Sonu"] = group_counts["Ortalama_Hafta_Sonu"].round(2)
    group_counts["Ortalama_Bayram"] = group_counts["Ortalama_Bayram"].round(2)

    st.dataframe(group_counts, use_container_width=True, hide_index=True)

with tab_plan:
    st.subheader("Oluşturulan Nöbet Planı")
    st.caption(
        "Takvimden tarih seçtikçe o güne ait aktif gruplar ve seçilmiş eczaneler gösterilir."
    )

    calendar_col, selected_date_col = st.columns([1, 2], gap="large")

    with calendar_col:
        st.date_input(
            "Tarih seçin",
            min_value=ROTATION_START_DATE,
            max_value=ROTATION_START_DATE + timedelta(days=365),
            format="DD.MM.YYYY",
            key="plan_calendar_picker",
            on_change=sync_plan_calendar_date,
        )

    with selected_date_col:
        st.markdown("#### Seçilen Tarih")
        st.markdown(
            f"### {st.session_state.canonical_current_date.day} "
            f"{month_names[st.session_state.canonical_current_date.month]} "
            f"{st.session_state.canonical_current_date.year}"
        )
        st.caption(
            "Bu tarih; üst özet, harita, grup yapısı ve aşağıdaki tablo için ortaktır."
        )

    # Bütün ekranlarda kullanılan tek tarih.
    plan_display_date = st.session_state.canonical_current_date
    st.session_state.plan_calendar_date = plan_display_date
    plan_day_no = (plan_display_date - ROTATION_START_DATE).days + 1
    plan_active_groups = group_for_day(
        (plan_day_no - 1) % len(KOMB_ABC)
    )

    if (
        planning_mode == "Otomatik Çok Günlük Plan"
        and st.session_state.auto_plan_ready
    ):
        plan_selected_by_group = (
            st.session_state.auto_assignments_by_date.get(
                plan_display_date.isoformat(),
                {},
            )
        )
    elif plan_display_date == st.session_state.canonical_current_date:
        plan_selected_by_group = dict(
            st.session_state.selected_by_group
        )
    else:
        plan_selected_by_group = {}

    # Grup kilidi: yalnızca o tarihin aktif gruplarındaki seçimler.
    plan_selected_by_group = sanitize_selected_by_group(
        plan_selected_by_group,
        allowed_groups=plan_active_groups,
    )

    plan_rows = []
    selected_weekday = weekday_names[plan_display_date.weekday()]

    for plan_group_name in plan_active_groups:
        pharmacy_id = plan_selected_by_group.get(plan_group_name)
        pharmacy_name = "Henüz seçilmedi"

        if pharmacy_id is not None:
            match = pharmacies.loc[
                pharmacies["pharmacy_id"].astype(int)
                == int(pharmacy_id)
            ]
            if not match.empty:
                pharmacy_name = str(match.iloc[0]["pharmacy_name"])

        plan_rows.append(
            {
                "Gün": selected_weekday,
                "Grup": plan_group_name,
                "Eczane": pharmacy_name,
            }
        )

    st.dataframe(
        pd.DataFrame(plan_rows),
        use_container_width=True,
        hide_index=True,
    )

    candidates_by_group = {}
    selected_ids_for_plan = list(plan_selected_by_group.values())

    for group_name in plan_active_groups:
        candidates_by_group[group_name] = eligible_candidates(
            pharmacies=pharmacies,
            group_name=group_name,
            selected_ids=selected_ids_for_plan,
            state=state,
            current_date=plan_display_date,
            min_distance_km=min_distance_km,
            min_gap_days=min_gap_days,
        )

    components.html(
        build_plan_cards(
            active_groups=plan_active_groups,
            selected_by_group=plan_selected_by_group,
            source_by_group={
                group_name: (
                    "AYÇA çok günlük otomatik plan"
                    if planning_mode == "Otomatik Çok Günlük Plan"
                    else st.session_state.selection_source_by_group.get(
                        group_name,
                        "Mevcut seçim",
                    )
                )
                for group_name in plan_selected_by_group
            },
            candidates_by_group=candidates_by_group,
        ),
        height=190,
        scrolling=False,
    )

    plan_left, plan_right = st.columns([1.45, 1], gap="large")

    with plan_left:
        st.markdown("### İleri Tarih Planı")

        if planning_mode == "Otomatik Çok Günlük Plan":
            if not st.session_state.auto_plan_ready:
                st.info(
                    "Sol menüden başlangıç tarihini ve gün sayısını seçip "
                    "'Çok Günlük Planı Oluştur' butonuna basın."
                )
            else:
                display_auto_df = st.session_state.auto_schedule_df.drop(
                    columns=["Eczane ID"],
                    errors="ignore",
                )
                st.dataframe(
                    display_auto_df,
                    use_container_width=True,
                    hide_index=True,
                    height=510,
                )
        else:
            st.info(
                "Manuel modda takvimden seçilen günün mevcut atamaları "
                "üstte gösterilir. Çok günlük otomatik plan için sol menüden "
                "Otomatik Çok Günlük Plan moduna geçin."
            )

    with plan_right:
        st.markdown("### Seçilen Günün Detayları")

        if not plan_selected_by_group:
            st.info(
                "Bu tarih için henüz eczane seçilmedi."
            )
        else:
            for group_name in plan_active_groups:
                pharmacy_id = plan_selected_by_group.get(group_name)
                if pharmacy_id is None:
                    continue

                group_df = candidates_by_group.get(
                    group_name,
                    pd.DataFrame(),
                )
                match = group_df.loc[
                    group_df["pharmacy_id"].astype(int)
                    == int(pharmacy_id)
                ]

                if match.empty:
                    pharmacy_match = pharmacies.loc[
                        pharmacies["pharmacy_id"].astype(int)
                        == int(pharmacy_id)
                    ]
                    if pharmacy_match.empty:
                        continue
                    selected_row = pharmacy_match.iloc[0].copy()
                    selected_row["decision_score"] = 0
                    selected_row["days_since_last_duty"] = None
                else:
                    selected_row = match.iloc[0]

                with st.container(border=True):
                    st.markdown(
                        f"#### {group_name} · "
                        f"{selected_row['pharmacy_name']}"
                    )
                    st.caption(
                        "AYÇA otomatik plan"
                        if planning_mode == "Otomatik Çok Günlük Plan"
                        else st.session_state.selection_source_by_group.get(
                            group_name,
                            "Mevcut seçim",
                        )
                    )

        st.markdown("### 8 Günlük Grup Rotasyonu")
        rotation_rows = []
        for idx, combo in enumerate(KOMB_ABC, start=1):
            rotation_rows.append(
                {
                    "Gün": idx,
                    "Grup Kombinasyonu": " • ".join(combo),
                    "Durum": (
                        "Aktif"
                        if idx
                        == ((plan_day_no - 1) % len(KOMB_ABC)) + 1
                        else ""
                    ),
                }
            )

        st.dataframe(
            pd.DataFrame(rotation_rows),
            use_container_width=True,
            hide_index=True,
            height=300,
        )

st.caption(
    "Not: Bu demo sentetik eczane ve koordinat verileri kullanır. Gerçek kurulumda oda tarafından sağlanan grup, koordinat ve geçmiş nöbet verileri sisteme aktarılır."
)
