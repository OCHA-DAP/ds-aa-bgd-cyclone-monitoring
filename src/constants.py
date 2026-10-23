"""Framework constants for Bangladesh cyclone monitoring on ECMWF tracks.

The trigger is taken from the 2025 Bangladesh cyclone AA framework (RC
approval 7 April 2025, USG/ERC endorsement 25 April 2025). ECMWF is one of the
five models the framework names (BMD, IMD, ECMWF, GFS, JTWC), and the
framework needs at least two of them to agree, so this monitor reports the
ECMWF contribution only.
"""

ISO3 = "BGD"
PROJECT_PREFIX = "ds-aa-bgd-cyclone-monitoring"

# ---------------------------------------------------------------------------
# Blob locations
# ---------------------------------------------------------------------------
BLOB_CONTAINER = "projects"
BLOB_STAGE = "dev"

MONITORING_LOG_BLOB = f"{PROJECT_PREFIX}/monitoring/monitoring_log.parquet"
OUTPUT_PREFIX = f"{PROJECT_PREFIX}/monitoring/forecasts/"

# ---------------------------------------------------------------------------
# ECMWF open data
# ---------------------------------------------------------------------------
# Tropical cyclone tracks (BUFR, product "tf") from the IFS. 00 and 12 UTC
# carry 360 h, 06 and 18 UTC carry 144 h. The ensemble file holds 51 members
# (control plus 50 perturbed); the oper file holds the HRES run.
ECMWF_OPEN_DATA_URL = "https://data.ecmwf.int/forecasts"
ECMWF_STREAMS = {"hres": "oper", "ens": "enfo"}
ECMWF_CYCLES_H = [0, 6, 12, 18]

# ---------------------------------------------------------------------------
# Target area
# ---------------------------------------------------------------------------
ADM_GPKG = "data/bgd_adm_sel_bbs_20201113_shp.gpkg"
ADM_LAYER = "bgd_admbnda_adm4_bbs_20201113"
LAND_GEOJSON = "data/land_bay_of_bengal_ne10m.geojson"
COUNTRIES_GEOJSON = "data/countries_bay_of_bengal_ne10m.geojson"

# The six CERF districts (ADM2), as in app.R
TARGET_DISTRICTS = [
    "Barguna",
    "Bhola",
    "Patuakhali",
    "Noakhali",
    "Satkhira",
    "Khulna",
]

# Bangladesh fits well in UTM 46N for distance calculations, as in app.R
PROJECTED_CRS = 32646

# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------
# "118 km/h or higher" at union level. app.R compares with a strict ">", the
# framework text reads ">=", so ">=" is used here.
THRESHOLD_KMH = 118

# Wind reduction factor applied to the forecast landfall wind, with distance
# measured from the landfall point to each union boundary. Same constants and
# distance basis as app.R.
WIND_REDUCTION_A = 0.9807
WIND_REDUCTION_B = 0.003

# Lead time to landfall, in hours: readiness is 3-5 days, action up to 72 h
READINESS_MIN_LEAD_H = 72
READINESS_MAX_LEAD_H = 120
ACTION_MAX_LEAD_H = 72

MS_TO_KMH = 3.6

# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------
# A storm is in play, and gets an email on every new ECMWF cycle, when the
# HRES track or any ensemble member comes within this distance of a target
# district within the forecast horizon.
RELEVANCE_BUFFER_KM = 500
RELEVANCE_MAX_LEAD_H = 168

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# All emails go to list 103 only, in every run mode.
LISTMONK_LIST_ID = 103

FRAMEWORK_URL = (
    "https://www.unocha.org/publications/report/bangladesh/"
    "anticipatory-action-framework-bangladesh-cyclones-2025-version"
)

CHD_GREEN = "#1BB580"
CHD_RED = "#c25048"
