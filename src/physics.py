"""
physics.py — Thrust-drag balance computations for the ABEP system.

Takes an AtmosphericResult and SpacecraftParams, returns a PhysicsResult
with full power budget, force balance, and mission status classification.
"""

import math

from .models import AtmosphericResult, PhysicsResult, SpacecraftParams

# Physical constants
GM = 3.986004418e14   # Earth's gravitational parameter (m³/s²)
R_EARTH = 6_371_000   # Mean Earth radius (m)
G0 = 9.80665          # Standard gravity (m/s²)
SOLAR_CONSTANT = 1361 # Solar irradiance at 1 AU (W/m²)


def orbital_period_s(alt_km: float) -> float:
    """Orbital period (seconds) for a circular orbit at alt_km."""
    a = R_EARTH + alt_km * 1000.0
    return 2.0 * math.pi * math.sqrt(a ** 3 / GM)


def eclipse_fraction_geometric(alt_km: float, beta_deg: float = 0.0) -> float:
    """
    Fraction of orbit spent in Earth's shadow for a circular orbit.

    Parameters
    ----------
    alt_km : float  Orbit altitude above Earth's surface.
    beta_deg : float
        Solar beta angle — angle between the orbit plane and the Sun vector (degrees).
        0° = Sun lies in the orbit plane (maximum eclipse).
        ≥ critical angle ≈ arcsin(R_E / (R_E + h)) → orbit never enters shadow.

    Returns
    -------
    float  Eclipse fraction in [0, 1].
    """
    R_km = R_EARTH / 1000.0
    r_km = R_km + alt_km
    cos_beta = math.cos(math.radians(beta_deg))
    if cos_beta < 1e-9:
        return 0.0

    discriminant = 1.0 - (R_km / r_km) ** 2 / cos_beta ** 2
    if discriminant <= 0.0:
        return 0.0

    half_shadow = math.acos(math.sqrt(discriminant))
    return half_shadow / math.pi


def compute_physics(
    atm: AtmosphericResult,
    sc: SpacecraftParams,
) -> PhysicsResult:
    """
    Compute the thrust-drag balance for a single atmospheric data point.

    Parameters
    ----------
    atm : AtmosphericResult
        Output from the NRLMSISE-00 model for this point.
    sc : SpacecraftParams
        Spacecraft and propulsion parameters.

    Returns
    -------
    PhysicsResult
        Full physics balance including forces, power budget, and status.
    """
    alt_m = atm.altitude_km * 1000.0

    # ------------------------------------------------------------------
    # 1. Orbital velocity
    # ------------------------------------------------------------------
    v_orb = math.sqrt(GM / (R_EARTH + alt_m))         # m/s

    # ------------------------------------------------------------------
    # 2. Drag force
    # ------------------------------------------------------------------
    rho = atm.total_density_kg_m3                       # kg/m³
    F_drag_N = 0.5 * rho * v_orb**2 * sc.drag_coefficient * sc.frontal_area_m2
    F_drag_mN = F_drag_N * 1000.0                       # convert to mN

    # ------------------------------------------------------------------
    # 3. Collected propellant mass flow rate
    # ------------------------------------------------------------------
    mdot_kg_s = rho * v_orb * sc.intake_area_m2 * sc.intake_efficiency  # kg/s

    # ------------------------------------------------------------------
    # 4. Available electrical power
    # ------------------------------------------------------------------
    P_solar = (sc.solar_panel_area_m2 * SOLAR_CONSTANT *
               sc.solar_panel_efficiency * (1.0 - sc.eclipse_fraction))   # W
    P_available = P_solar - sc.housekeeping_power_W                        # W

    # ------------------------------------------------------------------
    # 5. Maximum thrust (power-limited)
    #    thrust_to_power is in mN/kW = 1e-3 N / 1e3 W = 1e-6 N/W
    # ------------------------------------------------------------------
    tp_ratio_N_per_W = sc.thrust_to_power_mN_per_kW * 1e-6               # N/W
    F_thrust_power_N = max(P_available, 0.0) * tp_ratio_N_per_W          # N
    F_thrust_power_mN = F_thrust_power_N * 1000.0                        # mN

    # ------------------------------------------------------------------
    # 6. Propellant-limited thrust
    #    v_exhaust = Isp * g0
    #    F = mdot * v_exhaust * eta_ionization
    # ------------------------------------------------------------------
    v_exhaust = sc.specific_impulse_s * G0                                # m/s
    F_thrust_prop_N = mdot_kg_s * v_exhaust * sc.ionization_efficiency   # N
    F_thrust_prop_mN = F_thrust_prop_N * 1000.0                          # mN

    # ------------------------------------------------------------------
    # 7. Effective thrust = min(power-limited, propellant-limited)
    # ------------------------------------------------------------------
    F_eff_mN = min(F_thrust_power_mN, F_thrust_prop_mN)
    F_eff_N = F_eff_mN / 1000.0

    # ------------------------------------------------------------------
    # 8. Thrust-drag ratio
    # ------------------------------------------------------------------
    ratio = F_eff_N / F_drag_N if F_drag_N > 0 else float("inf")

    # ------------------------------------------------------------------
    # 9. Power budget for drag compensation
    # ------------------------------------------------------------------
    P_required = F_drag_N / tp_ratio_N_per_W if tp_ratio_N_per_W > 0 else 0.0
    P_deficit = max(P_required - P_available, 0.0)

    # ------------------------------------------------------------------
    # 10. Build result
    # ------------------------------------------------------------------
    result = PhysicsResult(
        altitude_km=atm.altitude_km,
        f107=atm.f107,
        ap=atm.ap,
        month=atm.datetime.month,
        latitude_deg=atm.latitude_deg,
        total_density_kg_m3=rho,
        o_fraction=atm.o_fraction,
        n2_fraction=atm.n2_fraction,
        temperature_K=atm.exospheric_temp_K,
        orbital_velocity_m_s=v_orb,
        drag_force_mN=F_drag_mN,
        thrust_max_mN=F_thrust_power_mN,
        thrust_propellant_mN=F_thrust_prop_mN,
        effective_thrust_mN=F_eff_mN,
        thrust_drag_ratio=ratio,
        power_solar_W=P_solar,
        power_available_W=P_available,
        power_required_W=P_required,
        power_deficit_W=P_deficit,
        mdot_collected_kg_s=mdot_kg_s,
    )
    result.status = result.classify()

    # ------------------------------------------------------------------
    # 11. Altitude loss rate for marginal/failure cases
    #     Simplified orbital mechanics: energy deficit -> altitude change
    #     dh/dt = -(F_net * v_orb) / (m * n_orb^2 * a)
    #     where n_orb = sqrt(GM/a^3), a = R_earth + h
    #     Simplification: dh/dt ≈ -2*(F_drag - F_thrust) / (m * n_orb)
    # ------------------------------------------------------------------
    if result.status in ("MARGINAL", "FAILURE"):
        a = R_EARTH + alt_m                         # semi-major axis (m)
        n_orb = math.sqrt(GM / a**3)                # mean motion (rad/s)
        F_net_N = F_drag_N - F_eff_N                # net decelerating force (N)
        dh_dt_m_s = -2.0 * F_net_N / (sc.mass_kg * n_orb)  # m/s (altitude loss rate)
        result.altitude_loss_rate_km_per_day = dh_dt_m_s * 86400.0 / 1000.0  # km/day

    return result
