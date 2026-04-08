"""
historical_timeline.py -- Solar / geomagnetic data loader and timeline runner.

Data strategy:
  1. Try NOAA SWPC JSON (monthly F10.7, back to 1967) for historical anchor points.
  2. Always fall back to the Solar Cycle 25 sinusoidal model for any gaps and
     for future dates (SC25 peak ≈ late 2025, F10.7_max ≈ 205 SFU).
  3. Daily F10.7 adds 27-day solar-rotation variability on top of monthly means.
  4. Ap is always model-generated from F10.7 with Poisson storm injection
     (daily NOAA Ap requires a separate large-file download).

Usage
-----
    from src.historical_timeline import run_timeline
    result = run_timeline(mission, sc, "2027-01-01", days=1825)
"""

import json
import math
import random
import datetime
import os
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Solar Cycle 25 model parameters  (anchor: minimum Dec 2019, T ≈ 11 yr)
# ---------------------------------------------------------------------------
_SC25_MIN  = datetime.date(2019, 12, 1)
_SC25_T    = 365.25 * 11.0        # days
_F107_MIN  = 68.0                  # observed 2019 minimum
_F107_MAX  = 205.0                 # SC25 ran hotter than predicted


def _sc25_f107_monthly(date: datetime.date) -> float:
    """Smooth sinusoidal SC25 monthly mean F10.7."""
    days = (date - _SC25_MIN).days
    phase = 2.0 * math.pi * days / _SC25_T
    f = _F107_MIN + (_F107_MAX - _F107_MIN) * 0.5 * (1.0 - math.cos(phase))
    return round(max(_F107_MIN, min(_F107_MAX, f)), 1)


def _daily_f107(monthly: float, day_index: int, rng: random.Random) -> float:
    """Add 27-day solar-rotation modulation and ±4% noise to a monthly mean."""
    mod = 1.0 + 0.10 * math.sin(2.0 * math.pi * day_index / 27.0)
    noise = rng.gauss(0.0, 0.04)
    val = monthly * (mod + noise)
    return round(max(65.0, min(260.0, val)), 1)


def _sample_ap(f107: float, rng: random.Random) -> float:
    """
    Statistical Ap based on solar activity.

    Quiet background Ap scales with F10.7; storms injected stochastically with
    probability rising from ~1.5 % day⁻¹ at solar min to ~18 % day⁻¹ at max.
    """
    ap_bg = 3.0 + 0.04 * max(f107 - 70.0, 0.0)   # 3 at F70, ~9 at F220

    # Storm probability (clamp base to avoid complex result when f107 < 70)
    p_storm = 0.015 + 0.165 * (max(f107 - 70.0, 0.0) / 155.0) ** 1.5

    if rng.random() < p_storm:
        # Storm intensity weighted toward minor events
        choices  = [30,  50,  80, 100, 150, 200, 300]
        weights  = [30,  25,  20,  12,   8,   4,   1]
        ap = rng.choices(choices, weights=weights)[0]
    else:
        ap = int(ap_bg * rng.lognormvariate(0.0, 0.35))
        ap = max(2, min(ap, 22))

    return float(ap)


# ---------------------------------------------------------------------------
# NOAA SWPC fetch
# ---------------------------------------------------------------------------

def _fetch_noaa_monthly_f107() -> Optional[dict]:
    """
    Download observed solar cycle indices from NOAA SWPC.
    Returns {YYYY-MM: f107} or None on any failure.
    """
    try:
        import urllib.request
        url = ("https://services.swpc.noaa.gov/json/solar-cycle/"
               "observed-solar-cycle-indices.json")
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = {}
        for row in data:
            tag  = row.get("time-tag", "")
            f107 = row.get("f10.7") or row.get("f107")
            if tag and f107 and float(f107) > 0:
                result[tag] = float(f107)
        return result or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public: generate daily solar data
# ---------------------------------------------------------------------------

