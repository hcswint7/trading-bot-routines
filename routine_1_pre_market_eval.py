#!/usr/bin/env python3
"""
Routine 1: Pre-Market Evaluation
Cron: 30 7 * * 1-5 (America/Chicago)
Role: EVALUATION agent — reads Perplexity research feed, applies rules, proposes 0-3 trades to Notion.
"""

import os
import sys
import json
import logging
from datetime import date, timedelta
from typing import Optional
import requests

# ─── Constants ────────────────────────────────────────────────────────────────

ALPACA_BASE      = "https://paper-api.alpaca.markets/v2"
NOTION_BASE      = "https://api.notion.com/v1"
NOTION_VERSION   = "2022-06-28"
GITHUB_FEED_BASE = (
    "https://raw.githubusercontent.com/hcswint7/pre-market-audit-feed/main/research"
)

COP_DB_ID        = "8d5a118d-ed5b-4cdf-a054-cd24e31b8199"
STATUS_LOG_DB_ID = "f27e0571-5ebd-46b5-b329-4203f37a2582"
PARENT_PAGE_ID   = "34e2b136-1dc0-80b1-bf0a-c77bf7beae59"

MEGACAPS = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"}

SIMULATED_EQUITY      = 10_000
KILL_SWITCH_THRESHOLD = 8_500
MAX_POSITION_VALUE    = 2_000
MAX_WEEKLY_TRADES     = 3
MAX_OPEN_POSITIONS    = 6
MIN_RR                = 2.0
MIN_VOLUME_M          = 5.0
MIN_MARKET_CAP_B      = 0.5
MIN_PRICE             = 5.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# ─── Alpaca helpers ───────────────────────────────────────────────────────────

def _alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
    }


def alpaca_get(path: str) -> any:
    r = requests.get(f"{ALPACA_BASE}{path}", headers=_alpaca_headers(), timeout=15)
    r.raise_for_status()
    return r.json()

# ─── Notion helpers ───────────────────────────────────────────────────────────

