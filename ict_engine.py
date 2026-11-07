"""
ict_engine.py
Core price-action detection primitives, built to the exact rules defined
in the strategy conversation:

- Swing highs/lows
- Fair Value Gaps (3-candle imbalance)
- Displacement (structure break + contains an FVG)
- Sticky, displacement-anchored dealing range -> premium/discount (50% midpoint)
- Liquidity sweep detection (nearest resting liquidity, either range extreme
  or minor swing/equal high-low)
- Order Block: largest-range opposing candle within a displacement leg,
  zone = full high-to-low range
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Literal

Direction = Literal["bullish", "bearish"]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Swing:
    index: int
    time: pd.Timestamp
    price: float
    kind: Literal["high", "low"]


@dataclass
class FVG:
    start_index: int      # index of the first candle of the 3-candle pattern
    end_index: int         # index of the third candle
    top: float
    bottom: float
    direction: Direction   # bullish FVG = gap up, bearish FVG = gap down
    filled: bool = False


@dataclass
class DisplacementLeg:
    start_index: int
    end_index: int
    direction: Direction
    origin_swing: Swing
    extreme_price: float
    fvgs: list = field(default_factory=list)
    order_block: Optional["OrderBlock"] = None


@dataclass
class OrderBlock:
    index: int
    time: pd.Timestamp
    high: float
    low: float
    direction: Direction   # direction of the TRADE this OB supports (bullish OB = buy zone)

    # --- Domain 2 fields (CISD-driven OB validation/invalidation) ---
    # These default to values that keep the pre-Domain-2 caller
    # (identify_order_block, used by fractal_engine's M15 entry logic)
    # working unchanged -- only the new CISD-based constructor path
    # (identify_order_blocks_from_cisd) populates them meaningfully.
    fvg: Optional["FVG"] = None            # required displacement FVG (non-rapid runs); None = invalid per spec
    fvg_checked: bool = False              # whether the FVG requirement was actually evaluated
    htf_context_checked: bool = False      # pending Domain 4/5 -- always False for now
    mitigated: bool = False
    mitigated_index: Optional[int] = None
    invalidated: bool = False
    invalidated_index: Optional[int] = None

    # --- Rapid-CISD refinement fields (confirmed spec update) ---
    is_rapid: bool = False                 # run was 1-2 candles -- FVG requirement doesn't apply
    ifvg: Optional["FVG"] = None           # the OLDER, opposite-direction FVG this CISD inverted (if any)
    pending_confirmation: bool = False     # rapid run with no FVG/iFVG -- awaiting Domain 4/5, not confirmed invalid
    cisd_event: Optional["CISDEvent"] = None  # backref, needed for the alternate entry rule (CISD candle's open)
    alt_entry_price: Optional[float] = None   # rapid+no-FVG path: limit entry at the CONFIRMING candle's open
    # (distinct from the OB candle's own open/reference_open) -- SL for
    # this path must sit beyond the structural liquidity sweep high/low,
    # not tightly below/above the OB candle itself, per the confirmed
    # spec. That level isn't computable yet -- needs Domain 5 (Liquidity).

    @property
    def mean_threshold(self) -> float:
        """The 50% Mean Threshold -- midpoint of the OB candle's full wick range."""
        return (self.high + self.low) / 2

    @property
    def valid(self) -> bool:
        """
        Mechanically valid per what's currently checkable. Three outcomes:
        - Invalidated (50% breach) -> always False.
        - Non-rapid run with no FVG -> False (hard disqualifier per spec).
        - Rapid run with no FVG and no iFVG -> False for now, but this is
          a PENDING state, not a confirmed rejection -- check
          `pending_confirmation` before treating this as a dead setup.
          HTF context and the equal-high/low trap check aren't wired in
          yet (Domain 4/5), so a `True` here means "valid on the checks
          we can currently make," not "fully validated per the complete
          spec." Always cross-check `htf_context_checked` before trusting
          this in production logic.
        """
        if self.invalidated:
            return False
        if self.fvg_checked and self.fvg is None and self.ifvg is None:
            return False
        return True


@dataclass
class CISDEvent:
    """
    A Change in State of Delivery: the candle whose body close breaches
    the reference line (the opening price of the FIRST candle in the
    immediately preceding opposite-direction run) confirms the flip.
    """
    index: int              # the confirming candle (body closed past the line)
    time: pd.Timestamp
    direction: Direction    # direction the algorithm just flipped INTO
    reference_open: float   # the line itself -- open of the broken run's first candle
    run_start_index: int    # index of that first candle (becomes the OB candle)
    run_end_index: int      # last candle of the broken run, just before the flip
    exception_checked: bool = False  # isolated-displacement exception -- not enforced yet (Domain 3)


