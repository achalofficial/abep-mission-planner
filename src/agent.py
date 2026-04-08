"""
agent.py — Autonomous sweep agent for ABEP mission planning.

Runs the full analysis loop:
  Phase 1: Coarse parameter sweep
  Phase 2: Rule-based analysis
  Phase 3: Autonomous grid refinement around the boundary zone
  Phase 4: Claude API escalation for unexplained marginal cases
  Phase 5: Storm recovery analysis
  Phase 6: Historical storm context
"""

from __future__ import annotations

import itertools
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from .models import AtmosphericConditions, MissionParams, SpacecraftParams
from .atmosphere import query_atmosphere
from .physics import compute_physics
from .analyzer import analyze, print_analysis


# ---------------------------------------------------------------------------
# Sweep grid definitions (from spec)
# ---------------------------------------------------------------------------

COARSE_GRID = {
    "altitudes_km": [150, 160, 170, 180, 190, 200, 210, 220, 230, 240, 250],
    "months":       list(range(1, 13)),
    "f107":         [70, 100, 140, 180, 220, 250],
    "ap":           [4, 15, 50, 100, 200, 300],
    "latitudes":    [0.0, 45.0, 70.0],
}

# Representative day-of-month for each month (21st)
_MONTH_DAYS = {m: 21 for m in range(1, 13)}


def _dt_for_month(month: int, year: int = 2025) -> datetime:
    return datetime(year, month, _MONTH_DAYS[month], 12, 0)


# ---------------------------------------------------------------------------
# Single-point runner
# ---------------------------------------------------------------------------

def _run_point(alt: float, f107: float, ap: float, month: int,
               lat: float, sc: SpacecraftParams) -> dict:
    """Run atmosphere + physics for one grid point. Returns a flat dict."""
    dt = _dt_for_month(month)
    cond = AtmosphericConditions(
        altitude_km=alt,
        f107=f107,
        f107_avg=f107,
        ap=ap,
        datetime=dt,
        latitude_deg=lat,
        longitude_deg=0.0,
    )
    atm = query_atmosphere(cond)
    pr = compute_physics(atm, sc)

    return {
        "altitude_km":          pr.altitude_km,
        "f107":                 pr.f107,
        "ap":                   pr.ap,
        "month":                pr.month,
        "latitude_deg":         pr.latitude_deg,
        "total_density_kg_m3":  pr.total_density_kg_m3,
        "o_fraction":           pr.o_fraction,
        "n2_fraction":          pr.n2_fraction,
        "temperature_K":        pr.temperature_K,
        "orbital_velocity_m_s": pr.orbital_velocity_m_s,
        "drag_force_mN":        pr.drag_force_mN,
        "thrust_max_mN":        pr.thrust_max_mN,
        "thrust_propellant_mN": pr.thrust_propellant_mN,
        "effective_thrust_mN":  pr.effective_thrust_mN,
        "thrust_drag_ratio":    pr.thrust_drag_ratio,
        "power_available_W":    pr.power_available_W,
        "power_required_W":     pr.power_required_W,
        "power_deficit_W":      pr.power_deficit_W,
        "mdot_collected_kg_s":  pr.mdot_collected_kg_s,
        "status":               pr.status,
        "altitude_loss_rate_km_per_day": pr.altitude_loss_rate_km_per_day,
        "limiter":              "PROP" if pr.thrust_propellant_mN < pr.thrust_max_mN else "PWR",
    }


def _run_sweep(points: list[tuple], sc: SpacecraftParams,
               label: str, print_interval: int = 500) -> pd.DataFrame:
    """
    Execute a list of (alt, f107, ap, month, lat) tuples through the engine.
    Prints progress every `print_interval` calls.
    """
    total = len(points)
    rows = []
    t0 = time.time()

    for i, (alt, f107, ap, month, lat) in enumerate(points, 1):
        rows.append(_run_point(alt, f107, ap, month, lat, sc))
        if i % print_interval == 0 or i == total:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0
            print(f"  [{label}] {i}/{total}  ({rate:.0f} pts/s,  ETA {eta:.0f}s)")

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Phase 1: Coarse sweep
# ---------------------------------------------------------------------------

