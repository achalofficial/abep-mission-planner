"""
analyzer.py — Rule-based analysis engine for ABEP sweep results.

Takes a DataFrame of PhysicsResult rows, identifies failure boundaries,
dominant drivers, interaction effects, and escalation triggers.
"""

from __future__ import annotations

from typing import Optional
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Status classification helpers
# ---------------------------------------------------------------------------

STATUS_ORDER = ["SAFE", "ADEQUATE", "MARGINAL", "FAILURE"]
STATUS_COLORS = {"SAFE": "green", "ADEQUATE": "lightgreen", "MARGINAL": "yellow", "FAILURE": "red"}

def is_failure(status: str) -> bool:
    return status == "FAILURE"

def is_marginal_or_worse(status: str) -> bool:
    return status in ("MARGINAL", "FAILURE")


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze(df: pd.DataFrame) -> dict:
    """
    Run full rule-based analysis on a sweep results DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: altitude_km, f107, ap, month, latitude_deg,
        status, thrust_drag_ratio, total_density_kg_m3, drag_force_mN,
        effective_thrust_mN, power_deficit_W.

    Returns
    -------
    dict with keys:
        summary, failure_rates, boundary_zone, dominant_drivers,
        interaction_effects, escalation_needed, findings
    """
    required = {"altitude_km", "f107", "ap", "month", "latitude_deg",
                "status", "thrust_drag_ratio"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing columns: {missing}")

    total = len(df)
    findings = []

    # ------------------------------------------------------------------
    # 1. Overall status distribution
    # ------------------------------------------------------------------
    counts = df["status"].value_counts().to_dict()
    for s in STATUS_ORDER:
        counts.setdefault(s, 0)

    summary = {
        "total_runs": total,
        "safe_count":     counts["SAFE"],
        "adequate_count": counts["ADEQUATE"],
        "marginal_count": counts["MARGINAL"],
        "failure_count":  counts["FAILURE"],
        "failure_rate":   counts["FAILURE"] / total,
        "success_rate":   (counts["SAFE"] + counts["ADEQUATE"]) / total,
    }

    findings.append(
        f"Overall: {summary['failure_rate']*100:.1f}% FAILURE across {total} runs "
        f"({counts['SAFE']} SAFE, {counts['ADEQUATE']} ADEQUATE, "
        f"{counts['MARGINAL']} MARGINAL, {counts['FAILURE']} FAILURE)"
    )

    # ------------------------------------------------------------------
    # 2. Failure rates by each variable
    # ------------------------------------------------------------------
    failure_rates = {}

    for col, label in [
        ("altitude_km", "altitude"),
        ("f107",        "f107"),
        ("ap",          "ap"),
        ("month",       "month"),
        ("latitude_deg","latitude"),
    ]:
        if col not in df.columns:
            continue
        grp = df.groupby(col)["status"].apply(
            lambda s: (s == "FAILURE").sum() / len(s)
        ).rename("failure_rate")
        failure_rates[label] = grp.reset_index().rename(columns={col: "value"})

    # ------------------------------------------------------------------
    # 3. Boundary zone: altitude band where failure rate transitions
    #    from >80% to <20%
    # ------------------------------------------------------------------
    alt_fr = failure_rates.get("altitude", pd.DataFrame())
    boundary_zone = {"alt_min": None, "alt_max": None}

    if not alt_fr.empty:
        above_80 = alt_fr[alt_fr["failure_rate"] >= 0.80]["value"]
        below_20 = alt_fr[alt_fr["failure_rate"] <= 0.20]["value"]

        if not above_80.empty and not below_20.empty:
            # alt_min = highest altitude that is STILL mostly failing (>80%)
            # alt_max = lowest altitude that is already mostly safe (<20%)
            # The boundary zone is the transition between these two points.
            boundary_zone["alt_min"] = float(above_80.max())
            boundary_zone["alt_max"] = float(below_20.min())
            findings.append(
                f"Boundary zone: failures transition between "
                f"{boundary_zone['alt_min']:.0f}–{boundary_zone['alt_max']:.0f} km"
            )
        elif not above_80.empty:
            boundary_zone["alt_min"] = float(above_80.max())
            findings.append(
                f"High failure rate (>80%) extends up to {boundary_zone['alt_min']:.0f} km "
                f"— entire studied range may be at risk."
            )

        # Most interesting altitude: where failure rate is closest to 50%
        alt_fr_sorted = alt_fr.copy()
        alt_fr_sorted["dist_to_50"] = (alt_fr_sorted["failure_rate"] - 0.5).abs()
        boundary_zone["alt_critical"] = float(
            alt_fr_sorted.sort_values("dist_to_50").iloc[0]["value"]
        )

    # ------------------------------------------------------------------
    # 4. Dominant drivers
    # ------------------------------------------------------------------
    dominant_drivers = {}

    # F10.7 threshold: lowest F10.7 where failures appear at any altitude
    f107_fr = failure_rates.get("f107", pd.DataFrame())
    if not f107_fr.empty:
        failures_present = f107_fr[f107_fr["failure_rate"] > 0]["value"]
        if not failures_present.empty:
            dominant_drivers["f107_failure_threshold"] = float(failures_present.min())
            findings.append(
                f"Failures first appear at F10.7 = {dominant_drivers['f107_failure_threshold']:.0f} SFU"
            )

    # Ap threshold: lowest Ap where failures appear
    ap_fr = failure_rates.get("ap", pd.DataFrame())
    if not ap_fr.empty:
        failures_present = ap_fr[ap_fr["failure_rate"] > 0]["value"]
        if not failures_present.empty:
            dominant_drivers["ap_failure_threshold"] = float(failures_present.min())
            findings.append(
                f"Failures first appear at Ap = {dominant_drivers['ap_failure_threshold']:.0f}"
            )

    # Which variable explains the most variance in failure?
    variances = {}
    for col in ["altitude_km", "f107", "ap", "month", "latitude_deg"]:
        if col not in df.columns:
            continue
        grp_mean = df.groupby(col)["thrust_drag_ratio"].mean()
        variances[col] = float(grp_mean.var())

    if variances:
        dominant_var = max(variances, key=variances.get)
        dominant_drivers["most_influential_variable"] = dominant_var
        findings.append(f"Most influential variable: {dominant_var} (highest between-group ratio variance)")

    # ------------------------------------------------------------------
    # 5. Interaction effects
    # ------------------------------------------------------------------
    interaction_effects = {}

    # Does the failure altitude shift with F10.7?
    if "altitude_km" in df.columns and "f107" in df.columns:
        f107_vals = sorted(df["f107"].unique())
        alt_boundaries = {}
        for f in f107_vals:
            sub = df[df["f107"] == f]
            alt_grp = sub.groupby("altitude_km")["status"].apply(
                lambda s: (s == "FAILURE").sum() / len(s)
            )
            # Find lowest altitude with <50% failure rate
            safe_alts = alt_grp[alt_grp < 0.5].index
            alt_boundaries[f] = float(safe_alts.min()) if len(safe_alts) > 0 else float("nan")

        valid = {k: v for k, v in alt_boundaries.items() if not np.isnan(v)}
        if len(valid) >= 2:
            f107_keys = sorted(valid.keys())
            shift = valid[f107_keys[-1]] - valid[f107_keys[0]]
            interaction_effects["failure_alt_shift_with_f107_km"] = shift
            findings.append(
                f"Failure altitude shifts {abs(shift):.0f} km "
                f"({'higher' if shift > 0 else 'lower'}) from F10.7={f107_keys[0]} "
                f"to F10.7={f107_keys[-1]}"
            )

    # Seasonal anomaly: month with anomalously high/low failure rate
    month_fr = failure_rates.get("month", pd.DataFrame())
    if not month_fr.empty and len(month_fr) > 1:
        mean_fr = month_fr["failure_rate"].mean()
        std_fr = month_fr["failure_rate"].std()
        anomalous = month_fr[
            (month_fr["failure_rate"] > mean_fr + std_fr) |
            (month_fr["failure_rate"] < mean_fr - std_fr)
        ]
        if not anomalous.empty:
            months_str = ", ".join(
                str(int(m)) for m in anomalous["value"].tolist()
            )
            interaction_effects["anomalous_months"] = anomalous["value"].tolist()
            findings.append(f"Anomalous failure rate in months: {months_str}")
        else:
            interaction_effects["anomalous_months"] = []
            findings.append("No significant seasonal anomaly detected.")

    # Non-monotonic altitude relationship?
    if "altitude_km" in df.columns:
        alt_grp = df.groupby("altitude_km")["thrust_drag_ratio"].mean().sort_index()
        diffs = alt_grp.diff().dropna()
        non_monotonic = (diffs < 0).any() and (diffs > 0).any()
        interaction_effects["non_monotonic_altitude"] = bool(non_monotonic)
        if non_monotonic:
            findings.append(
                "Non-monotonic ratio-vs-altitude relationship detected — "
                "likely propellant/power limiter transition."
            )

    # ------------------------------------------------------------------
    # 6. Escalation triggers
    # ------------------------------------------------------------------
    escalation_reasons = []

    # a) Boundary is not a clean function of a single variable
    if len([v for v in variances.values() if v > 0]) > 1:
        top_var_variance = max(variances.values())
        second_var_variance = sorted(variances.values())[-2] if len(variances) >= 2 else 0
        if second_var_variance > 0.3 * top_var_variance:
            escalation_reasons.append(
                "Failure boundary is driven by multiple variables, not a single dominant factor."
            )

    # b) Marginal clusters with no obvious pattern
    marginal = df[df["status"] == "MARGINAL"]
    if len(marginal) > 0:
        marginal_f107_range = marginal["f107"].max() - marginal["f107"].min()
        marginal_ap_range   = marginal["ap"].max()   - marginal["ap"].min()
        if marginal_f107_range > 100 and marginal_ap_range > 100:
            escalation_reasons.append(
                f"Marginal cases span wide F10.7 ({marginal_f107_range:.0f} SFU) "
                f"and Ap ({marginal_ap_range:.0f}) ranges — no clean threshold."
            )

    # c) Non-monotonic relationship
    if interaction_effects.get("non_monotonic_altitude"):
        escalation_reasons.append(
            "Non-monotonic altitude relationship detected — complex limiter transition."
        )

    escalation_needed = len(escalation_reasons) > 0

    return {
        "summary":            summary,
        "failure_rates":      failure_rates,
        "boundary_zone":      boundary_zone,
        "dominant_drivers":   dominant_drivers,
        "interaction_effects": interaction_effects,
        "escalation_needed":  escalation_needed,
        "escalation_reasons": escalation_reasons,
        "findings":           findings,
    }


def print_analysis(result: dict) -> None:
    """Pretty-print analysis results to terminal."""
    s = result["summary"]
    print("=" * 60)
    print("SWEEP ANALYSIS RESULTS")
    print("=" * 60)
    print(f"  Total runs:    {s['total_runs']}")
    print(f"  SAFE:          {s['safe_count']}  ({s['safe_count']/s['total_runs']*100:.1f}%)")
    print(f"  ADEQUATE:      {s['adequate_count']}  ({s['adequate_count']/s['total_runs']*100:.1f}%)")
    print(f"  MARGINAL:      {s['marginal_count']}  ({s['marginal_count']/s['total_runs']*100:.1f}%)")
    print(f"  FAILURE:       {s['failure_count']}  ({s['failure_count']/s['total_runs']*100:.1f}%)")
    print()

    bz = result["boundary_zone"]
    if bz["alt_min"] is not None and bz["alt_max"] is not None:
        print(f"  Boundary zone: {bz['alt_min']:.0f}–{bz['alt_max']:.0f} km")
    if bz.get("alt_critical") is not None:
        print(f"  Critical alt:  {bz['alt_critical']:.0f} km (50% failure rate)")
    print()

    dd = result["dominant_drivers"]
    if "f107_failure_threshold" in dd:
        print(f"  F10.7 failure threshold: {dd['f107_failure_threshold']:.0f} SFU")
    if "ap_failure_threshold" in dd:
        print(f"  Ap failure threshold:    {dd['ap_failure_threshold']:.0f}")
    if "most_influential_variable" in dd:
        print(f"  Most influential var:    {dd['most_influential_variable']}")
    print()

    print("  Findings:")
    for i, f in enumerate(result["findings"], 1):
        print(f"    {i}. {f}")
    print()

    if result["escalation_needed"]:
        print("  [!] CLAUDE API ESCALATION TRIGGERED:")
        for r in result["escalation_reasons"]:
            print(f"      - {r}")
    else:
        print("  [OK] Rule engine fully explains patterns — no Claude API call needed.")
    print()