@dataclass
class DealingRange:
    high: float
    low: float
    formed_by: DisplacementLeg

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2

    def zone_for(self, price: float) -> str:
        return "premium" if price > self.midpoint else "discount"


@dataclass
class LiquiditySweep:
    index: int
    time: pd.Timestamp
    level_swept: float
    direction: Direction   # "bearish" sweep = swept a high (liquidity above), reversal down expected


@dataclass
class StructureEvent:
    """
    One structural break, classified per the Domain 1 spec:

    - BOS: body close beyond the current EXTERNAL swing, same direction as
      the existing external trend. Continuation, no displacement required.
    - CHOCH: body close beyond the current INTERNAL swing, opposite the
      internal micro-trend. Early warning only, no displacement required.
    - MSS: body close beyond the current EXTERNAL swing, opposite the
      external trend, AND the breaking leg contains an FVG (displacement).
      A confirmed MSS is what promotes/redefines external structure.
    """
    kind: Literal["BOS", "CHOCH", "MSS"]
    index: int
    time: pd.Timestamp
    direction: Direction           # direction the market is now confirmed into
    broken_swing: Swing
    scope: Literal["internal", "external"]
    fvg: Optional[FVG] = None      # the displacement FVG, populated for MSS only
    precondition_checked: bool = False  # see analyze_market_structure() docstring


@dataclass
class StructureState:
    """
    Persistent per-timeframe structure state. Carry this forward call to
    call (per symbol, per timeframe) rather than recomputing blind each
    time new candles close -- callers own the persistence.
    """
    internal_trend: Optional[Direction] = None
    internal_high: Optional[Swing] = None
    internal_low: Optional[Swing] = None
    external_trend: Optional[Direction] = None
    external_high: Optional[Swing] = None
    external_low: Optional[Swing] = None
    events: list = field(default_factory=list)  # list[StructureEvent]

    @property
    def last_event(self) -> Optional[StructureEvent]:
        return self.events[-1] if self.events else None

    @property
    def last_mss(self) -> Optional[StructureEvent]:
        for e in reversed(self.events):
            if e.kind == "MSS":
                return e
        return None


# ---------------------------------------------------------------------------
# Swing detection
# ---------------------------------------------------------------------------

def detect_swings(df: pd.DataFrame) -> list[Swing]:
    """
    Strict ICT 3-candle rule (Domain 1 spec, confirmed):

    Swing High: candle B's high is strictly greater than candle A's (the
    candle before it) AND strictly greater than the next candle whose high
    isn't equal to B's -- i.e. a plateau of equal highs after B does NOT
    complete the pattern; we wait for the first candle after the plateau
    that prints a strictly lower high.

    Swing Low: mirrored -- strictly lower than the prior candle, and the
    pattern only completes once a later candle prints a strictly higher
    low (skipping over any equal-low plateau).

    Wicks only, never candle bodies. Identical rule at every timeframe --
    this function is timeframe-agnostic by design.

    Replaces the old lookback-window fractal approach: that version used a
    wide (currently 3-candle-each-side) window to reduce noise, but per the
    confirmed spec we now use ICT's original 1-candle-each-side definition,
    which catches more (and smaller) swing points.
    """
    swings = []
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    for i in range(1, n - 1):
        # --- swing high candidate ---
        if highs[i] > highs[i - 1]:
            j = i + 1
            while j < n and highs[j] == highs[i]:
                j += 1
            if j < n and highs[j] < highs[i]:
                swings.append(Swing(index=i, time=df.index[i], price=highs[i], kind="high"))

        # --- swing low candidate ---
        if lows[i] < lows[i - 1]:
            j = i + 1
            while j < n and lows[j] == lows[i]:
                j += 1
            if j < n and lows[j] > lows[i]:
                swings.append(Swing(index=i, time=df.index[i], price=lows[i], kind="low"))

    return swings


# ---------------------------------------------------------------------------
# Fair Value Gap detection
# ---------------------------------------------------------------------------

def detect_fvgs(df: pd.DataFrame) -> list[FVG]:
    """
    3-candle imbalance:
    Bullish FVG: candle1.high < candle3.low  (gap between them)
    Bearish FVG: candle1.low  > candle3.high
    """
    fvgs = []
    highs = df["high"].values
    lows = df["low"].values

    for i in range(2, len(df)):
        c1_high, c1_low = highs[i - 2], lows[i - 2]
        c3_high, c3_low = highs[i], lows[i]

        if c1_high < c3_low:
            fvgs.append(FVG(
                start_index=i - 2, end_index=i,
                top=c3_low, bottom=c1_high,
                direction="bullish",
            ))
        elif c1_low > c3_high:
            fvgs.append(FVG(
                start_index=i - 2, end_index=i,
                top=c1_low, bottom=c3_high,
                direction="bearish",
            ))

    return fvgs


