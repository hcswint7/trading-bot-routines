#!/usr/bin/env python3
"""
Routine 1: Pre-Market Evaluation
Cron: 30 7 * * 1-5  (7:30 AM America/Chicago)

Required Notion database property names
────────────────────────────────────────
Trading COP (8d5a118d-ed5b-4cdf-a054-cd24e31b8199):
  Name            title
  Symbol          rich_text
  Status          select   → "Proposed" | "Executed" | "Cancelled"
  Entry           number
  Stop            number
  Target          number
  R:R             number
  Conviction      number
  Qty             number
  Sector          rich_text
  Catalyst        rich_text
  Date            date
  Source Tiers    rich_text
  Trap Assessment rich_text

Bot Status Log (f27e0571-5ebd-46b5-b329-4203f37a2582):
  Name            title
  Run Date        date
  Status          select   → "SUCCESS" | "HOLD" | "SKIP" | "FAILED"
  Actions Taken   rich_text
  Routine         rich_text
  Proposals       number
  Notes           rich_text
"""

import datetime
import json
import os
import sys
import traceback
from typing import Any, Dict, List, Tuple

import requests

# ─── Constants ─────────────────────────────────────────────────────────────────

NOTION_VERSION          = "2022-06-28"
ALPACA_BASE             = "https://paper-api.alpaca.markets/v2"
GITHUB_FEED_TMPL        = (
    "https://raw.githubusercontent.com/hcswint7/"
    "pre-market-audit-feed/main/research/{date}.json"
)

NOTION_COP_DB_ID        = "8d5a118d-ed5b-4cdf-a054-cd24e31b8199"
NOTION_STATUS_LOG_DB_ID = "f27e0571-5ebd-46b5-b329-4203f37a2582"
NOTION_PARENT_PAGE_ID   = "34e2b136-1dc0-80b1-bf0a-c77bf7beae59"

SIMULATED_EQUITY  = 10_000.0
KILL_SWITCH_FLOOR = 8_500.0
MAX_POSITION_VAL  = 2_000.0
MAX_WEEKLY_TRADES = 3
MAX_OPEN_POS      = 6
MIN_RR            = 2.0

MEGACAPS = frozenset({"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"})

# ─── Environment ───────────────────────────────────────────────────────────────

NOTION_KEY    = os.environ.get("NOTION_API_KEY", "")
ALPACA_KEY    = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY", "")
GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")

today     = datetime.date.today()
today_str = today.strftime("%Y-%m-%d")
day_name  = today.strftime("%A")

# ─── Notion helpers ────────────────────────────────────────────────────────────

def _nh() -> Dict[str, str]:
    return {
        "Authorization":  f"Bearer {NOTION_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type":   "application/json",
    }


def _rt(text: str) -> List[Dict]:
    """Notion rich_text array, hard-capped at 2 000 chars."""
    return [{"type": "text", "text": {"content": str(text)[:2000]}}]


def _n_post(path: str, payload: Dict) -> Dict:
    r = requests.post(
        f"https://api.notion.com/v1{path}",
        headers=_nh(), json=payload, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _n_patch(path: str, payload: Dict) -> Dict:
    r = requests.patch(
        f"https://api.notion.com/v1{path}",
        headers=_nh(), json=payload, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _n_query(db_id: str, body: Dict = None) -> List[Dict]:
    results: List[Dict] = []
    cursor = None
    body = body or {}
    while True:
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=_nh(), json=body, timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results


def _h2_block(text: str) -> Dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": _rt(text)}}


def _para_block(text: str) -> Dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rt(text)}}


# ─── Alpaca helpers ────────────────────────────────────────────────────────────

