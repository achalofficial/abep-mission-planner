"""
report.py — Report and visualization generation for ABEP mission analysis.

Outputs:
  1. mission_report.md    — Full feasibility report in Markdown
  2. survival_heatmap.png — Altitude × F10.7 colored by thrust/drag ratio
  3. boundary_map.png     — Failure boundary across altitude × solar flux
  4. storm_recovery.png   — Altitude loss and recovery timelines
  5. sweep_results.csv    — Raw sweep data
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")   # non-interactive backend for headless use
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns


# ---------------------------------------------------------------------------
# Color / status palette
# ---------------------------------------------------------------------------

STATUS_PALETTE = {
    "SAFE":     "#2ecc71",
    "ADEQUATE": "#a8e063",
    "MARGINAL": "#f1c40f",
    "FAILURE":  "#e74c3c",
}

RATIO_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "abep_ratio",
    [
        (0.0,  "#e74c3c"),   # deep red  — ratio 0
        (0.45, "#e74c3c"),   # red  — ratio 0.9 (edge of failure)
        (0.50, "#f1c40f"),   # yellow  — ratio 1.0
        (0.60, "#a8e063"),   # light green  — ratio 1.2
        (1.0,  "#2ecc71"),   # green — ratio 2.0
    ],
)


# ---------------------------------------------------------------------------
# 1. Survival heatmap (altitude × F10.7, mean ratio, quiet conditions)
# ---------------------------------------------------------------------------

def plot_survival_heatmap(df: pd.DataFrame, output_path: str) -> None:
    """
    Heatmap: altitude (y) × F10.7 (x), colored by mean thrust/drag ratio.
    Aggregated over quiet conditions (Ap <= 15) and all months/latitudes.
    Uses 10-km altitude steps and the 6 canonical F10.7 levels to keep the
    heatmap readable even when the combined DataFrame includes refined grid points.
    """
    # Snap to coarse grid: alt multiples of 10 km and F10.7 in the canonical set
    canonical_f107 = [70, 100, 140, 180, 220, 250]
    df_coarse = df[
        (df["altitude_km"] % 10 == 0) &
        (df["f107"].isin(canonical_f107))
    ].copy()
    if len(df_coarse) == 0:
        df_coarse = df.copy()

    quiet = df_coarse[df_coarse["ap"] <= 15].copy()
    if len(quiet) == 0:
        quiet = df_coarse.copy()

    pivot = (
        quiet.groupby(["altitude_km", "f107"])["thrust_drag_ratio"]
        .mean()
        .unstack("f107")
    )
    pivot = pivot.sort_index(ascending=False)   # highest altitude at top

    fig, ax = plt.subplots(figsize=(10, 7))
    sns.heatmap(
        pivot,
        ax=ax,
        cmap=RATIO_CMAP,
        vmin=0.0,
        vmax=2.0,
        annot=True,
        fmt=".2f",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Mean Thrust/Drag Ratio"},
    )

    # Draw failure boundary (ratio = 1.0 contour)
    # We overlay a contour on the heatmap by re-plotting data as contourf
    alt_vals = sorted(quiet["altitude_km"].unique())
    f107_vals = sorted(quiet["f107"].unique())
    Z = pivot.reindex(index=sorted(pivot.index, reverse=False)).values
    X, Y = np.meshgrid(range(len(f107_vals)), range(len(alt_vals)))
    ax.contour(X + 0.5, Y + 0.5, Z[::-1], levels=[1.0],
               colors="black", linewidths=2.0, linestyles="--")

    ax.set_title("ABEP Survival Map — Mean Thrust/Drag Ratio (Quiet, Ap≤15)\n"
                 "Dashed line = failure boundary (ratio = 1.0)", fontsize=12)
    ax.set_xlabel("Daily Solar Flux F10.7 (SFU)")
    ax.set_ylabel("Altitude (km)")
    ax.set_xticklabels([str(int(f)) for f in f107_vals], rotation=45)
    ax.set_yticklabels([str(int(a)) for a in sorted(alt_vals, reverse=True)], rotation=0)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# 2. Boundary map (failure boundary line, seasonal bands)
# ---------------------------------------------------------------------------

def plot_boundary_map(df: pd.DataFrame, output_path: str) -> None:
    """
    For each F10.7 level, find the lowest altitude with <50% failure rate
    (quiet, moderate, storm conditions separately), showing the boundary band.
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    f107_vals = sorted(df["f107"].unique())
    ap_groups = [
        ("Quiet  (Ap ≤ 15)",    df["ap"] <= 15,     "#2ecc71", "o-"),
        ("Minor storm (Ap≤80)", (df["ap"] > 15) & (df["ap"] <= 80),  "#f1c40f", "s--"),
        ("Storm (Ap > 80)",     df["ap"] > 80,      "#e74c3c", "^:"),
    ]

    for label, mask, color, style in ap_groups:
        sub = df[mask]
        if len(sub) == 0:
            continue
        boundary_alts = []
        for f in f107_vals:
            fsub = sub[sub["f107"] == f]
            if len(fsub) == 0:
                boundary_alts.append(float("nan"))
                continue
            alt_grp = fsub.groupby("altitude_km")["status"].apply(
                lambda s: (s == "FAILURE").sum() / len(s)
            )
            safe_alts = alt_grp[alt_grp < 0.5].index
            boundary_alts.append(float(safe_alts.min()) if len(safe_alts) > 0 else float("nan"))

        ax.plot(f107_vals, boundary_alts, style, color=color, label=label,
                linewidth=2, markersize=7)

    ax.set_xlabel("Daily Solar Flux F10.7 (SFU)", fontsize=12)
    ax.set_ylabel("Minimum Safe Altitude (km)", fontsize=12)
    ax.set_title("ABEP Failure Boundary — Minimum Safe Altitude vs Solar Activity\n"
                 "(altitude below which >50% of conditions lead to orbit decay)", fontsize=11)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=df["altitude_km"].min() - 5, top=df["altitude_km"].max() + 5)

    # Shade the region below the worst-case boundary as unsafe
    worst_boundary = []
    for f in f107_vals:
        fsub = df[df["f107"] == f]
        alt_grp = fsub.groupby("altitude_km")["status"].apply(
            lambda s: (s == "FAILURE").sum() / len(s)
        )
        safe_alts = alt_grp[alt_grp < 0.5].index
        worst_boundary.append(float(safe_alts.min()) if len(safe_alts) > 0 else float("nan"))

    ax.fill_between(f107_vals, df["altitude_km"].min() - 5,
                    [b if not math.isnan(b) else df["altitude_km"].min() for b in worst_boundary],
                    alpha=0.08, color="#e74c3c", label="_nolegend_")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# 3. Storm recovery chart