def mark_filled_fvgs(fvgs: list[FVG], df: pd.DataFrame) -> None:
    """Mutates fvgs in place, marking filled=True if price has fully closed the gap."""
    closes = df["close"].values
    for fvg in fvgs:
        for i in range(fvg.end_index + 1, len(df)):
            price = closes[i]
            if fvg.direction == "bullish" and price <= fvg.bottom:
                fvg.filled = True
                break
            if fvg.direction == "bearish" and price >= fvg.top:
                fvg.filled = True
                break


# ---------------------------------------------------------------------------
# Displacement detection (structure break + must contain an FVG)
# ---------------------------------------------------------------------------

def detect_displacement_legs(df: pd.DataFrame, swings: list[Swing], fvgs: list[FVG]) -> list[DisplacementLeg]:
    """
    A displacement leg is confirmed when price breaks a prior swing point
    AND the move contains at least one FVG.
    """
    legs = []
    swing_highs = [s for s in swings if s.kind == "high"]
    swing_lows = [s for s in swings if s.kind == "low"]
    closes = df["close"].values

    # Bullish displacement: close breaks above a prior swing high
    for sh in swing_highs:
        for i in range(sh.index + 1, len(df)):
            if closes[i] > sh.price:
                leg_fvgs = [f for f in fvgs if f.direction == "bullish"
                            and sh.index <= f.start_index <= i]
                if leg_fvgs:
                    extreme = df["high"].iloc[sh.index:i + 1].max()
                    legs.append(DisplacementLeg(
                        start_index=sh.index, end_index=i,
                        direction="bullish", origin_swing=sh,
                        extreme_price=extreme, fvgs=leg_fvgs,
                    ))
                break  # only need the first break past this swing

    # Bearish displacement: close breaks below a prior swing low
    for sl in swing_lows:
        for i in range(sl.index + 1, len(df)):
            if closes[i] < sl.price:
                leg_fvgs = [f for f in fvgs if f.direction == "bearish"
                            and sl.index <= f.start_index <= i]
                if leg_fvgs:
                    extreme = df["low"].iloc[sl.index:i + 1].min()
                    legs.append(DisplacementLeg(
                        start_index=sl.index, end_index=i,
                        direction="bearish", origin_swing=sl,
                        extreme_price=extreme, fvgs=leg_fvgs,
                    ))
                break

    return legs


# ---------------------------------------------------------------------------
# Order Block identification
# largest-range opposing candle within the displacement leg, full H-L zone
# ---------------------------------------------------------------------------

def identify_order_block(df: pd.DataFrame, leg: DisplacementLeg) -> Optional[OrderBlock]:
    opposing_kind = "bearish" if leg.direction == "bullish" else "bullish"
    candidates = []

    for i in range(leg.start_index, leg.end_index + 1):
        o, h, l, c = df["open"].iloc[i], df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
        is_opposing = (c < o) if opposing_kind == "bearish" else (c > o)
        if is_opposing:
            candidates.append((i, h, l))

    if not candidates:
        return None

    # pick the candle with the largest range (high - low)
    best = max(candidates, key=lambda x: x[1] - x[2])
    idx, h, l = best
    return OrderBlock(index=idx, time=df.index[idx], high=h, low=l, direction=leg.direction)


# ---------------------------------------------------------------------------
# Sticky dealing range -> premium / discount
# ---------------------------------------------------------------------------

def build_dealing_range(legs: list[DisplacementLeg]) -> Optional[DealingRange]:
    """
    The dealing range is anchored to the MOST RECENT qualifying displacement
    leg (structure break + FVG). It stays fixed until a new qualifying
    displacement leg supersedes it -- callers should re-run this each time
    new candles close and simply take the latest leg.
    """
    if not legs:
        return None
    latest = legs[-1]
    high = max(latest.origin_swing.price, latest.extreme_price)
    low = min(latest.origin_swing.price, latest.extreme_price)
    return DealingRange(high=high, low=low, formed_by=latest)


def relevant_pd_array(dealing_range: DealingRange, fvgs: list[FVG], bias: Direction) -> Optional[FVG]:
    """
    The FVG that matters: on the premium side if bias is bearish,
    discount side if bias is bullish.
    """
    mid = dealing_range.midpoint
    candidates = []
    for f in fvgs:
        if f.filled:
            continue
        center = (f.top + f.bottom) / 2
        if not (dealing_range.low <= center <= dealing_range.high):
            continue
        in_premium = center > mid
        if bias == "bearish" and in_premium and f.direction == "bearish":
            candidates.append(f)
        elif bias == "bullish" and not in_premium and f.direction == "bullish":
            candidates.append(f)

    if not candidates:
        return None
    # prefer the most recent one
    return max(candidates, key=lambda f: f.start_index)


