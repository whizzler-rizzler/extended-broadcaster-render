"""
Pacifica Exchange REST API Client
Fetches account data (positions, balances, orders) for Pacifica accounts.
Authentication: Public REST API - only Solana wallet address needed for reads.
API: https://api.pacifica.fi/api/v1
"""

import os
import aiohttp
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

PACIFICA_API_BASE = "https://api.pacifica.fi/api/v1"


@dataclass
class PacificaAccountConfig:
    id: str
    name: str
    address: str
    api_key: Optional[str] = None
    proxy_url: Optional[str] = None


@dataclass
class PacificaAccountCache:
    positions: Any = None
    balance: Any = None
    orders: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "orders": 0,
    })


PACIFICA_CACHES: Dict[str, PacificaAccountCache] = {}


def _parse_proxy(proxy_raw: str) -> Optional[str]:
    proxy_raw = proxy_raw.strip()
    if not proxy_raw:
        return None
    if proxy_raw.startswith("http://") or proxy_raw.startswith("https://"):
        return proxy_raw
    parts = proxy_raw.split(':')
    if len(parts) == 4:
        ip, port, username, password = parts
        return f"http://{username}:{password}@{ip}:{port}"
    elif len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    return proxy_raw


def load_pacifica_accounts() -> List[PacificaAccountConfig]:
    accounts = []
    for i in range(1, 20):
        address = os.environ.get(f"Pacifica_account_{i}_adress", "").strip()
        if not address:
            address = os.environ.get(f"Pacifica_account_{i}_address", "").strip()
        if not address:
            continue

        api_key = os.environ.get(f"Pacifica_{i}_api_key", "").strip() or None

        proxy_url = None
        proxy_raw = os.environ.get(f"Pacifica_{i}_proxy", "").strip()
        if proxy_raw:
            proxy_url = _parse_proxy(proxy_raw)

        account = PacificaAccountConfig(
            id=f"pacifica_{i}",
            name=f"Pacifica {i}",
            address=address,
            api_key=api_key,
            proxy_url=proxy_url,
        )
        accounts.append(account)

        if account.id not in PACIFICA_CACHES:
            PACIFICA_CACHES[account.id] = PacificaAccountCache()

        print(f"✅ Loaded Pacifica account {i}: {account.name} (addr: {address[:8]}...)")

    print(f"📊 Total Pacifica accounts loaded: {len(accounts)}")
    return accounts


async def _fetch_json(url: str, proxy: Optional[str] = None, api_key: Optional[str] = None) -> Optional[Dict]:
    headers = {"Accept": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"⚠️ [Pacifica] {url} HTTP {resp.status}: {text[:200]}")
                    return None
                data = await resp.json()
                if data.get("success"):
                    return data.get("data")
                else:
                    print(f"⚠️ [Pacifica] {url} error: {data.get('error', 'unknown')}")
                    return None
    except Exception as e:
        print(f"❌ [Pacifica] {url} exception: {e}")
        return None


def normalize_pacifica_positions(raw_positions: List[Dict], total_unrealised_pnl: float = 0) -> List[Dict]:
    positions = []
    parsed = []
    total_notional = 0

    for p in raw_positions:
        symbol = p.get("symbol", "?")
        side_raw = p.get("side", "")
        side = "LONG" if side_raw == "bid" else "SHORT" if side_raw == "ask" else side_raw.upper()

        amount = float(p.get("amount", 0))
        entry_price = float(p.get("entry_price", 0))
        notional = amount * entry_price
        total_notional += notional
        funding = float(p.get("funding", 0))
        liq_price = p.get("liquidation_price")

        parsed.append({
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "entry_price": entry_price,
            "notional": notional,
            "funding": funding,
            "liq_price": liq_price,
            "isolated": p.get("isolated", False),
        })

    for p in parsed:
        pnl_share = (p["notional"] / total_notional * total_unrealised_pnl) if total_notional > 0 else 0
        mark_price = (p["entry_price"] + pnl_share / p["amount"]) if p["amount"] > 0 else p["entry_price"]
        if p["side"] == "SHORT":
            mark_price = (p["entry_price"] - pnl_share / p["amount"]) if p["amount"] > 0 else p["entry_price"]

        liq = float(p["liq_price"]) if p["liq_price"] else 0

        positions.append({
            "market": f"{p['symbol']}-PERP",
            "side": p["side"],
            "size": p["amount"],
            "openPrice": p["entry_price"],
            "entryPrice": p["entry_price"],
            "markPrice": round(mark_price, 2),
            "unrealisedPnl": round(pnl_share, 2),
            "midPriceUnrealisedPnl": round(pnl_share, 2),
            "notional": p["notional"],
            "value": str(round(p["notional"], 2)),
            "leverage": 0,
            "liquidationPrice": liq,
            "funding": p["funding"],
            "isolated": p["isolated"],
            "status": "OPENED",
        })
    return positions


