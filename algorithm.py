
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
