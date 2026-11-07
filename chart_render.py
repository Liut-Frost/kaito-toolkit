"""
chart_render.py
Renders an annotated M15 candlestick snapshot for a confirmed signal:
shows the Order Block zone, entry, SL, and TP.
"""

import mplfinance as mpf
import pandas as pd
from fractal_engine import SignalResult


def render_signal_chart(symbol: str, m15_df: pd.DataFrame, signal: SignalResult, out_path: str,
                         candles_to_show: int = 80) -> str:
    plot_df = m15_df.tail(candles_to_show).copy()

    addplots = []
    hlines = dict(hlines=[], colors=[], linestyle="--", linewidths=1.0)

    if signal.order_block:
        ob = signal.order_block
        hlines["hlines"].extend([ob.high, ob.low])
        hlines["colors"].extend(["orange", "orange"])

    if signal.trade_plan:
        tp_plan = signal.trade_plan
        hlines["hlines"].extend([tp_plan.entry, tp_plan.stop_loss, tp_plan.take_profit])
        hlines["colors"].extend(["blue", "red", "green"])

    title = f"{symbol} M15 -- {'CONFIRMED SIGNAL' if signal.valid else 'Setup Snapshot'}"

    mpf.plot(
        plot_df,
        type="candle",
        style="charles",
        title=title,
        hlines=hlines if hlines["hlines"] else None,
        savefig=dict(fname=out_path, dpi=150, bbox_inches="tight"),
    )

    return out_path
