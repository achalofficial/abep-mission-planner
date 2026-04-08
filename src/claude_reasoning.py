"""
claude_reasoning.py — Claude API integration for ABEP pattern interpretation.

Called only when the rule engine can't fully explain a pattern — typically
when the failure boundary is multi-variable or has non-monotonic structure.
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd


SYSTEM_PROMPT = (
    "You are an atmospheric physicist and mission planning analyst. "
    "Analyze ABEP system performance data and provide actionable findings "
    "for satellite mission planning. Be specific about which conditions "
    "create risk and quantify margins where possible."
)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 2000


# ---------------------------------------------------------------------------
# Data packaging helpers
# ---------------------------------------------------------------------------

def _summarize_boundary(df: pd.DataFrame, analysis: dict) -> str:
    """Build a compact text summary of boundary-zone data points."""
    bz = analysis.get("boundary_zone", {})
    alt_min = bz.get("alt_min") or df["altitude_km"].min()
    alt_max = bz.get("alt_max") or df["altitude_km"].max()

    # Focus on the boundary zone and marginal/failure transition
    boundary_df = df[
        (df["altitude_km"] >= alt_min - 10) &
        (df["altitude_km"] <= alt_max + 10)
    ]

    if len(boundary_df) == 0:
        boundary_df = df

    # Aggregate: mean ratio by (altitude, f107, ap bucket)
    boundary_df = boundary_df.copy()
    boundary_df["ap_bucket"] = pd.cut(
        boundary_df["ap"],
        bins=[0, 20, 80, 200, 500],
        labels=["quiet(4-20)", "minor_storm(20-80)", "moderate_storm(80-200)", "severe_storm(200+)"]
    )

    summary_table = (
        boundary_df.groupby(["altitude_km", "f107", "ap_bucket"], observed=True)
        .agg(
            mean_ratio=("thrust_drag_ratio", "mean"),
            failure_rate=("status", lambda s: (s == "FAILURE").mean()),
            n=("status", "count"),
        )
        .reset_index()
    )

    lines = ["altitude_km | f107 | ap_condition       | mean_ratio | failure_rate | n"]
    lines.append("-" * 72)
    for _, row in summary_table.iterrows():
        lines.append(
            f"{row['altitude_km']:>10.0f} | {row['f107']:>4.0f} | "
            f"{str(row['ap_bucket']):<18} | {row['mean_ratio']:>10.3f} | "
            f"{row['failure_rate']:>12.1%} | {row['n']:>4}"
        )

    return "\n".join(lines)


def _summarize_seasonal(df: pd.DataFrame) -> str:
    """Monthly failure rate pattern."""
    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    monthly = (
        df.groupby("month")
        .agg(failure_rate=("status", lambda s: (s == "FAILURE").mean()),
             mean_ratio=("thrust_drag_ratio", "mean"))
        .reset_index()
    )
    lines = ["month | failure_rate | mean_ratio"]
    for _, row in monthly.iterrows():
        lines.append(
            f"{month_names[int(row['month'])]:>5} | "
            f"{row['failure_rate']:>12.1%} | "
            f"{row['mean_ratio']:>10.3f}"
        )
    return "\n".join(lines)


def _build_prompt(df: pd.DataFrame, analysis: dict,
                  mission_alt: float, mission_days: float) -> str:
    """Assemble the full user message for the Claude API call."""
    s = analysis.get("summary", {})
    bz = analysis.get("boundary_zone", {})
    dd = analysis.get("dominant_drivers", {})
    escalation_reasons = analysis.get("escalation_reasons", [])

    boundary_table = _summarize_boundary(df, analysis)
    seasonal_table = _summarize_seasonal(df)

    reasons_str = "\n".join(f"  - {r}" for r in escalation_reasons)

    prompt = f"""
## ABEP Mission Feasibility Analysis Request

**Mission:** VLEO satellite at {mission_alt:.0f} km for {mission_days:.0f} days.
**System:** Air-Breathing Electric Propulsion (ABEP) — collects atmospheric gas as propellant.

**Overall sweep results:**
- Total conditions modeled: {s.get('total_runs', 0):,}
- SAFE: {s.get('safe_count', 0)} | ADEQUATE: {s.get('adequate_count', 0)} | MARGINAL: {s.get('marginal_count', 0)} | FAILURE: {s.get('failure_count', 0)}
- Overall failure rate: {s.get('failure_rate', 0):.1%}

**Boundary zone:** failures transition between {bz.get('alt_min', '?')} and {bz.get('alt_max', '?')} km altitude.

**Why the rule engine escalated:**
{reasons_str}

**Dominant driver summary:**
- F10.7 threshold where failures appear: {dd.get('f107_failure_threshold', '?')} SFU
- Ap threshold where failures appear: {dd.get('ap_failure_threshold', '?')}
- Most influential variable: {dd.get('most_influential_variable', '?')}

**Boundary zone data (thrust/drag ratio and failure rate by altitude, solar flux, storm level):**
{boundary_table}

**Seasonal pattern (failure rate by month):**
{seasonal_table}

---

Analyze this atmospheric data near the ABEP failure boundary. What interaction between
solar flux, geomagnetic activity, season, and atmospheric composition drives the marginal
cases? Specifically:

1. What is the primary driver of the failure boundary, and how do secondary variables
   modulate it?
2. Are there conditions where the system transitions non-monotonically (e.g., fails at
   moderate solar flux but recovers at high solar flux due to composition changes)?
3. What is the minimum safe altitude for this mission under realistic solar cycle conditions?
4. What are the highest-risk windows (season + solar cycle phase combinations)?
5. What single spacecraft parameter change would most improve the system's margins?

Provide a plain-language explanation suitable for mission planning, with specific numbers
where possible.
""".strip()

    return prompt


# ---------------------------------------------------------------------------
# Main API call
# ---------------------------------------------------------------------------

def call_claude_reasoning(
    df: pd.DataFrame,
    analysis: dict,
    mission,           # MissionParams
    sc,                # SpacecraftParams
    api_key: Optional[str] = None,
) -> str:
    """
    Call the Claude API with a data-driven prompt about the failure boundary.

    Returns the model's plain-language analysis as a string.
    Raises RuntimeError if the API call fails.
    """
    import anthropic  # imported here so the module loads without it

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. "
            "Set the environment variable or pass api_key= to call_claude_reasoning()."
        )

    prompt = _build_prompt(df, analysis, mission.target_altitude_km, mission.mission_duration_days)

    print(f"  Sending {len(prompt)} char prompt to {MODEL}...")

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text
    print(f"  Received {len(response_text)} char response  "
          f"(in={message.usage.input_tokens} tok, out={message.usage.output_tokens} tok)")

    return response_text