# ---------------------------------------------------------------------------
# Liquidity sweep detection
# nearest resting liquidity: range extreme OR minor swing/equal high-low
# ---------------------------------------------------------------------------

def detect_equal_levels(swings: list[Swing], tolerance_pips: float = 0.0005) -> list[dict]:
    """
    Finds clusters of swing highs or lows at roughly the same price (Domain 5).
    ICT considers equal highs/lows prime liquidity targets because resting
    stops accumulate tightly above/below them.

    Returns a list of dicts:
        {'kind': 'high'|'low', 'price': float, 'count': int, 'swings': list[Swing]}
    sorted by swing count descending (strongest pools first).
    """
    clusters = []
    for kind in ["high", "low"]:
        kind_swings = [s for s in swings if s.kind == kind]
        used = set()

        for i, s1 in enumerate(kind_swings):
            if i in used:
                continue
            matched = [s1]
            for j, s2 in enumerate(kind_swings):
                if i != j and j not in used:
                    if abs(s1.price - s2.price) <= tolerance_pips:
                        matched.append(s2)
                        used.add(j)

            if len(matched) >= 2:
                used.add(i)
                avg_price = sum(s.price for s in matched) / len(matched)
                clusters.append({
                    "kind": kind,
                    "price": avg_price,
                    "count": len(matched),
                    "swings": matched,
                })

    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters


def find_nearest_liquidity_level(df: pd.DataFrame, swings: list[Swing], current_index: int,
                                  direction: Direction, range_extreme: float,
                                  equal_tolerance_pips: float = 0.0005,
                                  pdh: Optional[float] = None,
                                  pdl: Optional[float] = None,
                                  pwh: Optional[float] = None,
                                  pwl: Optional[float] = None) -> float:
    """
    Returns the nearest liquidity level price to target for a sweep (Domain 5).
    Considers (in priority order):
    1. Equal highs/lows clusters (highest-probability liquidity pools)
    2. Previous Day / Previous Week extremes (major institutional reference points)
    3. The dealing-range extreme
    4. Recent swing highs/lows

    Chooses whichever qualifying level is closest to current price.
    """
    current_price = df["close"].iloc[current_index]
    kind = "high" if direction == "bearish" else "low"  # sweeping a high implies bearish reversal expectation
    relevant_swings = [s for s in swings if s.kind == kind and s.index < current_index]

    candidates = [range_extreme]

    # Major session/calendar levels
    if kind == "high":
        if pdh is not None:
            candidates.append(pdh)
        if pwh is not None:
            candidates.append(pwh)
    else:
        if pdl is not None:
            candidates.append(pdl)
        if pwl is not None:
            candidates.append(pwl)

    # Equal highs/lows pools (Domain 5: high priority)
    equal_pools = detect_equal_levels(relevant_swings, tolerance_pips=equal_tolerance_pips)
    for pool in equal_pools:
        if pool["kind"] == kind:
            candidates.append(pool["price"])

    # Recent swing points
    if relevant_swings:
        prices = sorted(s.price for s in relevant_swings)
        candidates.extend(prices[-5:] if kind == "high" else prices[:5])

    # Nearest candidate to current price
    return min(candidates, key=lambda p: abs(p - current_price))


def compute_structural_sl(df: pd.DataFrame, swings: list[Swing], ob: OrderBlock,
                          sweep: LiquiditySweep, buffer_pips: float = 0.0004) -> float:
    """
    For rapid CISD OBs using the alternate entry path (Domain 5):
    The entry is at the confirming candle's open, and the SL cannot sit tightly
    around the small OB candle itself. Instead, it must sit beyond the structural
    liquidity sweep high/low that initiated the reversal leg, plus a small buffer.

    - Bullish trade: SL below the swept low
    - Bearish trade: SL above the swept high
    """
    if ob.direction == "bullish":
        # Find the lowest point of the sweep / reversal leg
        sweep_low = min(df["low"].iloc[sweep.index], sweep.level_swept)
        # Check if any swing low in the immediate vicinity is even lower
        nearby_lows = [s.price for s in swings if s.kind == "low"
                       and abs(s.index - sweep.index) <= 5]
        lowest = min([sweep_low] + nearby_lows)
        return lowest - buffer_pips
    else:
        sweep_high = max(df["high"].iloc[sweep.index], sweep.level_swept)
        nearby_highs = [s.price for s in swings if s.kind == "high"
                        and abs(s.index - sweep.index) <= 5]
        highest = max([sweep_high] + nearby_highs)
        return highest + buffer_pips


def detect_liquidity_sweep(df: pd.DataFrame, level: float, direction: Direction,
                            start_index: int) -> Optional[LiquiditySweep]:
    """
    A sweep = price wicks beyond `level` then closes back on the other side
    (classic "turtle soup" signature).
    """
    for i in range(start_index, len(df)):
        h, l, c = df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
        if direction == "bearish":  # sweeping a high
            if h > level and c < level:
                return LiquiditySweep(index=i, time=df.index[i], level_swept=level, direction=direction)
        else:  # sweeping a low
            if l < level and c > level:
                return LiquiditySweep(index=i, time=df.index[i], level_swept=level, direction=direction)
    return None


