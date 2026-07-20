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
    CITY_CONFIG,
    REGION_ANGLES,
    region_angles_for_city,
    RING_LIMITS_KM,
    SimulationState,
    eligible_candidates,
    generate_pharmacies,
    pharmacy_layout_is_valid,
    group_for_day,
    status_palette,
    build_group_svg,
    build_simulation_summary,
    build_group_story,
)

st.set_page_config(
    page_title="AYÇA Nöbet | Karar Destek Platformu",
    page_icon="💊",
    layout="wide",
)

st.markdown(
    """
    <style>
        :root {
            --ayca-bg: #F6F8FC;
            --ayca-card: #FFFFFF;
            --ayca-border: #E8EDF5;
            --ayca-primary: #2F6BFF;
            --ayca-primary-dark: #1B4FD6;
            --ayca-title: #1B2B48;
            --ayca-secondary: #6B7280;
            --ayca-success: #16A34A;
            --ayca-warning: #F59E0B;
            --ayca-danger: #DC2626;
            --ayca-radius: 20px;
            --ayca-shadow: 0 6px 18px rgba(16,24,40,.05);
        }

        .stApp {
            background: var(--ayca-bg);
        }

        .block-container {padding-top: 1.4rem; padding-bottom: 2.5rem;}

        h1, h2, h3, h4, h5 {
            color: var(--ayca-title);
        }

        div[data-testid="stMetric"] {
            border: 1px solid var(--ayca-border);
            padding: 14px 16px;
            border-radius: var(--ayca-radius);
            background: var(--ayca-card);
            box-shadow: var(--ayca-shadow);
        }

        .legend {
            display:flex; gap:16px; flex-wrap:wrap; font-size:.86rem; color:var(--ayca-secondary);
            margin:.4rem 0 1.1rem 0;
        }
        .legend span {display:flex; align-items:center; gap:6px;}
        .dot {width:9px; height:9px; border-radius:50%; display:inline-block;}
        .small-note {font-size:.86rem; color:var(--ayca-secondary);}

        .group-pill {
            display:inline-block; padding:6px 12px; border-radius:999px;
            background:#EEF3FF; color:var(--ayca-primary-dark); font-weight:700; margin-right:6px;
            border: 1px solid #DCE6FF;
        }

        /* ---------- Genel kart yüzeyi ---------- */
        .ayca-card {
            border: 1px solid var(--ayca-border);
            border-radius: var(--ayca-radius);
            background: var(--ayca-card);
            box-shadow: var(--ayca-shadow);
            padding: 22px 24px;
        }

        /* ---------- Özet kartları ---------- */
        .summary-wrap {
            border: 1px solid var(--ayca-border);
            border-radius: var(--ayca-radius);
            background: var(--ayca-card);
            padding: 22px 24px;
            margin: 8px 0 20px 0;
            box-shadow: var(--ayca-shadow);
        }
        .summary-title {
            font-size: 13px;
            font-weight: 800;
            letter-spacing: .04em;
            text-transform: uppercase;
            color: var(--ayca-secondary);
            margin-bottom: 16px;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: 1.1fr 1.5fr 1fr 1fr;
            gap: 14px;
        }
        .summary-item {
            border: 1px solid var(--ayca-border);
            border-radius: 16px;
            padding: 18px 18px;
            background: #FBFCFE;
            min-height: 96px;
        }
        .summary-label {
            color: var(--ayca-secondary);
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 10px;
        }
        .summary-value {
            color: var(--ayca-title);
            font-size: 26px;
            font-weight: 800;
            line-height: 1.15;
            letter-spacing: -.01em;
        }
        .summary-sub {
            color: var(--ayca-secondary);
            font-size: 12px;
            margin-top: 8px;
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
            font-weight: 800;
            font-size: 14px;
            padding: 0 10px;
        }
        .status-ready {
            color: var(--ayca-success);
            background: #ECFDF3;
            border: 1px solid #BBF7D0;
            border-radius: 999px;
            display: inline-block;
            padding: 6px 12px;
            font-size: 13px;
            font-weight: 800;
            margin-top: 2px;
        }
        @media (max-width: 900px) {
            .summary-grid {grid-template-columns: 1fr 1fr;}
        }

        /* ---------- Plan kartları ---------- */
        .plan-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin: 10px 0 18px 0;
        }

        .plan-card {
            border: 1px solid var(--ayca-border);
            border-radius: var(--ayca-radius);
            background: var(--ayca-card);
            padding: 18px;
            min-height: 148px;
            box-shadow: var(--ayca-shadow);
        }

        .plan-card.empty {
            background: #FBFCFE;
            border-style: dashed;
        }

        .plan-group {
            font-size: 11px;
            font-weight: 800;
            letter-spacing: .04em;
            text-transform: uppercase;
            color: var(--ayca-secondary);
            margin-bottom: 10px;
        }

        .plan-name {
            color: var(--ayca-title);
            font-size: 18px;
            font-weight: 800;
            line-height: 1.25;
            margin-bottom: 8px;
        }

        .plan-detail {
            color: var(--ayca-secondary);
            font-size: 12px;
            line-height: 1.55;
        }

        .plan-source {
            display: inline-block;
            margin-top: 12px;
            padding: 5px 10px;
            border-radius: 999px;
            background: #EEF3FF;
            color: var(--ayca-primary-dark);
            font-size: 11px;
            font-weight: 700;
        }

        .plan-section {
            border: 1px solid var(--ayca-border);
            border-radius: var(--ayca-radius);
            background: var(--ayca-card);
            padding: 18px;
            box-shadow: var(--ayca-shadow);
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

        /* ---------- Üst kurumsal header ---------- */
        .product-header {
            border: 1px solid var(--ayca-border);
            border-radius: var(--ayca-radius);
            padding: 22px 26px;
            margin: 4px 0 20px 0;
            background: var(--ayca-card);
            box-shadow: var(--ayca-shadow);
        }

        .product-kicker {
            color: var(--ayca-primary);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .product-title {
            color: var(--ayca-title);
            font-size: 30px;
            line-height: 1.15;
            font-weight: 800;
            margin: 0;
            letter-spacing: -.01em;
        }

        .product-subtitle {
            color: var(--ayca-secondary);
            font-size: 14px;
            margin-top: 8px;
        }

        .product-date {
            display: inline-block;
            margin-top: 14px;
            padding: 7px 12px;
            border-radius: 999px;
            background: #F6F8FC;
            color: var(--ayca-title);
            border: 1px solid var(--ayca-border);
            font-size: 13px;
            font-weight: 700;
        }

        /* ---------- Karar Motoru sekmesi ---------- */
        .demo-stage {
            border: 1px solid var(--ayca-border);
            border-radius: var(--ayca-radius);
            padding: 20px;
            background: var(--ayca-card);
            box-shadow: var(--ayca-shadow);
            margin-bottom: 16px;
        }
        .demo-stage-title {
            font-size: 15px;
            color: var(--ayca-title);
            font-weight: 800;
            margin-bottom: 12px;
        }
        .demo-check {
            display:flex;
            align-items:center;
            gap:8px;
            padding:6px 0;
            color:#344054;
            font-size:13px;
        }
        .demo-check-icon {
            width:20px;
            height:20px;
            border-radius:50%;
            background:#DCFCE7;
            color:var(--ayca-success);
            display:inline-flex;
            align-items:center;
            justify-content:center;
            font-weight:800;
        }
        .demo-rule {
            display:flex;
            align-items:center;
            justify-content:space-between;
            padding:8px 0;
            border-bottom:1px solid var(--ayca-border);
            font-size:13px;
        }
        .demo-score {
            font-size:44px;
            font-weight:800;
            color:var(--ayca-success);
            line-height:1;
        }
        .performance-grid {
            display:grid;
            grid-template-columns:repeat(5,minmax(0,1fr));
            gap:12px;
        }
        .performance-card {
            border:1px solid var(--ayca-border);
            border-radius:16px;
            padding:16px 10px;
            text-align:center;
            background:var(--ayca-card);
            box-shadow: var(--ayca-shadow);
        }
        .performance-value {
            font-size:23px;
            color:var(--ayca-title);
            font-weight:800;
        }
        .performance-label {
            color:var(--ayca-secondary);
            font-size:11px;
            margin-top:6px;
        }
        @media(max-width:900px){
            .performance-grid{grid-template-columns:1fr 1fr;}
        }

        /* ---------- Karar motoru (engine) paneli — açık tema ---------- */
        .engine-panel {
            position: relative;
            overflow: hidden;
            border-radius: var(--ayca-radius);
            padding: 26px;
            min-height: 200px;
            background: var(--ayca-card);
            border: 1px solid var(--ayca-border);
            box-shadow: var(--ayca-shadow);
        }
        .engine-content { position:relative; z-index:2; }
        .engine-eyebrow {
            color:var(--ayca-primary); font-size:12px; font-weight:800;
            letter-spacing:.1em; text-transform:uppercase;
        }
        .engine-title {
            color: var(--ayca-title);
            font-size:26px; font-weight:800; line-height:1.15;
            margin:8px 0 8px 0;
        }
        .engine-subtitle {
            color:var(--ayca-secondary); font-size:14px; line-height:1.6; max-width:760px;
        }
        .engine-flow {
            display:flex; gap:8px; flex-wrap:wrap; margin-top:18px;
        }
        .engine-node {
            padding:8px 12px; border-radius:12px;
            background:#F6F8FC;
            border:1px solid var(--ayca-border);
            color: var(--ayca-title);
            font-weight:800;
        }
        .engine-stat-row {
            display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
            gap:12px; margin-top:18px;
        }
        .engine-stat {
            background:#FBFCFE;
            border:1px solid var(--ayca-border);
            border-radius:14px; padding:14px;
        }
        .engine-stat-value {font-size:22px;font-weight:800;color:var(--ayca-title);}
        .engine-stat-label {font-size:11px;color:var(--ayca-secondary);margin-top:4px;}

        .showcase-section-title {
            font-size:20px; font-weight:800; color:var(--ayca-title);
            margin:4px 0 12px 0;
        }
        .showcase-section-sub {
            color:var(--ayca-secondary); font-size:13px; margin:-6px 0 15px 0;
        }

        /* ---------- Nöbetçi kartları — düz beyaz, renk vurgusu ince şerit ---------- */
        .duty-grid {
            display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
            gap:14px;
        }
        .duty-card {
            position:relative;
            border-radius:18px; padding:18px;
            min-height:150px;
            background: var(--ayca-card);
            border: 1px solid var(--ayca-border);
            border-top: 3px solid var(--duty-accent, var(--ayca-primary));
            box-shadow: var(--ayca-shadow);
        }
        .duty-group {font-size:12px;font-weight:800;letter-spacing:.05em;color:var(--ayca-secondary);}
        .duty-name {font-size:19px;font-weight:800;margin-top:20px;line-height:1.2;color:var(--ayca-title);}
        .duty-score {font-size:12px;margin-top:10px;color:var(--ayca-secondary);}
        .duty-status {
            display:inline-flex;margin-top:10px;padding:5px 10px;border-radius:999px;
            background:#EEF3FF;color:var(--ayca-primary-dark);
            font-size:11px;font-weight:800;
        }

        .process-line {
            display:grid;grid-template-columns:repeat(6,minmax(0,1fr));
            gap:12px;position:relative;margin-top:12px;
        }
        .process-step {
            text-align:center;padding:18px 10px;border-radius:16px;
            background:var(--ayca-card);border:1px solid var(--ayca-border);
            box-shadow: var(--ayca-shadow);
        }
        .process-no {
            width:28px;height:28px;border-radius:50%;margin:0 auto 8px auto;
            display:flex;align-items:center;justify-content:center;
            background:var(--ayca-primary);
            color:white;font-weight:800;font-size:13px;
        }
        .process-icon {font-size:22px;margin-bottom:6px;}
        .process-title {font-size:12px;font-weight:800;color:var(--ayca-title);}
        .process-text {font-size:10px;color:var(--ayca-secondary);margin-top:5px;line-height:1.4;}

        /* ---------- Yetkinlik kartları — açık zemin ---------- */
        .capability-grid {
            display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;
        }
        .capability-card {
            position:relative;overflow:hidden;min-height:170px;
            border-radius:18px;padding:20px;
            background: var(--ayca-card);
            border: 1px solid var(--ayca-border);
            box-shadow: var(--ayca-shadow);
        }
        .capability-inner {position:relative;z-index:2;}
        .capability-icon {
            width:44px;height:44px;border-radius:13px;
            display:flex;align-items:center;justify-content:center;
            background:#F6F8FC;font-size:22px;
            border:1px solid var(--ayca-border);
        }
        .capability-title {font-size:16px;font-weight:800;margin-top:16px;color:var(--ayca-title);}
        .capability-text {font-size:12px;line-height:1.5;margin-top:8px;color:var(--ayca-secondary);}

        .advantage-strip {
            display:grid;grid-template-columns:repeat(5,minmax(0,1fr));
            gap:10px;margin-top:12px;
        }
        .advantage-item {
            border-radius:14px;padding:14px;background:var(--ayca-card);
            border:1px solid var(--ayca-border);color:va
