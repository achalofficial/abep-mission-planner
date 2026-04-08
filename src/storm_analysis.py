"""
storm_analysis.py — Storm recovery modeling for ABEP satellites.

Simulates altitude loss during geomagnetic storm events and the time
required to recover once the storm passes, using simplified orbital
mechanics with time-stepped integration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .models import SpacecraftParams
from .atmosphere import query_atmosphere
from .models import AtmosphericConditions

# Physical constants
GM = 3.986004418e14   # m³/s²
R_EARTH = 6_371_000   # m


@dataclass
class StormScenario:
    """A single storm event definition."""
    name: str
    ap_storm: float          # Ap during storm
    ap_quiet: float          # Ap during recovery
    duration_h: float        # Storm duration (hours)
    f107: float = 140.0      # Solar flux during event


@dataclass
class StormResult:
    """Outcome of simulating one storm scenario."""
    scenario: StormScenario
    initial_altitude_km: float

    altitude_loss_km: float = 0.0
    final_altitude_km: float = 0.0
    recovery_time_h: float = 0.0
    survived: bool = True

    # Time series (hourly snapshots)
    time_h: list = field(default_factory=list)
    altitude_km_series: list = field(default_factory=list)
    thrust_drag_ratio_series: list = field(default_factory=list)
    phase_series: list = field(default_factory=list)   # "storm" or "recovery"


# ---------------------------------------------------------------------------
# Simplified orbital mechanics
# ---------------------------------------------------------------------------

def _orbital_velocity(alt_km: float) -> float:
    return math.sqrt(GM / (R_EARTH + alt_km * 1000.0))


def _altitude_loss_rate_km_per_h(
    alt_km: float, ap: float, f107: float, sc: SpacecraftParams
) -> tuple[float, float]:
    """
    Compute instantaneous altitude loss rate at given conditions.

    Returns (dh_dt_km_per_h, thrust_drag_ratio).

    Uses the vis-viva / energy-loss formulation:
        da/dt = -2 * F_net / (m * n_orb)
    where F_net = F_drag - F_thrust (positive means losing altitude).
    """
    from .physics import compute_physics

    cond = AtmosphericConditions(
        altitude_km=alt_km,
        f107=f107,
        f107_avg=f107,
        ap=ap,
        datetime=datetime(2025, 6, 21, 12),
        latitude_deg=0.0,
        longitude_deg=0.0,
    )
    atm = query_atmosphere(cond)
    pr = compute_physics(atm, sc)

    a = R_EARTH + alt_km * 1000.0      # semi-major axis (m)
    n_orb = math.sqrt(GM / a**3)       # mean motion (rad/s)

    F_drag_N = pr.drag_force_mN / 1000.0
    F_thrust_N = pr.effective_thrust_mN / 1000.0
    F_net_N = F_drag_N - F_thrust_N    # > 0: losing altitude

    da_dt = -2.0 * F_net_N / (sc.mass_kg * n_orb)  # m/s
    dh_dt_km_per_h = da_dt * 3600.0 / 1000.0        # km/h (negative = losing alt)

    return dh_dt_km_per_h, pr.thrust_drag_ratio


# ---------------------------------------------------------------------------
# Storm integration
# ---------------------------------------------------------------------------

def simulate_storm(
    initial_altitude_km: float,
    scenario: StormScenario,
    sc: SpacecraftParams,
    dt_h: float = 1.0,          # integration time step (hours)
    max_recovery_h: float = 240.0,  # max recovery simulation time (hours)
    min_altitude_km: float = 150.0, # deorbit threshold
) -> StormResult:
    """
    Integrate the altitude trajectory through a storm and subsequent recovery.

    Storm phase: `scenario.duration_h` hours at `scenario.ap_storm`.
    Recovery phase: up to `max_recovery_h` hours at `scenario.ap_quiet`
                    until altitude returns to within 1 km of initial.
    """
    result = StormResult(
        scenario=scenario,
        initial_altitude_km=initial_altitude_km,
    )

    alt = initial_altitude_km
    t = 0.0

    # --- Storm phase ---
    while t < scenario.duration_h:
        dh_dt, ratio = _altitude_loss_rate_km_per_h(alt, scenario.ap_storm, scenario.f107, sc)
        result.time_h.append(t)
        result.altitude_km_series.append(alt)
        result.thrust_drag_ratio_series.append(ratio)
        result.phase_series.append("storm")

        alt += dh_dt * dt_h
        t += dt_h

        if alt < min_altitude_km:
            result.survived = False
            alt = min_altitude_km
            break

    altitude_after_storm = alt
    result.altitude_loss_km = initial_altitude_km - altitude_after_storm

    if not result.survived:
        result.final_altitude_km = alt
        result.recovery_time_h = float("inf")
        return result

    # --- Recovery phase ---
    recovery_start_t = t
    recovered = False
    while t < recovery_start_t + max_recovery_h:
        dh_dt, ratio = _altitude_loss_rate_km_per_h(alt, scenario.ap_quiet, scenario.f107, sc)
        result.time_h.append(t)
        result.altitude_km_series.append(alt)
        result.thrust_drag_ratio_series.append(ratio)
        result.phase_series.append("recovery")

        alt += dh_dt * dt_h
        t += dt_h

        if alt < min_altitude_km:
            result.survived = False
            break

        # Recovered: within 0.5 km of initial altitude and climbing
        if alt >= initial_altitude_km - 0.5 and dh_dt >= 0:
            recovered = True
            break

    result.final_altitude_km = alt
    result.recovery_time_h = (t - recovery_start_t) if recovered else float("inf")

    return result


# ---------------------------------------------------------------------------
# Full storm recovery analysis
# ---------------------------------------------------------------------------

STORM_SCENARIOS = [
    # (name,            ap_storm, ap_quiet, duration_h, f107)
    StormScenario("Minor (Kp5)",      50,  4, 6,  140),
    StormScenario("Moderate (Kp6)",   100, 4, 12, 140),
    StormScenario("Strong (Kp7)",     150, 4, 24, 200),
    StormScenario("Severe (Kp8)",     200, 4, 24, 250),
    StormScenario("Extreme (Kp9)",    300, 4, 48, 250),
]


def run_storm_recovery(
    target_altitude_km: float,
    sc: SpacecraftParams,
) -> dict:
    """
    Simulate all standard storm scenarios from the target altitude.

    Returns a dict with results list and summary table.
    """
    print(f"  Simulating {len(STORM_SCENARIOS)} storm scenarios from {target_altitude_km:.0f} km...")
    print()
    print(f"  {'Scenario':<22} {'Ap':>4} {'Dur(h)':>6} {'AltLoss(km)':>12} "
          f"{'FinalAlt(km)':>13} {'Recovery(h)':>12} {'Survived':>9}")
    print("  " + "-" * 84)

    results = []
    for s in STORM_SCENARIOS:
        r = simulate_storm(target_altitude_km, s, sc)
        results.append(r)

        rec_str = f"{r.recovery_time_h:.1f}" if r.recovery_time_h != float("inf") else "never"
        surv_str = "YES" if r.survived else "NO (deorbit)"
        print(f"  {s.name:<22} {s.ap_storm:>4.0f} {s.duration_h:>6.0f} "
              f"{r.altitude_loss_km:>12.2f} {r.final_altitude_km:>13.2f} "
              f"{rec_str:>12} {surv_str:>9}")

    print()

    # Summary statistics
    max_loss = max(r.altitude_loss_km for r in results)
    max_recovery = max(
        r.recovery_time_h for r in results if r.recovery_time_h != float("inf")
    ) if any(r.recovery_time_h != float("inf") for r in results) else float("inf")
    any_deorbit = any(not r.survived for r in results)

    print(f"  Max altitude loss (all scenarios): {max_loss:.2f} km")
    if max_recovery != float("inf"):
        print(f"  Max recovery time (survivable):    {max_recovery:.1f} h")
    if any_deorbit:
        scenarios_failed = [r.scenario.name for r in results if not r.survived]
        print(f"  Deorbit risk scenarios: {', '.join(scenarios_failed)}")
    else:
        print(f"  All scenarios survivable from {target_altitude_km:.0f} km.")

    return {
        "target_altitude_km": target_altitude_km,
        "results": results,
        "max_altitude_loss_km": max_loss,
        "max_recovery_time_h": max_recovery,
        "any_deorbit_risk": any_deorbit,
    }