def phase1_coarse_sweep(sc: SpacecraftParams, state: dict) -> pd.DataFrame:
    print("\n" + "=" * 60)
    print("PHASE 1: COARSE PARAMETER SWEEP")
    print("=" * 60)

    g = COARSE_GRID
    points = list(itertools.product(
        g["altitudes_km"], g["f107"], g["ap"], g["months"], g["latitudes"]
    ))
    expected = (len(g["altitudes_km"]) * len(g["f107"]) * len(g["ap"])
                * len(g["months"]) * len(g["latitudes"]))

    print(f"  Grid: {len(g['altitudes_km'])} alts × {len(g['f107'])} F10.7 "
          f"× {len(g['ap'])} Ap × {len(g['months'])} months × {len(g['latitudes'])} lats")
    print(f"  Total points: {expected:,}")
    print(f"  Running...")

    t0 = time.time()
    df = _run_sweep(points, sc, "COARSE", print_interval=1000)
    elapsed = time.time() - t0

    state["coarse_results"] = df
    state["sweep_count"] += len(df)
    state["phase"] = "rule_analysis"

    print(f"  Done. {len(df):,} points in {elapsed:.1f}s  ({len(df)/elapsed:.0f} pts/s)")
    return df


# ---------------------------------------------------------------------------
# Phase 2: Rule-based analysis
# ---------------------------------------------------------------------------

def phase2_rule_analysis(df: pd.DataFrame, state: dict) -> dict:
    print("\n" + "=" * 60)
    print("PHASE 2: RULE-BASED ANALYSIS")
    print("=" * 60)

    result = analyze(df)
    print_analysis(result)

    state["analysis"] = result
    state["boundary_zone"] = result["boundary_zone"]
    state["findings"].extend(result["findings"])
    state["phase"] = "grid_refinement"

    return result


# ---------------------------------------------------------------------------
# Phase 3: Autonomous grid refinement
# ---------------------------------------------------------------------------

def phase3_grid_refinement(coarse_df: pd.DataFrame, analysis: dict,
                            sc: SpacecraftParams, state: dict) -> Optional[pd.DataFrame]:
    print("\n" + "=" * 60)
    print("PHASE 3: AUTONOMOUS GRID REFINEMENT")
    print("=" * 60)

    bz = analysis["boundary_zone"]
    dd = analysis["dominant_drivers"]

    if bz["alt_min"] is None or bz["alt_max"] is None:
        print("  No clear boundary zone detected in coarse sweep.")
        print("  Skipping refinement — using coarse results only.")
        state["phase"] = "claude_escalation"
        return None

    alt_lo = max(bz["alt_min"] - 10, 150.0)
    alt_hi = min(bz["alt_max"] + 10, 250.0)
    print(f"  Boundary zone detected: {bz['alt_min']:.0f}–{bz['alt_max']:.0f} km")
    print(f"  Refining altitude range: {alt_lo:.0f}–{alt_hi:.0f} km (1 km steps)")

    # Refined altitude range
    refined_alts = [float(a) for a in range(int(alt_lo), int(alt_hi) + 1, 1)]

    # Refined F10.7 around the failure threshold
    f107_thresh = dd.get("f107_failure_threshold", 140)
    f107_lo = max(f107_thresh - 30, 70)
    f107_hi = min(f107_thresh + 60, 300)
    refined_f107 = sorted(set(
        COARSE_GRID["f107"] +
        [round(f107_lo + i * 10) for i in range(int((f107_hi - f107_lo) / 10) + 1)]
    ))
    print(f"  Refined F10.7 range: {min(refined_f107)}–{max(refined_f107)} "
          f"({len(refined_f107)} levels)")

    # Refined Ap around the storm threshold
    ap_thresh = dd.get("ap_failure_threshold", 50)
    refined_ap = sorted(set(
        COARSE_GRID["ap"] +
        [ap_thresh, ap_thresh + 25, ap_thresh + 50, ap_thresh + 100]
    ))
    print(f"  Refined Ap levels: {refined_ap}")

    # Months: all 12 (keep full seasonal coverage)
    # Latitudes: keep coarse set
    points = list(itertools.product(
        refined_alts, refined_f107, refined_ap,
        COARSE_GRID["months"], COARSE_GRID["latitudes"]
    ))

    print(f"  Refined grid: {len(refined_alts)} alts × {len(refined_f107)} F10.7 "
          f"× {len(refined_ap)} Ap × 12 months × 3 lats")
    print(f"  Refined points: {len(points):,}  (running...)")

    t0 = time.time()
    refined_df = _run_sweep(points, sc, "REFINE", print_interval=2000)
    elapsed = time.time() - t0

    state["refined_results"] = refined_df
    state["sweep_count"] += len(refined_df)
    state["refinement_iterations"] += 1
    state["phase"] = "claude_escalation"

    print(f"  Done. {len(refined_df):,} refined points in {elapsed:.1f}s")
    print(f"  Total sweep calls so far: {state['sweep_count']:,}")

    # Re-analyze combined data
    print("\n  Re-analyzing combined coarse + refined data...")
    combined = pd.concat([coarse_df, refined_df], ignore_index=True)
    refined_analysis = analyze(combined)
    state["analysis"] = refined_analysis
    state["boundary_zone"] = refined_analysis["boundary_zone"]
    print_analysis(refined_analysis)

    return refined_df