# ---------------------------------------------------------------------------
# Structure classification: BOS / CHOCH / MSS (Domain 1 & Domain 5 specs)
# ---------------------------------------------------------------------------

def _check_mss_precondition(df: pd.DataFrame, broken_swing: Swing, fvgs: list[FVG],
                            direction: Direction, break_index: int) -> tuple[bool, str]:
    """
    Evaluates Precondition 2.1 for a Market Structure Shift (MSS) per ICT rules:
    A trend change (MSS) is only confirmed if the reversal originated from:
    1. A liquidity sweep (price wicked past the key swing / resting liquidity
       and closed back inside, creating a 'turtle soup' rejection), OR
    2. Price trading into a qualifying PD array (FVG in discount for bullish,
       premium for bearish) before initiating the reversal leg.

    If neither condition is met, the structural break is classified as a
    continuation (BOS), NOT a true Market Structure Shift.
    """
    origin_idx = broken_swing.index

    # 1. Check for a prior liquidity sweep at or before the reversal origin
    # Look back up to 20 candles before the origin of the reversal leg
    lookback_start = max(0, origin_idx - 20)
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    if direction == "bullish":
        # Expecting bullish reversal: was there a sweep of a low?
        for j in range(lookback_start, origin_idx + 1):
            if lows[j] <= broken_swing.price and closes[j] > broken_swing.price:
                return True, f"Liquidity sweep confirmed at candle {j} (level {broken_swing.price:.5f})"
    else:
        # Expecting bearish reversal: was there a sweep of a high?
        for j in range(lookback_start, origin_idx + 1):
            if highs[j] >= broken_swing.price and closes[j] < broken_swing.price:
                return True, f"Liquidity sweep confirmed at candle {j} (level {broken_swing.price:.5f})"

    # 2. Check if price traded into an opposing FVG (PD array tap)
    for f in fvgs:
        if f.end_index < break_index:
            # For bullish MSS, did price dip into a bullish/discount FVG?
            if direction == "bullish" and f.direction == "bullish":
                for j in range(max(f.end_index, lookback_start), origin_idx + 1):
                    if lows[j] <= f.top and highs[j] >= f.bottom:
                        return True, f"PD array tapped at candle {j} (FVG [{f.bottom:.5f}-{f.top:.5f}])"
            elif direction == "bearish" and f.direction == "bearish":
                for j in range(max(f.end_index, lookback_start), origin_idx + 1):
                    if highs[j] >= f.bottom and lows[j] <= f.top:
                        return True, f"PD array tapped at candle {j} (FVG [{f.bottom:.5f}-{f.top:.5f}])"

    return False, "No prior liquidity sweep or PD array tap detected before structural break"


