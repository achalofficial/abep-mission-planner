"""
main.py — ABEP Mission Planner CLI entry point.

Usage examples:
  python main.py                               # full sweep at default 200 km
  python main.py --altitude 220                # different target altitude
  python main.py --altitude 200 --days 730     # 2-year mission sweep
  python main.py --quick                       # skip refinement
  python main.py --no-claude                   # skip Claude API call

  # Timeline mode — propagate through real/predicted solar conditions:
  python main.py --timeline --timeline-start 2027-01-01 --timeline-days 1825
  python main.py --timeline --altitude 205 --timeline-start 2025-06-01
  python main.py --timeline --timeline-use-model   # pure SC25 model, no network
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv()  # loads .env from the project root into os.environ


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="abep-planner",
        description="ABEP Mission Planner — maps failure boundaries for VLEO satellites.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Mission parameters
    p.add_argument("--altitude",  type=float, default=200.0,
                   help="Target orbit altitude (km). Range: 150–250.")
    p.add_argument("--days",      type=float, default=365.0,
                   help="Mission duration (days).")
    p.add_argument("--lat",       type=float, default=0.0,
                   help="Mission latitude for local analysis (deg). 0=equatorial.")
    p.add_argument("--output",    type=str,   default="outputs",
                   help="Output directory for reports and plots.")

    # Spacecraft parameters
    p.add_argument("--mass",      type=float, default=None,
                   help="Spacecraft mass (kg). Default: 200.")
    p.add_argument("--frontal",   type=float, default=None,
                   help="Frontal area facing ram direction (m²). Default: 1.2.")
    p.add_argument("--intake",    type=float, default=None,
                   help="Intake collection area (m²). Default: 1.0.")
    p.add_argument("--eta-intake",type=float, default=None,
                   help="Intake efficiency (0–1). Default: 0.40.")
    p.add_argument("--isp",       type=float, default=None,
                   help="Thruster specific impulse (s). Default: 5000.")
    p.add_argument("--tp-ratio",  type=float, default=None,
                   help="Thrust-to-power ratio (mN/kW). Default: 25.")
    p.add_argument("--panels",    type=float, default=None,
                   help="Solar panel area (m²). Default: 4.0.")
    p.add_argument("--panel-eff", type=float, default=None,
                   help="Solar panel efficiency (0–1). Default: 0.30.")

    # Sweep run control
    p.add_argument("--quick",      action="store_true",
                   help="Skip grid refinement (Phase 3). Faster but less precise.")
    p.add_argument("--no-claude",  action="store_true",
                   help="Skip Claude API escalation (Phase 4).")
    p.add_argument("--no-report",  action="store_true",
                   help="Skip report and plot generation.")

    # Timeline mode
    p.add_argument("--timeline",   action="store_true",
                   help="Run historical timeline mode instead of parameter sweep.")
    p.add_argument("--timeline-start", type=str, default="2027-01-01",
                   help="Start date for timeline simulation (YYYY-MM-DD).")
    p.add_argument("--timeline-days",  type=int, default=1825,
                   help="Number of days to propagate in timeline mode (default 5 yr).")
    p.add_argument("--timeline-dt",    type=float, default=1.0,
                   help="Time step in hours for orbit propagation (default 1 h).")
    p.add_argument("--timeline-use-model", action="store_true",
                   help="Force SC25 sinusoidal model; skip NOAA network fetch.")

    return p


def apply_overrides(sc, args) -> None:
    """Apply any command-line spacecraft parameter overrides."""
    overrides = {
        "mass_kg":                args.mass,
        "frontal_area_m2":        args.frontal,
        "intake_area_m2":         args.intake,
        "intake_efficiency":      args.eta_intake,
        "specific_impulse_s":     args.isp,
        "thrust_to_power_mN_per_kW": args.tp_ratio,
        "solar_panel_area_m2":    args.panels,
        "solar_panel_efficiency": args.panel_eff,
    }
    for attr, val in overrides.items():
        if val is not None:
            setattr(sc, attr, val)


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Validate altitude
    if not (150 <= args.altitude <= 250):
        print(f"[ERROR] Altitude must be between 150 and 250 km. Got: {args.altitude}")
        sys.exit(1)

    # Check API key early if Claude is requested
    if not args.no_claude and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[WARN] ANTHROPIC_API_KEY not set. Claude API escalation will be skipped.")
        print("       Set the variable or pass --no-claude to suppress this warning.")
        args.no_claude = True

    from src.models import MissionParams, SpacecraftParams

    mission = MissionParams(
        target_altitude_km=args.altitude,
        mission_duration_days=args.days,
        latitude_deg=args.lat,
    )

    sc = SpacecraftParams()
    apply_overrides(sc, args)

    print(f"\nABEP Mission Planner")
    print(f"  Target altitude:   {mission.target_altitude_km:.0f} km")
    print(f"  Isp:               {sc.specific_impulse_s:.0f} s")
    print(f"  Intake area:       {sc.intake_area_m2:.2f} m²")
    print(f"  Solar panels:      {sc.solar_panel_area_m2:.1f} m² @ {sc.solar_panel_efficiency:.0%}")
    print(f"  Battery:           {sc.battery_capacity_wh:.0f} Wh")
    print(f"  Output dir:        {args.output}")

    # ------------------------------------------------------------------
    # TIMELINE MODE
    # ------------------------------------------------------------------
    if args.timeline:
        from src.historical_timeline import run_timeline
        result = run_timeline(
            mission=mission,
            sc=sc,
            start_date_str=args.timeline_start,
            days=args.timeline_days,
            dt_hours=args.timeline_dt,
            use_model=args.timeline_use_model,
            output_dir=args.output,
        )
        tl = result["timeline_json"]
        meta = tl["meta"]
        print(f"\n{'='*60}")
        print(f"TIMELINE VERDICT")
        print(f"{'='*60}")
        survived = meta["survived"]
        print(f"  Survived mission: {'YES' if survived else 'NO — DEORBIT'}")
        print(f"  Final altitude:   {meta['final_altitude_km']:.1f} km")
        print(f"  Storm events:     {meta['n_storm_events']}")
        if not survived and meta.get("deorbit_time_h"):
            print(f"  Deorbit at:       day {meta['deorbit_time_h']/24:.1f}")
        print(f"\n  Timeline JSON:    {result['output_path']}")
        print(f"  -> Load in dashboard Timeline tab to visualise\n")
        return

    # ------------------------------------------------------------------
    # SWEEP MODE (default)
    # ------------------------------------------------------------------
    print(f"  Mission duration:  {mission.mission_duration_days:.0f} days")
    print(f"  Grid refinement:   {'OFF (--quick)' if args.quick else 'ON'}")
    print(f"  Claude API:        {'OFF' if args.no_claude else 'ON'}")

    from src.agent import run_agent
    state = run_agent(
        mission=mission,
        sc=sc,
        skip_refinement=args.quick,
        skip_claude=args.no_claude,
    )

    if not args.no_report:
        from src.report import generate_report
        print("\n" + "=" * 60)
        print("GENERATING REPORT")
        print("=" * 60)
        report_path = generate_report(mission, sc, state, args.output)
        print(f"\n  Mission report: {report_path}")

    analysis = state.get("analysis", {})
    s = analysis.get("summary", {})
    failure_rate = s.get("failure_rate", 0.0)
    bz = state.get("boundary_zone", {})

    print("\n" + "=" * 60)
    print("MISSION VERDICT")
    print("=" * 60)

    from src.report import _viability_verdict
    verdict = _viability_verdict(failure_rate)
    print(f"  Verdict:           {verdict}")
    print(f"  Failure rate:      {failure_rate:.1%} of modeled conditions")
    if bz.get("alt_critical"):
        print(f"  Critical altitude: {bz['alt_critical']:.0f} km (50% failure rate)")
    if bz.get("alt_min") and bz.get("alt_max"):
        print(f"  Boundary zone:     {bz['alt_min']:.0f}–{bz['alt_max']:.0f} km")
    print(f"  Total model calls: {state.get('sweep_count', 0):,}")
    print()


if __name__ == "__main__":
    main()