# ---------------------------------------------------------------------------
# Phase 4: Claude API escalation
# ---------------------------------------------------------------------------

def phase4_claude_escalation(combined_df: pd.DataFrame, analysis: dict,
                               mission: MissionParams, sc: SpacecraftParams,
                               state: dict) -> Optional[str]:
    print("\n" + "=" * 60)
    print("PHASE 4: CLAUDE API ESCALATION CHECK")
    print("=" * 60)

    if not analysis.get("escalation_needed", False):
        print("  Rule engine fully explains all patterns.")
        print("  No Claude API call needed.")
        state["phase"] = "storm_analysis"
        return None

    print("  Escalation triggered:")
    for reason in analysis.get("escalation_reasons", []):
        print(f"    - {reason}")
    print("  Calling Claude API for interpretation...")

    try:
        from .claude_reasoning import call_claude_reasoning
        insight = call_claude_reasoning(combined_df, analysis, mission, sc)
        state["claude_insights"].append(insight)
        print(f"\n  Claude insight received ({len(insight)} chars).")
        state["phase"] = "storm_analysis"
        return insight
    except ImportError:
        print("  [WARN] claude_reasoning.py not available yet — skipping.")
        state["phase"] = "storm_analysis"
        return None
    except Exception as e:
        print(f"  [WARN] Claude API call failed: {e}")
        state["phase"] = "storm_analysis"
        return None


# ---------------------------------------------------------------------------
# Phase 5 & 6: Delegated to storm_analysis module
# ---------------------------------------------------------------------------

def phase5_storm_recovery(combined_df: pd.DataFrame, mission: MissionParams,
                           sc: SpacecraftParams, state: dict) -> Optional[dict]:
    print("\n" + "=" * 60)
    print("PHASE 5: STORM RECOVERY ANALYSIS")
    print("=" * 60)
    try:
        from .storm_analysis import run_storm_recovery
        result = run_storm_recovery(mission.target_altitude_km, sc)
        state["storm_recovery"] = result
        state["phase"] = "report"
        return result
    except ImportError:
        print("  [WARN] storm_analysis.py not available yet — skipping.")
        state["phase"] = "report"
        return None


