"""
fractal_engine.py
Orchestrates the full top-down model:

Monthly/Weekly  -> macro context (can cap/invalidate lower TF bias)
Daily           -> actual trade bias
4H              -> zone + TP liquidity pool
Fractal descent -> at each TF drop: tap PD array -> sweep nearest liquidity
                   -> check SMT -> confirm displacement -> new FVG becomes
                   next PD array -> repeat down to M15
M15             -> Order Block identification + entry trigger

This is v1: a deterministic first pass at highly discretionary ICT logic.
Expect to tune thresholds/rules against your own chart reads (see README).
"""

from dataclasses import dataclass, field
from typing import Optional, Literal
import pandas as pd

import ict_engine as ict
from smt import check_smt_divergence, SMTResult
from trade_math import build_trade_plan, TradePlan
from session_filter import is_in_killzone

Direction = Literal["bullish", "bearish"]


@dataclass
class TFAnalysis:
    timeframe: str
    structure_state: Optional[ict.StructureState]
    dealing_range: Optional[ict.DealingRange]
    bias: Optional[Direction]
    pd_array: Optional[ict.FVG]
    note: str = ""


@dataclass
class SignalResult:
    symbol: str
    valid: bool
    trade_plan: Optional[TradePlan]
    reasoning_trail: list[str] = field(default_factory=list)
    order_block: Optional[ict.OrderBlock] = None
    entry_price: Optional[float] = None
    sweep_time: Optional[pd.Timestamp] = None


def analyze_timeframe(df: pd.DataFrame) -> TFAnalysis:
    swings = ict.detect_swings(df)
    fvgs = ict.detect_fvgs(df)
    ict.mark_filled_fvgs(fvgs, df)
    legs = ict.detect_displacement_legs(df, swings, fvgs)
    dealing_range = ict.build_dealing_range(legs)
    structure_state = ict.analyze_market_structure(df, swings, fvgs)

    # Bias now comes from validated External structure (Domain 1) rather
    # than the legacy displacement-leg heuristic. Falls back to the old
    # heuristic only when structure hasn't confirmed an external trend yet
    # (e.g. too little history for an MSS) -- this should get rarer as more
    # domains land and preconditions tighten what counts as "confirmed."
    bias = None
    pd_array = None
    if structure_state.external_trend:
        bias = structure_state.external_trend
    elif legs:
        bias = legs[-1].direction
    if dealing_range and bias:
        pd_array = ict.relevant_pd_array(dealing_range, fvgs, bias)

    return TFAnalysis(
        timeframe="", structure_state=structure_state,
        dealing_range=dealing_range, bias=bias, pd_array=pd_array,
    )


def macro_context_check(monthly: TFAnalysis, weekly: TFAnalysis, daily_bias: Direction) -> tuple[bool, str]:
    """
    Monthly/Weekly act as a filter, not a signal source. If price is sitting
    inside a monthly/weekly PD array opposing the daily bias, that caps
    conviction -- v1 treats this as a hard block; loosen this if it's too
    conservative once you've watched it run.
    """
    for label, analysis in [("Monthly", monthly), ("Weekly", weekly)]:
        if analysis.pd_array and analysis.pd_array.direction != daily_bias:
            return False, f"{label} PD array ({analysis.pd_array.direction}) opposes Daily bias ({daily_bias}) -- context blocks trade"
    return True, "Monthly/Weekly context does not oppose Daily bias"