# ---------------------------------------------------------------------------

def plot_storm_recovery(storm_data: dict, output_path: str) -> None:
    """
    Multi-panel chart showing altitude trajectory for each storm scenario.
    """
    results = storm_data.get("results", [])
    if not results:
        print(f"  [SKIP] No storm results to plot.")
        return

    n = len(results)
    cols = min(3, n)
    rows = math.ceil(n / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(6 * cols, 4 * rows),
                             squeeze=False)
    fig.suptitle(
        f"Storm Recovery Analysis — Starting from {storm_data['target_altitude_km']:.0f} km",
        fontsize=13, fontweight="bold"
    )

    for idx, r in enumerate(results):
        ax = axes[idx // cols][idx % cols]

        if not r.time_h:
            ax.set_visible(False)
            continue

        t = r.time_h
        alt = r.altitude_km_series
        phase = r.phase_series

        # Color segments by phase
        storm_mask = [p == "storm" for p in phase]
        recov_mask = [p == "recovery" for p in phase]

        ax.plot([t[i] for i in range(len(t)) if storm_mask[i]],
                [alt[i] for i in range(len(t)) if storm_mask[i]],
                color="#e74c3c", linewidth=2.0, label="Storm")
        ax.plot([t[i] for i in range(len(t)) if recov_mask[i]],
                [alt[i] for i in range(len(t)) if recov_mask[i]],
                color="#2ecc71", linewidth=2.0, label="Recovery")

        ax.axhline(storm_data["target_altitude_km"], color="gray",
                   linestyle="--", linewidth=1, alpha=0.6, label="Initial alt")
        ax.axhline(150, color="black", linestyle=":", linewidth=1.2,
                   alpha=0.5, label="Deorbit threshold")

        # Annotate loss
        loss_str = f"Loss: {r.altitude_loss_km:.1f} km"
        rec_str  = (f"Recovery: {r.recovery_time_h:.0f}h"
                    if r.recovery_time_h != float("inf") else "No recovery")
        ax.set_title(f"{r.scenario.name}\n{loss_str} | {rec_str}", fontsize=9)
        ax.set_xlabel("Time (h)", fontsize=8)
        ax.set_ylabel("Altitude (km)", fontsize=8)
        ax.legend(fontsize=7, loc="best")
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    # Hide unused axes
    for idx in range(n, rows * cols):
        axes[idx // cols][idx % cols].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# 4. CSV export
# ---------------------------------------------------------------------------

def export_csv(df: pd.DataFrame, output_path: str) -> None:
    df.to_csv(output_path, index=False)
    print(f"  Saved: {output_path}  ({len(df):,} rows)")


# ---------------------------------------------------------------------------
# 5. Markdown report
# ---------------------------------------------------------------------------

MONTH_NAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
               7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}


def _viability_verdict(failure_rate: float) -> str:
    if failure_rate < 0.20:
        return "FEASIBLE"
    elif failure_rate < 0.50:
        return "FEASIBLE WITH CAVEATS"
    else:
        return "NOT FEASIBLE"


def generate_report(
    mission,            # MissionParams
    sc,                 # SpacecraftParams
    agent_state: dict,
    output_dir: str,
) -> str:
    """
    Generate all outputs (report, heatmaps, CSV) from agent state.
    Returns the path to the mission_report.md file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    df: pd.DataFrame = agent_state.get("combined_results", pd.DataFrame())
    analysis: dict    = agent_state.get("analysis", {})
    storm_data: dict  = agent_state.get("storm_recovery") or {}
    historical: dict  = agent_state.get("historical_context") or {}
    findings: list    = agent_state.get("findings", [])
    claude_insights   = agent_state.get("claude_insights", [])

    s = analysis.get("summary", {})
    bz = analysis.get("boundary_zone", {})
    dd = analysis.get("dominant_drivers", {})

    failure_rate = s.get("failure_rate", 0.0)
    verdict = _viability_verdict(failure_rate)

    print(f"\n  Generating outputs to: {out.resolve()}")

    # --- Plots ---
    heatmap_path  = str(out / "survival_heatmap.png")
    boundary_path = str(out / "boundary_map.png")
    storm_path    = str(out / "storm_recovery.png")
    csv_path      = str(out / "sweep_results.csv")
    report_path   = str(out / "mission_report.md")

    if not df.empty:
        print("  Plotting survival heatmap...")
        plot_survival_heatmap(df, heatmap_path)
        print("  Plotting boundary map...")
        plot_boundary_map(df, boundary_path)
        print("  Exporting CSV...")
        export_csv(df, csv_path)

    if storm_data.get("results"):
        print("  Plotting storm recovery...")
        plot_storm_recovery(storm_data, storm_path)

    # --- Markdown ---
    lines = []
    lines += [
        "# ABEP Mission Feasibility Report",
        f"## Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Mission Parameters",
        "",
        f"| Parameter | Value |",
        f"|---|---|",
        f"| Target altitude | {mission.target_altitude_km:.0f} km |",
        f"| Mission duration | {mission.mission_duration_days:.0f} days "
        f"({mission.mission_duration_days/365.25:.2f} years) |",
        f"| Orbit inclination | {mission.orbit_inclination_deg:.0f}° |",
        "",
        "**Spacecraft configuration:**",
        "",
        f"| Parameter | Value |",
        f"|---|---|",
        f"| Mass | {sc.mass_kg:.0f} kg |",
        f"| Frontal area | {sc.frontal_area_m2:.2f} m² |",
        f"| Drag coefficient | {sc.drag_coefficient:.1f} |",
        f"| Intake area | {sc.intake_area_m2:.2f} m² |",
        f"| Intake efficiency | {sc.intake_efficiency:.0%} |",
        f"| Isp | {sc.specific_impulse_s:.0f} s |",
        f"| Thrust-to-power | {sc.thrust_to_power_mN_per_kW:.0f} mN/kW |",
        f"| Solar panel area | {sc.solar_panel_area_m2:.1f} m² @ {sc.solar_panel_efficiency:.0%} eff. |",
        f"| Available power | ~{sc.solar_panel_area_m2*1361*sc.solar_panel_efficiency*(1-sc.eclipse_fraction)-sc.housekeeping_power_W:.0f} W |",
        "",
        "---",
        "",
        "## Key Findings",
        "",
        f"### Overall Viability: **{verdict}**",
        "",
        f"- Total conditions modeled: {s.get('total_runs', 0):,}",
        f"- Overall failure rate: {failure_rate:.1%}",
        f"- SAFE: {s.get('safe_count',0)} | ADEQUATE: {s.get('adequate_count',0)} "
        f"| MARGINAL: {s.get('marginal_count',0)} | FAILURE: {s.get('failure_count',0)}",
        "",
    ]

    # Boundary zone
    if bz.get("alt_min") and bz.get("alt_max"):
        lines += [
            f"### Failure Boundary",
            "",
            f"The system transitions from reliable operation to orbit decay "
            f"between **{bz['alt_min']:.0f}–{bz['alt_max']:.0f} km**.",
            f"The critical altitude (50% failure rate) is "
            f"**{bz.get('alt_critical', '?'):.0f} km**.",
            "",
        ]

    # Dominant drivers
    if dd:
        lines += ["### Dominant Risk Drivers", ""]
        if "f107_failure_threshold" in dd:
            lines.append(f"- **Solar flux:** Failures begin at F10.7 = "
                         f"{dd['f107_failure_threshold']:.0f} SFU. "
                         f"Solar maximum (F10.7 > 200) dramatically increases failure probability.")
        if "ap_failure_threshold" in dd:
            lines.append(f"- **Geomagnetic activity:** Failures appear even at Ap = "
                         f"{dd['ap_failure_threshold']:.0f}, "
                         f"meaning the system operates near its limit even in quiet conditions.")
        if dd.get("most_influential_variable"):
            lines.append(f"- **Most influential variable:** {dd['most_influential_variable']}")
        lines.append("")

    # Detailed findings
    if findings:
        lines += ["### Detailed Findings", ""]
        for i, f in enumerate(findings, 1):
            lines.append(f"{i}. {f}")
        lines.append("")

    # Storm impact
    if storm_data.get("results"):
        lines += ["### Storm Impact Analysis", ""]
        lines += [
            f"| Scenario | Ap | Duration | Alt Loss | Final Alt | Recovery | Survived |",
            f"|---|---|---|---|---|---|---|",
        ]
        for r in storm_data["results"]:
            rec = f"{r.recovery_time_h:.0f}h" if r.recovery_time_h != float("inf") else "never"
            surv = "Yes" if r.survived else "**No (deorbit risk)**"
            lines.append(
                f"| {r.scenario.name} | {r.scenario.ap_storm:.0f} | "
                f"{r.scenario.duration_h:.0f}h | {r.altitude_loss_km:.1f} km | "
                f"{r.final_altitude_km:.1f} km | {rec} | {surv} |"
            )
        lines.append("")

    # Historical context
    if historical:
        exp = historical.get("expected_storms", {})
        lines += [
            "### Historical Storm Frequency",
            "",
            f"Over this {historical.get('mission_years', 1):.1f}-year mission "
            f"({historical.get('cycle_fraction', 0)*100:.0f}% of solar cycle):",
            "",
            f"| Storm Level | Events per Solar Cycle | Expected This Mission |",
            f"|---|---|---|",
            f"| Kp ≥ 5 (minor)   | 900   | {exp.get('Kp_ge_5', 0):.0f} |",
            f"| Kp ≥ 7 (strong)  | 75    | {exp.get('Kp_ge_7', 0):.1f} |",
            f"| Kp ≥ 8 (severe)  | 15    | {exp.get('Kp_ge_8', 0):.1f} |",
            f"| Kp = 9 (extreme) | 2     | {exp.get('Kp_eq_9', 0):.1f} |",
            "",
        ]

    # Claude insights
    if claude_insights:
        lines += [
            "---",
            "",
            "## AI Analysis",
            "",
            "*The following analysis was generated by Claude when the rule engine "
            "detected complex multi-variable boundary interactions:*",
            "",
        ]
        for i, insight in enumerate(claude_insights, 1):
            if len(claude_insights) > 1:
                lines.append(f"### Insight {i}")
                lines.append("")
            lines.append(insight)
            lines.append("")

    # Design feedback
    lines += [
        "---",
        "",
        "## Design Feedback",
        "",
        "Based on the physics analysis, the following parameter changes would most improve margins:",
        "",
        f"- **Increase Isp** (currently {sc.specific_impulse_s:.0f} s): "
        "Higher specific impulse directly raises the propellant-limited thrust/drag ratio. "
        "In the propellant-limited regime, ratio scales linearly with Isp.",
        f"- **Increase intake area** (currently {sc.intake_area_m2:.2f} m²): "
        "More collection area increases propellant flow without increasing drag "
        "(intake is ram-facing but smaller than frontal area).",
        f"- **Increase solar panel area** (currently {sc.solar_panel_area_m2:.1f} m²): "
        "More power raises the power-limited thrust ceiling, critical during high-density events.",
        f"- **Reduce frontal area** (currently {sc.frontal_area_m2:.2f} m²): "
        "Directly reduces drag force; most impactful at high-density conditions.",
        "",
    ]

    # Data files
    lines += [
        "---",
        "",
        "## Output Files",
        "",
        f"| File | Description |",
        f"|---|---|",
        f"| `sweep_results.csv` | Raw data from all {s.get('total_runs', 0):,} model runs |",
        f"| `survival_heatmap.png` | Thrust/drag ratio heatmap (altitude × F10.7) |",
        f"| `boundary_map.png` | Failure boundary line across conditions |",
        f"| `storm_recovery.png` | Altitude loss and recovery for each storm scenario |",
        "",
    ]

    report_text = "\n".join(lines)
    Path(report_path).write_text(report_text, encoding="utf-8")
    print(f"  Saved: {report_path}")

    return report_path
