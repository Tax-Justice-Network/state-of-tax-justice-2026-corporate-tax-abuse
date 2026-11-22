# %%
"""
SOTJ palette — the common colour scheme of the SOTJ 2026 chapter figures.

This module defines the common colour scheme of the State of Tax Justice 2026 chapter figures. The
tjn-main purple of the SOTJ report template is the dark "problem" colour (untaxed, lost, shifted),
earth green is the "good" colour (taxed, gained), and purple tints are the neutrals. The other brand
colours (red, teal, brown, blue, gold) serve categorical series. Everything stays inside the TJN brand
palette (src/_brand.py) plus the template purple.

Author: Tax Justice Network.
Last updated: 2026-11-23.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from _brand import (GOLD, EARTH_GREEN, RED, TEAL, BROWN, BLUE, INK, PURPLE, PURPLE_TINT, tint, shade)  # noqa: E402,F401

# semantic roles
LOSS = PURPLE                 # revenue lost, profit shifted away, obstructive statements
GAIN = EARTH_GREEN            # revenue gained, taxed, supportive statements
NEUTRAL = tint(PURPLE, 0.65)  # secondary / "other" blocks
NEUTRAL_LIGHT = tint(PURPLE, 0.3)
SAMPLE = tint(PURPLE, 0.45)   # Figure-1 style pairs: the sample bar …
SCALED = PURPLE               # … and the bar scaled to all multinationals
EARLY = tint(PURPLE, 0.45)    # 2016 vs 2023 pairs: the earlier year …
LATE = PURPLE                 # … and the later year
PROFIT = PURPLE               # profit series in profit-vs-tax charts
TAX = EARTH_GREEN             # tax series
RATE = INK                    # implicit / effective rate lines (dashed)
ACCENT = GOLD                 # highlighted single series (bars only, too light for lines)

# income groups, plus tax havens
INCOME_GROUP = {"Low income": TEAL, "Lower middle income": RED, "Upper middle income": EARTH_GREEN,
                "High income": PURPLE, "Tax havens": BROWN, "World": INK}
INCOME_GROUP_BARS = {**INCOME_GROUP, "Lower middle income": GOLD}      # gold for bars, red for lines
# blocs
BLOC = {"OECD": PURPLE, "G77": EARTH_GREEN, "Tax havens": BROWN, "Other": TEAL, "World": INK}
# Article 5 camps of the UN tax convention negotiations (not used by the chapter scripts here)
CAMP = {"market/source": EARTH_GREEN, "value creation": PURPLE, "balanced": BROWN}
# wealth groups (figC10): richest darkest
WEALTH_GROUP = {"Top 1%": PURPLE, "Next 9%": tint(PURPLE, 0.6), "Next 40%": tint(PURPLE, 0.3), "Bottom 50%": EARTH_GREEN}
# rate bands, lowest first
RATE_BANDS = [PURPLE, tint(PURPLE, 0.65), tint(PURPLE, 0.35), tint(PURPLE, 0.15)]
# stacked destinations: largest first
STACK = [PURPLE, EARTH_GREEN, RED, TEAL, BROWN, BLUE, tint(PURPLE, 0.6), tint(EARTH_GREEN, 0.6), tint(RED, 0.6), tint(TEAL, 0.6)]