def normalize_pacifica_balance(raw_account: Dict, positions: List[Dict]) -> Dict:
    balance = float(raw_account.get("balance", 0))
    equity = float(raw_account.get("account_equity", 0))
    total_margin = float(raw_account.get("total_margin_used", 0))
    cross_mmr = float(raw_account.get("cross_mmr", 0))
    available = float(raw_account.get("available_to_spend", 0))

    margin_ratio_pct = cross_mmr if cross_mmr > 0 else (total_margin / equity * 100 if equity > 0 else 0)
    margin_ratio = margin_ratio_pct / 100

    total_notional = sum(p.get("notional", 0) for p in positions)
    leverage = total_notional / equity if equity > 0 else 0

    return {
        "balance": balance,
        "equity": equity,
        "availableBalance": max(0, available),
        "availableForTrade": str(round(max(0, available), 2)),
        "totalMarginUsed": total_margin,
        "marginRatio": str(round(margin_ratio, 6)),
        "leverage": round(leverage, 2),
        "unrealisedPnl": round(equity - balance, 2),
        "walletBalance": balance,
    }


def normalize_pacifica_orders(raw_orders: List[Dict]) -> List[Dict]:
    orders = []
    for o in raw_orders:
        symbol = o.get("symbol", "?")
        side_raw = o.get("side", "")
        side = "LONG" if side_raw == "bid" else "SHORT" if side_raw == "ask" else side_raw.upper()

        initial = float(o.get("initial_amount", 0))
        filled = float(o.get("filled_amount", 0))
        remaining = initial - filled

        if remaining <= 0:
            continue

        orders.append({
            "market": f"{symbol}-PERP",
            "side": side,
            "price": float(o.get("price", 0)),
            "size": remaining,
            "filledSize": filled,
            "type": o.get("order_type", "limit"),
            "reduceOnly": o.get("reduce_only", False),
            "orderId": str(o.get("order_id", "")),
            "createdAt": o.get("created_at"),
        })
    return orders


async def poll_pacifica_account(account: PacificaAccountConfig, cache: PacificaAccountCache) -> bool:
    now = time.time()
    changed = False

    account_url = f"{PACIFICA_API_BASE}/account?account={account.address}"
    positions_url = f"{PACIFICA_API_BASE}/positions?account={account.address}"
    orders_url = f"{PACIFICA_API_BASE}/orders?account={account.address}"

    proxy = account.proxy_url
    api_key = account.api_key

    raw_account = await _fetch_json(account_url, proxy=proxy, api_key=api_key)
    raw_positions = await _fetch_json(positions_url, proxy=proxy, api_key=api_key)
    raw_orders = await _fetch_json(orders_url, proxy=proxy, api_key=api_key)

    total_unrealised_pnl = 0
    if raw_account is not None:
        acct_equity = float(raw_account.get("account_equity", 0))
        acct_balance = float(raw_account.get("balance", 0))
        total_unrealised_pnl = acct_equity - acct_balance

    if raw_positions is not None:
        normalized = normalize_pacifica_positions(raw_positions, total_unrealised_pnl)
        if normalized != cache.positions:
            cache.positions = normalized
            changed = True
        cache.last_update["positions"] = now

    if raw_account is not None:
        positions_for_balance = cache.positions or []
        normalized_bal = normalize_pacifica_balance(raw_account, positions_for_balance)
        if normalized_bal != cache.balance:
            cache.balance = normalized_bal
            changed = True
        cache.last_update["balance"] = now

    if raw_orders is not None:
        normalized_orders = normalize_pacifica_orders(raw_orders)
        if normalized_orders != cache.orders:
            cache.orders = normalized_orders
            changed = True
        cache.last_update["orders"] = now

    if changed:
        print(f"📊 [{account.name}] Pacifica changes detected")

    return changed
