"""
atmosphere.py — NRLMSISE-00 atmospheric model wrapper.

Queries the NRLMSISE-00 model for density and composition at any
altitude, time, location, and solar/geomagnetic condition.
"""

from datetime import datetime

from .models import AtmosphericConditions, AtmosphericResult

# flags[0] = 1  =>  output in SI (m⁻³ and kg/m³) instead of CGS (cm⁻³ and g/cm³)
_SI_FLAGS = [1] + [1] * 23   # 24 flags total; flag 0 enables SI output


def query_atmosphere(conditions: AtmosphericConditions) -> AtmosphericResult:
    """
    Call NRLMSISE-00 for a single set of atmospheric conditions.

    Parameters
    ----------
    conditions : AtmosphericConditions
        Altitude, solar indices, geomagnetic index, datetime, and location.

    Returns
    -------
    AtmosphericResult
        Total density, species number densities, and exospheric temperature.
    """
    from nrlmsise00._nrlmsise00 import gtd7

    dt = conditions.datetime
    doy = dt.timetuple().tm_yday
    sec = dt.hour * 3600.0 + dt.minute * 60.0 + dt.second

    # Local solar time (approximate: UT + longitude/15)
    lst = (dt.hour + dt.minute / 60.0 + dt.second / 3600.0 +
           conditions.longitude_deg / 15.0) % 24.0

    densities, temperatures = gtd7(
        year=dt.year,
        doy=doy,
        sec=sec,
        alt=conditions.altitude_km,
        g_lat=conditions.latitude_deg,
        g_long=conditions.longitude_deg,
        lst=lst,
        f107A=conditions.f107_avg,
        f107=conditions.f107,
        ap=conditions.ap,
        flags=_SI_FLAGS,
    )

    # With flags[0]=1 the library returns:
    #   densities[0] He (m⁻³), [1] O (m⁻³), [2] N₂ (m⁻³), [3] O₂ (m⁻³),
    #   [4] Ar (m⁻³), [5] total mass density (kg/m³), [6] H (m⁻³), [7] N (m⁻³)
    #   temperatures[0] exospheric T (K), [1] local T (K)

    return AtmosphericResult(
        altitude_km=conditions.altitude_km,
        f107=conditions.f107,
        ap=conditions.ap,
        datetime=conditions.datetime,
        latitude_deg=conditions.latitude_deg,
        longitude_deg=conditions.longitude_deg,
        total_density_kg_m3=densities[5],
        exospheric_temp_K=temperatures[0],
        n_He=densities[0],
        n_O=densities[1],
        n_N2=densities[2],
        n_O2=densities[3],
        n_Ar=densities[4],
        n_H=densities[6],
    )


def query_atmosphere_dict(params: dict) -> dict:
    """
    Convenience wrapper accepting and returning plain dictionaries.

    Expected keys in params:
        altitude_km, f107, f107_avg, ap, datetime (or year/month/day),
        latitude_deg (optional, default 0), longitude_deg (optional, default 0)
    """
    dt = params.get("datetime")
    if dt is None:
        dt = datetime(
            params.get("year", 2025),
            params.get("month", 6),
            params.get("day", 21),
            params.get("hour", 12),
        )

    cond = AtmosphericConditions(
        altitude_km=params["altitude_km"],
        f107=params["f107"],
        f107_avg=params.get("f107_avg", params["f107"]),
        ap=params["ap"],
        datetime=dt,
        latitude_deg=params.get("latitude_deg", 0.0),
        longitude_deg=params.get("longitude_deg", 0.0),
    )
    result = query_atmosphere(cond)

    return {
        "altitude_km": result.altitude_km,
        "f107": result.f107,
        "ap": result.ap,
        "datetime": result.datetime,
        "latitude_deg": result.latitude_deg,
        "total_density_kg_m3": result.total_density_kg_m3,
        "exospheric_temp_K": result.exospheric_temp_K,
        "n_O": result.n_O,
        "n_N2": result.n_N2,
        "n_O2": result.n_O2,
        "n_He": result.n_He,
        "n_Ar": result.n_Ar,
        "n_H": result.n_H,
        "o_fraction": result.o_fraction,
        "n2_fraction": result.n2_fraction,
        "o_n2_ratio": result.o_n2_ratio,
    }
