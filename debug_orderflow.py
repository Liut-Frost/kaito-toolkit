"""
debug_orderflow.py
Standalone diagnostic: prints CISD (Change in State of Delivery) events and
the Order Blocks they confirm, for one symbol/timeframe -- same purpose as
debug_structure.py, but for Domain 2.

Usage:
    python debug_orderflow.py GBPUSD h4
    python debug_orderflow.py EURUSD m15
"""

import sys
import json
from data_fetch import TwelveDataClient
import ict_engine as ict


def main():
    if len(sys.argv) < 3:
        print("Usage: python debug_orderflow.py <SYMBOL_LABEL> <TIMEFRAME_LABEL>")
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

    fvgs = ict.detect_fvgs(df)
    ict.mark_filled_fvgs(fvgs, df)
    events = ict.detect_cisd_events(df)
    obs = ict.identify_order_blocks_from_cisd(df, events, fvgs)
    live = ict.current_cisd_reference(df)

    print(f"\n=== Last 20 raw candles: {symbol_label} [{tf_label} = {interval}] ===")
    print(df.tail(20).to_string())

    print(f"\n=== CISD events (last 15 of {len(events)}) ===")
    for e in events[-15:]:
        print(f"{e.direction:7s} | confirmed idx={e.index:4d} {e.time} | "
              f"ref_open={e.reference_open:.5f} (run [{e.run_start_index}-{e.run_end_index}], "
              f"origin {df.index[e.run_start_index]})")

    print(f"\n=== Order Blocks confirmed from those CISD events (last 15 of {len(obs)}) ===")
    for ob in obs[-15:]:
        if ob.invalidated:
            status = "INVALIDATED"
        elif ob.pending_confirmation:
            status = "PENDING (rapid, no FVG/iFVG -- awaiting Domain 4/5, not rejected)"
        elif ob.mitigated:
            status = "mitigated"
        else:
            status = "fresh/unmitigated"

        if ob.fvg:
            validation = "displacement FVG"
        elif ob.ifvg:
            validation = "inversion FVG (rapid path)"
        elif ob.pending_confirmation:
            validation = "none yet -- pending"
        else:
            validation = "NONE -- disqualified"

        rapid_note = f" [RAPID run, len<=2]" if ob.is_rapid else ""
        print(f"{ob.direction:7s} | candle idx={ob.index:4d} {ob.time} | "
              f"zone=[{ob.low:.5f}-{ob.high:.5f}] mean={ob.mean_threshold:.5f} | "
              f"validated via: {validation}{rapid_note} | {status}"
              + (f" @idx={ob.invalidated_index}" if ob.invalidated else
                 (f" @idx={ob.mitigated_index}" if ob.mitigated else "")))
        if ob.alt_entry_price is not None:
            print(f"          --> alternate entry model: limit @ {ob.alt_entry_price:.5f} "
                  f"(CISD confirming candle's open), SL beyond structural sweep "
                  f"(not computable yet -- pending Domain 5)")

    print("\nNOTE: htf_context_checked is False on every OB above -- the HTF "
          "PD-array reaction requirement (Domain 4/5) isn't wired in yet, so "
          "an OB showing here as 'valid' has only passed the FVG + "
          "invalidation checks, not the full 3-part spec.")

    print(f"\n=== LIVE pending reference (what price must break RIGHT NOW) ===")
    if live:
        origin_time = df.index[live["run_start_index"]]
        print(f"Current delivery state : {live['direction']}")
        print(f"Reference line (open)  : {live['reference_open']:.5f}")
        print(f"Anchor candle          : idx={live['run_start_index']} ({origin_time})")
        print(f"Run extends through    : idx={live['run_end_index']} ({df.index[live['run_end_index']]})")
        print("--> Compare this price level directly against your chart right now.")
    else:
        print("No non-doji candles found -- nothing to anchor a reference to.")


if __name__ == "__main__":
    main()