def phase6_historical_context(state: dict) -> dict:
    print("\n" + "=" * 60)
    print("PHASE 6: HISTORICAL STORM CONTEXT")
    print("=" * 60)

    # Hardcoded NOAA historical statistics (per solar cycle ~11 years)
    storms_per_cycle = {
        "Kp_ge_5":  900,
        "Kp_ge_7":  75,
        "Kp_ge_8":  15,
        "Kp_eq_9":  2,
    }

    mission_years = state.get("mission_duration_days", 365) / 365.25
    cycle_fraction = mission_years / 11.0

    expected_storms = {
        k: round(v * cycle_fraction, 1)
        for k, v in storms_per_cycle.items()
    }

    print(f"  Mission duration: {mission_years:.2f} years "
          f"({cycle_fraction*100:.1f}% of solar cycle)")
    print(f"  Expected geomagnetic storms during mission:")
    print(f"    Kp >= 5 (minor):    {expected_storms['Kp_ge_5']:.0f} events")
    print(f"    Kp >= 7 (strong):   {expected_storms['Kp_ge_7']:.1f} events")
    print(f"    Kp >= 8 (severe):   {expected_storms['Kp_ge_8']:.1f} events")
    print(f"    Kp = 9  (extreme):  {expected_storms['Kp_eq_9']:.1f} events")

    context = {
        "storms_per_cycle":     storms_per_cycle,
        "mission_years":        mission_years,
        "cycle_fraction":       cycle_fraction,
        "expected_storms":      expected_storms,
    }
    state["historical_context"] = context
    state["phase"] = "done"
    return context


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

def run_agent(
    mission: MissionParams,
    sc: SpacecraftParams,
    skip_refinement: bool = False,
    skip_claude: bool = False,
) -> dict:
    """
    Run the full autonomous agent loop.

    Parameters
    ----------
    mission : MissionParams
    sc : SpacecraftParams
    skip_refinement : bool
        If True, skip Phase 3 (useful for quick tests).
    skip_claude : bool
        If True, skip Phase 4 Claude API call.

    Returns
    -------
    dict
        Full agent state with all results, findings, and data.
    """
    state = {
        "phase":                "coarse_sweep",
        "coarse_results":       pd.DataFrame(),
        "refined_results":      pd.DataFrame(),
        "analysis":             {},
        "boundary_zone":        {"alt_min": None, "alt_max": None},
        "findings":             [],
        "claude_insights":      [],
        "storm_recovery":       None,
        "historical_context":   None,
        "sweep_count":          0,
        "refinement_iterations": 0,
        "mission_duration_days": mission.mission_duration_days,
    }

    t_total = time.time()
    print("\n" + "#" * 60)
    print("# ABEP AUTONOMOUS MISSION ANALYSIS AGENT")
    print(f"# Target altitude: {mission.target_altitude_km:.0f} km")
    print(f"# Mission duration: {mission.mission_duration_days:.0f} days")
    print("#" * 60)

    # Phase 1
    coarse_df = phase1_coarse_sweep(sc, state)

    # Phase 2
    analysis = phase2_rule_analysis(coarse_df, state)

    # Phase 3
    refined_df = None
    if not skip_refinement:
        refined_df = phase3_grid_refinement(coarse_df, analysis, sc, state)
        if refined_df is not None:
            analysis = state["analysis"]  # updated by phase3

    combined_df = (
        pd.concat([coarse_df, refined_df], ignore_index=True)
        if refined_df is not None
        else coarse_df
    )

    # Phase 4
    if not skip_claude:
        phase4_claude_escalation(combined_df, analysis, mission, sc, state)

    # Phase 5
    phase5_storm_recovery(combined_df, mission, sc, state)

    # Phase 6
    phase6_historical_context(state)

    total_time = time.time() - t_total
    print("\n" + "#" * 60)
    print(f"# AGENT COMPLETE")
    print(f"# Total atmospheric model calls: {state['sweep_count']:,}")
    print(f"# Total wall time: {total_time:.1f}s")
    print("#" * 60 + "\n")

    state["combined_results"] = combined_df
    return state
