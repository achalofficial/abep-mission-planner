"""
orbit_propagator.py -- Time-stepping orbital propagator for ABEP mission simulation.

At each time step (1 h default):
  1. Look up solar/geomagnetic conditions for the current date.
  2. Compute geometric eclipse fraction from beta-angle.
  3. Track battery charge across eclipse/sunlit periods.
  4. Query NRLMSISE-00, compute thrust-drag balance.
  5. Advance altitude:  dh/dt = -2*(F_drag - F_thrust) / (m * n_orb)
  6. Flag deorbit if altitude < 150 km.

Usage
-----
    from src.orbit_propagator import propagate_orbit
    result = propagate_orbit(mission, sc, solar_df, dt_hours=1.0)
"""

import math
import datetime
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from .models import AtmosphericConditions, MissionParams, SpacecraftParams
from .atmosphere import query_atmosphere
from .physics import (GM, R_EARTH, SOLAR_CONSTANT,
                      compute_physics, eclipse_fraction_geometric, orbital_period_s)

DEORBIT_ALT_KM = 150.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class PropagationEvent:
    time_h: float
    date: str               # ISO date string "YYYY-MM-DD"
    event_type: str         # "storm" | "eclipse_deficit" | "deorbit" | "altitude_warning"
    description: str
    altitude_km: float
    ap: float
    f107: float


@dataclass
class PropagationResult:
    """Full time-series output from propagate_orbit()."""
    # Per-step arrays (sampled at dt_hours)
    times_h:        List[float] = field(default_factory=list)
    dates:          List[str]   = field(default_factory=list)
    altitudes_km:   List[float] = field(default_factory=list)
    ratios:         List[float] = field(default_factory=list)
    f107s:          List[float] = field(default_factory=list)
    aps:            List[float] = field(default_factory=list)
    drag_mN:        List[float] = field(default_factory=list)
    thrust_mN:      List[float] = field(default_factory=list)
    eclipse_fracs:  List[float] = field(default_factory=list)
    power_deficit_W: List[float] = field(default_factory=list)
    battery_wh:     List[float] = field(default_factory=list)

    # Notable events
    events: List[PropagationEvent] = field(default_factory=list)

    # Summary
    survived: bool = True
    deorbit_time_h: Optional[float] = None
    final_altitude_km: float = 0.0
    dt_hours: float = 1.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _beta_angle_deg(
    t_days: float,
    start_dt: datetime.datetime,
    inclination_deg: float,
) -> float:
    """
    Approximate solar beta angle (orbit-plane ↔ Sun vector, degrees).
    For low-inclination orbits this ≈ solar declination ≈ 23.5° × sin(seasonal phase).
    """
    current = start_dt + datetime.timedelta(days=t_days)
    doy = current.timetuple().tm_yday
    declination = 23.5 * math.sin(2.0 * math.pi * (doy - 80) / 365.25)
    beta = inclination_deg + declination
    return max(-90.0, min(90.0, beta))


def _power_budget(sc: SpacecraftParams, ecl_frac: float) -> dict:
    """
    Compute orbital-average power budget including battery effects.

    Returns a dict with keys:
      p_thruster_W  -- power available to the thruster (orbital average)
      p_deficit_W   -- power the spacecraft *cannot* supply (> 0 = problem)
      eclipse_energy_J -- energy required from battery per orbit eclipse pass
    """
    from .physics import SOLAR_CONSTANT
    T_orb = orbital_period_s(200.0)  # approximate; recalculated per step in main loop

    # Sunlit fraction
    sunlit = 1.0 - ecl_frac

    # Gross solar power during sunlit phase (W)
    p_solar = sc.solar_panel_area_m2 * SOLAR_CONSTANT * sc.solar_panel_efficiency

    # Orbital-average net power after housekeeping
    p_avg = p_solar * sunlit - sc.housekeeping_power_W

    # Energy needed from battery to cover housekeeping during one eclipse pass (J)
    t_eclipse_s = ecl_frac * T_orb
    eclipse_energy_J = sc.housekeeping_power_W * t_eclipse_s

    # Available power to thruster (can't be negative)
    p_thruster = max(p_avg, 0.0)

    # Power deficit: how much the orbital-average power is short
    p_deficit = max(-p_avg, 0.0)

    return {
        "p_thruster_W": p_thruster,
        "p_deficit_W": p_deficit,
        "eclipse_energy_J": eclipse_energy_J,
    }


