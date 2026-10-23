"""Maps for the monitoring email.

One map per storm: every ensemble member, HRES on top with daily labels,
and each landfall shaded by how soon it comes (darker is sooner).
"""

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from src.constants import (  # noqa: E402
    ACTION_MAX_LEAD_H,
    COUNTRIES_GEOJSON,
    LAND_GEOJSON,
    READINESS_MAX_LEAD_H,
    THRESHOLD_KMH,
)
from src.trigger import load_unions  # noqa: E402

# Chart tokens
SEA = "#eef4fa"
LAND = "#f4f3ef"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
BORDER = "#c3c2b7"
TRACK = "#9a9892"
TRACK_HIT = "#d03b3b"
TARGET = "#1baf7a"

# Landfall shading by lead time, one blue hue, darker is sooner
LANDFALL_COLORS = {
    "action": "#104281",
    "readiness": "#3987e5",
    "later": "#b7d3f6",
}

COUNTRY_LABELS = {
    "Bangladesh": (90.2, 24.1),
    "India": (80.5, 21.0),
    "Myanmar": (95.6, 21.5),
    "Sri Lanka": (80.7, 7.6),
}
EMPHASISED = {"Bangladesh", "India"}

TARGET_BOX = (88.75, 91.6, 21.4, 23.25)
MAX_EXTENT = (76, 100, 5, 28)


def _lead_class(lead_h) -> str:
    if lead_h <= ACTION_MAX_LEAD_H:
        return "action"
    if lead_h <= READINESS_MAX_LEAD_H:
        return "readiness"
    return "later"


def _extent(df_storm) -> tuple:
    """Frame the 7-day tracks and the target districts, with some margin."""
    pts = df_storm[df_storm["lead_h"] <= 168]
    lon = np.concatenate([pts["lon"].to_numpy(), [TARGET_BOX[0], TARGET_BOX[1]]])
    lat = np.concatenate([pts["lat"].to_numpy(), [TARGET_BOX[2], TARGET_BOX[3]]])
    x0, x1 = np.nanmin(lon) - 1.5, np.nanmax(lon) + 1.5
    y0, y1 = np.nanmin(lat) - 1.5, np.nanmax(lat) + 1.5
    x0, x1 = max(x0, MAX_EXTENT[0]), min(x1, MAX_EXTENT[1])
    y0, y1 = max(y0, MAX_EXTENT[2]), min(y1, MAX_EXTENT[3])
    # Keep the panel close to square so it does not turn into a sliver
    w, h = x1 - x0, y1 - y0
    if w < h * 0.8:
        pad = (h * 0.8 - w) / 2
        x0, x1 = x0 - pad, x1 + pad
    elif h < w * 0.8:
        pad = (w * 0.8 - h) / 2
        y0, y1 = y0 - pad, y1 + pad
    return x0, x1, y0, y1


HALO = [patheffects.withStroke(linewidth=2.5, foreground="white")]


def _base_map(ax, extent, label_countries=True, borders=True):
    land = gpd.read_file(LAND_GEOJSON)
    countries = gpd.read_file(COUNTRIES_GEOJSON)
    ax.set_facecolor(SEA)
    land.plot(ax=ax, color=LAND, edgecolor=BORDER, linewidth=0.4, zorder=1)
    if borders:
        other = countries[~countries["NAME"].isin(EMPHASISED)]
        main = countries[countries["NAME"].isin(EMPHASISED)]
        other.boundary.plot(ax=ax, color=BORDER, linewidth=0.6, zorder=2)
        main.boundary.plot(ax=ax, color=INK_2, linewidth=0.9, zorder=2)
    if label_countries:
        x0, x1, y0, y1 = extent
        for name, (x, y) in COUNTRY_LABELS.items():
            if x0 + 0.5 < x < x1 - 0.5 and y0 + 0.3 < y < y1 - 0.3:
                ax.text(x, y, name.upper(), fontsize=7.5, color=INK_2,
                        ha="center", va="center", zorder=7,
                        fontweight="bold", path_effects=HALO)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(BORDER)