def load_solar_data(
    start_date: datetime.date,
    days: int,
    use_model: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Return a DataFrame [date, f107, ap] for every day in the window.

    Parameters
    ----------
    start_date : datetime.date
    days       : int
    use_model  : bool  Force pure SC25 model (no network call). Reproducible.
    seed       : int   RNG seed for storm injection.
    """
    rng = random.Random(seed)

    noaa = None if use_model else _fetch_noaa_monthly_f107()
    if noaa:
        print(f"  [solar data] NOAA monthly F10.7 loaded ({len(noaa)} months)")
    else:
        print(f"  [solar data] Using SC25 model (NOAA fetch {'skipped' if use_model else 'failed'})")

    records = []
    for i in range(days):
        d = start_date + datetime.timedelta(days=i)
        ym = d.strftime("%Y-%m")

        # Monthly F10.7 base
        f107_base = (noaa[ym] if (noaa and ym in noaa)
                     else _sc25_f107_monthly(d))

        f107_daily = _daily_f107(f107_base, i, rng)
        ap = _sample_ap(f107_daily, rng)
        records.append({"date": d, "f107": f107_daily, "ap": ap})

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Public: run full timeline simulation
# ---------------------------------------------------------------------------

def run_timeline(
    mission,
    sc,
    start_date_str: str,
    days: int,
    dt_hours: float = 1.0,
    use_model: bool = False,
    output_dir: str = "outputs",
    seed: int = 42,
) -> dict:
    """
    Load solar data and propagate the orbit through the timeline.

    Returns
    -------
    dict with keys:
        "propagation"   - PropagationResult
        "solar_data"    - pd.DataFrame
        "output_path"   - path to timeline_data.json
        "timeline_json" - the dict that was written to JSON
    """
    from .orbit_propagator import propagate_orbit
    from .models import MissionParams

    start_date = datetime.date.fromisoformat(start_date_str)

    print(f"\n{'='*60}")
    print(f"TIMELINE MODE  {start_date_str} + {days} days  "
          f"(dt={dt_hours} h -> {days*24//dt_hours:.0f} steps)")
    print(f"{'='*60}")

    print(f"\n[1/3] Loading solar data …")
    solar_df = load_solar_data(start_date, days, use_model=use_model, seed=seed)

    f107_mean = solar_df["f107"].mean()
    ap_mean   = solar_df["ap"].mean()
    n_storms  = int((solar_df["ap"] >= 50).sum())
    print(f"       F10.7 mean={f107_mean:.1f}  Ap mean={ap_mean:.1f}  "
          f"Storm days (Ap>=50): {n_storms}")

    # Build mission with correct start datetime
    mission_tl = MissionParams(
        target_altitude_km=mission.target_altitude_km,
        mission_duration_days=float(days),
        orbit_inclination_deg=getattr(mission, "orbit_inclination_deg", 0.0),
        latitude_deg=mission.latitude_deg,
        longitude_deg=mission.longitude_deg,
        start_datetime=datetime.datetime(start_date.year, start_date.month, start_date.day),
    )

    print(f"\n[2/3] Propagating orbit …")
    prop = propagate_orbit(mission_tl, sc, solar_df, dt_hours=dt_hours, verbose=True)

    n_storm_ev  = sum(1 for e in prop.events if e.event_type == "storm")
    n_power_ev  = sum(1 for e in prop.events if e.event_type == "eclipse_deficit")

    print(f"\n  Survived:         {prop.survived}")
    print(f"  Final altitude:   {prop.final_altitude_km:.1f} km")
    print(f"  Storm events:     {n_storm_ev}")
    print(f"  Power deficits:   {n_power_ev}")
    if not prop.survived:
        print(f"  Deorbit at:       day {prop.deorbit_time_h/24:.1f} "
              f"(hour {prop.deorbit_time_h:.0f})")

    # ------------------------------------------------------------------
    # Export JSON (daily-sampled for reasonable file size)
    # ------------------------------------------------------------------
    print(f"\n[3/3] Exporting timeline JSON …")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "timeline_data.json")

    pts = max(1, int(24 / dt_hours))   # points per day
    s = slice(None, None, pts)

    events_export = [{
        "time_h":     e.time_h,
        "date":       e.date,
        "type":       e.event_type,
        "description": e.description,
        "altitude_km": e.altitude_km,
        "ap":         e.ap,
        "f107":       e.f107,
    } for e in prop.events]

    tl_json = {
        "meta": {
            "start_date":         start_date_str,
            "days":               days,
            "target_altitude_km": mission.target_altitude_km,
            "survived":           prop.survived,
            "final_altitude_km":  prop.final_altitude_km,
            "deorbit_time_h":     prop.deorbit_time_h,
            "n_storm_events":     n_storm_ev,
            "n_power_deficits":   n_power_ev,
            "f107_mean":          round(f107_mean, 1),
            "ap_mean":            round(ap_mean, 1),
        },
        "timeline": {
            "times_h":       prop.times_h[s],
            "dates":         prop.dates[s],
            "altitudes_km":  prop.altitudes_km[s],
            "ratios":        prop.ratios[s],
            "f107s":         prop.f107s[s],
            "aps":           prop.aps[s],
        },
        "events": events_export,
    }

    with open(out_path, "w") as fh:
        json.dump(tl_json, fh, indent=2)

    print(f"  Saved -> {out_path}  ({os.path.getsize(out_path)//1024} KB)")

    return {
        "propagation":   prop,
        "solar_data":    solar_df,
        "output_path":   out_path,
        "timeline_json": tl_json,
    }
