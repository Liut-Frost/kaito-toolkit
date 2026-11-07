"""
debug_fvg.py
Standalone diagnostic: prints raw candles and every detected FVG for one
symbol/timeframe, so you can line them up against your TradingView chart
candle-by-candle and spot exactly where detection diverges.

Usage:
    python debug_fvg.py GBPUSD h4
    python debug_fvg.py EURUSD m15
"""

import sys
import json
from data_fetch import TwelveDataClient
import ict_engine as ict


def main():
    if len(sys.argv) < 3:
        print("Usage: python debug_fvg.py <SYMBOL_LABEL> <TIMEFRAME_LABEL>")
        print("  SYMBOL_LABEL: EURUSD, GBPUSD, or DXY")
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

    if symbol_label == "DXY":
        print("DXY is synthetic -- run this against EURUSD/GBPUSD/USDJPY/etc components instead.")
        return

    symbol = config["symbols"][symbol_label]
    interval = config["timeframes"][tf_label]
    df = client.get_candles(symbol, interval, outputsize=100)

    print(f"\n=== Last 20 raw candles: {symbol_label} [{tf_label} = {interval}] ===")
    print(df.tail(20).to_string())

    fvgs = ict.detect_fvgs(df)
    ict.mark_filled_fvgs(fvgs, df)

    print(f"\n=== Detected FVGs (last 10) ===")
    for f in fvgs[-10:]:
        c1_time = df.index[f.start_index]
        c3_time = df.index[f.end_index]
        print(f"{f.direction:8s} | top={f.top:.5f} bottom={f.bottom:.5f} | "
              f"candle1={c1_time} candle3={c3_time} | filled={f.filled}")


if __name__ == "__main__":
    main()
