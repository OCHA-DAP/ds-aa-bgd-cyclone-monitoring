# Bangladesh cyclone AA monitoring

Two parts:

- **Shiny app** (`app.R`): enter a landfall point and wind speed, get the
  estimated wind at every union in the six target districts.
- **ECMWF monitor** (`pipelines/monitor_ecmwf.py`): the same calculation run
  automatically on every ECMWF cycle, with an email to Listmonk list 103.

## ECMWF monitor

CMA's live feed carries no Bay of Bengal bulletins (WTPQ/TCPQ only, Western
Pacific), so the monitor uses ECMWF tropical cyclone tracks from the open
data portal (`data.ecmwf.int`, product `tf`, BUFR): HRES plus the 51-member
ensemble, four cycles a day.

For each track the monitor finds every sea-to-land crossing, applies the
framework's wind reduction factor (`0.9807 * exp(-0.003 * km)`, distance to
union boundary, as in `app.R`) to the landfall wind, and keeps the landfall
giving the highest union wind. A track meets the threshold when any union
reaches 118 km/h or more. Landfall lead time places it in the readiness
(72-120 h) or action (up to 72 h) window.

A storm is in play when the HRES track or any member comes within 500 km of
a target district within 168 h. Each new cycle with a storm in play gives one
email to list 103. The framework needs two of five models; the email covers
ECMWF only.

It runs only in GitHub Actions (`.github/workflows/run_monitor_ecmwf.yml`),
hourly, from the default branch. To check a cycle by hand, run the workflow
from the Actions tab with `dry_run` ticked (and `cycle`, e.g.
`2026-10-22T18`, to pick one). Every run, dry or not, uploads the email it
built as the `email-preview` artifact.

The email names the landfall country for HRES and counts ensemble members by
landfall country, with one map of the forecast tracks per storm (landfalls
shaded by lead time).
- State: `projects/ds-aa-bgd-cyclone-monitoring/monitoring/monitoring_log.parquet`
  (dev blob), one row per cycle and storm. Per-track, per-union and track
  point tables go to `monitoring/forecasts/<cycle>/`.
- Winds are ECMWF 10 m maximum wind as published, with no averaging-period
  conversion.
- `data/land_bay_of_bengal_ne10m.geojson` (landfall detection) and
  `data/countries_bay_of_bengal_ne10m.geojson` (map outlines) are clipped from
  Natural Earth 10 m.
- The email list is fixed to 103 in `src/constants.py`.
