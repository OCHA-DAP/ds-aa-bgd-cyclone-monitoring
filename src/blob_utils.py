"""Read and write the monitoring state and outputs on blob storage."""

from datetime import datetime, timezone

import ocha_stratus as stratus
import pandas as pd

from src.constants import (
    BLOB_CONTAINER,
    BLOB_STAGE,
    MONITORING_LOG_BLOB,
    OUTPUT_PREFIX,
)

LOG_COLUMNS = [
    "issue_time",
    "processed_time",
    "storm_id",
    "storm_name",
    "in_play",
    "n_members",
    "n_members_readiness",
    "n_members_action",
    "n_members_landfall_target",
    "hres_landfall_country",
    "hres_landfall_time",
    "hres_landfall_lead_h",
    "hres_landfall_wind_kmh",
    "hres_max_union_wind_kmh",
    "hres_window",
    "hres_meets_threshold",
    "email_campaign_id",
]


def load_monitoring_log() -> pd.DataFrame:
    """Log of cycles and storms already processed.

    Returns an empty frame with the expected columns if the log does not
    exist yet, so the first run works without any bootstrapping.
    """
    try:
        df = stratus.load_parquet_from_blob(
            MONITORING_LOG_BLOB, stage=BLOB_STAGE, container_name=BLOB_CONTAINER
        )
    except Exception:
        return pd.DataFrame(columns=LOG_COLUMNS)
    for col in LOG_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df


def processed_cycles(df_log: pd.DataFrame) -> set:
    if df_log.empty:
        return set()
    return set(pd.to_datetime(df_log["issue_time"], utc=True))


def append_monitoring_log(rows) -> pd.DataFrame:
    """Append rows to the monitoring log and write it back to blob."""
    df_log = load_monitoring_log()
    df_new = pd.DataFrame(rows, columns=LOG_COLUMNS)
    df_new["processed_time"] = datetime.now(timezone.utc)
    df_out = pd.concat(
        [df for df in (df_log, df_new) if not df.empty], ignore_index=True
    )
    df_out["issue_time"] = pd.to_datetime(df_out["issue_time"], utc=True)
    df_out = df_out.drop_duplicates(
        subset=["issue_time", "storm_id"], keep="last"
    )
    stratus.upload_parquet_to_blob(
        df_out, MONITORING_LOG_BLOB, stage=BLOB_STAGE,
        container_name=BLOB_CONTAINER,
    )
    return df_out


def save_outputs(issue_time, storm_id: str, frames: dict) -> list:
    """Write per-track and per-union tables for one storm and cycle."""
    stamp = issue_time.strftime("%Y%m%d_%H%M")
    names = []
    for kind, df in frames.items():
        if df is None or df.empty:
            continue
        df = df.copy()
        for col in df.columns:
            if df[col].map(lambda v: isinstance(v, list)).any():
                df[col] = df[col].map(
                    lambda v: ", ".join(v) if isinstance(v, list) else v
                )
        name = f"{OUTPUT_PREFIX}{stamp}/{storm_id}_{kind}.parquet"
        stratus.upload_parquet_to_blob(
            df, name, stage=BLOB_STAGE, container_name=BLOB_CONTAINER
        )
        names.append(name)
    return names
