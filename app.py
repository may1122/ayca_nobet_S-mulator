
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from algorithm import (
    KOMB_ABC,
    SimulationState,
    build_demo_schedule,
    eligible_candidates,
    generate_pharmacies,
    group_for_day,
    status_palette,
)

st.set_page_config(
    page_title="AYÇA Nöbet | Grup Simülasyonu",
    page_icon="💊",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
        .ayca-title {font-size: 2rem; font-weight: 800; color: #123B6D; margin-bottom: .1rem;}
        .ayca-subtitle {color: #667085; margin-bottom: 1rem;}
        .metric-card {
            border: 1px solid #E4E7EC; border-radius: 14px; padding: 14px 16px;
            background: white; box-shadow: 0 4px 14px rgba(16,24,40,.05);
        }
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
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="ayca-title">AYÇA Nöbet — Akıllı Grup Simülasyonu</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="ayca-subtitle">Grup kombinasyonu, yakınlık, nöbet aralığı ve geçmiş yük kurallarının canlı gösterimi</div>',
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

m1, m2, m3, m4 = st.columns(4)
m1.metric("Tarih", current_date.strftime("%d.%m.%Y"))
m2.metric("Aktif kombinasyon", combination_text)
m3.metric("Toplam eczane", len(pharmacies))
m4.metric("Seçilen nöbetçi", len(st.session_state.selected_by_group))

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

selected_ids = list(st.session_state.selected_by_group.values())

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
    {"selected": 170, "selectable": 115, "distance_blocked": 105, "gap_blocked": 105, "inactive": 70}
).fillna(80)

with left:
    st.subheader("Şehir Haritası")
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=base_map_df,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.88,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
    )

    selected_df = base_map_df[base_map_df["status"] == "selected"]
    layers = [layer]

    if not selected_df.empty:
        radius_layer = pdk.Layer(
            "ScatterplotLayer",
            data=selected_df,
            get_position="[lon, lat]",
            get_fill_color=[29, 78, 216, 22],
            get_line_color=[29, 78, 216, 110],
            get_radius=min_distance_km * 1000,
            stroked=True,
            filled=True,
            line_width_min_pixels=2,
            pickable=False,
        )
        layers.insert(0, radius_layer)

    view_state = pdk.ViewState(
        latitude=float(pharmacies["lat"].mean()),
        longitude=float(pharmacies["lon"].mean()),
        zoom=11.8,
        pitch=30,
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
            "pharmacy_name", "group", "status", "reason",
            "distance_to_nearest_selected_km", "days_since_last_duty",
            "historical_load", "decision_score",
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
                    ["pharmacy_name", "reason", "distance_to_nearest_selected_km", "days_since_last_duty"]
                ],
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

st.subheader("Günlük Rotasyon")
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
