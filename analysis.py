"""
Shared analysis module for Alaska hunt success rate data.

Handles data loading (both old and new CSV formats), success rate computation,
and renders the full Streamlit UI for any animal type.
"""

import streamlit as st
import pandas as pd
import numpy as np


@st.cache_data
def load_data(csv_path):
    """
    Load and normalize hunt data from CSV.

    Supports two formats:
      - New (scraper) format: hunt, year, gmu, permits, hunters, harvest, success_rate
      - Old format: hunt, year, hunted, killed (Y/N values)

    Returns a DataFrame with columns: hunt, year, total_hunters, kills, success_rate
    """
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Detect format and normalize
    if "success_rate" in df.columns and "hunters" in df.columns:
        # New scraper format
        result = pd.DataFrame({
            "hunt": df["hunt"],
            "year": pd.to_numeric(df["year"], errors="coerce"),
            "total_hunters": pd.to_numeric(df["hunters"], errors="coerce"),
            "kills": pd.to_numeric(df.get("harvest", 0), errors="coerce"),
            "success_rate": pd.to_numeric(df["success_rate"], errors="coerce"),
        })
    elif "hunted" in df.columns and "killed" in df.columns:
        # Old format — compute success rate from individual records
        hunters = df[df["hunted"] == "Y"]
        grouped = hunters.groupby(["hunt", "year"]).agg(
            total_hunters=("killed", "size"),
            kills=("killed", lambda x: (x == "Y").sum()),
        ).reset_index()
        grouped["success_rate"] = grouped["kills"] / grouped["total_hunters"]
        result = grouped
    else:
        st.error(
            f"Unrecognized CSV format. Expected columns:\n"
            f"  New format: hunt, year, hunters, harvest, success_rate\n"
            f"  Old format: hunt, year, hunted, killed\n\n"
            f"Found: {', '.join(df.columns)}"
        )
        st.stop()

    result = result.dropna(subset=["year"])
    result["year"] = result["year"].astype(int)
    return result


def compute_trend(years, rates):
    """Compute linear trend slope. Returns slope per year."""
    if len(years) < 2:
        return 0.0
    try:
        slope = np.polyfit(years, rates, 1)[0]
        return slope
    except (np.linalg.LinAlgError, ValueError):
        return 0.0


def trend_label(slope):
    """Convert a slope value to a human-readable trend label."""
    if slope > 0.005:
        return "Rising"
    elif slope < -0.005:
        return "Falling"
    return "Stable"