def _alpaca_get(path: str) -> Any:
    r = requests.get(
        f"{ALPACA_BASE}{path}",
        headers={
            "APCA-API-KEY-ID":     ALPACA_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


# ─── Bot Status Log ────────────────────────────────────────────────────────────

def log_bot_status(
    status: str,
    actions: str,
    proposals: int = 0,
    notes: str = "",
) -> None:
    payload = {
        "parent": {"database_id": NOTION_STATUS_LOG_DB_ID},
        "properties": {
            "Name":          {"title": _rt(f"Routine 1 -- {today_str}")},
            "Run Date":      {"date": {"start": today_str}},
            "Status":        {"select": {"name": status}},
            "Actions Taken": {"rich_text": _rt(actions[:2000])},
            "Routine":       {"rich_text": _rt("Routine 1: Pre-Market Evaluation")},
            "Proposals":     {"number": proposals},
            "Notes":         {"rich_text": _rt(notes[:2000])},
        },
    }
    _n_post("/pages", payload)


# ─── Research summary page ─────────────────────────────────────────────────────

def create_research_page(sections: Dict[str, str]) -> str:
    """Build the Pre-Market Research page; returns the new page ID."""
    blocks: List[Dict] = []
    for heading, body in sections.items():
        blocks.append(_h2_block(heading))
        for line in body.strip().split("\n"):
            blocks.append(_para_block(line or " "))

    # Notion allows ≤ 100 children on page create; append the rest.
    first_100 = blocks[:100]
    overflow  = [blocks[i:i + 100] for i in range(100, len(blocks), 100)]

    page = _n_post("/pages", {
        "parent":     {"page_id": NOTION_PARENT_PAGE_ID},
        "properties": {"title": {"title": _rt(f"Pre-Market Research -- {today_str}")}},
        "children":   first_100,
    })
    page_id = page["id"]

    for batch in overflow:
        _n_patch(f"/blocks/{page_id}/children", {"children": batch})

    return page_id


# ─── COP entry ─────────────────────────────────────────────────────────────────

def write_cop_entry(trade: Dict) -> None:
    payload = {
        "parent": {"database_id": NOTION_COP_DB_ID},
        "properties": {
            "Name":            {"title": _rt(f"{trade['symbol']} -- {today_str}")},
            "Symbol":          {"rich_text": _rt(trade["symbol"])},
            "Status":          {"select": {"name": "Proposed"}},
            "Entry":           {"number": float(trade["entry"])},
            "Stop":            {"number": float(trade["stop"])},
            "Target":          {"number": float(trade["target"])},
            "R:R":             {"number": float(trade["rr"])},
            "Conviction":      {"number": float(trade["final_conviction"])},
            "Qty":             {"number": 0},
            "Sector":          {"rich_text": _rt(trade["sector"])},
            "Catalyst":        {"rich_text": _rt(trade["catalyst"][:2000])},
            "Date":            {"date": {"start": today_str}},
            "Source Tiers":    {"rich_text": _rt(", ".join(trade.get("source_tiers", [])))},
            "Trap Assessment": {"rich_text": _rt(trade.get("trap_assessment", ""))},
        },
    }
    _n_post("/pages", payload)


# ─── Weekly trade count ────────────────────────────────────────────────────────

def get_weekly_executed_count() -> int:
    monday = today - datetime.timedelta(days=today.weekday())
    friday = monday + datetime.timedelta(days=4)
    try:
        pages = _n_query(NOTION_COP_DB_ID, {
            "filter": {
                "and": [
                    {"property": "Status", "select": {"equals": "Executed"}},
                    {"property": "Date",   "date":   {"on_or_after":  monday.isoformat()}},
                    {"property": "Date",   "date":   {"on_or_before": friday.isoformat()}},
                ]
            }
        })
        return len(pages)
    except Exception as exc:
        print(f"[WARN] Weekly trade count fetch failed: {exc}", file=sys.stderr)
        return 0


# ─── Sector analysis ───────────────────────────────────────────────────────────

def build_sector_summary(
    tickers: List[Dict], macro: Dict
) -> Tuple[Dict, str]:
    top_set    = set(macro.get("top_sectors_5d", []))
    bottom_set = set(macro.get("bottom_sectors_5d", []))
    by_sector: Dict[str, List] = {}
    for t in tickers:
        by_sector.setdefault(t.get("sector", "Unknown"), []).append(t)

    summary: Dict[str, Dict] = {}
    for sector, members in by_sector.items():
        convs = [float(m.get("conviction", 5)) for m in members]
        rrs   = [float(m.get("rr", 0))         for m in members]
        summary[sector] = {
            "count":    len(members),
            "avg_conv": round(sum(convs) / len(convs), 2),
            "avg_rr":   round(sum(rrs)   / len(rrs),   2),
            "momentum": (
                "TOP"    if sector in top_set    else
                "BOTTOM" if sector in bottom_set else
                "NEUTRAL"
            ),
        }

    lines = [f"{'Sector':<32} {'N':>3} {'AvgConv':>8} {'AvgR:R':>7} {'Momentum':>9}"]
    lines.append("─" * 65)
    for s, info in sorted(summary.items(), key=lambda x: x[1]["avg_conv"], reverse=True):
        lines.append(
            f"{s:<32} {info['count']:>3} {info['avg_conv']:>8.2f} "
            f"{info['avg_rr']:>7.2f} {info['momentum']:>9}"
        )
    return summary, "\n".join(lines)


def _sector_adj(ticker: Dict, macro: Dict) -> float:
    top_set    = set(macro.get("top_sectors_5d", []))
    bottom_set = set(macro.get("bottom_sectors_5d", []))
    s = ticker.get("sector", "")
    if s in top_set:
        return 1.0
    if s in bottom_set:
        return -1.0
    return 0.0


# ─── Megacap staleness ─────────────────────────────────────────────────────────

def _megacap_adj(ticker: Dict) -> float:
    if ticker.get("symbol", "").upper() not in MEGACAPS:
        return 0.0
    sources = ticker.get("catalyst_sources", [])
    if not sources:
        return 0.0
    # 5 trading days ≈ 7 calendar days
    cutoff = today - datetime.timedelta(days=7)
    all_stale = all(
        datetime.date.fromisoformat(s["published_ct"]) < cutoff
        for s in sources
        if s.get("published_ct")
    )
    return -2.0 if all_stale else 0.0


# ─── Ticker evaluation (Steps 2, 3, megacap) ──────────────────────────────────

def evaluate_ticker(t: Dict, macro: Dict) -> Dict:
    symbol     = t.get("symbol", "UNKNOWN").upper()
    flags      = t.get("flags", {})
    src_tiers  = t.get("source_tiers", [])   # ["Tier-1", "Tier-2", ...]
    conviction = float(t.get("conviction", 0))
    price      = float(t.get("price", 0))
    entry      = float(t.get("entry", price))
    rr         = float(t.get("rr", 0))
    vol_m      = float(t.get("avg_daily_volume_m", 0))
    cap_b      = float(t.get("market_cap_b", 0))

    out: Dict = {
        "symbol":           symbol,
        "sector":           t.get("sector", "Unknown"),
        "base_conviction":  conviction,
        "final_conviction": conviction,
        "rr":               rr,
        "entry":            entry,
        "stop":             float(t.get("stop", 0)),
        "target":           float(t.get("target", 0)),
        "catalyst":         t.get("catalyst", ""),
        "source_tiers":     src_tiers,
        "decision":         "PASS",
        "discard_reason":   "",
        "adjustments":      [],
        "trap_assessment":  "",
    }

    def discard(reason: str) -> Dict:
        out["decision"]       = "DISCARD"
        out["discard_reason"] = reason
        return out

    # ── Hard discards ──────────────────────────────────────────────────────────
    only_t3 = len(src_tiers) == 1 and src_tiers[0] == "Tier-3"
    if only_t3:
        return discard("Single Tier-3 source only")
    if flags.get("trap_flag_count", 0) >= 4:
        return discard(f"trap_flag_count={flags['trap_flag_count']} ≥ 4")
    if flags.get("pump_pattern", False):
        return discard("pump_pattern=true")
    if flags.get("earnings_miss_recent", False):
        return discard("earnings_miss_recent=true")
    if flags.get("contradictory_news", False):
        return discard("contradictory_news=true")
    if flags.get("thin_liquidity", False):
        return discard("thin_liquidity=true")
    if vol_m < 5.0:
        return discard(f"avg_daily_volume_m={vol_m:.1f} < 5 M")
    if cap_b < 0.5:
        return discard(f"market_cap_b={cap_b:.2f} < 0.5 B")
    if price < 5.0:
        return discard(f"price=${price:.2f} < $5")
    if rr < MIN_RR:
        return discard(f"R:R={rr:.2f} < {MIN_RR}")
    if not any(t in ("Tier-1", "Tier-2") for t in src_tiers):
        return discard("No Tier-1 or Tier-2 catalyst source")

    # ── Conviction adjustments ─────────────────────────────────────────────────
    adjs: List[str] = out["adjustments"]

    # Single quality source: cap at 7
    if len(src_tiers) == 1 and src_tiers[0] in ("Tier-1", "Tier-2"):
        if conviction > 7.0:
            conviction = 7.0
            adjs.append("cap@7 (single quality source)")

    if flags.get("analyst_only_catalyst", False):
        conviction -= 1.0
        adjs.append("-1 analyst_only_catalyst")
    if flags.get("pre_market_gap_fade_risk", False):
        conviction -= 1.0
        adjs.append("-1 pre_market_gap_fade_risk")
    if flags.get("wide_spread", False):
        conviction -= 1.0
        adjs.append("-1 wide_spread")
    if price > entry * 1.03:
        conviction -= 1.0
        adjs.append("-1 price>3% above entry")

    # Sector momentum (Step 2)
    s_adj = _sector_adj(t, macro)
    if s_adj:
        conviction += s_adj
        adjs.append(f"{'+' if s_adj > 0 else ''}{s_adj:.0f} sector_momentum")

    # Megacap staleness (Step 3)
    mc_adj = _megacap_adj(t)
    if mc_adj:
        conviction += mc_adj
        adjs.append(f"{mc_adj:.0f} megacap_stale")

    out["final_conviction"] = round(min(conviction, 10.0), 2)
    out["trap_assessment"] = (
        f"trap_flags={flags.get('trap_flag_count', 0)}, "
        f"pump={flags.get('pump_pattern', False)}, "
        f"thin_liq={flags.get('thin_liquidity', False)}, "
        f"wide_spread={flags.get('wide_spread', False)}, "
        f"sources={','.join(src_tiers)}"
    )
    return out


# ─── Macro gate (Step 4) ───────────────────────────────────────────────────────

def parse_macro_gate(macro: Dict) -> Dict:
    vix     = float(macro.get("vix", 20))
    spy_pm  = float(macro.get("spy_premarket_change_pct", 0))
    spy_vol = str(macro.get("spy_premarket_volume", "normal")).lower()

    halt         = False
    weekly_cap   = MAX_WEEKLY_TRADES
    floor_bonus  = 0.0
    conv_penalty = 0.0
    parts: List[str] = []

    if vix > 35:
        halt = True
        parts.append(f"VIX={vix:.1f} >35 EXTREME: all proposals halted")
    elif vix >= 25:
        weekly_cap   = 1
        floor_bonus  = 1.0
        conv_penalty = 1.0
        parts.append(f"VIX={vix:.1f} ELEVATED: weekly_cap=1, floor+1, conv-1")
    elif vix >= 18:
        parts.append(f"VIX={vix:.1f} NORMAL")
    else:
        parts.append(f"VIX={vix:.1f} COMPLACENT")

    if not halt:
        if spy_pm <= -3.0:
            halt = True
            parts.append(f"SPY PM={spy_pm:.2f}% ≤-3%: risk-off HOLD")
        elif spy_pm <= -1.5 and spy_vol == "heavy":
            weekly_cap  = min(weekly_cap, 1)
            floor_bonus = max(floor_bonus, 1.0)
            parts.append(f"SPY PM={spy_pm:.2f}% heavy vol: cap=1, floor+1")

    return {
        "halt":         halt,
        "weekly_cap":   weekly_cap,
        "floor_bonus":  floor_bonus,
        "conv_penalty": conv_penalty,
        "reason":       " | ".join(parts),
        "vix":          vix,
        "spy_pm":       spy_pm,
    }


# ─── Conviction floor (Step 5) ─────────────────────────────────────────────────

def conviction_floor(open_count: int, floor_bonus: float) -> float:
    if open_count == 0:
        base = 6.0
    elif open_count == 1:
        base = 6.5
    elif open_count == 2:
        base = 7.0
    else:
        base = 7.5
    return base + floor_bonus


# ─── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_positions(positions: List[Dict]) -> str:
    if not positions:
        return "No open positions."
    lines = []
    for p in positions:
        pct = float(p.get("unrealized_plpc", 0)) * 100
        lines.append(
            f"  {p['symbol']}: qty={p['qty']:.0f}, "
            f"entry=${p['avg_entry']:.2f}, current=${p['current_price']:.2f}, "
            f"P/L={pct:+.1f}%"
        )
    return "\n".join(lines)


def _fmt_eval_table(evaluated: List[Dict]) -> str:
    header = (
        f"{'Symbol':<8} {'BaseConv':>8} {'FinalConv':>9} {'R:R':>5} "
        f"{'Decision':<9} Detail"
    )
    lines = [header, "─" * 90]
    for e in evaluated:
        detail = e.get("discard_reason") or "; ".join(e.get("adjustments", []))
        lines.append(
            f"{e['symbol']:<8} {e['base_conviction']:>8.1f} "
            f"{e['final_conviction']:>9.2f} {e['rr']:>5.1f} "
            f"{e['decision']:<9} {detail}"
        )
    return "\n".join(lines)


def _fmt_proposals(proposals: List[Dict]) -> str:
    if not proposals:
        return "HOLD -- zero proposals met all criteria."
    parts = []
    for p in proposals:
        adjs = "; ".join(p["adjustments"]) or "none"
        parts.append(
            f"SYMBOL:      {p['symbol']}\n"
            f"  Sector:    {p['sector']}\n"
            f"  Entry:     {p['entry']}  Stop: {p['stop']}  Target: {p['target']}\n"
            f"  R:R:       {p['rr']}   Conviction: {p['final_conviction']}\n"
            f"  Adj:       {adjs}\n"
            f"  Trap:      {p['trap_assessment']}\n"
            f"  Sources:   {', '.join(p['source_tiers'])}\n"
            f"  Catalyst:  {p['catalyst'][:300]}\n"
            f"  Qty:       0  (Manus sets at 8:30 AM CT)"
        )
    return "\n\n".join(parts)


def _fmt_account(
    equity: float, cash: float, bp: float, pdt: int,
    open_count: int, weekly_exec: int, weekly_cap: int,
) -> str:
    return (
        f"Paper equity:      ${equity:.2f}\n"
        f"Simulated equity:  ${SIMULATED_EQUITY:.2f} (sizing base)\n"
        f"Cash:              ${cash:.2f}\n"
        f"Buying Power:      ${bp:.2f}\n"
        f"PDT count:         {pdt}\n"
        f"Open positions:    {open_count}/{MAX_OPEN_POS}\n"
        f"Weekly executed:   {weekly_exec}/{weekly_cap}"
    )


def _fmt_market(macro: Dict, gate: Dict) -> str:
    return (
        f"VIX:               {gate['vix']:.2f}\n"
        f"SPY pre-market:    {gate['spy_pm']:+.2f}%  "
        f"volume={macro.get('spy_premarket_volume', 'N/A')}\n"
        f"Top sectors 5d:    {', '.join(macro.get('top_sectors_5d', ['N/A']))}\n"
        f"Bottom sectors 5d: {', '.join(macro.get('bottom_sectors_5d', ['N/A']))}\n"
        f"Macro gate:        {gate['reason']}"
    )


# ─── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[Routine 1] {today_str} ({day_name}) — starting")

    # Validate required env vars
    missing = [
        k for k in ("NOTION_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY")
        if not os.environ.get(k)
    ]
    if missing:
        msg = f"Missing required env vars: {', '.join(missing)}"
        print(f"[FATAL] {msg}", file=sys.stderr)
        try:
            log_bot_status("FAILED", msg)
        except Exception:
            pass
        sys.exit(1)

    # ── STEP 1: Alpaca account state ───────────────────────────────────────────
    print("[Step 1] Alpaca paper account state...")
    try:
        account   = _alpaca_get("/account")
        positions = _alpaca_get("/positions")
        orders    = _alpaca_get("/orders?status=open")
    except Exception as exc:
        msg = f"Alpaca API error: {exc}"
        print(f"[FATAL] {msg}", file=sys.stderr)
        log_bot_status("FAILED", msg)
        sys.exit(1)

    equity       = float(account.get("equity", 0))
    cash         = float(account.get("cash", 0))
    buying_power = float(account.get("buying_power", 0))
    pdt_count    = int(account.get("daytrade_count", 0))

    open_pos: List[Dict] = []
    for p in (positions if isinstance(positions, list) else []):
        open_pos.append({
            "symbol":          p.get("symbol", ""),
            "qty":             float(p.get("qty", 0)),
            "avg_entry":       float(p.get("avg_entry_price", 0)),
            "current_price":   float(p.get("current_price", 0)),
            "unrealized_plpc": float(p.get("unrealized_plpc", 0)),
        })
    open_count   = len(open_pos)
    open_orders  = len(orders) if isinstance(orders, list) else 0

    print(
        f"  equity=${equity:.2f}  cash=${cash:.2f}  bp=${buying_power:.2f}  "
        f"PDT={pdt_count}  open_pos={open_count}  open_orders={open_orders}"
    )

    # Kill switch
    if equity < KILL_SWITCH_FLOOR:
        msg = f"KILL_SWITCH_TRIPPED: equity=${equity:.2f} < ${KILL_SWITCH_FLOOR:.0f}"
        print(f"[STOP] {msg}")
        log_bot_status("SKIP", msg)
        sys.exit(0)

    # Position hard cap
    if open_count >= MAX_OPEN_POS:
        msg = f"Position hard cap: {open_count}/{MAX_OPEN_POS} open — no new proposals possible"
        print(f"[STOP] {msg}")
        log_bot_status("HOLD", msg)
        sys.exit(0)

    # Weekly trade count
    weekly_executed = get_weekly_executed_count()
    print(f"  Weekly executed: {weekly_executed}/{MAX_WEEKLY_TRADES}")
    if weekly_executed >= MAX_WEEKLY_TRADES:
        msg = (
            f"Weekly trade cap reached: {weekly_executed}/{MAX_WEEKLY_TRADES} "
            f"executed this week — HOLD"
        )
        print(f"[STOP] {msg}")
        log_bot_status("HOLD", msg)
        sys.exit(0)

    # ── STEP 1.5: Research feed ────────────────────────────────────────────────
    feed_url = GITHUB_FEED_TMPL.format(date=today_str)
    print(f"[Step 1.5] Fetching research feed: {feed_url}")

    gh_headers: Dict[str, str] = {"User-Agent": "trading-bot-routine-1/1.0"}
    if GITHUB_TOKEN:
        gh_headers["Authorization"] = f"token {GITHUB_TOKEN}"

    def _hold_feed_missing(reason: str, write_page: bool = True) -> None:
        msg = f"PERPLEXITY_RESEARCH_FEED_MISSING -- no autonomous fallback by design. {reason}"
        print(f"[STOP] {msg}")
        log_bot_status("SKIP", msg)
        if write_page:
            try:
                create_research_page({
                    "PERPLEXITY FEED STATUS": (
                        f"Feed unavailable.\nURL: {feed_url}\nReason: {reason}"
                    ),
                    "OVERALL ASSESSMENT": "HOLD by design — no autonomous fallback.",
                })
            except Exception as ne:
                print(f"[WARN] Research page write failed: {ne}", file=sys.stderr)
        sys.exit(0)

    try:
        resp = requests.get(feed_url, headers=gh_headers, timeout=15)
        if resp.status_code == 404:
            _hold_feed_missing("HTTP 404 — file not found on GitHub")
        resp.raise_for_status()
        research_data: Dict = resp.json()
    except json.JSONDecodeError as exc:
        _hold_feed_missing(f"Malformed JSON: {exc}")
    except SystemExit:
        raise
    except Exception as exc:
        _hold_feed_missing(f"Network/HTTP error: {exc}")

    feed_status  = str(research_data.get("status", "OK")).upper()
    tickers_raw: List[Dict] = research_data.get("research", [])
    macro: Dict  = research_data.get("macro_context", {})

    if feed_status == "FAILED":
        notes = research_data.get("notes", "Perplexity reported FAILED status")
        _hold_feed_missing(f"status=FAILED — {notes}")

    if not isinstance(tickers_raw, list) or len(tickers_raw) == 0:
        _hold_feed_missing("research array is empty or missing", write_page=False)
        # log_bot_status called inside; sys.exit(0) called inside

    partial_note = ""
    if feed_status == "PARTIAL":
        partial_note = f"Perplexity ran PARTIAL — {len(tickers_raw)} tickers present."
        print(f"[WARN] {partial_note}")

    print(f"  Feed OK: status={feed_status}  tickers={len(tickers_raw)}")

    # ── STEP 2: Sector drill-down ──────────────────────────────────────────────
    print("[Step 2] Sector analysis...")
    _sector_summary, sector_text = build_sector_summary(tickers_raw, macro)

    # ── STEP 4: Macro gate ─────────────────────────────────────────────────────
    print("[Step 4] Macro gate...")
    gate = parse_macro_gate(macro)
    print(f"  {gate['reason']}")

    if gate["halt"]:
        msg = f"MACRO_GATE_HALT: {gate['reason']}"
        print(f"[STOP] {msg}")
        log_bot_status("HOLD", msg)
        try:
            create_research_page({
                "ACCOUNT STATUS":         _fmt_account(equity, cash, buying_power, pdt_count, open_count, weekly_executed, gate["weekly_cap"]),
                "PERPLEXITY FEED STATUS": f"status={feed_status}  tickers={len(tickers_raw)}\nURL: {feed_url}\n{partial_note}",
                "MARKET ENVIRONMENT":     _fmt_market(macro, gate),
                "SECTOR DRILL-DOWN":      sector_text,
                "EVALUATION TABLE":       "Halted before ticker evaluation — macro gate tripped.",
                "TRADE IDEAS":            f"HOLD\n{gate['reason']}",
                "RISK FACTORS":           "Extreme VIX or SPY pre-market conditions.",
                "HELD POSITION UPDATES":  _fmt_positions(open_pos),
                "OVERALL ASSESSMENT":     f"HOLD — macro gate tripped. {gate['reason']}",
            })
        except Exception as ne:
            print(f"[WARN] Research page write failed: {ne}", file=sys.stderr)
        sys.exit(0)

    # ── STEP 3 + 5: Evaluate tickers & apply conviction floor ─────────────────
    print("[Step 3/5] Evaluating tickers...")
    evaluated = [evaluate_ticker(t, macro) for t in tickers_raw]

    # Apply VIX conviction penalty (Step 6 formula: - vix_floor_adjustment)
    conv_pen  = gate["conv_penalty"]
    c_floor   = conviction_floor(open_count, gate["floor_bonus"])
    print(f"  conv_floor={c_floor}  conv_penalty={conv_pen}  weekly_cap={gate['weekly_cap']}")

    for e in evaluated:
        if e["decision"] == "PASS" and conv_pen > 0:
            e["final_conviction"] = round(e["final_conviction"] - conv_pen, 2)
            e["adjustments"].append(f"-{conv_pen:.0f} VIX_elevated")

    # ── STEP 6: Generate proposals ─────────────────────────────────────────────
    candidates = sorted(
        [
            e for e in evaluated
            if e["decision"] == "PASS"
            and e["final_conviction"] >= c_floor
            and e["rr"] >= MIN_RR
        ],
        key=lambda x: (x["final_conviction"], x["rr"]),
        reverse=True,
    )

    remaining_weekly = min(gate["weekly_cap"], MAX_WEEKLY_TRADES) - weekly_executed
    remaining_slots  = MAX_OPEN_POS - open_count
    proposal_limit   = max(0, min(3, remaining_weekly, remaining_slots))
    print(f"  candidates={len(candidates)}  proposal_limit={proposal_limit}")

    proposals: List[Dict] = []
    for c in candidates:
        if len(proposals) >= proposal_limit:
            break
        entry = c["entry"]
        if entry <= 0:
            c["decision"] = "SKIP"
            c["discard_reason"] = "entry price = 0"
            continue
        max_qty = int(MAX_POSITION_VAL / entry)
        if max_qty < 1:
            c["decision"] = "SKIP"
            c["discard_reason"] = (
                f"entry=${entry:.2f} exceeds ${MAX_POSITION_VAL:.0f} per-position cap"
            )
            continue
        proposals.append(c)

    # ── STEP 7: Write to Trading COP ──────────────────────────────────────────
    cop_errors: List[str] = []
    if proposals:
        print(f"[Step 7] Writing {len(proposals)} proposal(s) to COP...")
        for p in proposals:
            try:
                write_cop_entry(p)
                print(f"  [COP ✓] {p['symbol']}  conv={p['final_conviction']}  rr={p['rr']}")
            except Exception as exc:
                err = f"COP write failed for {p['symbol']}: {exc}"
                print(f"  [ERROR] {err}", file=sys.stderr)
                cop_errors.append(err)

    # ── STEP 8: Research summary page ─────────────────────────────────────────
    print("[Step 8] Writing research summary page...")
    if not proposals:
        hold_reasons: List[str] = []
        if not candidates:
            hold_reasons.append(f"no tickers cleared conv_floor={c_floor}")
        elif proposal_limit == 0:
            hold_reasons.append(
                f"proposal_limit=0 "
                f"(weekly_remaining={remaining_weekly}, slots={remaining_slots})"
            )
        hold_reasons.append(gate["reason"])
        ideas_text = f"HOLD\nReasons: {' | '.join(hold_reasons)}"
    else:
        ideas_text = _fmt_proposals(proposals)

    risk_lines = [
        f"Open positions:    {open_count}/{MAX_OPEN_POS}",
        f"PDT count:         {pdt_count}",
        f"VIX:               {gate['vix']:.2f}",
        f"SPY pre-market:    {gate['spy_pm']:+.2f}%",
        f"Conviction floor:  {c_floor}",
        f"Weekly remaining:  {remaining_weekly}",
    ]
    overall = (
        f"{'SUCCESS: ' + str(len(proposals)) + ' proposal(s) generated.' if proposals else 'HOLD: 0 proposals.'}\n"
        f"Candidates: {len(candidates)}/{len(tickers_raw)}. "
        f"Conv floor: {c_floor}. VIX: {gate['vix']:.2f}."
        + (f"\nCOP errors: {'; '.join(cop_errors)}" if cop_errors else "")
    )

    sections: Dict[str, str] = {
        "ACCOUNT STATUS":         _fmt_account(equity, cash, buying_power, pdt_count, open_count, weekly_executed, gate["weekly_cap"]),
        "PERPLEXITY FEED STATUS": f"status={feed_status}  tickers={len(tickers_raw)}\nURL: {feed_url}\n{partial_note}",
        "MARKET ENVIRONMENT":     _fmt_market(macro, gate),
        "SECTOR DRILL-DOWN":      sector_text,
        "EVALUATION TABLE":       _fmt_eval_table(evaluated),
        "TRADE IDEAS":            ideas_text,
        "RISK FACTORS":           "\n".join(risk_lines),
        "HELD POSITION UPDATES":  _fmt_positions(open_pos),
        "OVERALL ASSESSMENT":     overall,
    }
    try:
        create_research_page(sections)
    except Exception as exc:
        print(f"[ERROR] Research page write failed: {exc}", file=sys.stderr)

    # ── STEP 9: Bot Status Log ─────────────────────────────────────────────────
    print("[Step 9] Bot Status Log...")
    if proposals:
        status  = "SUCCESS"
        actions = (
            f"Proposed {len(proposals)} trade(s): "
            + ", ".join(p["symbol"] for p in proposals)
            + f". Conv_floor={c_floor}. VIX={gate['vix']:.2f}."
            + (f" COP errors: {'; '.join(cop_errors)}" if cop_errors else "")
        )
    else:
        status  = "HOLD"
        actions = (
            f"No trades proposed. "
            f"Candidates: {len(candidates)}/{len(tickers_raw)}. "
            f"{gate['reason']}. Conv_floor={c_floor}."
        )

    try:
        log_bot_status(status, actions, proposals=len(proposals))
    except Exception as exc:
        print(f"[ERROR] Bot Status Log write failed: {exc}", file=sys.stderr)

    print(f"[Routine 1] Done — {status}")


# ─── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc()
        print(f"[FATAL] Unhandled exception:\n{tb}", file=sys.stderr)
        try:
            log_bot_status(
                "FAILED",
                f"Unhandled exception: {str(sys.exc_info()[1])[:500]}",
                notes=tb[:2000],
            )
        except Exception:
            pass
        sys.exit(1)
