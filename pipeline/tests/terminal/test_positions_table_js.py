"""Node-driven tests for positions-table.js — armed-trail stop display.

Tracking item: Track A #10 (2026-04-23). When peak_pnl > |daily_stop|, the
trail is armed and the daily stop becomes INERT per signal_tracker.py. The UI
must reflect this: Stop cell should not show a misleading "active-looking"
number. User language: "stop loss there must be only trailing and the actual
stop loss should not exist" (for Sovereign Shield Alpha-style armed positions).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPONENT = REPO_ROOT / "pipeline/terminal/static/js/components/positions-table.js"


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not on PATH")
    return node


def _run_harness(body: str) -> dict:
    script = _PRELUDE + "\n" + body
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False,
                                      dir=str(REPO_ROOT), encoding="utf-8") as f:
        f.write(script)
        temp_path = f.name
    try:
        proc = subprocess.run(
            [_node(), temp_path],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"Node harness failed (rc={proc.returncode})\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise AssertionError(f"no JSON in harness stdout:\n{proc.stdout}")


_PRELUDE = r"""
import { pathToFileURL } from 'node:url';
function makeContainer() {
  let html = '';
  return {
    get innerHTML() { return html; },
    set innerHTML(v) { html = v; },
  };
}
globalThis.makeContainer = makeContainer;
const modUrl = pathToFileURL(process.cwd() + '/pipeline/terminal/static/js/components/positions-table.js').href;
globalThis.pos = await import(modUrl);
"""


def test_unarmed_position_shows_daily_stop_value():
    """Peak (0.4%) < |daily_stop| (2.0%) → trail not armed → daily stop active."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'FOO', signal_id: 'X', open_timestamp: '2026-04-23T09:30',
  spread_pnl_pct: 0.4, daily_stop: -2.0, trail_stop: null, peak_pnl: 0.4,
  source: 'CORRELATION_BREAK',
}], {});
const html = c.innerHTML;
console.log(JSON.stringify({
  // Stop cell should contain the -2.00 reading
  stop_cell_has_value: html.includes('-2.00'),
  // Should NOT be marked armed/inert
  stop_cell_has_inert_marker: html.includes('trail armed') || html.includes('daily stop inert'),
}));
""")
    assert result["stop_cell_has_value"], "unarmed: Stop cell must still show -2.00%"
    assert not result["stop_cell_has_inert_marker"], \
        "unarmed: no 'trail armed' marker expected"


def test_armed_position_hides_daily_stop_with_inert_marker():
    """Peak (8.0%) > |daily_stop| (0.99%) → trail armed → daily stop INERT.
    User's Sovereign Shield Alpha case. Stop cell should not show the
    misleading 0.99% as if it were live."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'Sovereign Shield Alpha', signal_id: 'X',
  open_timestamp: '2026-04-15T09:30',
  spread_pnl_pct: 5.5, daily_stop: -0.99, trail_stop: 4.0, peak_pnl: 8.0,
  source: 'SPREAD',
}], {});
const html = c.innerHTML;
// Grab the Stop cell (6th td in the row)
const rowMatch = html.match(/<tr[^>]*>([\s\S]*?)<\/tr>/g) || [];
// First <tr> is the thead row; data row is the last one that contains 'Sovereign Shield Alpha'
const dataRow = rowMatch.find(r => r.includes('Sovereign Shield Alpha')) || '';
const cells = (dataRow.match(/<td[^>]*>[\s\S]*?<\/td>/g) || []);
// Column order: Name, Legs, Entry→LTP, Opened, P&L, Today, Stop, Trail, Peak, Held, Source
const stopCell = cells[6] || '';
const trailCell = cells[7] || '';
console.log(JSON.stringify({
  // When armed, stop cell must NOT show "-0.99" as a live value
  stop_cell_raw: stopCell,
  stop_has_misleading_value: /-0\.99/.test(stopCell.replace(/title=['"][^'"]*['"]/g, '')),
  stop_has_inert_marker: /trail armed|daily stop inert|INERT/i.test(stopCell),
  // Trail cell should still show 4.00
  trail_has_value: /\+?4\.00/.test(trailCell),
}));
""")
    assert not result["stop_has_misleading_value"], (
        f"armed position must not display -0.99% as a live stop value. "
        f"Stop cell: {result['stop_cell_raw']}"
    )
    assert result["stop_has_inert_marker"], (
        f"armed position must show 'trail armed' or 'INERT' marker. "
        f"Stop cell: {result['stop_cell_raw']}"
    )
    assert result["trail_has_value"], "Trail cell must still show the trail stop value"


def test_armed_threshold_is_peak_above_abs_daily_stop():
    """Exact threshold boundary: peak == |daily_stop| (1.00) is NOT armed
    (needs strictly greater). peak > |daily_stop| is armed."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [
  {spread_name: 'boundary_not_armed', signal_id: 'A', daily_stop: -1.0, trail_stop: null, peak_pnl: 1.0, source: 'SPREAD'},
  {spread_name: 'just_armed',         signal_id: 'B', daily_stop: -1.0, trail_stop: 0.5,  peak_pnl: 1.01, source: 'SPREAD'},
], {});
const html = c.innerHTML;
const rows = html.match(/<tr[^>]*>([\s\S]*?)<\/tr>/g) || [];
const notArmedRow = rows.find(r => r.includes('boundary_not_armed')) || '';
const armedRow = rows.find(r => r.includes('just_armed')) || '';
console.log(JSON.stringify({
  not_armed_shows_stop: /-1\.00/.test(notArmedRow),
  armed_hides_stop: !/-1\.00/.test(armedRow.replace(/title=['"][^'"]*['"]/g, '')),
}));
""")
    assert result["not_armed_shows_stop"], "boundary peak == |stop| → still unarmed → show stop"
    assert result["armed_hides_stop"], "peak > |stop| → armed → hide stop value"


def test_multi_leg_basket_shows_per_leg_entry_ltp():
    """Sovereign Shield Alpha case: multi-leg basket must show every leg's
    entry + LTP + pnl%, not the bare em-dash. User: 'even soverign shield
    alpha must have entry prices and LTP -- screen must look informative'."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'Sovereign Shield Alpha', signal_id: 'X',
  open_timestamp: '2026-04-15T09:30',
  spread_pnl_pct: 1.0, daily_stop: -2.0, trail_stop: null, peak_pnl: 1.0,
  source: 'SPREAD',
  long_legs: [
    {ticker: 'HAL', entry: 4284.8, current: 4364.6, pnl_pct: 1.86},
    {ticker: 'BEL', entry: 449.85, current: 448.4, pnl_pct: -0.32},
  ],
  short_legs: [
    {ticker: 'TCS', entry: 2572.0, current: 2534.3, pnl_pct: 1.47},
  ],
}], {});
const html = c.innerHTML;
const rowMatch = html.match(/<tr[^>]*>([\s\S]*?)<\/tr>/g) || [];
const dataRow = rowMatch.find(r => r.includes('Sovereign Shield Alpha')) || '';
const cells = (dataRow.match(/<td[^>]*>[\s\S]*?<\/td>/g) || []);
// Column order: Name, Legs, Entry→LTP, Opened, P&L, Stop, Trail, Peak, Held, Source
const priceCell = cells[2] || '';
console.log(JSON.stringify({
  price_cell: priceCell,
  shows_hal_entry: /4[,]?284\.80/.test(priceCell),
  shows_hal_current: /4[,]?364\.60/.test(priceCell),
  shows_bel_entry: /449\.85/.test(priceCell),
  shows_bel_current: /448\.40/.test(priceCell),
  shows_tcs_entry: /2[,]?572\.00/.test(priceCell),
  shows_tcs_current: /2[,]?534\.30/.test(priceCell),
  shows_hal_ticker: /HAL/.test(priceCell),
  shows_bel_ticker: /BEL/.test(priceCell),
  shows_tcs_ticker: /TCS/.test(priceCell),
  // Must not be the legacy em-dash-only cell
  is_not_bare_dash: !/^<td[^>]*>[\s\W]*—[\s\W]*<\/td>$/.test(priceCell),
  // Short legs must be visually distinguished from longs
  distinguishes_short_leg: /short|S:|SHORT/.test(priceCell),
}));
""")
    assert result["is_not_bare_dash"], \
        f"multi-leg must not render bare em-dash; got: {result['price_cell']}"
    assert result["shows_hal_ticker"] and result["shows_hal_entry"] and result["shows_hal_current"], \
        f"HAL leg missing from price cell: {result['price_cell']}"
    assert result["shows_bel_ticker"] and result["shows_bel_entry"] and result["shows_bel_current"], \
        f"BEL leg missing from price cell: {result['price_cell']}"
    assert result["shows_tcs_ticker"] and result["shows_tcs_entry"] and result["shows_tcs_current"], \
        f"TCS leg missing from price cell: {result['price_cell']}"
    assert result["distinguishes_short_leg"], \
        f"short leg (TCS) must be visually distinguished: {result['price_cell']}"


def test_multi_leg_basket_without_prices_falls_back_gracefully():
    """Leg with only ticker (no entry/current) — don't crash, just show ticker."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'Legacy Basket', signal_id: 'X',
  open_timestamp: '2026-04-15T09:30',
  spread_pnl_pct: 0.5, source: 'SPREAD',
  long_legs: ['INFY', 'TCS'],
  short_legs: ['HDFCBANK'],
}], {});
const html = c.innerHTML;
console.log(JSON.stringify({
  contains_infy: /INFY/.test(html),
  contains_hdfcbank: /HDFCBANK/.test(html),
  rendered: true,
}));
""")
    assert result["rendered"], "render must succeed on string-only legs"
    assert result["contains_infy"] and result["contains_hdfcbank"], \
        "tickers must still appear even without entry/current prices"


def test_today_column_shows_todays_move_distinct_from_cumulative():
    """Track A #5: Positions table must have a 'Today' column showing
    p.todays_move (today's spread move) separate from the cumulative 'P&L'
    (p.spread_pnl_pct). User: 'it is showing Unrealized total P&L -- it is
    misleading. Need Yesterday close - LTP'."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'TestSpread', signal_id: 'X',
  open_timestamp: '2026-04-20T09:30', open_date: '2026-04-20',
  spread_pnl_pct: 7.5, todays_move: 1.2,
  daily_stop: -2.0, trail_stop: null, peak_pnl: 7.5,
  source: 'SPREAD',
}], {});
const html = c.innerHTML;
// Must have "Today" header cell
const hasTodayHeader = /<th[^>]*>[^<]*Today[^<]*<\/th>/i.test(html);
const rowMatch = html.match(/<tr[^>]*>([\s\S]*?)<\/tr>/g) || [];
const dataRow = rowMatch.find(r => r.includes('TestSpread')) || '';
// Today value should be 1.2 (+1.20%), cumulative should be 7.5 (+7.50%)
const shows_today_value = /\+1\.20/.test(dataRow);
const shows_cum_value = /\+7\.50/.test(dataRow);
console.log(JSON.stringify({
  has_today_header: hasTodayHeader,
  shows_today_value,
  shows_cum_value,
  data_row: dataRow,
}));
""")
    assert result["has_today_header"], \
        f"positions table must have a 'Today' column header. HTML did not match"
    assert result["shows_today_value"], \
        f"Today column must render +1.20% for a position with todays_move=1.2. Row: {result['data_row']}"
    assert result["shows_cum_value"], \
        f"P&L column must still render +7.50% cumulative. Row: {result['data_row']}"


def test_today_column_flags_stale_snapshot():
    """When prev_close snapshot is missing, backend silently returns
    todays_move == cumulative. Position opened > 0 days ago with
    todays_move == spread_pnl_pct should carry a warning marker so user
    knows Today is really cum-since-entry."""
    result = _run_harness(r"""