def fractal_descend(
    symbol: str,
    daily_df: pd.DataFrame,
    h4_df: pd.DataFrame,
    m15_df: pd.DataFrame,
    daily_bias: Direction,
    other_symbol: str,
    other_h4_df: pd.DataFrame,
    dxy_h4_df: pd.DataFrame,
    min_rr: float = 3.0,
    require_killzone: bool = True,
    killzone_config: Optional[dict] = None,
) -> SignalResult:
    trail = []
    trail.append(f"Daily bias established: {daily_bias}")

    # --- Session / Killzone filter check ---
    latest_m15_time = m15_df.index[-1]
    in_kz, kz_name = is_in_killzone(latest_m15_time, killzone_config)

    if require_killzone and not in_kz:
        trail.append(f"Session filter: {latest_m15_time} is outside active ICT killzones -- skipping setup")
        return SignalResult(symbol, False, None, trail)
    elif in_kz:
        trail.append(f"Session filter: active inside {kz_name} killzone ({latest_m15_time})")

    # --- 4H: zone identification ---
    h4_swings = ict.detect_swings(h4_df)
    h4_fvgs = ict.detect_fvgs(h4_df)
    ict.mark_filled_fvgs(h4_fvgs, h4_df)
    h4_legs = ict.detect_displacement_legs(h4_df, h4_swings, h4_fvgs)
    h4_range = ict.build_dealing_range(h4_legs)

    if not h4_range:
        trail.append("4H: no qualifying dealing range found -- no setup")
        return SignalResult(symbol, False, None, trail)

    h4_pd_array = ict.relevant_pd_array(h4_range, h4_fvgs, daily_bias)
    if not h4_pd_array:
        trail.append("4H: no relevant PD array on the correct side of the range -- no setup")
        return SignalResult(symbol, False, None, trail)

    trail.append(f"4H: relevant {h4_pd_array.direction} FVG identified as zone "
                 f"[{h4_pd_array.bottom:.5f} - {h4_pd_array.top:.5f}]")

    # has price tapped the 4H PD array?
    zone_touch_idx = None
    for i in range(h4_pd_array.end_index, len(h4_df)):
        lo, hi = h4_df["low"].iloc[i], h4_df["high"].iloc[i]
        if lo <= h4_pd_array.top and hi >= h4_pd_array.bottom:
            zone_touch_idx = i
            break

    if zone_touch_idx is None:
        trail.append("4H: price has not yet tapped the PD array -- no setup yet")
        return SignalResult(symbol, False, None, trail)

    trail.append(f"4H: price tapped the PD array at {h4_df.index[zone_touch_idx]}")

    # --- drop to M15: sweep -> SMT -> displacement -> CISD-driven OB ---
    m15_swings = ict.detect_swings(m15_df)
    sweep_direction: Direction = "bearish" if daily_bias == "bearish" else "bullish"

    range_extreme = h4_range.low if daily_bias == "bullish" else h4_range.high
    level = ict.find_nearest_liquidity_level(
        m15_df, m15_swings, len(m15_df) - 1, sweep_direction, range_extreme
    )

    sweep = ict.detect_liquidity_sweep(m15_df, level, sweep_direction, start_index=0)
    if not sweep:
        trail.append(f"M15: no liquidity sweep detected yet at level {level:.5f} -- no setup yet")
        return SignalResult(symbol, False, None, trail)

    trail.append(f"M15: liquidity sweep confirmed at {sweep.time} (level {sweep.level_swept:.5f})")

    # --- SMT check at the sweep ---
    other_swings = ict.detect_swings(other_h4_df)
    dxy_swings = ict.detect_swings(dxy_h4_df)

    smt_vs_pair: SMTResult = check_smt_divergence(
        symbol, m15_df, m15_swings, sweep.index, sweep_direction,
        other_symbol, other_h4_df, other_swings, is_dxy=False,
    )
    smt_vs_dxy: SMTResult = check_smt_divergence(
        symbol, m15_df, m15_swings, sweep.index, sweep_direction,
        "DXY", dxy_h4_df, dxy_swings, is_dxy=True,
    )
    trail.append(f"SMT vs {other_symbol}: {smt_vs_pair.detail}")
    trail.append(f"SMT vs DXY: {smt_vs_dxy.detail}")

    if not (smt_vs_pair.confirmed or smt_vs_dxy.confirmed):
        trail.append("SMT: no divergence confirmed on either correlated instrument -- setup weakened, skipping")
        return SignalResult(symbol, False, None, trail)

    # --- M15: detect CISD events & Order Blocks after the sweep ---
    m15_fvgs = ict.detect_fvgs(m15_df)
    ict.mark_filled_fvgs(m15_fvgs, m15_df)

    # Slice post-sweep for CISD detection
    m15_post_sweep = m15_df.iloc[sweep.index:].copy()
    post_sweep_fvgs = [f for f in m15_fvgs if f.start_index >= sweep.index]

    # Run CISD events detection with Domain 3 isolated displacement support
    cisd_events = ict.detect_cisd_events(m15_df, fvgs=m15_fvgs)
    post_sweep_events = [e for e in cisd_events if e.index >= sweep.index]

    if not post_sweep_events:
        trail.append("M15: no CISD delivery flip confirmed yet after the sweep -- no setup yet")
        return SignalResult(symbol, False, None, trail)

    # Identify order blocks from CISD flips (Domain 2 spec)
    obs = ict.identify_order_blocks_from_cisd(m15_df, post_sweep_events, m15_fvgs)

    # Filter for OBs that align with daily bias and are currently valid
    qualifying_obs = [
        ob for ob in obs
        if ob.direction == daily_bias and ob.valid and not ob.mitigated
    ]

    if not qualifying_obs:
        trail.append(f"M15: CISD occurred but no fresh, unmitigated {daily_bias} Order Block found")
        return SignalResult(symbol, False, None, trail)

    # Pick the most recent qualifying Order Block
    order_block = qualifying_obs[-1]

    # --- Domain 4: Validate OB against HTF context ---
    htf_valid = ict.validate_ob_htf_context(order_block, h4_fvgs, h4_range)
    if not htf_valid:
        trail.append(f"Domain 4 HTF context check: OB failed HTF alignment filter -- skipping setup")
        return SignalResult(symbol, False, None, trail, order_block)

    trail.append(f"M15: CISD-confirmed {order_block.direction.upper()} Order Block at {order_block.time} "
                 f"[{order_block.low:.5f} - {order_block.high:.5f}] (HTF context confirmed)")

    # Entry price selection: alternate entry (CISD candle open) for rapid run, else OB midpoint
    if order_block.alt_entry_price is not None:
        entry_price = order_block.alt_entry_price
        trail.append(f"Entry model: alternate limit @ {entry_price:.5f} (CISD confirming candle open, rapid run)")
        # Structural SL beyond the liquidity sweep
        custom_sl = ict.compute_structural_sl(m15_df, m15_swings, order_block, sweep)
    else:
        entry_price = order_block.mean_threshold
        trail.append(f"Entry model: standard limit @ 50% Mean Threshold {entry_price:.5f}")
        custom_sl = None

    trade_plan = build_trade_plan(order_block, entry_price, h4_df, h4_swings, min_rr=min_rr)

    # Apply custom structural SL if this was an alternate entry path
    if custom_sl is not None:
        trade_plan.stop_loss = custom_sl
        risk = abs(trade_plan.entry - trade_plan.stop_loss)
        reward = abs(trade_plan.take_profit - trade_plan.entry) if trade_plan.take_profit else 0.0
        trade_plan.rr = reward / risk if risk > 0 else 0.0
        trade_plan.valid = trade_plan.rr >= min_rr
        if not trade_plan.valid:
            trade_plan.reason = f"RR {trade_plan.rr:.2f} below minimum {min_rr}"

    trail.append(f"Trade plan: entry {trade_plan.entry:.5f}, SL {trade_plan.stop_loss:.5f}, "
                 f"TP {trade_plan.take_profit if trade_plan.take_profit else 'N/A'}, RR {trade_plan.rr:.2f}")

    if not trade_plan.valid:
        trail.append(f"Filtered out: {trade_plan.reason}")
        return SignalResult(symbol, False, trade_plan, trail, order_block, entry_price, sweep.time)

    trail.append("All conditions met -- signal confirmed")
    return SignalResult(symbol, True, trade_plan, trail, order_block, entry_price, sweep.time)