def analyze_market_structure(df: pd.DataFrame, swings: list[Swing], fvgs: list[FVG]) -> StructureState:
    """
    Single-pass structure engine implementing the confirmed Domain 1 & 5 specs.

    Internal structure pointers are CONTINUOUS: they always track the most
    recently confirmed swing of each kind, whether or not it's ever been
    broken. This matters -- during a sustained trend making a series of
    lower highs (or higher lows), the relevant internal reference for CHOCH
    is always the latest minor swing, not some older, unbroken level from
    earlier in the trend that price never revisits.

    External structure pointers are STICKY: they only change when their own
    level is actually broken (BOS or MSS). When a pointer is broken it goes
    to None and is refilled from whichever internal swing is current at
    that moment.

    MSS PRECONDITION (Domain 5): Enforces Precondition 2.1. An MSS candidate
    (opposite external break + displacement FVG) is only confirmed if preceded
    by a liquidity sweep or PD array tap. If not met, the event is recorded as
    a BOS with precondition_checked=True, avoiding false trend-change flips.
    """
    state = StructureState()
    closes = df["close"].values
    n = len(df)

    swing_highs = sorted([s for s in swings if s.kind == "high"], key=lambda s: s.index)
    swing_lows = sorted([s for s in swings if s.kind == "low"], key=lambda s: s.index)

    def leg_fvg(direction: Direction, start_index: int, end_index: int) -> Optional[FVG]:
        for f in fvgs:
            if f.direction == direction and start_index <= f.start_index <= end_index:
                return f
        return None

    hi_ptr = 0
    lo_ptr = 0

    for i in range(n):
        while hi_ptr < len(swing_highs) and swing_highs[hi_ptr].index < i:
            state.internal_high = swing_highs[hi_ptr]
            hi_ptr += 1
        while lo_ptr < len(swing_lows) and swing_lows[lo_ptr].index < i:
            state.internal_low = swing_lows[lo_ptr]
            lo_ptr += 1

        if state.external_high is None and state.internal_high is not None:
            state.external_high = state.internal_high
        if state.external_low is None and state.internal_low is not None:
            state.external_low = state.internal_low

        # ---------------- upside break ----------------
        if state.internal_high is not None and closes[i] > state.internal_high.price:
            broken = state.internal_high
            breaks_external = state.external_high is not None and closes[i] > state.external_high.price

            if breaks_external:
                fvg = leg_fvg("bullish", broken.index, i)
                is_potential_mss = fvg is not None and state.external_trend == "bearish"

                if is_potential_mss:
                    precond_met, _ = _check_mss_precondition(df, state.external_high, fvgs, "bullish", i)
                    if precond_met:
                        state.events.append(StructureEvent(
                            "MSS", i, df.index[i], "bullish", state.external_high, "external",
                            fvg=fvg, precondition_checked=True,
                        ))
                        state.external_trend = "bullish"
                        state.external_low = state.internal_low
                    else:
                        # Precondition failed: downgrade to BOS, trend remains bearish
                        state.events.append(StructureEvent(
                            "BOS", i, df.index[i], "bullish", state.external_high, "external",
                            fvg=fvg, precondition_checked=True,
                        ))
                else:
                    state.events.append(StructureEvent(
                        "BOS", i, df.index[i], "bullish", state.external_high, "external",
                        precondition_checked=True,
                    ))
                    state.external_trend = "bullish"
                state.external_high = None
            else:
                kind = "CHOCH" if state.internal_trend == "bearish" else "BOS"
                state.events.append(StructureEvent(kind, i, df.index[i], "bullish", broken, "internal",
                                                   precondition_checked=True))

            state.internal_trend = "bullish"
            state.internal_high = None

        # ---------------- downside break ----------------
        if state.internal_low is not None and closes[i] < state.internal_low.price:
            broken = state.internal_low
            breaks_external = state.external_low is not None and closes[i] < state.external_low.price

            if breaks_external:
                fvg = leg_fvg("bearish", broken.index, i)
                is_potential_mss = fvg is not None and state.external_trend == "bullish"

                if is_potential_mss:
                    precond_met, _ = _check_mss_precondition(df, state.external_low, fvgs, "bearish", i)
                    if precond_met:
                        state.events.append(StructureEvent(
                            "MSS", i, df.index[i], "bearish", state.external_low, "external",
                            fvg=fvg, precondition_checked=True,
                        ))
                        state.external_trend = "bearish"
                        state.external_high = state.internal_high
                    else:
                        state.events.append(StructureEvent(
                            "BOS", i, df.index[i], "bearish", state.external_low, "external",
                            fvg=fvg, precondition_checked=True,
                        ))
                else:
                    state.events.append(StructureEvent(
                        "BOS", i, df.index[i], "bearish", state.external_low, "external",
                        precondition_checked=True,
                    ))
                    state.external_trend = "bearish"
                state.external_low = None
            else:
                kind = "CHOCH" if state.internal_trend == "bullish" else "BOS"
                state.events.append(StructureEvent(kind, i, df.index[i], "bearish", broken, "internal",
                                                   precondition_checked=True))

            state.internal_trend = "bearish"
            state.internal_low = None

    return state


# ---------------------------------------------------------------------------
# CISD (Change in State of Delivery) + CISD-driven Order Blocks (Domain 2)
# ---------------------------------------------------------------------------

def _candle_direction(opens: np.ndarray, closes: np.ndarray, i: int) -> Optional[Direction]:
    if closes[i] > opens[i]:
        return "bullish"
    if closes[i] < opens[i]:
        return "bearish"
    return None  # doji -- neither extends nor breaks a run


def _check_isolated_displacement(df: pd.DataFrame, fvgs: list[FVG],
                                  run_start: int, current_idx: int,
                                  run_direction: Direction) -> Optional[int]:
    """
    Domain 3 spec: Isolated-displacement exception.
    Within an extended same-direction run, if a single candle prints an outsized,
    high-momentum move that creates an FVG entirely within its own span, that
    candle is an institutional displacement injection.

    Instead of keeping the reference line anchored all the way back at the run's
    first candle, the reference shifts to this outlier candle's open -- treating
    the pre-outlier move as absorbed and redefining the new delivery baseline.

    Returns the index of the outlier candle, or None if no isolated displacement.
    """
    if current_idx - run_start < 2:
        return None  # Needs some run history to qualify as an isolated event

    # Check if the candle created an FVG starting at or around its index
    for f in fvgs:
        if f.direction == run_direction and f.start_index == current_idx - 1:
            # Verify the candle itself was an outsized move (body > 1.5x average body of the run)
            run_bodies = [abs(df["close"].iloc[k] - df["open"].iloc[k])
                          for k in range(run_start, current_idx)]
            if run_bodies:
                avg_body = sum(run_bodies) / len(run_bodies)
                current_body = abs(df["close"].iloc[current_idx] - df["open"].iloc[current_idx])
                if current_body > 1.5 * avg_body:
                    return current_idx
    return None