def render_animal_page(animal_name, csv_path):
    """Render the full analysis page for one animal type."""
    st.title(f"{animal_name} Success Rates by GMU")

    df = load_data(csv_path)

    if df.empty:
        st.warning("No data available.")
        return

    # ---- Sidebar controls ----
    all_hunts = sorted(df["hunt"].unique())
    year_min, year_max = int(df["year"].min()), int(df["year"].max())

    selected_hunts = st.sidebar.multiselect(
        "GMU / Hunt",
        options=all_hunts,
        default=[all_hunts[0]] if all_hunts else [],
    )

    year_range = st.sidebar.slider(
        "Year Range",
        min_value=year_min,
        max_value=year_max,
        value=(year_min, year_max),
    )

    compare_since = st.sidebar.number_input(
        "Compare GMUs since",
        min_value=year_min,
        max_value=year_max,
        value=max(year_min, year_max - 10),
    )

    # Filter data by year range
    df_filtered = df[(df["year"] >= year_range[0]) & (df["year"] <= year_range[1])]

    # ---- Tabs ----
    tab1, tab2, tab3 = st.tabs(["GMU Analysis", "Compare GMUs", "Best Bets"])

    # ========== Tab 1: GMU Analysis ==========
    with tab1:
        if not selected_hunts:
            st.info("Select one or more GMUs from the sidebar.")
            return

        df_selected = df_filtered[df_filtered["hunt"].isin(selected_hunts)]

        if df_selected.empty:
            st.warning("No data for the selected GMU(s) and year range.")
            return

        # Metric cards for each selected GMU (2 per row for mobile)
        for row_start in range(0, len(selected_hunts), 2):
            row_hunts = selected_hunts[row_start:row_start + 2]
            cols = st.columns(len(row_hunts))
            for i, hunt in enumerate(row_hunts):
                hunt_data = df_selected[df_selected["hunt"] == hunt].sort_values("year")
                if hunt_data.empty:
                    continue
                latest_rate = hunt_data.iloc[-1]["success_rate"]
                avg_rate = hunt_data["success_rate"].mean()
                slope = compute_trend(hunt_data["year"].values, hunt_data["success_rate"].values)
                delta = f"{slope * 100:+.1f}%/yr"
                cols[i].metric(
                    label=f"{hunt}",
                    value=f"{latest_rate:.0%}",
                    delta=delta,
                    help=f"Latest year: {latest_rate:.1%} | Avg: {avg_rate:.1%}",
                )

        # Line chart — pivot so each GMU is a column
        chart_data = df_selected.pivot_table(
            index="year", columns="hunt", values="success_rate"
        )
        st.line_chart(chart_data)

        # Data table
        display_df = df_selected[["hunt", "year", "total_hunters", "kills", "success_rate"]].copy()
        display_df["success_rate"] = display_df["success_rate"].apply(lambda x: f"{x:.1%}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ========== Tab 2: Compare GMUs ==========
    with tab2:
        df_compare = df_filtered[df_filtered["year"] >= compare_since]

        if df_compare.empty:
            st.warning(f"No data since {compare_since}.")
            return

        # Compute per-GMU stats
        gmu_stats = []
        for hunt, group in df_compare.groupby("hunt"):
            avg_rate = group["success_rate"].mean()
            total_hunters = group["total_hunters"].sum()
            years_data = group.sort_values("year")
            slope = compute_trend(years_data["year"].values, years_data["success_rate"].values)
            gmu_stats.append({
                "GMU": hunt,
                "Avg Success Rate": avg_rate,
                "Total Hunters": int(total_hunters),
                "Years of Data": len(group),
                "Trend": trend_label(slope),
            })

        stats_df = pd.DataFrame(gmu_stats).sort_values("Avg Success Rate", ascending=False)

        # Bar chart
        bar_data = stats_df.set_index("GMU")["Avg Success Rate"]
        st.bar_chart(bar_data)

        # Table
        display_stats = stats_df.copy()
        display_stats["Avg Success Rate"] = display_stats["Avg Success Rate"].apply(lambda x: f"{x:.1%}")
        st.dataframe(display_stats, use_container_width=True, hide_index=True)

    # ========== Tab 3: Best Bets ==========
    with tab3:
        st.subheader("Top GMU Recommendations")
        st.caption(
            "Ranked by a combination of historical success rate and recent trend. "
            "GMUs with too little data are filtered out."
        )

        col1, col2 = st.columns(2)
        min_years = col1.number_input("Min years of data", min_value=1, max_value=20, value=3)
        min_hunters = col2.number_input("Min total hunters", min_value=1, max_value=1000, value=10)

        df_recent = df_filtered[df_filtered["year"] >= compare_since]

        if df_recent.empty:
            st.warning(f"No data since {compare_since}.")
            return

        # Score each GMU
        scored = []
        for hunt, group in df_recent.groupby("hunt"):
            total_hunters = group["total_hunters"].sum()
            years_count = len(group)
            if years_count < min_years or total_hunters < min_hunters:
                continue
            avg_rate = group["success_rate"].mean()
            years_data = group.sort_values("year")
            slope = compute_trend(years_data["year"].values, years_data["success_rate"].values)
            scored.append({
                "hunt": hunt,
                "avg_rate": avg_rate,
                "total_hunters": int(total_hunters),
                "years": years_count,
                "slope": slope,
            })

        if not scored:
            st.warning("No GMUs meet the minimum data requirements. Try lowering the filters.")
            return

        scored_df = pd.DataFrame(scored)

        # Normalize slope to 0-1 range for scoring
        slope_min = scored_df["slope"].min()
        slope_max = scored_df["slope"].max()
        if slope_max > slope_min:
            scored_df["norm_slope"] = (scored_df["slope"] - slope_min) / (slope_max - slope_min)
        else:
            scored_df["norm_slope"] = 0.5

        scored_df["score"] = 0.6 * scored_df["avg_rate"] + 0.4 * scored_df["norm_slope"]
        scored_df = scored_df.sort_values("score", ascending=False)

        # Show top 5 as metric cards (2 per row for mobile)
        top_n = min(5, len(scored_df))
        top = scored_df.head(top_n)
        top_list = list(top.iterrows())

        for row_start in range(0, len(top_list), 2):
            row_items = top_list[row_start:row_start + 2]
            cols = st.columns(len(row_items))
            for i, (_, row) in enumerate(row_items):
                rank = row_start + i + 1
                delta = f"{row['slope'] * 100:+.1f}%/yr"
                cols[i].metric(
                    label=f"#{rank}: {row['hunt']}",
                    value=f"{row['avg_rate']:.0%}",
                    delta=delta,
                )
                cols[i].caption(f"{row['total_hunters']} hunters over {row['years']} years")

        # Combined line chart of top picks
        st.subheader("Trend Comparison")
        top_hunts = top["hunt"].tolist()
        chart_df = df_filtered[df_filtered["hunt"].isin(top_hunts)]
        if not chart_df.empty:
            chart_pivot = chart_df.pivot_table(
                index="year", columns="hunt", values="success_rate"
            )
            st.line_chart(chart_pivot)
