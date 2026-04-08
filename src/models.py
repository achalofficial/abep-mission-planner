"""
models.py — Dataclasses for all parameters and results in the ABEP Mission Planner.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Input Parameter Models
# ---------------------------------------------------------------------------

@dataclass
class SpacecraftParams:
    """Physical and propulsion parameters of the spacecraft."""
    mass_kg: float = 200.0
    frontal_area_m2: float = 1.2          # Cross-sectional area facing ram direction
    drag_coefficient: float = 2.2         # Cd in free molecular flow
    intake_efficiency: float = 0.40       # Fraction of incoming particles captured
    intake_area_m2: float = 1.0           # Effective intake collection area
    thrust_to_power_mN_per_kW: float = 25.0  # Thruster performance
    solar_panel_area_m2: float = 4.0      # Total solar panel area
    solar_panel_efficiency: float = 0.30  # Solar panel conversion efficiency
    eclipse_fraction: float = 0.35        # Fraction of orbit in Earth's shadow
    housekeeping_power_W: float = 50.0    # Power for avionics/comms/payload
    ionization_efficiency: float = 0.70   # Fraction of collected gas successfully ionized
    specific_impulse_s: float = 5000.0    # Isp of thruster (RF ion, 3000–6000 s range)
    battery_capacity_wh: float = 500.0   # Onboard battery capacity (Wh)


@dataclass
class MissionParams:
    """Mission-level parameters."""
    target_altitude_km: float = 200.0
    mission_duration_days: float = 365.0
    orbit_inclination_deg: float = 0.0    # 0 = equatorial
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0
    start_datetime: datetime = field(default_factory=lambda: datetime(2025, 1, 1))


@dataclass
class AtmosphericConditions:
    """Solar and geomagnetic input conditions for a single model query."""
    altitude_km: float
    f107: float          # Daily solar flux (SFU)
    f107_avg: float      # 81-day centered average
    ap: float            # Geomagnetic index
    datetime: datetime = field(default_factory=lambda: datetime(2025, 6, 21))
    latitude_deg: float = 0.0
    longitude_deg: float = 0.0


# ---------------------------------------------------------------------------
# Output Result Models
# ---------------------------------------------------------------------------

@dataclass
class AtmosphericResult:
    """Output from the NRLMSISE-00 atmospheric model for a single query point."""
    altitude_km: float
    f107: float
    ap: float
    datetime: datetime
    latitude_deg: float
    longitude_deg: float

    # Key outputs
    total_density_kg_m3: float = 0.0       # Total mass density (critical for drag)
    exospheric_temp_K: float = 0.0         # Exospheric temperature

    # Number densities (particles/m³)
    n_O: float = 0.0    # Atomic oxygen
    n_N2: float = 0.0   # Molecular nitrogen
    n_O2: float = 0.0   # Molecular oxygen
    n_He: float = 0.0   # Helium
    n_Ar: float = 0.0   # Argon
    n_H: float = 0.0    # Hydrogen

    # Derived composition metrics
    @property
    def o_fraction(self) -> float:
        """Atomic oxygen fraction by mass density (approximate)."""
        total_n = self.n_O + self.n_N2 * 2 + self.n_O2 * 2 + self.n_He + self.n_Ar
        if total_n == 0:
            return 0.0
        return self.n_O / total_n

    @property
    def n2_fraction(self) -> float:
        """Molecular nitrogen fraction by particle count."""
        total_n = self.n_O + self.n_N2 + self.n_O2 + self.n_He + self.n_Ar
        if total_n == 0:
            return 0.0
        return self.n_N2 / total_n

    @property
    def o_n2_ratio(self) -> float:
        """O/N2 ratio — composition metric affecting ionization efficiency."""
        if self.n_N2 == 0:
            return float('inf')
        return self.n_O / self.n_N2


@dataclass
class PhysicsResult:
    """Output from the thrust-drag balance computation for a single data point."""
    altitude_km: float
    f107: float
    ap: float
    month: int
    latitude_deg: float

    # Atmospheric inputs (mirrored for convenience)
    total_density_kg_m3: float = 0.0
    o_fraction: float = 0.0
    n2_fraction: float = 0.0
    temperature_K: float = 0.0

    # Physics outputs (in millinewtons for readability)
    orbital_velocity_m_s: float = 0.0
    drag_force_mN: float = 0.0
    thrust_max_mN: float = 0.0             # Power-limited maximum thrust
    thrust_propellant_mN: float = 0.0      # Propellant-limited thrust
    effective_thrust_mN: float = 0.0       # min(power-limited, propellant-limited)
    thrust_drag_ratio: float = 0.0

    # Power budget
    power_solar_W: float = 0.0
    power_available_W: float = 0.0
    power_required_W: float = 0.0
    power_deficit_W: float = 0.0           # > 0 means system cannot cope

    # Mass flow
    mdot_collected_kg_s: float = 0.0

    # Classification
    status: str = "UNKNOWN"                # SAFE / ADEQUATE / MARGINAL / FAILURE

    # Degradation (only computed for marginal/failure cases)
    altitude_loss_rate_km_per_day: Optional[float] = None

    def classify(self) -> str:
        """Classify the thrust-drag ratio into a status category."""
        r = self.thrust_drag_ratio
        if r > 1.5:
            return "SAFE"
        elif r >= 1.2:
            return "ADEQUATE"
        elif r >= 1.0:
            return "MARGINAL"
        else:
            return "FAILURE"
