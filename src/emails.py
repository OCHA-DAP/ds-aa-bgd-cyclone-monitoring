"""Build and send the Bangladesh cyclone monitoring email via Listmonk.

One email per ECMWF cycle, covering every storm in play. It goes to list 103
only, whatever the run mode.
"""

import base64
import os
import time
from io import BytesIO

from ocha_relay.listmonk import ListmonkClient

from src.constants import (
    ACTION_MAX_LEAD_H,
    CHD_GREEN,
    FRAMEWORK_URL,
    LISTMONK_LIST_ID,
    THRESHOLD_KMH,
)


def listmonk_client() -> ListmonkClient:
    """Build the Listmonk client from DSCI_LISTMONK_API_URL.

    The two URL variables differ only in whether they carry the ``/api``
    suffix, so it is normalised rather than assumed.
    """
    url = os.getenv("DSCI_LISTMONK_API_URL") or os.getenv(
        "DSCI_LISTMONK_BASE_URL"
    )
    if not url:
        raise ValueError("Set DSCI_LISTMONK_API_URL to reach Listmonk")
    url = url.rstrip("/")
    if not url.startswith("http"):
        url = f"https://{url}"
    if not url.endswith("/api"):
        url = f"{url}/api"
    return ListmonkClient(
        base_url=url,
        username=os.environ["DSCI_LISTMONK_API_USERNAME"],
        password=os.environ["DSCI_LISTMONK_API_KEY"],
    )


def _embed(fig) -> str:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=110)
    buffer.seek(0)
    return f"data:image/png;base64,{base64.b64encode(buffer.read()).decode()}"


def _hres_line(hres) -> str:
    if hres is None:
        return "<strong>HRES:</strong> no track for this storm."
    if not hres.get("makes_landfall"):
        return (
            "<strong>HRES:</strong> no landfall; peak wind "
            f"{hres['max_wind_kmh']:.0f} km/h."
        )
    line = (
        f"<strong>HRES:</strong> landfall in {hres['landfall_country']}, "
        f"{hres['landfall_time']:%d %b %H:%M} UTC "
        f"({hres['landfall_lead_h']:.0f} h ahead), "
        f"{hres['landfall_wind_kmh']:.0f} km/h. Highest target-union wind "
        f"{hres['max_union_wind_kmh']:.0f} km/h"
    )
    if hres["n_unions_above"]:
        line += (
            f"; {hres['n_unions_above']} unions at or above {THRESHOLD_KMH} "
            f"km/h ({', '.join(hres['districts_above'])})"
        )
    return line + "."


def _ensemble_line(summary) -> str:
    n = summary["n_members"]
    if not n:
        return "<strong>Ensemble:</strong> no members track this storm."
    line = (
        f"<strong>Ensemble ({n} members):</strong> "
        f"{summary['n_members_readiness']} reaching {THRESHOLD_KMH} km/h in a "
        "target union with landfall in 3-5 days, "
        f"{summary['n_members_action']} within {ACTION_MAX_LEAD_H} h."
    )
    by_country = summary.get("members_by_country") or {}
    if by_country:
        ordered = sorted(
            by_country.items(), key=lambda x: (x[0] == "No landfall", -x[1])
        )
        line += " Landfall: " + ", ".join(
            f"{'none' if c == 'No landfall' else c} {k}" for c, k in ordered
        ) + "."
    return line


def _storm_section(storm: dict) -> str:
    return f"""
          <h2>{storm['label']}</h2>
          <p>{_hres_line(storm['summary']['hres'])}<br/>
          {_ensemble_line(storm['summary'])}</p>
          <div style="text-align:center;margin:8px 0 20px;">
            <img src="{_embed(storm['fig'])}" alt="ECMWF forecast tracks"
                 width="520" style="display:block;width:100%;max-width:600px;">
          </div>"""


def build_body(issue_time, storms: list) -> str:
    sections = "".join(_storm_section(s) for s in storms)
    names = ", ".join(s["label"] for s in storms)
    return f"""<style>
  .bgd-cyclone {{ font-family: Helvetica, Arial, sans-serif; font-size:14px;
                 color:#222; }}
  .bgd-cyclone h1 {{ font-size:20px; }}
  .bgd-cyclone h2 {{ font-size:16px; color:{CHD_GREEN};
                    margin-top:22px; margin-bottom:4px; }}
  .bgd-cyclone p {{ line-height:1.5; }}
</style>
<div class="bgd-cyclone">
          <h1>Bangladesh Cyclone Monitoring: ECMWF forecast</h1>
          <p>Issued {issue_time:%d %B %Y %H:%M UTC}. Storms within reach of
          the target districts: {names}.</p>
          {sections}
          <p style="font-size:12px;color:#555;">The framework needs at least
          two of five models (BMD, IMD, ECMWF, GFS, JTWC) at
          {THRESHOLD_KMH} km/h or higher in a target union, 3-5 days before
          landfall for readiness and up to {ACTION_MAX_LEAD_H} hours for
          action. This email covers ECMWF only. Union winds apply the
          framework's wind reduction factor to the ECMWF landfall wind (10 m
          maximum wind, not converted).
          <a href="{FRAMEWORK_URL}" target="_blank"
             style="color:{CHD_GREEN};">Framework Document</a>.</p>
</div>"""


def _delivered(client, campaign_id, polls: int = 10) -> bool:
    """Wait for a sent campaign to finish and read back its sent count.

    This instance has been seen to mark a campaign ``finished`` while having
    sent to nobody, so delivery is read back rather than assumed.
    """
    for _ in range(polls):
        time.sleep(3)
        campaign = client.get_campaign(campaign_id)
        data = campaign if isinstance(campaign, dict) else campaign.__dict__
        if data.get("sent"):
            return True
        if data.get("status") == "finished":
            return False
    return False


def send_monitoring_email(issue_time, storms: list, attempts: int = 3) -> int:
    """Send the monitoring email to list 103. Returns the campaign ID.

    A finished campaign cannot be sent again, so a silent drop is retried
    with a new campaign.
    """
    client = listmonk_client()
    names = ", ".join(s["storm_id"] for s in storms)
    subject = (
        f"Bangladesh Cyclone Monitoring: ECMWF {issue_time:%d %b %H}Z ({names})"
    )
    body = build_body(issue_time, storms)
    campaign_id = None
    for attempt in range(1, attempts + 1):
        suffix = "" if attempt == 1 else f"-retry{attempt - 1}"
        campaign_id = client.create_campaign(
            name=f"bgd-cyclone-ecmwf-{issue_time:%Y%m%dT%H}{suffix}",
            subject=subject,
            body=body,
            list_ids=[LISTMONK_LIST_ID],
        )
        client.send_campaign(campaign_id, skip_confirmation=True)
        if _delivered(client, campaign_id):
            return campaign_id
        print(
            f"  Listmonk campaign {campaign_id} finished with nobody sent "
            f"({attempt}/{attempts})"
        )
    print(
        f"  WARNING: no Listmonk campaign reported a delivery; last was "
        f"{campaign_id}. Check the Listmonk UI."
    )
    return campaign_id