const c = makeContainer();
const today = new Date().toISOString().slice(0, 10);
const yesterday = new Date(Date.now() - 86400_000).toISOString().slice(0, 10);
pos.render(c, [
  {spread_name: 'stale_snap', signal_id: 'A',
   open_date: yesterday, spread_pnl_pct: 5.11, todays_move: 5.11,
   source: 'SPREAD'},
  {spread_name: 'fresh_today', signal_id: 'B',
   open_date: today, spread_pnl_pct: 2.0, todays_move: 2.0,
   source: 'SPREAD'},
], {});
const html = c.innerHTML;
const rows = html.match(/<tr[^>]*>([\s\S]*?)<\/tr>/g) || [];
const staleRow = rows.find(r => r.includes('stale_snap')) || '';
const freshRow = rows.find(r => r.includes('fresh_today')) || '';
console.log(JSON.stringify({
  stale_has_warning: /⚠|snapshot.missing|stale/i.test(staleRow),
  fresh_no_warning: !/⚠|snapshot.missing|stale/i.test(freshRow),
}));
""")
    assert result["stale_has_warning"], \
        "position opened yesterday with todays_move == cum must flag stale snapshot"
    assert result["fresh_no_warning"], \
        "position opened today with todays_move == cum is correct (day-1 semantics), no warning"


def test_correlation_break_row_emits_break_detail_subrow():
    """Track A #6: CORRELATION_BREAK position rows must be followed by an
    expandable sub-row that shows the break details in lay language
    (z-score, expected move, actual move, classification, regime)."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'Phase C: TECHM OPPORTUNITY',
  signal_id: 'BRK-2026-04-23-TECHM',
  open_date: '2026-04-23', source: 'CORRELATION_BREAK',
  spread_pnl_pct: 2.15, todays_move: 2.15,
  daily_stop: -3.0, trail_stop: 0.15, peak_pnl: 2.15,
  short_legs: [{ticker: 'TECHM', entry: 1600, current: 1565.6, pnl_pct: 2.15}],
  long_legs: [],
  break_detail: {
    symbol: 'TECHM',
    z_score: -4.6, classification: 'OPPORTUNITY',
    regime: 'CAUTION', oi_anomaly: false,
    expected_1d: -0.19, actual_return: 2.85,
    days_in_regime: 3,
  },
}], {});
const html = c.innerHTML;
// Must render something in the break-detail region — e.g. class break-detail,
// or a sub-row carrying the z-score value
const hasBreakDetailMarker = /break-detail|data-break-detail|z-?score/i.test(html);
// The absolute z-score value must appear
const hasZScore = /4\.6|-4\.6/.test(html);
// Classification OPPORTUNITY must be visible (either in the row itself or sub-row)
const hasClassification = /OPPORTUNITY/i.test(html);
// The expected vs actual contrast ("expected -0.19% vs actual +2.85%") is the
// whole point of the sub-row.
const hasExpectedActual = /expected[^<]*-0\.19|actual[^<]*2\.85|expected[^<]*actual/i.test(html);
console.log(JSON.stringify({
  has_break_detail_marker: hasBreakDetailMarker,
  has_z_score: hasZScore,
  has_classification: hasClassification,
  has_expected_actual: hasExpectedActual,
  html_len: html.length,
}));
""")
    assert result["has_break_detail_marker"], \
        "CORRELATION_BREAK row must emit a break-detail marker (sub-row or equivalent)"
    assert result["has_z_score"], \
        "break-detail sub-row must show the z-score value"
    assert result["has_classification"], \
        "break-detail sub-row must show the classification label"
    assert result["has_expected_actual"], \
        "break-detail sub-row must show expected vs actual move"


def test_opportunity_thesis_describes_follow_not_fade():
    """reverse_regime_breaks.py:403 sets direction = LONG if expected>0 else SHORT,
    which is FOLLOW-the-peer-direction logic. The prior UI text said 'fade the
    move back ... (mean-reversion)' — that's the opposite of what the engine
    does. TECHM 2026-04-23 (expected=-0.19, actual=-2.91, shorted) exposed it.
    New text must describe FOLLOW: we trade in the peer-implied direction; target
    = 5-day drift mean; stop = 1.5σ. No 'fade' / 'mean-reversion' wording."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'Phase C: TECHM OPPORTUNITY',
  signal_id: 'BRK-2026-04-23-TECHM', open_date: '2026-04-23',
  source: 'CORRELATION_BREAK', spread_pnl_pct: 3.07, todays_move: 3.07,
  daily_stop: -3.0, trail_stop: 0.15, peak_pnl: 3.07,
  short_legs: [{ticker: 'TECHM', entry: 1530, current: 1483, pnl_pct: 3.07}],
  long_legs: [],
  break_detail: {
    symbol: 'TECHM', z_score: -4.25, classification: 'OPPORTUNITY',
    regime: 'CAUTION', expected_1d: -0.19, actual_return: -2.91,
  },
}], {});
const html = c.innerHTML.toLowerCase();
console.log(JSON.stringify({
  has_fade_wording: /fade the move|mean[- ]reversion/.test(html),
  has_follow_wording: /follow|peer[- ]direction|peer[- ]implied|peer cohort/i.test(c.innerHTML),
  has_target_language: /5[- ]day drift|target/i.test(c.innerHTML),
  has_stop_language: /1\.5|stop/i.test(c.innerHTML),
}));
""")
    assert not result["has_fade_wording"], \
        "OPPORTUNITY thesis must not say 'fade' or 'mean-reversion' — engine follows peer direction"
    assert result["has_follow_wording"], \
        "OPPORTUNITY thesis must describe following peer cohort direction"
    assert result["has_target_language"], \
        "thesis must name the target (5-day drift mean)"
    assert result["has_stop_language"], \
        "thesis must name the stop (1.5σ)"


def test_opportunity_distinguishes_overshoot_vs_lag():
    """Within OPPORTUNITY the engine currently conflates two regimes:
    (a) actual ~ 0 and |expected| large → LAG (stock hasn't caught up);
    (b) |actual| >> |expected| same direction → OVERSHOOT (stock already did move+).
    Until the engine splits them, the UI at least names which case the current
    break fits so the viewer understands what they're trading."""
    result = _run_harness(r"""
const c = makeContainer();
// Overshoot case: TECHM actual=-2.91 is ~15× expected=-0.19
pos.render(c, [{
  spread_name: 'Phase C: TECHM OPPORTUNITY', signal_id: 'X1',
  open_date: '2026-04-23', source: 'CORRELATION_BREAK',
  spread_pnl_pct: 3.0, short_legs: [{ticker: 'TECHM'}], long_legs: [],
  break_detail: {symbol: 'TECHM', z_score: -4.25, classification: 'OPPORTUNITY',
    regime: 'CAUTION', expected_1d: -0.19, actual_return: -2.91},
}], {});
const htmlA = c.innerHTML;
// Lag case: stock barely moved when peers expected big move
pos.render(c, [{
  spread_name: 'Phase C: ABC OPPORTUNITY', signal_id: 'X2',
  open_date: '2026-04-23', source: 'CORRELATION_BREAK',
  spread_pnl_pct: 0.1, short_legs: [{ticker: 'ABC'}], long_legs: [],
  break_detail: {symbol: 'ABC', z_score: 3.5, classification: 'OPPORTUNITY',
    regime: 'CAUTION', expected_1d: -2.0, actual_return: 0.1},
}], {});
const htmlB = c.innerHTML;
console.log(JSON.stringify({
  overshoot_named: /overshoot|already moved|over-?extended/i.test(htmlA),
  lag_named: /lag|catch[- ]up|hasn[' ]?t moved/i.test(htmlB),
}));
""")
    assert result["overshoot_named"], \
        "overshoot case (|actual| >> |expected|) must be named explicitly"
    assert result["lag_named"], \
        "lag case (|actual| << |expected|) must be named explicitly"


def test_non_break_row_emits_no_break_detail_subrow():
    """Only CORRELATION_BREAK source gets the sub-row — SPREAD must not."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'Sovereign Shield Alpha',
  signal_id: 'SIG-X',
  open_date: '2026-04-15', source: 'SPREAD',
  spread_pnl_pct: 5.11, todays_move: 0.5,
  long_legs: [{ticker: 'HAL', entry: 4200, current: 4350, pnl_pct: 3.57}],
  short_legs: [{ticker: 'TCS', entry: 2600, current: 2550, pnl_pct: 1.92}],
}], {});
const html = c.innerHTML;
// SPREAD row must not carry the break-detail decoration. We look for a
// sub-row data attribute or the specific "z=" marker emitted only in
// break-detail cells — NOT the legend text which mentions these words
// for explanation purposes.
const rowsOnly = (html.match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || []).join('');
console.log(JSON.stringify({
  no_break_detail_in_rows: !/data-break-detail|class="[^"]*break-detail/i.test(rowsOnly),
}));
""")
    assert result["no_break_detail_in_rows"], \
        "SPREAD rows must NOT emit break-detail markup"


