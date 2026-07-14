"""
Choropleth maps. Read the whole module docstring before changing anything
here - a map is persuasion technology in a way a table of numbers is not,
and every design choice below exists to stop the map from saying something
the text explicitly does not claim.

**Colour scale is clipped, not the raw min/max.** A handful of extreme
outliers (Westminster/Wandsworth's inflated single-pot gaps; a few Surrey
commuter-belt LAs under Variant 2's compression effect) would otherwise
saturate the colour scale and make every other LA look pale by
comparison - a real cartographic distortion, not a political one, but one
that would ALSO happen to work against the "lead with the North" framing
this project has settled on, so it is named explicitly here rather than
adjusted quietly. The scale is clipped to a symmetric, percentile-based
bound (`clip_percentile`, default the 2nd/98th percentile of the actual
data) and centred on zero.

**The five single-pot-flagged LAs are drawn with a visibly different
texture, not just a different shade.** Colour alone survives a glance;
colour plus hatching survives a screenshot with no caption. See
`aggregates.SINGLE_POT_FLAGGED_LAS`.

**No map in this module includes the 2000-09 backward-extension period.**
That period uses imputed (not observed) band shares - see DATA.md - and
mixing it into the same choropleth as the observed 2009-26 headline
period, even with a caveat in the text, would present two different
evidentiary standards in one visual register. If a map of the extension
period is ever added, it must use a visually distinct style (e.g.
diagonal stripes across the whole map, or a separate figure entirely),
never share a colour scale with the headline map, and never appear
side-by-side implying equivalence.
"""

from __future__ import annotations

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

# matplotlib's plain "RdBu" maps LOW values to red, HIGH to blue - the
# opposite of what every label in this module claims ("red = overpaid" =
# positive = high). Caught only by rendering the map and looking at it
# (see project log) - checked directly, not assumed: "RdBu_r" maps
# positive/high (overpaid, the North) to red and negative/low (underpaid,
# London) to blue, matching every legend and caption this module writes.
DIVERGING_CMAP = "RdBu_r"


def plot_gap_choropleth(
    gdf: gpd.GeoDataFrame,
    data: "object",
    value_col: str,
    ons_code_col: str = "ons_code",
    flagged_codes: dict[str, str] | None = None,
    title: str = "",
    subtitle: str = "",
    legend_label: str = "",
    clip_percentile: float = 2.0,
    figsize: tuple[float, float] = (9, 11),
    inset_bbox: tuple[float, float, float, float] | None = None,
    inset_label: str = "",
):
    """One England choropleth. `gdf` must have a `LAD25CD` geometry column
    (boundaries/lad_2025.geojson, English rows only); `data` is a
    DataFrame with `ons_code_col` and `value_col`. `flagged_codes` (dict
    of ons_code -> label) get a hatched overlay, a bright high-contrast
    border, AND are excluded from the percentile calculation that sets
    the colour scale, so a handful of LAs already flagged as inflated
    cannot ALSO be the reason the rest of the map looks washed out.

    **A hatch pattern alone was checked and found not to be enough.**
    Rendered and inspected directly (see project log): a black `///`
    hatch is nearly invisible against the darkest cells in the colour
    scale, which is exactly where the flagged LAs (Westminster, Wandsworth
    etc.) sit, since they are also the most extreme values. Fixed two
    ways, not one: a bright, fixed-colour border (`#39FF14`, high-contrast
    against both ends of a red/blue diverging scale) in addition to the
    hatch, and - because London's flagged LAs are also geographically
    tiny on an England-wide map, however they're coloured - an optional
    `inset_bbox` (minx, miny, maxx, maxy in the gdf's own CRS) that draws
    a second, zoomed panel at a legible scale, with a rectangle on the
    main map showing what it's a zoom of.

    Diverging red/blue (`DIVERGING_CMAP`), LA boundaries drawn in a thin
    grey line - the same visual grammar as the Tax Policy Associates LVT
    model this project was prompted by, so a reader can compare the two
    directly."""
    merged = gdf.merge(data[[ons_code_col, value_col]], left_on="LAD25CD", right_on=ons_code_col, how="left")

    flagged_codes = flagged_codes or {}
    unflagged = merged[~merged["LAD25CD"].isin(flagged_codes)]
    flagged = merged[merged["LAD25CD"].isin(flagged_codes)]

    bound = np.nanpercentile(np.abs(unflagged[value_col].dropna()), 100 - clip_percentile)
    norm = TwoSlopeNorm(vmin=-bound, vcenter=0, vmax=bound)
    flag_border = "#39FF14"  # fixed, saturated colour - never part of DIVERGING_CMAP's own range, so it never blends in

    def _draw(target_ax, linewidth=0.15, flag_linewidth=1.4):
        merged.plot(
            column=value_col,
            cmap=DIVERGING_CMAP,
            norm=norm,
            linewidth=linewidth,
            edgecolor="#555555",
            ax=target_ax,
            missing_kwds={"color": "#dddddd"},
        )
        if len(flagged):
            flagged.plot(ax=target_ax, facecolor="none", edgecolor=flag_border, linewidth=flag_linewidth, hatch="///")

    fig, ax = plt.subplots(figsize=figsize)
    _draw(ax)

    if inset_bbox is not None:
        inset_ax = ax.inset_axes([0.62, 0.58, 0.42, 0.42])
        _draw(inset_ax, linewidth=0.4, flag_linewidth=2.2)
        minx, miny, maxx, maxy = inset_bbox
        inset_ax.set_xlim(minx, maxx)
        inset_ax.set_ylim(miny, maxy)
        inset_ax.set_xticks([])
        inset_ax.set_yticks([])
        for spine in inset_ax.spines.values():
            spine.set_edgecolor("#333333")
            spine.set_linewidth(1.0)
        if inset_label:
            inset_ax.set_title(inset_label, fontsize=8, style="italic")
        ax.indicate_inset_zoom(inset_ax, edgecolor="#333333", linewidth=0.8)

    sm = plt.cm.ScalarMappable(cmap=DIVERGING_CMAP, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.02)
    cbar.set_label(legend_label or value_col)

    legend_handles = []
    if len(flagged):
        legend_handles.append(Patch(facecolor="none", edgecolor=flag_border, hatch="///", label="Upper-bound estimate (single-pot exposure) — not a point estimate"))
    if legend_handles:
        ax.legend(handles=legend_handles, loc="lower left", fontsize=8, frameon=True)

    ax.set_axis_off()
    fig.suptitle(title, fontsize=14, fontweight="bold", x=0.02, ha="left", y=0.98)
    if subtitle:
        fig.text(0.02, 0.945, subtitle, fontsize=9, ha="left", va="top", color="#333333")

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig, ax


