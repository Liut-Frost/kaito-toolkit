"""
trade_math.py
SL = beyond the Order Block.
TP = nearest draw on liquidity on the 4H timeframe.
Setups under 1:3 RR are discarded.
"""

from dataclasses import dataclass
from typing import Optional, Literal
import pandas as pd
from ict_engine import OrderBlock, Swing

Direction = Literal["bullish", "bearish"]


@dataclass
class TradePlan:
    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float
    rr: float
    valid: bool
    reason: str = ""


def nearest_4h_liquidity_target(h4_df: pd.DataFrame, h4_swings: list[Swing],
                                 direction: Direction, entry_price: float) -> Optional[float]:
    """
    TP = nearest 4H liquidity draw in the direction of the trade.
    Bullish trade -> nearest untaken swing HIGH above entry.
    Bearish trade -> nearest untaken swing LOW below entry.
    """
    kind = "high" if direction == "bullish" else "low"
    candidates = [s for s in h4_swings if s.kind == kind]

    if direction == "bullish":
        above = [s.price for s in candidates if s.price > entry_price]
        return min(above) if above else None
    else:
        below = [s.price for s in candidates if s.price < entry_price]
        return max(below) if below else None


def build_trade_plan(order_block: OrderBlock, entry_price: float,
                      h4_df: pd.DataFrame, h4_swings: list[Swing],
                      min_rr: float = 3.0, sl_buffer_pips: float = 0.0004) -> TradePlan:
    """
    sl_buffer_pips default was widened from 0.0002 to 0.0004 to account for
    cross-provider forex data variance -- your data feed (TwelveData) won't
    have identical wicks to your own broker/chart, so a small extra buffer
    beyond the OB avoids getting stopped out by a discrepancy that isn't a
    real structural break, just a quoting difference between providers.
    """
    direction = order_block.direction

    if direction == "bullish":
        stop_loss = order_block.low - sl_buffer_pips
    else:
        stop_loss = order_block.high + sl_buffer_pips

    take_profit = nearest_4h_liquidity_target(h4_df, h4_swings, direction, entry_price)

    if take_profit is None:
        return TradePlan(direction, entry_price, stop_loss, 0.0, 0.0, False,
                          "No 4H liquidity target found")

    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit - entry_price)
    rr = reward / risk if risk > 0 else 0.0

    valid = rr >= min_rr
    reason = "" if valid else f"RR {rr:.2f} below minimum {min_rr}"

    return TradePlan(direction, entry_price, stop_loss, take_profit, rr, valid, reason)