def test_name_cell_renders_spread_description_as_tooltip():
    """Track A #9: clicking/hovering a Strategy NNN or Sovereign-Shield-Alpha
    name should reveal the real spread and its thesis."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'Sovereign Shield Alpha',
  spread_description: 'Defence vs IT — long defence basket, short IT basket.',
  signal_id: 'X', open_date: '2026-04-15', source: 'SPREAD',
  spread_pnl_pct: 1.0,
  long_legs: [{ticker: 'HAL', entry: 4200, current: 4250, pnl_pct: 1.2}],
  short_legs: [{ticker: 'TCS', entry: 2600, current: 2580, pnl_pct: 0.8}],
}], {});
const html = c.innerHTML;
const rows = html.match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || [];
const dataRow = rows.find(r => r.includes('Sovereign Shield Alpha')) || '';
const cells = (dataRow.match(/<td[^>]*>[\s\S]*?<\/td>/g) || []);
const nameCell = cells[0] || '';
// Real name AND a tooltip attribute must be present
const hasDescriptionTooltip = /title\s*=\s*['"][^'"]*Defence/i.test(nameCell);
const hasStrategyNamedInline = /Sovereign Shield Alpha/.test(nameCell);
console.log(JSON.stringify({
  name_cell: nameCell,
  has_description_tooltip: hasDescriptionTooltip,
  has_strategy_named_inline: hasStrategyNamedInline,
}));
""")
    assert result["has_strategy_named_inline"], \
        f"Name cell must still show the display name: {result['name_cell']}"
    assert result["has_description_tooltip"], \
        f"Name cell must carry spread_description as title tooltip: {result['name_cell']}"


