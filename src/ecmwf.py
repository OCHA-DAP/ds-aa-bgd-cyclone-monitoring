"""Fetch and parse ECMWF tropical cyclone track forecasts from open data.

ECMWF publishes IFS cyclone tracks as BUFR (product ``tf``) on its open data
portal, four cycles a day. They are decoded with pybufrkit, which is pure
Python, because ecCodes has no Windows wheel.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from pybufrkit.decoder import Decoder, generate_bufr_message

from src.constants import (
    ECMWF_CYCLES_H,
    ECMWF_OPEN_DATA_URL,
    ECMWF_STREAMS,
    MS_TO_KMH,
)

TRACK_COLUMNS = [
    "issue_time",
    "model",
    "member",
    "storm_id",
    "storm_name",
    "lead_h",
    "valid_time",
    "lat",
    "lon",
    "pressure_hpa",
    "wind_ms",
    "wind_kmh",
]


def _file_url(issue_time: datetime, stream: str) -> str:
    horizon = 360 if issue_time.hour in (0, 12) else 144
    day = issue_time.strftime("%Y%m%d")
    stamp = issue_time.strftime("%Y%m%d%H0000")
    return (
        f"{ECMWF_OPEN_DATA_URL}/{day}/{issue_time:%H}z/ifs/0p25/{stream}/"
        f"{stamp}-{horizon}h-{stream}-tf.bufr"
    )


def recent_cycles(now: datetime = None, n: int = 8) -> list:
    """The ``n`` most recent ECMWF cycle times, newest first."""
    now = now or datetime.now(timezone.utc)
    cycle = now.replace(minute=0, second=0, microsecond=0)
    while cycle.hour not in ECMWF_CYCLES_H:
        cycle -= timedelta(hours=1)
    return [cycle - timedelta(hours=6 * i) for i in range(n)]


def fetch_cycle(issue_time: datetime, timeout: int = 120) -> dict:
    """Download both track files for one cycle.

    Returns ``{model: bytes}`` for the files that exist. A cycle counts as
    available only once the ensemble file is there, since that is the larger
    file and lands last.
    """
    files = {}
    for model, stream in ECMWF_STREAMS.items():
        url = _file_url(issue_time, stream)
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        files[model] = resp.content
    return files


def latest_available_cycle(now: datetime = None):
    """Newest cycle whose ensemble track file is published."""
    for cycle in recent_cycles(now):
        url = _file_url(cycle, ECMWF_STREAMS["ens"])
        resp = requests.head(url, timeout=60)
        if resp.status_code == 200:
            return cycle
    return None


def _parse_subset(descriptors, values) -> tuple:
    """Turn one BUFR subset (one storm, one member) into track points.

    The track is a sequence of time steps. Each starts with a time period
    (004024, absent for the first step), then locations tagged by their
    significance (008005): the storm centre is the location followed by the
    mean sea level pressure, and the maximum 10 m wind follows its own
    location.
    """
    header = {}
    points = []
    lead = 0
    lat = lon = None
    current = None
    for desc, value in zip(descriptors, values):
        code = f"{desc.id:06d}"
        if code in ("001025", "001027"):
            header.setdefault(code, value.decode("latin-1").strip())
        elif code == "001091":
            header.setdefault(code, value)
        elif code == "004024":
            lead = value
        elif code == "005002":
            lat = value
        elif code == "006002":
            lon = value
        elif code == "010051":
            current = {
                "lead_h": lead,
                "lat": lat,
                "lon": lon,
                "pressure_hpa": value / 100 if value is not None else None,
                "wind_ms": None,
            }
            points.append(current)
        elif code == "011012" and current is not None:
            if current["lead_h"] == lead and current["wind_ms"] is None:
                current["wind_ms"] = value
    return header, points


def parse_tracks(data: bytes, issue_time: datetime, model: str) -> pd.DataFrame:
    """Decode a ``tf`` BUFR file into one row per track point."""
    decoder = Decoder()
    rows = []
    for message in generate_bufr_message(decoder, data):
        template = message.template_data.value
        for descriptors, values in zip(
            template.decoded_descriptors_all_subsets,
            template.decoded_values_all_subsets,
        ):
            header, points = _parse_subset(descriptors, values)
            for p in points:
                if p["lat"] is None or p["lon"] is None:
                    continue
                rows.append(
                    {
                        "issue_time": issue_time,
                        "model": model,
                        "member": header.get("001091"),
                        "storm_id": header.get("001025"),
                        "storm_name": header.get("001027"),
                        **p,
                    }
                )
    df = pd.DataFrame(rows, columns=[c for c in TRACK_COLUMNS
                                     if c not in ("valid_time", "wind_kmh")])
    if df.empty:
        return pd.DataFrame(columns=TRACK_COLUMNS)
    df["valid_time"] = df["issue_time"] + pd.to_timedelta(df["lead_h"], "h")
    df["wind_kmh"] = df["wind_ms"] * MS_TO_KMH
    # The ensemble member number identifies the track within a model; HRES
    # carries a single track per storm.
    if model == "hres":
        df["member"] = "hres"
    else:
        df["member"] = df["member"].astype(int).astype(str)
    return df[TRACK_COLUMNS]


def load_cycle_tracks(issue_time: datetime) -> pd.DataFrame:
    """All HRES and ensemble track points for one cycle."""
    files = fetch_cycle(issue_time)
    frames = [
        parse_tracks(data, issue_time, model) for model, data in files.items()
    ]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=TRACK_COLUMNS)
    return pd.concat(frames, ignore_index=True)