def detect_cisd_events(df: pd.DataFrame, fvgs: Optional[list[FVG]] = None) -> list[CISDEvent]:
    """
    Domain 2 & 3 spec: treats an unbroken run of consecutive same-direction
    candles as one macro candle. The reference line is the OPENING price of the
    run's FIRST candle -- unless shifted by an isolated displacement candle (Domain 3).
    A CISD confirms the instant a candle's body closes past that line.
    """
    events, _ = _detect_cisd_events_with_state(df, fvgs=fvgs)
    return events


def current_cisd_reference(df: pd.DataFrame, fvgs: Optional[list[FVG]] = None) -> Optional[dict]:
    """
    The live, still-unconfirmed reference line as of the last candle in
    `df` -- i.e. what a NEW CISD would need to break right now.
    """
    _, state = _detect_cisd_events_with_state(df, fvgs=fvgs)
    return state


def _detect_cisd_events_with_state(df: pd.DataFrame, fvgs: Optional[list[FVG]] = None):
    opens = df["open"].values
    closes = df["close"].values
    n = len(df)
    events = []

    if n == 0:
        return events, None

    # bootstrap: find the first non-doji candle to seed the reference
    start = 0
    while start < n and _candle_direction(opens, closes, start) is None:
        start += 1
    if start >= n:
        return events, None

    ref_direction = _candle_direction(opens, closes, start)
    ref_open = opens[start]
    ref_start_index = start
    ref_end_index = start
    exception_applied = False

    for i in range(start + 1, n):
        d = _candle_direction(opens, closes, i)
        if d is None:
            continue  # doji -- ignore, doesn't extend or break the run
        if d == ref_direction:
            # Check for isolated displacement exception (Domain 3)
            if fvgs:
                outlier = _check_isolated_displacement(df, fvgs, ref_start_index, i, ref_direction)
                if outlier is not None:
                    ref_open = opens[outlier]
                    ref_start_index = outlier
                    exception_applied = True

            ref_end_index = i  # run extends
            continue

        # opposite-direction candle -- test for a CISD breach
        crossed = (closes[i] < ref_open) if ref_direction == "bullish" else (closes[i] > ref_open)
        if crossed:
            events.append(CISDEvent(
                index=i, time=df.index[i], direction=d,
                reference_open=ref_open,
                run_start_index=ref_start_index, run_end_index=ref_end_index,
                exception_checked=True,
            ))
            # new leg begins, anchored to this confirming candle
            ref_direction = d
            ref_open = opens[i]
            ref_start_index = i
            ref_end_index = i
            exception_applied = False
        # else: failed reversal attempt -- reference left unchanged

    state = {
        "direction": ref_direction,
        "reference_open": ref_open,
        "run_start_index": ref_start_index,
        "run_end_index": ref_end_index,
    }
    return events, state


def _find_inversion_fvg(df: pd.DataFrame, fvgs: list[FVG], event: CISDEvent,
                         opposite_direction: Direction) -> Optional[FVG]:
    """
    Looks for an existing, OLDER FVG (formed before this CISD's confirming
    candle) on the OPPOSITE side to the new delivery direction -- the gap
    left behind by the leg that traded INTO this level. An inversion is
    confirmed when the CISD-confirming candle's body close fully closes
    through that gap's far edge, converting former support into
    resistance (or vice versa). This is the mechanically-checkable path
    for validating a rapid (1-2 candle) CISD, per the confirmed spec.
    """
    close = df["close"].iloc[event.index]
    candidates = [f for f in fvgs if f.direction == opposite_direction and f.end_index < event.index]
    candidates.sort(key=lambda f: f.start_index, reverse=True)  # most recent first
    for f in candidates:
        if opposite_direction == "bullish" and close < f.bottom:
            return f
        if opposite_direction == "bearish" and close > f.top:
            return f
    return None


