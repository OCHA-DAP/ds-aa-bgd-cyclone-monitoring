"""Union-level wind estimates and trigger windows from ECMWF tracks.

For each track (HRES, or one ensemble member) the forecast landfall is found,
and the framework's wind reduction factor is applied to the landfall wind to
estimate the wind at every union in the six target districts. This is the
same calculation app.R performs on a landfall point entered by hand.
"""

from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from src.constants import (
    ACTION_MAX_LEAD_H,
    ADM_GPKG,
    ADM_LAYER,
    COUNTRIES_GEOJSON,
    LAND_GEOJSON,
    PROJECTED_CRS,
    READINESS_MAX_LEAD_H,
    READINESS_MIN_LEAD_H,
    RELEVANCE_BUFFER_KM,
    RELEVANCE_MAX_LEAD_H,
    TARGET_DISTRICTS,
    THRESHOLD_KMH,
    WIND_REDUCTION_A,
    WIND_REDUCTION_B,
)

LANDFALL_TOLERANCE_M = 10_000
COUNTRY_TOLERANCE_M = 25_000


@lru_cache(maxsize=1)
def load_unions() -> gpd.GeoDataFrame:
    """Unions (ADM4) of the six target districts, in EPSG:4326."""
    unions = gpd.read_file(ADM_GPKG, layer=ADM_LAYER)
    unions = unions[unions["ADM2_EN"].isin(TARGET_DISTRICTS)]
    cols = [
        "ADM1_EN", "ADM2_EN", "ADM2_PCODE", "ADM3_EN", "ADM3_PCODE",
        "ADM4_EN", "ADM4_PCODE", "geometry",
    ]
    return unions[cols].to_crs(4326).reset_index(drop=True)


@lru_cache(maxsize=1)
def _union_boundaries_m() -> gpd.GeoSeries:
    return load_unions().to_crs(PROJECTED_CRS).boundary


@lru_cache(maxsize=1)
def _land():
    return gpd.read_file(LAND_GEOJSON).to_crs(4326).union_all()


@lru_cache(maxsize=1)
def _target_area_m():
    # Simplified to 1 km: only used for the 500 km relevance check, where the
    # full union outlines make the distance calculation slow.
    area = load_unions().to_crs(PROJECTED_CRS).union_all()
    return area.buffer(0).simplify(1000)


@lru_cache(maxsize=1)
def _countries_m() -> gpd.GeoDataFrame:
    return gpd.read_file(COUNTRIES_GEOJSON).to_crs(PROJECTED_CRS)


def landfall_country(point_m) -> str:
    """Country of a landfall point, or the nearest within 25 km.

    The coastline used to detect landfall and the country outlines are both
    Natural Earth, but simplified differently, so a point on the coast can
    fall just outside every country.
    """
    countries = _countries_m()
    dist = countries.distance(point_m)
    nearest = dist.idxmin()
    if dist[nearest] <= COUNTRY_TOLERANCE_M:
        return countries.loc[nearest, "NAME"]
    return "Other"


@lru_cache(maxsize=1)
def _target_districts_m():
    """Outline of the six target districts, in metres."""
    return load_unions().to_crs(PROJECTED_CRS).union_all().buffer(0)


def is_relevant(df_tracks: pd.DataFrame) -> pd.Series:
    """Per storm: does any track come within the relevance buffer?"""
    df = df_tracks[df_tracks["lead_h"] <= RELEVANCE_MAX_LEAD_H]
    if df.empty:
        return pd.Series(dtype=bool)
    pts = gpd.GeoSeries(
        gpd.points_from_xy(df["lon"], df["lat"]), crs=4326
    ).to_crs(PROJECTED_CRS)
    dist_km = pts.distance(_target_area_m()).to_numpy() / 1000
    near = pd.Series(dist_km <= RELEVANCE_BUFFER_KM, index=df.index)
    return near.groupby(df["storm_id"]).any()


def find_landfalls(track: pd.DataFrame) -> list:
    """Every crossing from sea to land along a track.

    Position, time and wind are interpolated linearly to the coastline
    crossing. A track can cross land more than once (Sri Lanka or the Indian
    coast before Bangladesh), so all crossings are returned and the caller
    picks the one that matters for the target unions. A track that already
    starts over land contributes its first point.
    """
    track = track.sort_values("lead_h")
    land = _land()
    rows = track.to_dict("records")
    if not rows:
        return []
    on_land = [land.contains(Point(r["lon"], r["lat"])) for r in rows]
    landfalls = []
    if on_land[0]:
        landfalls.append({**_landfall_from(rows[0]), "started_over_land": True})
    for i in range(1, len(rows)):
        if on_land[i] and not on_land[i - 1]:
            landfalls.append(_crossing(rows[i - 1], rows[i], land))
    for lf in landfalls:
        point = (
            gpd.GeoSeries(
                [Point(lf["landfall_lon"], lf["landfall_lat"])], crs=4326
            )
            .to_crs(PROJECTED_CRS)
            .iloc[0]
        )
        # The Natural Earth coastline and the BBS union outlines differ by a
        # few km, so a landfall within 10 km of a target district counts.
        lf["landfall_in_target_district"] = (
            _target_districts_m().distance(point) <= LANDFALL_TOLERANCE_M
        )
        lf["landfall_country"] = landfall_country(point)
    return landfalls


