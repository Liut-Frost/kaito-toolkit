"""
smt.py
SMT (Smart Money Technique) divergence check between EURUSD, GBPUSD, and DXY.

Checked at the liquidity-sweep step: when one pair sweeps a high/low, do the
correlated instruments confirm (also sweep / make a new extreme) or diverge
(fail to reach an equal high/low)? DXY is inversely correlated, so its
divergence logic is flipped relative to EURUSD/GBPUSD.
"""

import pandas as pd
from dataclasses import dataclass
from typing import Literal
from ict_engine import Swing

Direction = Literal["bullish", "bearish"]


@dataclass
class SMTResult:
    confirmed: bool
    detail: str


def _recent_extreme(df: pd.DataFrame, swings: list[Swing], kind: str, before_index: int, lookback_swings: int = 3):
    candidates = [s for s in swings if s.kind == kind and s.index < before_index]
    if not candidates:
        return None
    candidates = candidates[-lookback_swings:]
    return max(candidates, key=lambda s: s.price) if kind == "high" else min(candidates, key=lambda s: s.price)


def check_smt_divergence(
    primary_symbol: str,
    primary_df: pd.DataFrame,
    primary_swings: list[Swing],
    sweep_index: int,
    sweep_direction: Direction,
    other_symbol: str,
    other_df: pd.DataFrame,
    other_swings: list[Swing],
    is_dxy: bool = False,
) -> SMTResult:
    """
    sweep_direction "bearish" = primary swept a HIGH (expecting reversal down)
    sweep_direction "bullish" = primary swept a LOW (expecting reversal up)

    For EURUSD vs GBPUSD (same correlation): divergence = the other pair does
    NOT make an equal/new extreme at the same time -> confirms SMT.

    For DXY (inverse correlation): if primary swept a high (bearish setup),
    DXY should be making a LOW at the same time. If DXY fails to make a new
    low (i.e. holds higher), that confirms SMT alignment with the primary's
    bearish reversal.
    """
    kind = "high" if sweep_direction == "bearish" else "low"
    other_kind = kind
    if is_dxy:
        # inverse instrument: primary sweeping a high (bearish) pairs with
        # DXY expected to sweep/hold a low
        other_kind = "low" if kind == "high" else "high"

    # find the swing on primary that was swept
    primary_extreme = _recent_extreme(primary_df, primary_swings, kind, sweep_index)
    other_extreme = _recent_extreme(other_df, other_swings, other_kind, sweep_index)

    if primary_extreme is None or other_extreme is None:
        return SMTResult(confirmed=False, detail="Insufficient swing data to compare")

    # Did the "other" instrument fail to reach/break its corresponding extreme
    # around the same time window? That failure = divergence = SMT confirmed.
    window = other_df.loc[other_df.index >= primary_df.index[sweep_index - 5] if sweep_index >= 5 else other_df.index[0]]
    if other_kind == "high":
        other_reached = window["high"].max() >= other_extreme.price
    else:
        other_reached = window["low"].min() <= other_extreme.price

    confirmed = not other_reached
    detail = (
        f"{primary_symbol} swept {kind} while {other_symbol} "
        f"{'also reached' if other_reached else 'failed to reach'} its corresponding {other_kind} "
        f"-> SMT {'NOT confirmed (no divergence)' if other_reached else 'CONFIRMED (divergence present)'}"
    )
    return SMTResult(confirmed=confirmed, detail=detail)
