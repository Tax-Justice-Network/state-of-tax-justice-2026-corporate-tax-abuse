"""Tax Justice Network brand styling for matplotlib figures.

This module applies the TJN brand guide and fonts guide (2020) to matplotlib figures:
  * Typeface: **Work Sans** (the publication sans-serif for headings, titles and body text).
    Montserrat Black is reserved for slogans and Catamaran Black for the logo,
    so neither is used in charts.
  * Colour palette: the brand primary and support colours.

The Work Sans static TTFs ship in `assets/fonts/` (SIL OFL), and this module registers them
with matplotlib, so that the brand font renders even though it is not installed system-wide.
Call `apply_tjn_style()` once at import in any figure script:

    from _brand import apply_tjn_style, PALETTE, POSITIVE, NEGATIVE, ORIGIN_DEST_NEXUS
    apply_tjn_style()
"""
from pathlib import Path

import matplotlib as mpl
import matplotlib.font_manager as fm

_ROOT = Path(__file__).resolve().parent.parent
_FONT_DIR = _ROOT / "assets" / "fonts"

# ---- Brand colours (TJN brand guide 2020) ----
GOLD = "#FFD371"          # primary
EARTH_GREEN = "#50805E"   # primary
WHITE = "#FFFFFF"         # primary
RED = "#AD756C"           # support
TEAL = "#45636C"          # support
BROWN = "#AE8D6C"         # support
BLUE = "#586AAD"          # support
INK = "#1A1A1A"           # near-black for text / axes (brand text is black)
# State of Tax Justice report template: the tjn-main purple and its tints, used for the
# report's own figures.
PURPLE = "#564A5C"        # tjn-main (RGB 86,74,92)
PURPLE_TINT = "#DDDBDE"   # tjn-main-tint
RED_TINT = "#EFE3E2"      # tjn-red-tint
BOX_BG = "#EDE7E0"        # cthi-background (box background in the SOTJ template)

# The general categorical cycle lists the primary colours first, then the support colours.
# Earth green leads because it is the dominant brand colour.
PALETTE = [EARTH_GREEN, BLUE, GOLD, RED, TEAL, BROWN]

# Semantic helpers, used consistently across the deliverables:
POSITIVE = EARTH_GREEN          # winners / gains
NEGATIVE = RED                  # losers / losses
ORIGIN_DEST_NEXUS = [BLUE, GOLD, EARTH_GREEN]   # origin / destination / dest+nexus

# Colour-blind redundancy: each categorical series gets a hatch (texture) on top of the brand
# colour, so that grouped bars stay distinguishable for viewers who cannot separate the hues
# (and in greyscale or print). The first series is solid and the others carry a distinct
# texture.
# Use `HATCH_CYCLE[i % len(HATCH_CYCLE)]`.
HATCH_CYCLE = ["", "\\\\", "..", "xx", "++", "oo"]


def tint(hex_color: str, frac: float = 0.2) -> str:
    """Returns a tint of a brand colour over white (20% by default), for the brand's tinted backgrounds."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: round(c * frac + 255 * (1 - frac))
    return f"#{mix(r):02X}{mix(g):02X}{mix(b):02X}"


def shade(hex_color: str, frac: float = 0.35) -> str:
    """Returns a brand colour darkened toward black by `frac` (for the deep endpoints of colour ramps)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: round(c * (1 - frac))
    return f"#{mix(r):02X}{mix(g):02X}{mix(b):02X}"


# Diverging anchors for signed heatmaps: losses on the brand red (RED) pole and gains on the
# brand blue (BLUE) pole. I do not use earth green, because red and green form the classic
# diverging pair that fails under deuteranopia. The midpoint is a neutral warm grey, never a
# hue. The endpoints are darkened brand anchors, so that the ramp has enough range.
DIVERGING_ANCHORS = [shade(RED), RED, "#F1EFEA", BLUE, shade(BLUE)]
# Green and red gain–loss variant (matches the POSITIVE / NEGATIVE semantics). The two hues
# are not separable under deuteranopia on their own. Use it only where every cell also carries
# a signed annotation (+/−), so that the sign, not the hue, carries the polarity.
DIVERGING_GAIN_LOSS = [shade(RED), RED, "#F1EFEA", EARTH_GREEN, shade(EARTH_GREEN)]


def _install_pdf_sidecar():
    """Makes every figure also save a vector PDF next to its PNG.

    I patch Figure.savefig (which plt.savefig routes through), so that a save to
    `<name>.png` also writes `<name>.pdf` and no figure script needs to change. The
    patch is idempotent. It skips non-path targets (buffers) and never recurses,
    because it calls the captured original."""
    from matplotlib.figure import Figure
    if getattr(Figure, "_tjn_pdf_patched", False):
        return
    _orig = Figure.savefig

    def savefig(self, fname, *args, **kwargs):
        result = _orig(self, fname, *args, **kwargs)
        try:
            p = Path(fname)
        except TypeError:
            return result                      # file-like / buffer target
        if p.suffix.lower() == ".png":
            try:
                _orig(self, str(p.with_suffix(".pdf")), *args, **kwargs)
            except Exception:
                pass                            # never let the PDF break the PNG
        return result

    Figure.savefig = savefig
    Figure._tjn_pdf_patched = True


_applied = False


def apply_tjn_style():
    """Registers Work Sans and sets the brand rcParams. Calling it more than once has no further effect."""
    global _applied
    if _applied:
        return
    _install_pdf_sidecar()
    for f in sorted(_FONT_DIR.glob("WorkSans-*.ttf")):
        try:
            fm.fontManager.addfont(str(f))
        except Exception:
            pass
    mpl.rcParams.update({
        "font.family": "Work Sans",
        "font.sans-serif": ["Work Sans", "DejaVu Sans", "Arial"],
        "axes.prop_cycle": mpl.cycler(color=PALETTE),
        # near-black ink for text + axes
        "text.color": INK, "axes.labelcolor": INK, "axes.titlecolor": INK,
        "axes.edgecolor": INK, "xtick.color": INK, "ytick.color": INK,
        "axes.titleweight": "bold",
        # clean spines + light horizontal grid
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y",
        "grid.color": "#E8E8E8", "grid.linewidth": 0.8, "axes.axisbelow": True,
        # white backgrounds (brand primary background)
        "figure.facecolor": "white", "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "legend.frameon": True, "legend.framealpha": 0.9,
        "legend.edgecolor": "#DDDDDD",
        "font.size": 11, "figure.dpi": 130, "savefig.dpi": 130,
    })
    _applied = True