def identify_order_blocks_from_cisd(df: pd.DataFrame, cisd_events: list[CISDEvent],
                                     fvgs: list[FVG]) -> list[OrderBlock]:
    """
    Builds and validates Order Blocks per the Domain 2 spec: the OB candle
    is always the run's first candle (the CISD reference candle) from the
    leg that just got broken -- not the largest-range candle, not the
    last candle before the flip.

    Validation implemented now:
    - Non-rapid runs (3+ candles): the FVG requirement, as before.
    - Rapid runs (1-2 candles): the FVG requirement is replaced per the
      confirmed refinement. Checked now: Inversion FVG (an older, opposite
      -direction gap the confirming candle closed all the way through).
      NOT yet checked: HTF PD-array tap and clean liquidity sweep (both
      need Domain 4/5) -- a rapid CISD with no FVG and no iFVG is left as
      `pending_confirmation=True`, not hard-invalidated, since those two
      paths might still confirm it once built.

    Invalidation implemented now: 50% Mean Threshold breach (a later
    candle body-closing past the OB candle's midpoint) and prior
    mitigation (price already tapped the zone and left before the most
    recent test). Both are evaluated by scanning forward from the OB's
    creation to the end of `df`.
    """
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)
    blocks = []

    for event in cisd_events:
        ob_index = event.run_start_index
        ob_direction = event.direction  # bullish CISD -> bullish (buy) OB, etc.
        ob_high = highs[ob_index]
        ob_low = lows[ob_index]
        mean_threshold = (ob_high + ob_low) / 2

        run_length = event.run_end_index - event.run_start_index + 1
        is_rapid = run_length <= 2

        # --- FVG requirement: must exist within the displacement leg
        # (run_start_index -> confirming candle), on the OB's own direction
        fvg = None
        for f in fvgs:
            if f.direction == ob_direction and event.run_start_index <= f.start_index <= event.index:
                fvg = f
                break

        ifvg = None
        pending_confirmation = False
        if fvg is None and is_rapid:
            opposite = "bearish" if ob_direction == "bullish" else "bullish"
            ifvg = _find_inversion_fvg(df, fvgs, event, opposite)
            if ifvg is None:
                # neither displacement FVG nor iFVG -- HTF tap / liquidity
                # sweep (Domain 4/5) might still validate this; not a
                # confirmed rejection yet.
                pending_confirmation = True

        ob = OrderBlock(
            index=ob_index, time=df.index[ob_index], high=ob_high, low=ob_low,
            direction=ob_direction, fvg=fvg, fvg_checked=True,
            htf_context_checked=False,
            is_rapid=is_rapid, ifvg=ifvg, pending_confirmation=pending_confirmation,
            cisd_event=event,
            alt_entry_price=(df["open"].iloc[event.index] if is_rapid and fvg is None else None),
        )

        # --- scan forward for mitigation and 50%-threshold invalidation ---
        for j in range(event.index + 1, n):
            touched = lows[j] <= ob_high and highs[j] >= ob_low
            if touched and not ob.mitigated:
                ob.mitigated = True
                ob.mitigated_index = j

            if ob_direction == "bullish":
                breached = closes[j] < mean_threshold
            else:
                breached = closes[j] > mean_threshold
            if breached and not ob.invalidated:
                ob.invalidated = True
                ob.invalidated_index = j
                break  # once invalidated, no further state changes matter

        blocks.append(ob)

    return blocks


# ---------------------------------------------------------------------------
# Higher-Timeframe PD-Array Validation (Domain 4)
# ---------------------------------------------------------------------------

def validate_ob_htf_context(ob: OrderBlock, htf_fvgs: list[FVG],
                            htf_dealing_range: Optional[DealingRange],
                            tolerance_pips: float = 0.0010) -> bool:
    """
    Domain 4 spec: Validates an entry Order Block against HTF context.
    An ICT Order Block has highest probability when formed within or reacting
    to a higher-timeframe PD array (confluence across timeframes).

    - Bullish OB: must sit in the discount side of the HTF dealing range
      AND align with or follow a tap into an HTF bullish FVG.
    - Bearish OB: must sit in the premium side of the HTF dealing range
      AND align with or follow a tap into an HTF bearish FVG.

    Sets `ob.htf_context_checked = True` and returns True/False.
    """
    ob.htf_context_checked = True

    # Check 1: Dealing range premium/discount alignment
    if htf_dealing_range:
        midpoint = htf_dealing_range.midpoint
        if ob.direction == "bullish" and ob.low > midpoint:
            # Bullish setup in HTF premium is low-probability
            return False
        elif ob.direction == "bearish" and ob.high < midpoint:
            # Bearish setup in HTF discount is low-probability
            return False

    # Check 2: HTF FVG proximity / reaction
    # The OB zone should overlap with or be near an HTF FVG of the same direction
    matching_fvgs = [f for f in htf_fvgs if f.direction == ob.direction]
    if not matching_fvgs:
        # If no HTF FVGs exist, allow if dealing range was favorable
        return htf_dealing_range is not None

    for f in matching_fvgs:
        # Check for overlap or close proximity
        zone_top = max(ob.high, f.top)
        zone_bottom = min(ob.low, f.bottom)
        # If they overlap or are within tolerance:
        if (ob.low <= f.top + tolerance_pips) and (ob.high >= f.bottom - tolerance_pips):
            return True

    return False