def plot_top_la_bars(
    data,
    value_col: str,
    name_col: str,
    n: int = 15,
    direction: str = "positive",
    flagged_codes: dict[str, str] | None = None,
    ons_code_col: str = "ons_code",
    title: str = "",
    xlabel: str = "",
    color: str = "#b2182b",
    figsize: tuple[float, float] = (8, 6),
):
    """A ranked bar chart of the top N LAs by `value_col`, in the
    requested direction. Exists specifically so the North gets its own
    figure with its own visual real estate, rather than being one region
    among many in an England-wide choropleth where a handful of London
    outliers draw the eye by colour saturation alone - see module
    docstring. `flagged_codes` get a hatch pattern here too, for the
    (mirror-image) case of ranking the top underpaying LAs, where the
    five single-pot-flagged LAs would otherwise dominate the top of the
    list with no visual signal that they're upper bounds."""
    flagged_codes = flagged_codes or {}
    df = data.copy()
    ascending = direction == "negative"
    top = df.sort_values(value_col, ascending=ascending).head(n).iloc[::-1]

    fig, ax = plt.subplots(figsize=figsize)
    colors = ["#f4a582" if c in flagged_codes else color for c in top[ons_code_col]]
    hatches = ["///" if c in flagged_codes else None for c in top[ons_code_col]]
    bars = ax.barh(top[name_col], top[value_col], color=colors, edgecolor="#333333", linewidth=0.4)
    for bar, hatch in zip(bars, hatches):
        if hatch:
            bar.set_hatch(hatch)

    ax.set_title(title, fontsize=13, fontweight="bold", loc="left")
    ax.set_xlabel(xlabel)
    ax.spines[["top", "right"]].set_visible(False)

    if flagged_codes and any(c in flagged_codes for c in top[ons_code_col]):
        ax.legend(
            handles=[Line2D([0], [0], color="#f4a582", lw=6, label="Upper-bound estimate (single-pot exposure)")],
            loc="lower right",
            fontsize=8,
            frameon=True,
        )

    fig.tight_layout()
    return fig, ax
