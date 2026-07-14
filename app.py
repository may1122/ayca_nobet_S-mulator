from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import math

import pandas as pd
import pydeck as pdk
import streamlit as st
import streamlit.components.v1 as components

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
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="ayca-title">AYÇA Nöbet — Akıllı Grup Simülasyonu</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="ayca-subtitle">Grup kombinasyonu, eşlenik ilişkileri, yakınlık, nöbet aralığı ve geçmiş yük kurallarının canlı gösterimi</div>',
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
                ascending=[True, False],
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

m1, m2, m3, m4 = st.columns(4)
m1.metric("Tarih", current_date.strftime("%d.%m.%Y"))
m2.metric("Aktif kombinasyon", combination_text)
m3.metric("Toplam eczane", len(pharmacies))
m4.metric("Seçilen nöbetçi", len(selected_ids))

tab_map, tab_groups, tab_plan = st.tabs(
    ["🗺️ Harita ve Seçim", "⭕ Grup Yapısı ve Eşlenikler", "📅 Günlük Plan"]
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
        st.subheader("Şehir Haritası")

        layers = []

        selected_df = base_map_df[base_map_df["status"] == "selected"]
        if not selected_df.empty:
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=selected_df,
                    get_position="[lon, lat]",
                    get_fill_color=[29, 78, 216, 20],
                    get_line_color=[29, 78, 216, 110],
                    get_radius=min_distance_km * 1000,
                    stroked=True,
                    filled=True,
                    line_width_min_pixels=2,
                    pickable=False,
                )
            )

        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=base_map_df,
                get_position="[lon, lat]",
                get_fill_color="color",
                get_radius="radius",
                pickable=True,
                opacity=0.9,
                stroked=True,
                get_line_color=[255, 255, 255],
                line_width_min_pixels=1,
            )
        )

        label_df = base_map_df[base_map_df["status"].isin(["selected", "selectable"])].copy()
        layers.append(
            pdk.Layer(
                "TextLayer",
                data=label_df,
                get_position="[lon, lat]",
                get_text="pharmacy_name",
                get_size=12,
                get_color=[18, 59, 109],
                get_alignment_baseline="'bottom'",
                get_pixel_offset=[0, -10],
                pickable=False,
            )
        )

        view_state = pdk.ViewState(
            latitude=float(pharmacies["lat"].mean()),
            longitude=float(pharmacies["lon"].mean()),
            zoom=11.8,
            pitch=28,
        )

        tooltip = {
            "html": """
            <b>{pharmacy_name}</b><br/>
            Grup: {group}<br/>
            Durum: {status}<br/>
            Gerekçe: {reason}<br/>
            Skor: {decision_score}<br/>
            En yakın seçili eczane: {distance_to_nearest_selected_km} km
            """,
            "style": {"backgroundColor": "#123B6D", "color": "white"},
        }

        st.pydeck_chart(
            pdk.Deck(
                map_style="light",
                initial_view_state=view_state,
                layers=layers,
                tooltip=tooltip,
            ),
            use_container_width=True,
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
            st.dataframe(
                base_map_df[base_map_df["group"].isin(active_groups)][display_cols]
                .sort_values(["group", "status", "decision_score"]),
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.subheader("Adım Adım Seçim")

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

            selectable = candidates[candidates["selectable"]].sort_values("decision_score")
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
                        f'{r["pharmacy_name"]} | skor {r["decision_score"]:.2f}'
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
                row = pharmacies.loc[pharmacies["pharmacy_id"] == current_pid].iloc[0]
                st.success(f'{row["pharmacy_name"]} seçildi.')

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
    st.subheader("Çembersel Grup Yapısı")

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
        '<div class="small-note">Kalın mavi çizgiler seçilen günün aktif eşleniklerini, açık gri çizgiler diğer olası kombinasyonları gösterir.</div>',
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
    st.subheader("Gün Gün Nöbetçi Görünümü")

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
            valid = result[result["selectable"]].sort_values("decision_score")

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
                    "Karar Skoru": round(float(row["decision_score"]), 2),
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