def run_model(symbol: str, other_symbol: str, dataset: dict, min_rr: float = 3.0,
              require_killzone: bool = True, killzone_config: Optional[dict] = None) -> SignalResult:
    """
    dataset structure: dataset[symbol_label]["monthly"/"weekly"/"daily"/"h4"/"m15"] = df
    """
    monthly = analyze_timeframe(dataset[symbol]["monthly"])
    weekly = analyze_timeframe(dataset[symbol]["weekly"])
    daily = analyze_timeframe(dataset[symbol]["daily"])

    if not daily.bias:
        return SignalResult(symbol, False, None, ["Daily: no clear bias established -- no setup"])

    context_ok, context_note = macro_context_check(monthly, weekly, daily.bias)
    if not context_ok:
        return SignalResult(symbol, False, None, [context_note])

    return fractal_descend(
        symbol=symbol,
        daily_df=dataset[symbol]["daily"],
        h4_df=dataset[symbol]["h4"],
        m15_df=dataset[symbol]["m15"],
        daily_bias=daily.bias,
        other_symbol=other_symbol,
        other_h4_df=dataset[other_symbol]["h4"],
        dxy_h4_df=dataset["DXY"]["h4"],
        min_rr=min_rr,
        require_killzone=require_killzone,
        killzone_config=killzone_config,
    )
