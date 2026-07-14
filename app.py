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
    SimulationState,
    eligible_candidates,
    generate_pharmacies,
    group_for_day,
    status_palette,
    build_group_svg,
)

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
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="ayca-title">AYÇA Nöbet — Akıllı Grup Simülasyonu</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="ayca-subtitle">Bugünün nöbet gruplarını, uygun eczaneleri ve oluşturulan planı canlı olarak inceleyin</div>',
    unsafe_allow_html=True,
)

DATA_PATH = Path(__file__).with_name("pharmacies.csv")

@st.cache_data
def load_pharmacies() -> pd.DataFrame:
    if DATA_PATH.exists():
        return pd.read_csv(DATA_PATH)
    df = generate_pharmacies(seed=42)
    df.to_csv(DATA_PATH, index=False)
    return df

pharmacies = load_pharmacies()

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
        """
    ).strip()


def build_folium_map(
    map_df: pd.DataFrame,
    selected_df: pd.DataFrame,
    min_distance_km: float,
) -> folium.Map:
    center = [float(map_df["lat"].mean()), float(map_df["lon"].mean())]
    fmap = folium.Map(
        location=center,
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=True,
    )

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


if "state" not in st.session_state:
    st.session_state.state = SimulationState.from_dataframe(pharmacies)

if "selected_by_group" not in st.session_state:
    st.session_state.selected_by_group = {}

state: SimulationState = st.session_state.state

with st.sidebar:
    st.header("Simülasyon Ayarları")
    start_date = st.date_input("Başlangıç tarihi", value=date(2026, 8, 1))
    day_no = st.slider("Gün", min_value=1, max_value=31, value=1)
    current_date = start_date + timedelta(days=day_no - 1)

    min_distance_km = st.slider(
        "Minimum eczaneler arası mesafe",
        min_value=0.2,
        max_value=3.0,
        value=1.0,
        step=0.1,
    )
    min_gap_days = st.slider(
        "Minimum nöbet aralığı",
        min_value=7,
        max_value=30,
        value=14,
        step=1,
    )

    st.divider()

    if st.button("Seçimleri Temizle", use_container_width=True):
        st.session_state.selected_by_group = {}
        st.rerun()

    if st.button("Günü Otomatik Tamamla", type="primary", use_container_width=True):
        active_groups = group_for_day(day_no - 1)
        chosen = {}
        temp_state = state.copy()

        for group_name in active_groups:
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
            )

            if not valid.empty:
                pharmacy_id = int(valid.iloc[0]["pharmacy_id"])
                chosen[group_name] = pharmacy_id
                temp_state.apply_assignment(pharmacy_id, current_date)

        st.session_state.selected_by_group = chosen
        st.rerun()

active_groups = group_for_day(day_no - 1)
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
      <div class="summary-title">Bugünün Nöbet Özeti</div>
      <div class="summary-grid">

        <div class="summary-item">
          <div class="summary-label">Nöbet Tarihi</div>
          <div class="summary-value">{date_text}</div>
          <div class="summary-sub">{weekday_text}</div>
        </div>

        <div class="summary-item">
          <div class="summary-label">Bugünkü Nöbet Grupları</div>
          <div class="group-row">{group_chips}</div>
          <div class="summary-sub">Her gruptan bir eczane seçilir</div>
        </div>

        <div class="summary-item">
          <div class="summary-label">Bugün Görev Alacak</div>
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
    base_map_df["reason"] = "Bugünkü aktif kombinasyonda değil"
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
        st.subheader("Bugün Seçilebilecek Eczaneler")
        st.caption("Bir eczane işaretine tıklayın. Sistem uygunluk puanını ve tüm karar kontrollerini canlı gösterir.")

        selected_df = base_map_df[base_map_df["status"] == "selected"].copy()
        fmap = build_folium_map(
            map_df=base_map_df,
            selected_df=selected_df,
            min_distance_km=min_distance_km,
        )

        map_event = st_folium(
            fmap,
            height=610,
            use_container_width=True,
            returned_objects=["last_object_clicked_tooltip"],
            key=f"ayca_map_{day_no}_{len(selected_ids)}",
        )

        clicked_id = clicked_pharmacy_id(map_event)
        if clicked_id is not None:
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
                previous = st.session_state.selected_by_group.get(clicked_group)
                if previous != clicked_id:
                    st.session_state.selected_by_group[clicked_group] = int(clicked_id)
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

            selectable = candidates[candidates["selectable"]].sort_values("decision_score", ascending=False)
            blocked = candidates[~candidates["selectable"]]

            st.markdown(f"#### {group_name} Grubu")
            c1, c2 = st.columns(2)
            c1.metric("Seçilebilir", len(selectable))
            c2.metric("Elenen", len(blocked))

            current_pid = st.session_state.selected_by_group.get(group_name)

            option_ids = [None] + selectable["pharmacy_id"].astype(int).tolist()
            labels = {None: "— Eczane seç —"}
            labels.update(
                {
                    int(r["pharmacy_id"]): (
                        f'{r["pharmacy_name"]} | uygunluk %{r["decision_score"]:.0f}'
                    )
                    for _, r in selectable.iterrows()
                }
            )

            default_index = option_ids.index(current_pid) if current_pid in option_ids else 0

            chosen = st.selectbox(
                f"{group_name} için nöbetçi",
                options=option_ids,
                format_func=lambda x: labels[x],
                index=default_index,
                key=f"select_{group_name}_{day_no}",
            )

            if chosen is not None and chosen != current_pid:
                st.session_state.selected_by_group[group_name] = int(chosen)
                st.rerun()
            elif chosen is None and current_pid is not None:
                st.session_state.selected_by_group.pop(group_name, None)
                st.rerun()

            if current_pid is not None:
                row = base_map_df.loc[
                    base_map_df["pharmacy_id"] == current_pid
                ].iloc[0]
                st.success(f'{row["pharmacy_name"]} seçildi.')
                st.markdown(
                    build_decision_engine_card(
                        row=row,
                        min_gap_days=min_gap_days,
                        min_distance_km=min_distance_km,
                    ),
                    unsafe_allow_html=True,
                )
            elif not selectable.empty:
                preview_row = selectable.iloc[0]
                st.markdown(
                    build_decision_engine_card(
                        row=preview_row,
                        min_gap_days=min_gap_days,
                        min_distance_km=min_distance_km,
                    ),
                    unsafe_allow_html=True,
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
        index=((day_no - 1) % 8),
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

    days_to_show = st.slider("Gösterilecek gün sayısı", min_value=3, max_value=31, value=8)

    schedule_rows = []
    temp_state = state.copy()

    for day_idx in range(days_to_show):
        sim_date = start_date + timedelta(days=day_idx)
        chosen = []

        for group_name in group_for_day(day_idx):
            result = eligible_candidates(
                pharmacies=pharmacies,
                group_name=group_name,
                selected_ids=chosen,
                state=temp_state,
                current_date=sim_date,
                min_distance_km=min_distance_km,
                min_gap_days=min_gap_days,
            )
            valid = result[result["selectable"]].sort_values("decision_score", ascending=False)

            if valid.empty:
                continue

            row = valid.iloc[0]
            pid = int(row["pharmacy_id"])
            chosen.append(pid)
            temp_state.apply_assignment(pid, sim_date)

            schedule_rows.append(
                {
                    "Tarih": sim_date.strftime("%d.%m.%Y"),
                    "Gün": day_idx + 1,
                    "Grup": group_name,
                    "Eczane": row["pharmacy_name"],
                    "Uygunluk Skoru": round(float(row["decision_score"]), 2),
                }
            )

    schedule_df = pd.DataFrame(schedule_rows)

    st.dataframe(
        schedule_df,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("8 Günlük Rotasyon")
    rotation_rows = []
    for idx, combo in enumerate(KOMB_ABC, start=1):
        rotation_rows.append(
            {
                "Gün": idx,
                "Grup Kombinasyonu": " • ".join(combo),
                "Durum": "Aktif" if idx == ((day_no - 1) % len(KOMB_ABC)) + 1 else "",
            }
        )
    st.dataframe(pd.DataFrame(rotation_rows), use_container_width=True, hide_index=True)

st.caption(
    "Not: Bu demo sentetik eczane ve koordinat verileri kullanır. Gerçek kurulumda oda tarafından sağlanan grup, koordinat ve geçmiş nöbet verileri sisteme aktarılır."
)