def _notion_headers() -> dict:
    return {
        "Authorization":  f"Bearer {os.environ['NOTION_API_KEY']}",
        "Content-Type":   "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def notion_post(path: str, payload: dict) -> dict:
    r = requests.post(
        f"{NOTION_BASE}{path}",
        headers=_notion_headers(),
        json=payload,
        timeout=20,
    )
    if not r.ok:
        log.error("Notion POST %s → %s: %s", path, r.status_code, r.text[:400])
        r.raise_for_status()
    return r.json()


def notion_query_db(db_id: str, filter_body: Optional[dict] = None) -> list:
    payload = {}
    if filter_body:
        payload["filter"] = filter_body
    r = requests.post(
        f"{NOTION_BASE}/databases/{db_id}/query",
        headers=_notion_headers(),
        json=payload,
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("results", [])


def get_db_properties(db_id: str) -> dict:
    r = requests.get(
        f"{NOTION_BASE}/databases/{db_id}",
        headers=_notion_headers(),
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("properties", {})


# ── Block / rich-text builders ────────────────────────────────────────────────

def rt(text: str) -> list:
    return [{"type": "text", "text": {"content": str(text)[:2000]}}]


def h2(text: str) -> dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": rt(text)}}


def para(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": rt(text)}}


def divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def append_blocks(page_id: str, blocks: list) -> None:
    """Appends blocks in batches of 100 (Notion API limit)."""
    for i in range(0, len(blocks), 100):
        notion_post(f"/blocks/{page_id}/children", {"children": blocks[i:i + 100]})

# ─── Property-name resolver ───────────────────────────────────────────────────

def resolve_prop(props: dict, *candidates: str) -> Optional[str]:
    lower_map = {k.lower(): k for k in props}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None

# ─── Research feed ────────────────────────────────────────────────────────────

def fetch_research_feed(today_str: str) -> Optional[dict]:
    url = f"{GITHUB_FEED_BASE}/{today_str}.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            log.warning("Research feed HTTP %s for %s", r.status_code, url)
            return None
        return r.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        log.warning("Research feed error: %s", e)
        return None

# ─── Weekly executed count ────────────────────────────────────────────────────

def _week_bounds(today: date) -> tuple[str, str]:
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat(), (monday + timedelta(days=4)).isoformat()


def get_weekly_executed_count(today: date) -> int:
    mon, fri = _week_bounds(today)
    try:
        results = notion_query_db(
            COP_DB_ID,
            {
                "and": [
                    {"property": "Status", "select": {"equals": "Executed"}},
                    {"property": "Date", "date": {"on_or_after": mon, "on_or_before": fri}},
                ]
            },
        )
        return len(results)
    except Exception as e:
        log.warning("Weekly executed query failed (defaulting to 0): %s", e)
        return 0

# ─── Step 2: Sector drill-down ────────────────────────────────────────────────

def analyze_sectors(research: dict) -> dict:
    tickers    = research.get("research", [])
    macro      = research.get("macro_context", {})
    top_set    = set(macro.get("top_sectors_5d", []))
    bottom_set = set(macro.get("bottom_sectors_5d", []))

    by_sector: dict[str, list] = {}
    for t in tickers:
        by_sector.setdefault(t.get("sector", "Unknown"), []).append(t)

    stats = {}
    for sector, group in by_sector.items():
        convs = [float(g.get("conviction", 5)) for g in group]
        rrs   = [float(g.get("r_r", 0)) for g in group]
        stats[sector] = {
            "count":          len(group),
            "avg_conviction": round(sum(convs) / len(convs), 2),
            "avg_rr":         round(sum(rrs) / len(rrs), 2),
            "momentum": (
                "top"    if sector in top_set    else
                "bottom" if sector in bottom_set else
                "neutral"
            ),
        }

    return {
        "by_sector":    by_sector,
        "stats":        stats,
        "top_sectors":  top_set,
        "bottom_sectors": bottom_set,
    }

# ─── Step 3: Trap filter & quality screen ─────────────────────────────────────

def apply_trap_filter(ticker: dict) -> tuple[bool, str, float]:
    """Returns (keep, discard_reason, conviction_penalty)."""
    symbol  = ticker.get("symbol", "?")
    sources = ticker.get("catalyst_sources", [])
    tiers   = [s.get("tier", 3) for s in sources]
    price   = float(ticker.get("current_price", ticker.get("entry", 0)))

    # ── Hard discards ──────────────────────────────────────────────────────────
    if len(sources) == 1 and all(t == 3 for t in tiers):
        return False, "single_tier3_source", 0.0

    if int(ticker.get("trap_flag_count", 0)) >= 4:
        return False, "trap_flag_count>=4", 0.0

    for flag in ("pump_pattern", "earnings_miss_recent", "contradictory_news", "thin_liquidity"):
        if ticker.get(flag, False):
            return False, flag, 0.0

    if float(ticker.get("avg_daily_volume_m", 0)) < MIN_VOLUME_M:
        return False, f"avg_daily_volume_m<{MIN_VOLUME_M}", 0.0

    if float(ticker.get("market_cap_b", 0)) < MIN_MARKET_CAP_B:
        return False, f"market_cap_b<{MIN_MARKET_CAP_B}", 0.0

    if price < MIN_PRICE:
        return False, f"price<{MIN_PRICE}", 0.0

    # ── Conviction penalties ──────────────────────────────────────────────────
    penalty = 0.0

    for flag in ("analyst_only_catalyst", "pre_market_gap_fade_risk", "wide_spread"):
        if ticker.get(flag, False):
            penalty += 1.0

    entry = float(ticker.get("entry", 0))
    if entry > 0 and price > entry and (price - entry) / entry > 0.03:
        penalty += 1.0

    # ── Megacap stale catalyst guard ──────────────────────────────────────────
    if symbol in MEGACAPS and sources:
        if all(int(s.get("published_days_ago", 0)) > 5 for s in sources):
            penalty += 2.0

    return True, "", penalty

# ─── Step 4: Macro gate ───────────────────────────────────────────────────────

def evaluate_macro(research: dict) -> tuple[bool, int, float]:
    """Returns (proceed, effective_weekly_cap, floor_addon)."""
    macro       = research.get("macro_context", {})
    vix         = float(macro.get("vix", 20))
    spy_pm      = float(macro.get("spy_premarket_change_pct", 0))
    spy_pm_heavy = bool(macro.get("spy_premarket_volume_heavy", False))

    if vix > 35:
        return False, 0, 0.0
    if spy_pm < -3.0:
        return False, 0, 0.0

    weekly_cap  = MAX_WEEKLY_TRADES
    floor_addon = 0.0

    if 25 <= vix <= 35:
        weekly_cap  = 1
        floor_addon = 1.0

    if spy_pm < -1.5 and spy_pm_heavy:
        weekly_cap  = min(weekly_cap, 1)
        floor_addon = max(floor_addon, 1.0)

    return True, weekly_cap, floor_addon

# ─── Step 5: Conviction floor ─────────────────────────────────────────────────

def conviction_floor(open_count: int, floor_addon: float) -> float:
    base_map = {0: 6.0, 1: 6.5, 2: 7.0, 3: 7.5}
    base = base_map.get(open_count, 7.5)
    return base + floor_addon

# ─── Step 6: Generate trade proposals ─────────────────────────────────────────

def generate_proposals(
    research: dict,
    sector_analysis: dict,
    positions: list,
    weekly_executed: int,
) -> tuple[list, str]:
    """Returns (proposals, hold_reason)."""
    proceed, weekly_cap, floor_addon = evaluate_macro(research)
    macro = research.get("macro_context", {})

    if not proceed:
        vix    = float(macro.get("vix", 20))
        spy_pm = float(macro.get("spy_premarket_change_pct", 0))
        if vix > 35:
            return [], f"MACRO_HALT: VIX={vix:.1f} exceeds 35 (EXTREME)"
        return [], f"MACRO_HALT: SPY pre-market {spy_pm:+.2f}% < -3% (risk-off)"

    open_count   = len(positions)
    open_symbols = {p.get("symbol") for p in positions}

    if open_count >= MAX_OPEN_POSITIONS:
        return [], f"POSITION_CAP: {open_count}/{MAX_OPEN_POSITIONS} open positions"

    if weekly_executed >= weekly_cap:
        return [], f"WEEKLY_CAP: {weekly_executed}/{weekly_cap} trades executed this week"

    max_proposals = min(3, MAX_OPEN_POSITIONS - open_count, weekly_cap - weekly_executed)
    floor         = conviction_floor(open_count, floor_addon)
    top_sectors   = sector_analysis["top_sectors"]
    bottom_sectors = sector_analysis["bottom_sectors"]

    candidates = []
    for ticker in research.get("research", []):
        symbol  = ticker.get("symbol", "?")
        sources = ticker.get("catalyst_sources", [])
        tiers   = [s.get("tier", 3) for s in sources]

        if symbol in open_symbols:
            ticker["_discard_reason"] = "already_open_position"
            continue

        if float(ticker.get("r_r", 0)) < MIN_RR:
            ticker["_discard_reason"] = f"r_r={ticker.get('r_r', 0)}<{MIN_RR}"
            continue

        if not any(t in (1, 2) for t in tiers):
            ticker["_discard_reason"] = "no_tier1_or_tier2_source"
            continue

        keep, discard_reason, penalty = apply_trap_filter(ticker)
        ticker["_discard_reason"] = discard_reason
        if not keep:
            continue

        sector     = ticker.get("sector", "Unknown")
        sector_adj = 1 if sector in top_sectors else (-1 if sector in bottom_sectors else 0)

        base_conv  = float(ticker.get("conviction", 0))
        final_conv = base_conv + sector_adj - penalty

        # Single high-quality source: cap at 7
        if len(sources) == 1 and any(t in (1, 2) for t in tiers):
            final_conv = min(final_conv, 7.0)

        final_conv = round(min(10.0, max(0.0, final_conv)), 2)
        ticker["_final_conviction"] = final_conv
        ticker["_sector_adj"]       = sector_adj
        ticker["_penalty"]          = penalty

        if final_conv >= floor:
            candidates.append(ticker)

    if not candidates:
        return [], f"No tickers met conviction floor of {floor} after all filters"

    candidates.sort(key=lambda t: t["_final_conviction"], reverse=True)
    chosen = candidates[:max_proposals]

    proposals = []
    for t in chosen:
        sources    = t.get("catalyst_sources", [])
        tier_summary = ", ".join(
            f"Tier-{s.get('tier', '?')} ({s.get('source', 'unknown')})"
            for s in sources
        )
        trap_flags = [
            f for f in ("analyst_only_catalyst", "pre_market_gap_fade_risk", "wide_spread")
            if t.get(f)
        ]
        proposals.append({
            "symbol":            t.get("symbol"),
            "catalyst":          t.get("catalyst", ""),
            "sector":            t.get("sector", ""),
            "entry":             float(t.get("entry", 0)),
            "stop":              float(t.get("stop", 0)),
            "target":            float(t.get("target", 0)),
            "r_r":               float(t.get("r_r", 0)),
            "final_conviction":  t["_final_conviction"],
            "trap_assessment":   "Flags: " + ", ".join(trap_flags) if trap_flags else "No flags",
            "source_tier_summary": tier_summary,
            "qty":               0,
        })

    return proposals, ""

# ─── Step 7: Write proposal to COP ───────────────────────────────────────────

def write_proposal_to_cop(proposal: dict, today_str: str) -> None:
    props     = get_db_properties(COP_DB_ID)
    prop_type = lambda k: props.get(k, {}).get("type")

    def build(candidates, value_builder):
        key = resolve_prop(props, *candidates)
        if key is None:
            return {}
        return {key: value_builder(key)}

    page_props: dict = {}

    title_key = resolve_prop(props, "Name", "Symbol", "Title")
    if title_key:
        page_props[title_key] = {"title": rt(proposal["symbol"])}

    date_key = resolve_prop(props, "Date", "Trade Date")
    if date_key and prop_type(date_key) == "date":
        page_props[date_key] = {"date": {"start": today_str}}

    status_key = resolve_prop(props, "Status")
    if status_key:
        if prop_type(status_key) == "select":
            page_props[status_key] = {"select": {"name": "Proposed"}}
        elif prop_type(status_key) == "rich_text":
            page_props[status_key] = {"rich_text": rt("Proposed")}

    for field, candidates in [
        ("entry",           ["Entry", "Entry Price"]),
        ("stop",            ["Stop", "Stop Loss", "Stop Price"]),
        ("target",          ["Target", "Target Price"]),
        ("r_r",             ["R/R", "RR", "Risk Reward", "R:R"]),
        ("final_conviction",["Conviction", "Final Conviction"]),
        ("qty",             ["Qty", "Quantity"]),
    ]:
        key = resolve_prop(props, *candidates)
        if key and prop_type(key) == "number":
            page_props[key] = {"number": float(proposal[field])}

    sector_key = resolve_prop(props, "Sector")
    if sector_key:
        if prop_type(sector_key) == "select":
            page_props[sector_key] = {"select": {"name": proposal["sector"]}}
        elif prop_type(sector_key) == "rich_text":
            page_props[sector_key] = {"rich_text": rt(proposal["sector"])}

    for field, candidates in [
        ("catalyst",           ["Catalyst"]),
        ("trap_assessment",    ["Trap Assessment", "Trap"]),
        ("source_tier_summary",["Source Tier Summary", "Sources"]),
    ]:
        key = resolve_prop(props, *candidates)
        if key and prop_type(key) == "rich_text":
            page_props[key] = {"rich_text": rt(proposal[field])}

    notion_post("/pages", {
        "parent":     {"database_id": COP_DB_ID},
        "properties": page_props,
    })

# ─── Step 8: Research summary page ───────────────────────────────────────────

def create_research_summary(
    today_str: str,
    account: Optional[dict],
    research: Optional[dict],
    proposals: list,
    positions: list,
    sector_analysis: Optional[dict],
    hold_reason: str = "",
    feed_status_note: str = "",
) -> str:
    page = notion_post("/pages", {
        "parent":     {"page_id": PARENT_PAGE_ID},
        "properties": {"title": {"title": rt(f"Pre-Market Research -- {today_str}")}},
    })
    page_id = page["id"]
    blocks: list[dict] = []

    # 1. Account status
    blocks.append(h2("1. ACCOUNT STATUS"))
    if account:
        blocks.append(para(
            f"Equity: {account.get('equity', 'N/A')} | "
            f"Cash: {account.get('cash', 'N/A')} | "
            f"Buying Power: {account.get('buying_power', 'N/A')} | "
            f"Day Trade Count: {account.get('daytrade_count', 'N/A')} | "
            f"Simulated Equity: $10,000"
        ))
        blocks.append(para(f"Open Positions: {len(positions)}"))
        for p in positions:
            plpc = p.get("unrealized_plpc", 0)
            try:
                plpc_str = f"{float(plpc)*100:.2f}%"
            except (ValueError, TypeError):
                plpc_str = str(plpc)
            blocks.append(para(
                f"  {p.get('symbol')}: {p.get('qty')} shares @ "
                f"${p.get('avg_entry_price')} | Current: ${p.get('current_price')} | "
                f"P/L: {plpc_str}"
            ))
    else:
        blocks.append(para("Account data unavailable."))
    blocks.append(divider())

    # 2. Perplexity feed status
    blocks.append(h2("2. PERPLEXITY FEED STATUS"))
    if research is None:
        blocks.append(para(
            f"MISSING — no autonomous fallback by design. {feed_status_note}"
        ))
    else:
        ticker_count = len(research.get("research", []))
        blocks.append(para(
            f"Status: {research.get('status', 'OK')} | "
            f"Tickers loaded: {ticker_count}"
        ))
        if research.get("notes"):
            blocks.append(para(f"Notes: {research['notes']}"))
    blocks.append(divider())

    # 3. Market environment
    blocks.append(h2("3. MARKET ENVIRONMENT"))
    if research:
        macro = research.get("macro_context", {})
        vix     = macro.get("vix", "N/A")
        spy_pm  = macro.get("spy_premarket_change_pct", 0)
        heavy   = macro.get("spy_premarket_volume_heavy", False)
        top_sec = macro.get("top_sectors_5d", [])
        bot_sec = macro.get("bottom_sectors_5d", [])
        try:
            spy_str = f"{float(spy_pm):+.2f}%"
        except (ValueError, TypeError):
            spy_str = str(spy_pm)
        blocks.append(para(
            f"VIX: {vix} | SPY Pre-Market: {spy_str} "
            f"({'heavy volume' if heavy else 'normal volume'})"
        ))
        blocks.append(para(f"Top sectors (5d): {', '.join(top_sec) if top_sec else 'N/A'}"))
        blocks.append(para(f"Bottom sectors (5d): {', '.join(bot_sec) if bot_sec else 'N/A'}"))
    else:
        blocks.append(para("Research feed unavailable."))
    blocks.append(divider())

    # 4. Sector drill-down
    blocks.append(h2("4. SECTOR DRILL-DOWN"))
    if sector_analysis:
        for sector, stats in sector_analysis["stats"].items():
            blocks.append(para(
                f"{sector}: {stats['count']} tickers | "
                f"Avg conviction: {stats['avg_conviction']} | "
                f"Avg R:R: {stats['avg_rr']} | "
                f"Momentum: {stats['momentum']}"
            ))
    else:
        blocks.append(para("N/A"))
    blocks.append(divider())

    # 5. Evaluation table
    blocks.append(h2("5. EVALUATION TABLE"))
    if research:
        for t in research.get("research", []):
            sym    = t.get("symbol", "?")
            base   = t.get("conviction", "?")
            reason = t.get("_discard_reason", "")
            final  = t.get("_final_conviction")
            if reason:
                outcome = f"DISCARD → {reason}"
            elif final is not None:
                outcome = (
                    f"PASS → final conviction {final} "
                    f"(base={base}, sector_adj={t.get('_sector_adj', 0):+}, "
                    f"penalty={t.get('_penalty', 0):.1f})"
                )
            else:
                outcome = f"NOT EVALUATED (base conviction {base})"
            blocks.append(para(f"{sym}: {outcome}"))
    blocks.append(divider())

    # 6. Trade ideas
    blocks.append(h2("6. TRADE IDEAS"))
    if proposals:
        for p in proposals:
            blocks.append(para(
                f"{p['symbol']} | Entry: {p['entry']} | Stop: {p['stop']} | "
                f"Target: {p['target']} | R:R: {p['r_r']} | "
                f"Conviction: {p['final_conviction']} | Qty: 0"
            ))
            blocks.append(para(f"  Catalyst: {p['catalyst']}"))
            blocks.append(para(f"  Sector: {p['sector']} | Trap: {p['trap_assessment']}"))
            blocks.append(para(f"  Sources: {p['source_tier_summary']}"))
    else:
        blocks.append(para(f"HOLD — {hold_reason or 'No tickers met all criteria.'}"))
    blocks.append(divider())

    # 7. Risk factors
    blocks.append(h2("7. RISK FACTORS"))
    risks = []
    if research:
        macro  = research.get("macro_context", {})
        vix    = float(macro.get("vix", 20))
        spy_pm = float(macro.get("spy_premarket_change_pct", 0))
        if vix > 25:
            risks.append(f"Elevated VIX ({vix:.1f})")
        if spy_pm < -1.5:
            risks.append(f"SPY pre-market weakness ({spy_pm:+.2f}%)")
    if len(positions) >= 5:
        risks.append(f"Near position cap ({len(positions)}/6 open)")
    if not risks:
        risks.append("No elevated risk flags")
    for risk in risks:
        blocks.append(para(f"• {risk}"))
    blocks.append(divider())

    # 8. Held position updates
    blocks.append(h2("8. HELD POSITION UPDATES"))
    if positions:
        for p in positions:
            plpc = p.get("unrealized_plpc", 0)
            try:
                plpc_str = f"{float(plpc)*100:.2f}%"
            except (ValueError, TypeError):
                plpc_str = str(plpc)
            blocks.append(para(
                f"{p.get('symbol')}: {p.get('qty')} shares @ "
                f"avg ${p.get('avg_entry_price')} | "
                f"Current: ${p.get('current_price')} | P/L: {plpc_str}"
            ))
    else:
        blocks.append(para("No open positions."))
    blocks.append(divider())

    # 9. Overall assessment
    blocks.append(h2("9. OVERALL ASSESSMENT"))
    if proposals:
        syms = ", ".join(p["symbol"] for p in proposals)
        blocks.append(para(
            f"Proposing {len(proposals)} trade(s): {syms}. "
            f"Pipeline continues to Workflow B (audit/veto) at 8:00 AM CT."
        ))
    else:
        blocks.append(para(f"HOLD — {hold_reason or 'No trades proposed today.'}"))

    append_blocks(page_id, blocks)
    return page_id

# ─── Step 9: Bot status log ───────────────────────────────────────────────────

def log_bot_status(
    today_str: str,
    status: str,
    actions_taken: str,
    trades_proposed: int = 0,
) -> None:
    props     = get_db_properties(STATUS_LOG_DB_ID)
    prop_type = lambda k: props.get(k, {}).get("type")

    page_props: dict = {}

    title_key = resolve_prop(props, "Name", "Title", "Log")
    if title_key:
        page_props[title_key] = {"title": rt(f"Pre-Market Eval {today_str}")}

    run_date_key = resolve_prop(props, "Run Date", "Date")
    if run_date_key and prop_type(run_date_key) == "date":
        page_props[run_date_key] = {"date": {"start": today_str}}

    status_key = resolve_prop(props, "Status")
    if status_key:
        if prop_type(status_key) == "select":
            page_props[status_key] = {"select": {"name": status}}
        elif prop_type(status_key) == "rich_text":
            page_props[status_key] = {"rich_text": rt(status)}

    actions_key = resolve_prop(props, "Actions Taken", "Actions", "Notes")
    if actions_key and prop_type(actions_key) == "rich_text":
        page_props[actions_key] = {"rich_text": rt(actions_taken)}

    trades_key = resolve_prop(props, "Trades Proposed", "Proposals")
    if trades_key and prop_type(trades_key) == "number":
        page_props[trades_key] = {"number": trades_proposed}

    notion_post("/pages", {
        "parent":     {"database_id": STATUS_LOG_DB_ID},
        "properties": page_props,
    })

# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    today     = date.today()
    today_str = today.isoformat()
    log.info("Routine 1 Pre-Market Eval starting for %s", today_str)

    for var in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "NOTION_API_KEY"):
        if not os.environ.get(var):
            log.error("Missing required env var: %s", var)
            sys.exit(1)

    # ── Step 1: Alpaca account state ──────────────────────────────────────────
    try:
        account    = alpaca_get("/account")
        positions  = alpaca_get("/positions")
        open_orders = alpaca_get("/orders?status=open")
    except Exception as e:
        log.error("Alpaca API error: %s", e)
        try:
            log_bot_status(today_str, "FAILED", f"Alpaca API error: {e}")
        except Exception:
            pass
        sys.exit(1)

    equity = float(account.get("equity", 0))
    log.info(
        "Account: equity=%.2f cash=%s bp=%s dtc=%s open_pos=%d open_orders=%d",
        equity,
        account.get("cash"),
        account.get("buying_power"),
        account.get("daytrade_count"),
        len(positions),
        len(open_orders),
    )

    if equity < KILL_SWITCH_THRESHOLD:
        log.warning("KILL SWITCH: equity %.2f < threshold %.2f", equity, KILL_SWITCH_THRESHOLD)
        log_bot_status(today_str, "SKIP", "KILL_SWITCH_TRIPPED")
        sys.exit(0)

    weekly_executed = get_weekly_executed_count(today)
    log.info("Weekly executed trades: %d", weekly_executed)

    # ── Step 1.5: Research feed ───────────────────────────────────────────────
    research = fetch_research_feed(today_str)

    if research is None:
        hold_reason = "PERPLEXITY_RESEARCH_FEED_MISSING -- no autonomous fallback by design"
        log.warning(hold_reason)
        try:
            create_research_summary(
                today_str, account, None, [], positions, None,
                hold_reason=hold_reason,
                feed_status_note="Feed URL returned non-200 or malformed JSON.",
            )
        except Exception as e:
            log.error("Failed to write summary page: %s", e)
        log_bot_status(today_str, "SKIP", hold_reason)
        sys.exit(0)

    feed_status = research.get("status", "OK")

    if feed_status == "FAILED":
        reason = research.get("notes", "Perplexity run failed (no notes provided)")
        hold_reason = f"PERPLEXITY_FEED_STATUS_FAILED: {reason}"
        log.warning(hold_reason)
        try:
            create_research_summary(
                today_str, account, research, [], positions, None,
                hold_reason=hold_reason,
            )
        except Exception as e:
            log.error("Failed to write summary page: %s", e)
        log_bot_status(today_str, "SKIP", hold_reason)
        sys.exit(0)

    tickers = research.get("research", [])
    if not isinstance(tickers, list) or len(tickers) == 0:
        hold_reason = "Research array empty or malformed in feed"
        log.warning(hold_reason)
        try:
            create_research_summary(
                today_str, account, research, [], positions, None,
                hold_reason=hold_reason,
            )
        except Exception as e:
            log.error("Failed to write summary page: %s", e)
        log_bot_status(today_str, "SKIP", hold_reason)
        sys.exit(0)

    if feed_status == "PARTIAL":
        log.info("Research feed PARTIAL — proceeding with %d tickers", len(tickers))

    # ── Steps 2–6: Sector analysis + proposal generation ─────────────────────
    sector_analysis = analyze_sectors(research)
    log.info("Sectors: %s", {k: v["count"] for k, v in sector_analysis["stats"].items()})

    proposals, hold_reason = generate_proposals(
        research, sector_analysis, positions, weekly_executed
    )
    log.info("Proposals: %d | Hold reason: %s", len(proposals), hold_reason or "none")

    # ── Step 7: Write proposals to COP ───────────────────────────────────────
    try:
        for prop in proposals:
            write_proposal_to_cop(prop, today_str)
            log.info("COP entry written for %s (conviction=%.2f)", prop["symbol"], prop["final_conviction"])
    except Exception as e:
        log.error("COP write error: %s", e)
        log_bot_status(today_str, "FAILED", f"Notion COP write error: {e}")
        sys.exit(1)

    # ── Step 8: Research summary page ────────────────────────────────────────
    try:
        summary_page_id = create_research_summary(
            today_str, account, research, proposals, positions,
            sector_analysis, hold_reason=hold_reason,
        )
        log.info("Research summary page created: %s", summary_page_id)
    except Exception as e:
        log.error("Research summary write error: %s", e)
        log_bot_status(today_str, "FAILED", f"Research summary write error: {e}")
        sys.exit(1)

    # ── Step 9: Bot status log ────────────────────────────────────────────────
    if proposals:
        status  = "SUCCESS"
        actions = (
            f"Proposed {len(proposals)} trade(s): "
            + ", ".join(p["symbol"] for p in proposals)
        )
    else:
        status  = "HOLD"
        actions = hold_reason or "No trades met criteria today"

    try:
        log_bot_status(today_str, status, actions, trades_proposed=len(proposals))
        log.info("Bot status logged: %s", status)
    except Exception as e:
        log.error("Bot status log write error: %s", e)
        sys.exit(1)

    log.info("Routine 1 complete: %s", status)


if __name__ == "__main__":
    main()
