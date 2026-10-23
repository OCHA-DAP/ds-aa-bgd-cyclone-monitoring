"""Monitor ECMWF cyclone tracks against the Bangladesh cyclone framework.

Each run takes the newest ECMWF cycle not yet processed, finds the storms
whose tracks come within reach of the six target districts, estimates union
winds for every HRES and ensemble track, and sends one email to list 103.

    python pipelines/monitor_ecmwf.py               # newest unprocessed cycle
    python pipelines/monitor_ecmwf.py --cycle 2026-10-22T00
    python pipelines/monitor_ecmwf.py --dry-run     # no email, no blob writes
    python pipelines/monitor_ecmwf.py --save-html out.html
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib.pyplot as plt  # noqa: E402

from src import blob_utils, ecmwf, emails, plotting, trigger  # noqa: E402


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", help="ECMWF cycle, YYYY-MM-DDTHH (UTC)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute only: no email, nothing written to blob")
    parser.add_argument("--force", action="store_true",
                        help="Process the cycle even if already logged")
    parser.add_argument("--save-html", help="Also write the email HTML here")
    return parser.parse_args()


def _log_row(issue_time, storm_id, name, summary, in_play, campaign_id):
    hres = summary["hres"] if summary else None
    hres = hres or {}
    return {
        "issue_time": issue_time,
        "storm_id": storm_id,
        "storm_name": name,
        "in_play": in_play,
        "n_members": summary["n_members"] if summary else None,
        "n_members_readiness": summary["n_members_readiness"] if summary else None,
        "n_members_action": summary["n_members_action"] if summary else None,
        "n_members_landfall_target": (
            summary["n_members_landfall_target"] if summary else None
        ),
        "hres_landfall_country": hres.get("landfall_country"),
        "hres_landfall_time": hres.get("landfall_time"),
        "hres_landfall_lead_h": hres.get("landfall_lead_h"),
        "hres_landfall_wind_kmh": hres.get("landfall_wind_kmh"),
        "hres_max_union_wind_kmh": hres.get("max_union_wind_kmh"),
        "hres_window": hres.get("window"),
        "hres_meets_threshold": hres.get("meets_threshold"),
        "email_campaign_id": campaign_id,
    }


def main():
    args = _parse_args()

    if args.cycle:
        issue_time = datetime.strptime(args.cycle, "%Y-%m-%dT%H").replace(
            tzinfo=timezone.utc
        )
    else:
        issue_time = ecmwf.latest_available_cycle()
        if issue_time is None:
            print("No ECMWF track files found for the recent cycles")
            return

    if not args.force and not args.dry_run:
        df_log = blob_utils.load_monitoring_log()
        if issue_time in blob_utils.processed_cycles(df_log):
            print(f"Cycle {issue_time:%Y-%m-%d %HZ} already processed")
            return

    print(f"Processing ECMWF cycle {issue_time:%Y-%m-%d %HZ}")
    df = ecmwf.load_cycle_tracks(issue_time)
    if df.empty:
        print("  No tracks in this cycle")
        return

    relevant = trigger.is_relevant(df)
    in_play = sorted(relevant[relevant].index)
    print(f"  {df['storm_id'].nunique()} storms, in play: {in_play or 'none'}")

    storms, log_rows = [], []
    for storm_id in in_play:
        df_storm = df[df["storm_id"] == storm_id]
        df_tracks, df_unions = trigger.assess_storm(df_storm)
        summary = trigger.summarise_storm(df_tracks)
        name = df_storm["storm_name"].iloc[0]
        label = storm_id if name == storm_id else f"{name} ({storm_id})"
        print(
            f"  {label}: readiness {summary['n_members_readiness']}/"
            f"{summary['n_members']}, action {summary['n_members_action']}/"
            f"{summary['n_members']}, HRES meets threshold: "
            f"{(summary['hres'] or {}).get('meets_threshold')}"
        )
        storms.append({
            "storm_id": storm_id,
            "label": label,
            "summary": summary,
            "fig": plotting.plot_storm_map(
                df_storm, df_tracks, label, issue_time
            ),
        })
        log_rows.append(_log_row(issue_time, storm_id, name, summary, True, None))
        if not args.dry_run:
            blob_utils.save_outputs(
                issue_time, storm_id,
                {"tracks": df_tracks, "unions": df_unions, "points": df_storm},
            )

    if args.save_html and storms:
        Path(args.save_html).write_text(
            emails.build_body(issue_time, storms), encoding="utf-8"
        )
        print(f"  Email HTML written to {args.save_html}")

    campaign_id = None
    if storms and not args.dry_run:
        campaign_id = emails.send_monitoring_email(issue_time, storms)
        print(f"  Email sent to list 103, campaign {campaign_id}")
        for row in log_rows:
            row["email_campaign_id"] = campaign_id

    for fig in (s["fig"] for s in storms):
        plt.close(fig)

    if not args.dry_run:
        if not log_rows:
            # Record the cycle so the next run moves on to the next one.
            log_rows.append(
                _log_row(issue_time, None, None, None, False, None)
            )
        blob_utils.append_monitoring_log(log_rows)


if __name__ == "__main__":
    main()