# ---------------------------------------------------------------------------
# Main propagator
# ---------------------------------------------------------------------------

def propagate_orbit(
    mission: MissionParams,
    sc: SpacecraftParams,
    solar_data: pd.DataFrame,
    dt_hours: float = 1.0,
    verbose: bool = True,
) -> PropagationResult:
    """
    Propagate the ABEP orbit over the full mission timeline.

    Parameters
    ----------
    mission : MissionParams
    sc      : SpacecraftParams
    solar_data : pd.DataFrame
        Columns: date (date or str), f107 (float), ap (float).  One row per day.
    dt_hours : float
        Integration time step in hours (default 1 h).
    verbose : bool
        Print progress every 1000 steps.

    Returns
    -------
    PropagationResult
    """
    result = PropagationResult(dt_hours=dt_hours)

    # Build fast date-keyed index for solar data
    solar = solar_data.copy()
    solar["date"] = pd.to_datetime(solar["date"])
    solar = solar.set_index("date")

    alt_km = mission.target_altitude_km
    total_h = mission.mission_duration_days * 24.0
    n_steps = int(total_h / dt_hours)
    t_step_s = dt_hours * 3600.0

    battery_wh = sc.battery_capacity_wh   # start full
    prev_ap = 5.0
    last_print_step = 0

    for i in range(n_steps):
        t_h = i * dt_hours
        current_dt = mission.start_datetime + datetime.timedelta(hours=t_h)
        date_key = pd.Timestamp(current_dt.date())

        # --- Solar / geomagnetic conditions ---
        try:
            row = solar.loc[date_key]
            f107 = float(row["f107"])
            ap   = float(row["ap"])
        except KeyError:
            f107, ap = 140.0, 10.0

        # --- Geometric eclipse fraction ---
        beta = _beta_angle_deg(t_h / 24.0, mission.start_datetime,
                               getattr(mission, "orbit_inclination_deg", 0.0))
        ecl = eclipse_fraction_geometric(alt_km, beta_deg=beta)

        # --- Per-orbit power budget ---
        T_orb_s = orbital_period_s(alt_km)
        t_eclipse_s = ecl * T_orb_s
        t_sunlit_s  = (1.0 - ecl) * T_orb_s

        p_solar_peak = sc.solar_panel_area_m2 * SOLAR_CONSTANT * sc.solar_panel_efficiency
        p_avg_net = p_solar_peak * (1.0 - ecl) - sc.housekeeping_power_W

        # Battery bookkeeping (Wh over this time step)
        energy_generated_J = max(p_avg_net, 0.0) * t_step_s
        eclipse_draw_J = sc.housekeeping_power_W * t_eclipse_s * (t_step_s / T_orb_s)
        battery_wh = min(
            battery_wh + (energy_generated_J - eclipse_draw_J) / 3600.0,
            sc.battery_capacity_wh,
        )
        battery_wh = max(battery_wh, 0.0)

        # Power deficit: can battery cover the eclipse housekeeping?
        bat_J = battery_wh * 3600.0
        p_deficit_W = 0.0
        if bat_J < sc.housekeeping_power_W * t_eclipse_s * (t_step_s / T_orb_s):
            p_deficit_W = sc.housekeeping_power_W
            if not any(e.event_type == "eclipse_deficit" and
                       abs(e.time_h - t_h) < 24 for e in result.events):
                result.events.append(PropagationEvent(
                    time_h=t_h,
                    date=current_dt.strftime("%Y-%m-%d"),
                    event_type="eclipse_deficit",
                    description=(f"Battery insufficient for eclipse housekeeping "
                                 f"(Ap={ap:.0f}, ecl={ecl:.2f})"),
                    altitude_km=round(alt_km, 2),
                    ap=ap, f107=f107,
                ))

        # Thruster gets orbital-average power
        p_thruster = max(p_avg_net, 0.0)

        # --- Atmosphere & physics ---
        sc_step = SpacecraftParams(
            mass_kg=sc.mass_kg,
            frontal_area_m2=sc.frontal_area_m2,
            drag_coefficient=sc.drag_coefficient,
            intake_efficiency=sc.intake_efficiency,
            intake_area_m2=sc.intake_area_m2,
            thrust_to_power_mN_per_kW=sc.thrust_to_power_mN_per_kW,
            solar_panel_area_m2=sc.solar_panel_area_m2,
            solar_panel_efficiency=sc.solar_panel_efficiency,
            eclipse_fraction=ecl,          # geometric value, overrides default
            housekeeping_power_W=sc.housekeeping_power_W,
            ionization_efficiency=sc.ionization_efficiency,
            specific_impulse_s=sc.specific_impulse_s,
            battery_capacity_wh=sc.battery_capacity_wh,
        )

        conds = AtmosphericConditions(
            altitude_km=alt_km,
            f107=f107,
            f107_avg=f107,
            ap=ap,
            datetime=current_dt,
            latitude_deg=mission.latitude_deg,
            longitude_deg=mission.longitude_deg,
        )
        atm  = query_atmosphere(conds)
        phys = compute_physics(atm, sc_step)

        # --- Altitude update ---
        a = R_EARTH + alt_km * 1000.0
        n_orb = math.sqrt(GM / a ** 3)
        F_net_N = max(phys.drag_force_mN - phys.effective_thrust_mN, 0.0) / 1000.0
        dh_dt = -2.0 * F_net_N / (sc.mass_kg * n_orb)   # m/s
        delta_h_km = dh_dt * t_step_s / 1000.0

        # --- Record ---
        result.times_h.append(t_h)
        result.dates.append(current_dt.strftime("%Y-%m-%d"))
        result.altitudes_km.append(round(alt_km, 3))
        result.ratios.append(round(phys.thrust_drag_ratio, 3))
        result.f107s.append(round(f107, 1))
        result.aps.append(round(ap, 1))
        result.drag_mN.append(round(phys.drag_force_mN, 4))
        result.thrust_mN.append(round(phys.effective_thrust_mN, 4))
        result.eclipse_fracs.append(round(ecl, 3))
        result.power_deficit_W.append(round(p_deficit_W, 1))
        result.battery_wh.append(round(battery_wh, 2))

        # --- Flag storm events ---
        if ap >= 50 and (ap - prev_ap) > 20:
            sev = ("Minor" if ap < 100 else
                   "Moderate" if ap < 150 else
                   "Strong" if ap < 200 else "Severe/Extreme")
            result.events.append(PropagationEvent(
                time_h=t_h,
                date=current_dt.strftime("%Y-%m-%d"),
                event_type="storm",
                description=(f"{sev} geomagnetic storm  "
                             f"Ap={ap:.0f}  T/D={phys.thrust_drag_ratio:.2f}"),
                altitude_km=round(alt_km, 2),
                ap=ap, f107=f107,
            ))

        prev_ap = ap
        alt_km = max(alt_km + delta_h_km, 0.0)

        # --- Progress ---
        if verbose and i - last_print_step >= 1000:
            rate = (i + 1) / max(t_h, 0.001)
            pct  = 100.0 * i / n_steps
            print(f"  [{pct:4.1f}%] t={t_h/24:.1f} d  alt={alt_km:.1f} km  "
                  f"Ap={ap:.0f}  T/D={phys.thrust_drag_ratio:.2f}", flush=True)
            last_print_step = i

        # --- Deorbit check ---
        if alt_km < DEORBIT_ALT_KM:
            result.deorbit_time_h = t_h
            result.survived = False
            result.events.append(PropagationEvent(
                time_h=t_h,
                date=current_dt.strftime("%Y-%m-%d"),
                event_type="deorbit",
                description=f"Orbit decayed below {DEORBIT_ALT_KM:.0f} km",
                altitude_km=round(alt_km, 2),
                ap=ap, f107=f107,
            ))
            break

    result.final_altitude_km = round(alt_km, 2)
    return result
