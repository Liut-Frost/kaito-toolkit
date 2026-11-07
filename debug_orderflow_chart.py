"""
debug_orderflow_chart.py
Renders an annotated candlestick PNG showing CISD-confirmed Order Blocks
and the live pending reference line -- a visual companion to
debug_orderflow.py's text output, same purpose as chart_render.py but for
Domain 2 (Orderflow/CISD) instead of a confirmed trade signal.

Usage:
    python debug_orderflow_chart.py GBPUSD h4
    python debug_orderflow_chart.py EURUSD m15 --candles 100

Output: saves a PNG to /tmp and prints the path. Open it to compare
directly against your TradingView chart.
"""

import sys
import os
import json
import argparse
import mplfinance as mpf
from data_fetch import TwelveDataClient
import ict_engine as ict


def render(symbol_label: str, tf_label: str, candles_to_show: int = 80, outputsize: int = 150) -> str:
    with open("config.json") as f:
        config = json.load(f)

    client = TwelveDataClient(
        config["twelvedata_api_key"],
        request_delay=config.get("api_delay_seconds", 8.0),
        display_tz=config.get("display_timezone", "UTC"),
    )
    symbol = config["symbols"][symbol_label]
    interval = config["timeframes"][tf_label]
    df = client.get_candles(symbol, interval, outputsize=outputsize)

    fvgs = ict.detect_fvgs(df)
    ict.mark_filled_fvgs(fvgs, df)
    events = ict.detect_cisd_events(df)
    obs = ict.identify_order_blocks_from_cisd(df, events, fvgs)
    live = ict.current_cisd_reference(df)

    candles_to_show = min(candles_to_show, len(df))
    plot_df = df.tail(candles_to_show).copy()
    plot_start_idx = len(df) - candles_to_show

    # Only draw OBs that are either visible in this window or still live
    # (unvalidated/unmitigated far-off ones would just clutter the chart;
    # a still-active reference from weeks ago is exactly what matters).
    relevant_obs = [
        ob for ob in obs
        if ob.index >= plot_start_idx - 10 or not ob.invalidated
    ]

    hlines, hcolors = [], []
    for ob in relevant_obs:
        if ob.invalidated:
            color = "#888888"
        elif ob.direction == "bullish":
            color = "#1a8f4c"
        else:
            color = "#c0392b"
        hlines.extend([ob.high, ob.low])
        hcolors.extend([color, color])

    plot_kwargs = dict(
        type="candle",
        style="charles",
        title=f"{symbol_label} {tf_label.upper()} -- CISD / Order Blocks  "
              f"({df.index[-1].strftime('%Y-%m-%d %H:%M')})",
        returnfig=True,
        figsize=(16, 9),
    )
    if hlines:
        plot_kwargs["hlines"] = dict(hlines=hlines, colors=hcolors, linewidths=1.2)

    fig, axes = mpf.plot(plot_df, **plot_kwargs)
    ax = axes[0]

    # Order Block labels, placed at the OB's own candle when it's visible,
    # otherwise pinned to the left edge so a still-live older zone doesn't
    # get lost off-screen.
    for ob in relevant_obs:
        rel_x = max(0, ob.index - plot_start_idx)
        color = "#888888" if ob.invalidated else ("#1a8f4c" if ob.direction == "bullish" else "#c0392b")
        label = f"{'BUY' if ob.direction == 'bullish' else 'SELL'} OB"
        if ob.invalidated:
            label += " (invalidated)"
        elif ob.pending_confirmation:
            label += " (PENDING -- see debug_orderflow.py)"
        elif ob.mitigated:
            label += " (mitigated)"
        else:
            label += " (fresh)"
        if ob.is_rapid:
            label += " [rapid]"
        ax.annotate(label, xy=(rel_x, ob.high), xytext=(rel_x, ob.high),
                    fontsize=7, color=color, va="bottom")

    # Live pending reference line -- dashed, distinct from confirmed OB edges
    if live:
        ax.axhline(y=live["reference_open"], color="#e67e22", linestyle="--", linewidth=1.5, zorder=5)
        ax.annotate(f"LIVE {live['direction']} reference -- what price must break now",
                    xy=(0, live["reference_open"]), xytext=(0, live["reference_open"]),
                    fontsize=8, color="#e67e22", va="bottom", fontweight="bold")

    out_path = os.path.join(os.getcwd(), f"{symbol_label}_{tf_label}_orderflow.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="EURUSD or GBPUSD")
    parser.add_argument("timeframe", help="monthly, weekly, daily, h4, or m15")
    parser.add_argument("--candles", type=int, default=80, help="how many candles to show (default 80)")
    args = parser.parse_args()
    render(args.symbol, args.timeframe, candles_to_show=args.candles)


if __name__ == "__main__":
    main()