def _tracks_panel(ax, df_storm, df_tracks):
    extent = _extent(df_storm)
    _base_map(ax, extent)
    districts = load_unions().dissolve("ADM2_EN")
    districts.plot(ax=ax, color=TARGET, alpha=0.55, edgecolor=TARGET,
                   linewidth=0.5, zorder=3)

    meets = set(
        df_tracks.loc[df_tracks["meets_threshold"], ["model", "member"]]
        .itertuples(index=False, name=None)
    )
    for (model, member), track in df_storm.groupby(["model", "member"]):
        if model != "ens":
            continue
        track = track.sort_values("lead_h")
        hit = (model, member) in meets
        ax.plot(track["lon"], track["lat"],
                color=TRACK_HIT if hit else TRACK,
                linewidth=1.1 if hit else 0.5,
                alpha=0.9 if hit else 0.5, zorder=5 if hit else 4,
                solid_capstyle="round")

    hres = df_storm[df_storm["model"] == "hres"].sort_values("lead_h")
    if not hres.empty:
        ax.plot(hres["lon"], hres["lat"], color="white", linewidth=4.0,
                zorder=6, solid_capstyle="round")
        ax.plot(hres["lon"], hres["lat"], color=INK, linewidth=2.0,
                zorder=6, solid_capstyle="round")
        # A dot per day; a date label only where it will not sit on top of
        # the previous one, which happens when the storm stalls.
        labelled = []
        min_gap = 0.09 * (extent[1] - extent[0])
        for lead in range(0, int(hres["lead_h"].max()) + 1, 24):
            pt = hres[hres["lead_h"] == lead]
            if pt.empty:
                continue
            x, y = pt["lon"].iloc[0], pt["lat"].iloc[0]
            if not (extent[0] < x < extent[1] and extent[2] < y < extent[3]):
                continue
            ax.scatter(x, y, s=22, color=INK, edgecolor="white",
                       linewidth=1, zorder=8)
            if any(np.hypot(x - lx, y - ly) < min_gap for lx, ly in labelled):
                continue
            labelled.append((x, y))
            ax.annotate(f"{pt['valid_time'].iloc[0]:%d %b}", (x, y),
                        xytext=(5, 4), textcoords="offset points",
                        fontsize=7.5, color=INK, zorder=8,
                        path_effects=HALO)

    landed = df_tracks[df_tracks["makes_landfall"]].copy()
    if not landed.empty:
        landed["lead_class"] = landed["landfall_lead_h"].map(_lead_class)
        for cls, color in LANDFALL_COLORS.items():
            sub = landed[landed["lead_class"] == cls]
            ax.scatter(sub["landfall_lon"], sub["landfall_lat"], s=26,
                       color=color, edgecolor="white", linewidth=0.8,
                       zorder=9)
    return extent


def plot_storm_map(df_storm, df_tracks, storm_label: str, issue_time):
    """One map per storm: forecast tracks over the Bay of Bengal."""
    fig = plt.figure(figsize=(7, 8.2))
    grid = fig.add_gridspec(2, 1, height_ratios=[1, 0.1], hspace=0.04)
    ax = fig.add_subplot(grid[0])
    ax_legend = fig.add_subplot(grid[1])

    _tracks_panel(ax, df_storm, df_tracks)
    ax.set_title(
        f"{storm_label}: ECMWF forecast tracks, "
        f"{issue_time:%d %b %H:%M} UTC",
        fontsize=11, loc="left", color=INK, pad=8,
    )

    ax_legend.axis("off")
    handles = [
        Line2D([], [], color=INK, linewidth=2, label="HRES (dots daily)"),
        Line2D([], [], color=TRACK, linewidth=1, label="Ensemble member"),
        Line2D([], [], color=TRACK_HIT, linewidth=1.2,
               label=f"Member reaching {THRESHOLD_KMH} km/h in a target union"),
        Line2D([], [], marker="s", linestyle="", color=TARGET, alpha=0.6,
               markersize=8, label="Target districts"),
    ] + [
        Line2D([], [], marker="o", linestyle="", markersize=6,
               markerfacecolor=c, markeredgecolor="white", label=lbl)
        for c, lbl in [
            (LANDFALL_COLORS["action"], "Landfall within 72 h"),
            (LANDFALL_COLORS["readiness"], "Landfall in 3-5 days"),
            (LANDFALL_COLORS["later"], "Landfall after 5 days"),
        ]
    ]
    ax_legend.legend(handles=handles, loc="center", ncol=2, fontsize=7.5,
                     frameon=False, handlelength=1.8, columnspacing=1.5)
    fig.patch.set_facecolor("white")
    return fig
