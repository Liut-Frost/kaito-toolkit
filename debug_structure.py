"""
debug_structure.py
Standalone diagnostic: prints swing points and BOS/CHOCH/MSS structure
events for one symbol/timeframe, so you can line them up against your own
chart read candle-by-candle -- same purpose as debug_fvg.py, but for the
Domain 1 structure engine.

Usage:
    python debug_structure.py GBPUSD h4
    python debug_structure.py EURUSD m15
"""

import sys
import json
from data_fetch import TwelveDataClient
import ict_engine as ict


def main():
    if len(sys.argv) < 3:
        print("Usage: python debug_structure.py <SYMBOL_LABEL> <TIMEFRAME_LABEL>")
        print("  SYMBOL_LABEL: EURUSD or GBPUSD")
        print("  TIMEFRAME_LABEL: monthly, weekly, daily, h4, or m15")
        return

    symbol_label, tf_label = sys.argv[1], sys.argv[2]

    with open("config.json") as f:
        config = json.load(f)

    client = TwelveDataClient(
        config["twelvedata_api_key"],
        request_delay=config.get("api_delay_seconds", 8.0),
        display_tz=config.get("display_timezone", "UTC"),
    )

    symbol = config["symbols"][symbol_label]
    interval = config["timeframes"][tf_label]
    df = client.get_candles(symbol, interval, outputsize=150)

    swings = ict.detect_swings(df)
    fvgs = ict.detect_fvgs(df)
    ict.mark_filled_fvgs(fvgs, df)
    state = ict.analyze_market_structure(df, swings, fvgs)

    print(f"\n=== Last 20 raw candles: {symbol_label} [{tf_label} = {interval}] ===")
    print(df.tail(20).to_string())

    print(f"\n=== Swing points (last 15 of {len(swings)}) ===")
    for s in swings[-15:]:
        print(f"{s.kind:5s} | idx={s.index:4d} | {df.index[s.index]} | {s.price:.5f}")

    print(f"\n=== Structure events -- BOS / CHOCH / MSS (last 15 of {len(state.events)}) ===")
    for e in state.events[-15:]:
        fvg_note = ""
        if e.fvg:
            fvg_note = f" | fvg=[{e.fvg.bottom:.5f}-{e.fvg.top:.5f}]"
        precond_note = " (precondition NOT checked -- see analyze_market_structure docstring)" if e.kind == "MSS" else ""
        print(f"{e.kind:6s} | scope={e.scope:8s} | {e.direction:7s} | idx={e.index:4d} | "
              f"{e.time} | broke {e.broken_swing.kind}@{e.broken_swing.price:.5f}"
              f"{fvg_note}{precond_note}")

    print(f"\n=== Current state ===")
    print(f"Internal trend : {state.internal_trend}")
    print(f"Internal high  : {state.internal_high}")
    print(f"Internal low   : {state.internal_low}")
    print(f"External trend : {state.external_trend}")
    print(f"External high  : {state.external_high}")
    print(f"External low   : {state.external_low}")


if __name__ == "__main__":
    main()