def _crossing(a: dict, b: dict, land) -> dict:
    """Interpolate the coastline crossing between a sea and a land point."""
    segment = LineString([(a["lon"], a["lat"]), (b["lon"], b["lat"])])
    crossing = segment.intersection(land.boundary)
    if crossing.is_empty:
        frac = 1.0
    else:
        first = min(
            getattr(crossing, "geoms", [crossing]),
            key=lambda g: segment.project(g),
        )
        frac = segment.project(first) / segment.length
    wind_a = a["wind_kmh"] if pd.notna(a["wind_kmh"]) else b["wind_kmh"]
    wind_b = b["wind_kmh"] if pd.notna(b["wind_kmh"]) else wind_a
    lead = a["lead_h"] + frac * (b["lead_h"] - a["lead_h"])
    return {
        "landfall_lon": a["lon"] + frac * (b["lon"] - a["lon"]),
        "landfall_lat": a["lat"] + frac * (b["lat"] - a["lat"]),
        "landfall_lead_h": lead,
        "landfall_time": a["issue_time"] + pd.Timedelta(hours=lead),
        "landfall_wind_kmh": wind_a + frac * (wind_b - wind_a),
        "started_over_land": False,
    }


def _landfall_from(row: dict) -> dict:
    return {
        "landfall_lon": row["lon"],
        "landfall_lat": row["lat"],
        "landfall_lead_h": row["lead_h"],
        "landfall_time": row["valid_time"],
        "landfall_wind_kmh": row["wind_kmh"],
    }


def union_winds(landfall: dict) -> pd.DataFrame:
    """Estimated wind at every target union for one landfall."""
    unions = load_unions()
    point = (
        gpd.GeoSeries(
            [Point(landfall["landfall_lon"], landfall["landfall_lat"])],
            crs=4326,
        )
        .to_crs(PROJECTED_CRS)
        .iloc[0]
    )
    dist_km = _union_boundaries_m().distance(point).to_numpy() / 1000
    factor = WIND_REDUCTION_A * np.exp(-WIND_REDUCTION_B * dist_km)
    df = unions.drop(columns="geometry").copy()
    df["distance_km"] = dist_km
    df["reduction_factor"] = factor
    df["wind_kmh"] = factor * landfall["landfall_wind_kmh"]
    df["above_threshold"] = df["wind_kmh"] >= THRESHOLD_KMH
    return df


def trigger_window(lead_h: float):
    """Which framework window a landfall lead time falls in."""
    if lead_h is None or pd.isna(lead_h):
        return None
    if lead_h <= ACTION_MAX_LEAD_H:
        return "action"
    if READINESS_MIN_LEAD_H < lead_h <= READINESS_MAX_LEAD_H:
        return "readiness"
    return "beyond 5 days"


def assess_storm(df_storm: pd.DataFrame) -> tuple:
    """Assess every track of one storm.

    Returns ``(df_tracks, df_unions)``: one row per track with its landfall
    and union summary, and the per-union winds for every track that makes
    landfall.
    """
    track_rows = []
    union_frames = []
    for (model, member), track in df_storm.groupby(["model", "member"]):
        # Of all the landfalls on a track, the one that matters is the one
        # giving the highest wind at the target unions.
        landfall, df_u = None, None
        for lf in find_landfalls(track):
            df_lf = union_winds(lf)
            if df_u is None or df_lf["wind_kmh"].max() > df_u["wind_kmh"].max():
                landfall, df_u = lf, df_lf
        row = {
            "model": model,
            "member": member,
            "max_wind_kmh": track["wind_kmh"].max(),
            "makes_landfall": landfall is not None,
        }
        if landfall is not None:
            above = df_u[df_u["above_threshold"]]
            row.update(landfall)
            row.update(
                {
                    "window": trigger_window(landfall["landfall_lead_h"]),
                    "max_union_wind_kmh": df_u["wind_kmh"].max(),
                    "n_unions_above": len(above),
                    "districts_above": sorted(above["ADM2_EN"].unique()),
                    "meets_threshold": len(above) > 0,
                }
            )
            df_u.insert(0, "member", member)
            df_u.insert(0, "model", model)
            union_frames.append(df_u)
        else:
            row.update(
                {
                    "window": None,
                    "max_union_wind_kmh": 0.0,
                    "n_unions_above": 0,
                    "districts_above": [],
                    "meets_threshold": False,
                }
            )
        track_rows.append(row)
    df_tracks = pd.DataFrame(track_rows)
    df_unions = (
        pd.concat(union_frames, ignore_index=True)
        if union_frames
        else pd.DataFrame()
    )
    return df_tracks, df_unions


def summarise_storm(df_tracks: pd.DataFrame) -> dict:
    """Headline figures for one storm: HRES and the ensemble share."""
    hres = df_tracks[df_tracks["model"] == "hres"]
    ens = df_tracks[df_tracks["model"] == "ens"]
    summary = {
        "hres": hres.iloc[0].to_dict() if not hres.empty else None,
        "n_members": len(ens),
    }
    for window in ("readiness", "action"):
        hits = ens[ens["meets_threshold"] & (ens["window"] == window)]
        summary[f"n_members_{window}"] = len(hits)
    summary["n_members_any"] = int(ens["meets_threshold"].sum())
    in_target = ens.get("landfall_in_target_district")
    summary["n_members_landfall_target"] = (
        int((in_target == True).sum()) if in_target is not None else 0  # noqa: E712
    )
    district_counts = {}
    for districts in ens.loc[ens["meets_threshold"], "districts_above"]:
        for d in districts:
            district_counts[d] = district_counts.get(d, 0) + 1
    summary["members_by_district"] = district_counts
    countries = (
        ens["landfall_country"].fillna("No landfall")
        if "landfall_country" in ens
        else pd.Series("No landfall", index=ens.index)
    )
    summary["members_by_country"] = countries.value_counts().to_dict()
    return summary