def test_name_cell_tooltip_absent_when_no_description():
    """Legacy rows without spread_description should render fine (no crash,
    no bogus tooltip with an 'undefined' value)."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [{
  spread_name: 'OldThing', signal_id: 'X', open_date: '2026-04-23',
  source: 'SPREAD', spread_pnl_pct: 0.1,
  long_legs: [{ticker: 'X', entry: 100, current: 100, pnl_pct: 0}],
  short_legs: [],
}], {});
const html = c.innerHTML;
const rows = html.match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || [];
const dataRow = rows.find(r => r.includes('OldThing')) || '';
console.log(JSON.stringify({
  no_undefined_title: !/title\s*=\s*['"]undefined['"]/i.test(dataRow),
  no_null_title: !/title\s*=\s*['"]null['"]/i.test(dataRow),
}));
""")
    assert result["no_undefined_title"], "missing description must not produce title='undefined'"
    assert result["no_null_title"], "missing description must not produce title='null'"


def test_tickers_are_wrapped_as_ticker_links():
    """Track A #8: Every ticker shown in Positions / legs / Entry→LTP /
    break-detail must be wrapped in <a class='ticker-link' data-ticker='X'>
    so the global chart-drawer click handler can catch any click."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [
  {
    spread_name: 'S1', signal_id: 'X1', open_date: '2026-04-15',
    source: 'SPREAD', spread_pnl_pct: 1.0,
    long_legs:  [{ticker: 'HAL', entry: 4200, current: 4250, pnl_pct: 1.2}],
    short_legs: [{ticker: 'TCS', entry: 2600, current: 2580, pnl_pct: 0.8}],
  },
  {
    spread_name: 'Phase C: TECHM', signal_id: 'BRK-1', open_date: '2026-04-23',
    source: 'CORRELATION_BREAK', spread_pnl_pct: 2.0,
    short_legs: [{ticker: 'TECHM', entry: 1600, current: 1568, pnl_pct: 2.0}],
    long_legs: [],
    break_detail: {
      symbol: 'TECHM', z_score: -4.6, classification: 'OPPORTUNITY',
      regime: 'CAUTION', oi_anomaly: false,
      expected_1d: -0.19, actual_return: 2.85, days_in_regime: 3,
    },
  },
]);
const html = c.innerHTML;
// Each ticker must be at least once a ticker-link
const halLinks = (html.match(/data-ticker=['"]HAL['"]/g) || []).length;
const tcsLinks = (html.match(/data-ticker=['"]TCS['"]/g) || []).length;
const techmLinks = (html.match(/data-ticker=['"]TECHM['"]/g) || []).length;
console.log(JSON.stringify({
  hal_links: halLinks,
  tcs_links: tcsLinks,
  techm_links: techmLinks,
  has_ticker_link_class: /class=['"][^'"]*ticker-link/.test(html),
}));
""")
    assert result["has_ticker_link_class"], \
        "at least one element must use class='ticker-link'"
    assert result["hal_links"] >= 1, "HAL ticker must have data-ticker attribute"
    assert result["tcs_links"] >= 1, "TCS ticker must have data-ticker attribute"
    assert result["techm_links"] >= 1, "TECHM ticker must have data-ticker attribute"


