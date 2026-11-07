"""
main.py
Entry point. Loads config, fetches data, runs the model for EURUSD and
GBPUSD, and delivers any confirmed signals to Telegram.

Usage:
    python main.py                 # run once
    python main.py --loop          # run continuously, polling every
                                    # config['poll_seconds']
"""

import argparse
import json
import os
import time
import traceback
from datetime import datetime

from data_fetch import fetch_full_dataset, DataFetchError
from fractal_engine import run_model
from chart_render import render_signal_chart
from telegram_alert import deliver_signal, send_telegram_message


def load_config(path: str = "config.json") -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Copy config.example.json to config.json "
            "and fill in your API keys."
        )
    with open(path) as f:
        return json.load(f)


def run_once(config: dict) -> dict:
    """Returns a summary dict per symbol: {"EURUSD": "bearish, no PD array", ...}"""
    print("Fetching data...")
    dataset = fetch_full_dataset(config)

    pairs = [("EURUSD", "GBPUSD"), ("GBPUSD", "EURUSD")]
    summary = {}

    for symbol, other in pairs:
        print(f"Running model for {symbol}...")
        signal = run_model(
            symbol,
            other,
            dataset,
            min_rr=config.get("min_rr", 3.0),
            require_killzone=config.get("require_killzone", True),
            killzone_config=config.get("killzones", None),
        )

        for line in signal.reasoning_trail:
            print(f"  {line}")

        # last trail line is the most informative status for a heartbeat
        summary[symbol] = signal.reasoning_trail[-1] if signal.reasoning_trail else "no data"

        if signal.valid:
            print(f"  >>> SIGNAL CONFIRMED for {symbol} <<<")
            chart_path = f"/tmp/{symbol}_signal.png"
            try:
                render_signal_chart(symbol, dataset[symbol]["m15"], signal, chart_path)
            except Exception:
                print("  Chart rendering failed, sending text-only alert.")
                chart_path = None

            deliver_signal(
                config["telegram_bot_token"],
                config["telegram_chat_id"],
                symbol,
                signal,
                chart_path,
            )
        else:
            print(f"  No confirmed setup for {symbol}.")

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()

    config = load_config(args.config)

    if not args.loop:
        run_once(config)
        return

    poll_seconds = config.get("poll_seconds", 900)
    heartbeat_seconds = config.get("heartbeat_seconds", 4 * 3600)
    last_heartbeat = 0.0

    print(f"Starting loop, polling every {poll_seconds}s, heartbeat every {heartbeat_seconds}s...")
    while True:
        try:
            summary = run_once(config)

            now = time.time()
            if now - last_heartbeat >= heartbeat_seconds:
                lines = [f"<b>Heartbeat</b> -- {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
                lines.append("Still running, no confirmed signal yet." if all(
                    "confirmed" not in v.lower() for v in summary.values()
                ) else "Still running.")
                lines.append("")
                for sym, status in summary.items():
                    lines.append(f"<b>{sym}:</b> {status}")
                send_telegram_message(config["telegram_bot_token"], config["telegram_chat_id"], "\n".join(lines))
                last_heartbeat = now

        except DataFetchError as e:
            print(f"Data fetch error: {e}")
        except Exception:
            print("Unexpected error:")
            traceback.print_exc()
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
