#!/usr/bin/env python
"""Quick test runner for the ICT model."""

import json
from main import load_config, run_once

if __name__ == "__main__":
    config = load_config()

    print("=" * 60)
    print("KAITO TOOLKIT - ICT TRADING MODEL")
    print("=" * 60)
    print(f"\nConfiguration loaded:")
    print(f"  - Symbols: {list(config['symbols'].keys())}")
    print(f"  - Killzone required: {config.get('require_killzone', 'using default')}")
    print(f"  - Minimum RR: {config.get('min_rr', 3.0)}")
    print("\n" + "=" * 60)
    print("RUNNING MODEL...")
    print("=" * 60 + "\n")

    try:
        result = run_once(config)
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        for sym, status in result.items():
            print(f"  {sym}: {status}")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()