def test_header_shows_today_basket_pnl_alongside_total():
    """User feedback 2026-04-28: the basket header must surface 'Today' P&L
    next to 'Total P&L'. With trades opened on different days, the cumulative
    total alone is misleading — a +9.9% basket where one trade was opened
    yesterday and another last week reads identically to two-trades-from-today.
    """
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [
  {spread_name: 'A', signal_id: 'X1', open_date: '2026-04-27',
   spread_pnl_pct: 4.34, todays_move: -0.05, source: 'SPREAD',
   long_legs: [{ticker: 'X', entry: 100, current: 104, pnl_pct: 4.34}],
   short_legs: []},
  {spread_name: 'B', signal_id: 'X2', open_date: '2026-04-27',
   spread_pnl_pct: 5.56, todays_move: 1.68, source: 'SPREAD',
   long_legs: [{ticker: 'Y', entry: 100, current: 105.56, pnl_pct: 5.56}],
   short_legs: []},
]);
const html = c.innerHTML;
// Header must include both a Total label and a Today label
const headerMatch = html.match(/<div[^>]*display:\s*flex[^>]*>[\s\S]*?<\/div>/);
console.log(JSON.stringify({
  has_total_pnl_header: /Total P&amp;L/.test(html) || /Total P&L/.test(html),
  has_today_header: /Today:\s*[+\-]\d/.test(html),
  // Sum of -0.05 + 1.68 = +1.63
  today_value_correct: /Today:\s*\+1\.63%/.test(html),
  // Total: +4.34 + +5.56 = +9.90
  total_value_correct: /Total P&amp;L:\s*\+9\.90%|Total P&L:\s*\+9\.90%/.test(html),
}));
""")
    assert result["has_total_pnl_header"], "header must still show Total P&L"
    assert result["has_today_header"], (
        "header must also show 'Today: +X.XX%' so single-day reads aren't "
        "swamped by older trades' cumulative gains"
    )
    assert result["today_value_correct"], (
        f"Today header must sum the per-position todays_move "
        f"(-0.05 + 1.68 = +1.63%)"
    )
    assert result["total_value_correct"], (
        f"Total P&L header must equal sum of cumulative position P&L "
        f"(+4.34 + +5.56 = +9.90%)"
    )


def test_header_shows_dash_when_any_position_lacks_todays_move():
    """If even one position is missing todays_move (backend snapshot gap), the
    aggregate Today figure is incomplete — show '—' rather than a partial
    sum that under-represents today's basket move."""
    result = _run_harness(r"""
const c = makeContainer();
pos.render(c, [
  {spread_name: 'A', signal_id: 'X1', open_date: '2026-04-27',
   spread_pnl_pct: 4.0, todays_move: 1.0, source: 'SPREAD',
   long_legs: [{ticker: 'X', entry: 100, current: 104, pnl_pct: 4.0}], short_legs: []},
  {spread_name: 'B', signal_id: 'X2', open_date: '2026-04-27',
   spread_pnl_pct: 5.0, /* todays_move: missing */ source: 'SPREAD',
   long_legs: [{ticker: 'Y', entry: 100, current: 105, pnl_pct: 5.0}], short_legs: []},
]);
const html = c.innerHTML;
console.log(JSON.stringify({
  today_shows_dash: /Today:\s*—/.test(html),
  today_does_not_show_partial: !/Today:\s*\+1\.00%/.test(html),
}));
""")
    assert result["today_shows_dash"], (
        "with one position missing todays_move, header Today must render '—' "
        "rather than a partial sum"
    )
    assert result["today_does_not_show_partial"], (
        "header Today must not show a misleading partial sum (1.00) when one "
        "position is missing the field"
    )


def test_syntax_smoke():
    proc = subprocess.run(
        [_node(), "--check", str(COMPONENT)],
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0, f"syntax error: {proc.stderr}"
