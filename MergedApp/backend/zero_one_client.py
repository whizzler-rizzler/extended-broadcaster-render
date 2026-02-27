"""
01 Exchange REST API Client
Fetches account data (positions, balances, orders) for 01 Exchange accounts.
Public API - no authentication required for read operations.
API docs: https://docs.01.xyz/reference/rest-api
Base URL: https://zo-mainnet.n1.xyz
"""

import os
import aiohttp
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

ZERO_ONE_API_BASE = "https://zo-mainnet.n1.xyz"

ZERO_ONE_MARKETS: Dict[int, Dict[str, Any]] = {}
ZERO_ONE_MARKETS_UPDATED: float = 0


@dataclass
class ZeroOneAccountConfig:
    id: str
    name: str
    wallet_pubkey: str
    account_id: int
    proxy_url: Optional[str] = None


@dataclass
class ZeroOneAccountCache:
    positions: Any = None
    balance: Any = None
    orders: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "orders": 0,
    })


def _parse_proxy_raw(proxy_raw: str) -> Optional[str]:
    proxy_raw = proxy_raw.strip()
    if not proxy_raw:
        return None
    if proxy_raw.startswith("http://") or proxy_raw.startswith("https://"):
        return proxy_raw
    parts = proxy_raw.split(':')
    if len(parts) == 4:
        ip, port, username, password = parts
        return f"http://{username}:{password}@{ip}:{port}"
    return None


def _find_proxy(account_num: int) -> Optional[str]:
    for env_name in [
        f"_01exchange_{account_num}_proxy",
        f"Rest_account_{account_num}_proxy",
    ]:
        raw = os.getenv(env_name, "").strip()
        if raw:
            parsed = _parse_proxy_raw(raw)
            if parsed:
                return parsed
    return None


async def fetch_01_api(path: str, proxy_url: Optional[str] = None) -> Any:
    url = f"{ZERO_ONE_API_BASE}{path}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "extended-broadcaster/3.0",
    }
    timeout = aiohttp.ClientTimeout(total=15.0)

    async def _do_request(proxy: Optional[str] = None) -> Any:
        kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout}
        if proxy:
            kwargs["proxy"] = proxy

        async with aiohttp.ClientSession() as session:
            async with session.get(url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    body_text = await response.text()
                    via = " via proxy" if proxy else ""
                    print(f"⚠️ [01 Exchange][{path}]{via} HTTP {response.status}: {body_text[:150]}")
                    return None

    try:
        if proxy_url:
            try:
                result = await _do_request(proxy_url)
                if result is not None:
                    return result
            except Exception as proxy_err:
                print(f"⚠️ [01 Exchange][{path}] proxy failed ({type(proxy_err).__name__}), trying direct...")
        return await _do_request(None)
    except Exception as e:
        error_type = type(e).__name__
        print(f"❌ [01 Exchange][{path}] {error_type}: {e}")
        return None


async def fetch_01_markets() -> Dict[int, Dict[str, Any]]:
    global ZERO_ONE_MARKETS, ZERO_ONE_MARKETS_UPDATED
    if ZERO_ONE_MARKETS and time.time() - ZERO_ONE_MARKETS_UPDATED < 3600:
        return ZERO_ONE_MARKETS

    data = await fetch_01_api("/info")
    if data and "markets" in data:
        markets = {}
        for m in data["markets"]:
            market_id = m.get("marketId")
            if market_id is not None:
                markets[market_id] = {
                    "symbol": m.get("symbol", f"MARKET_{market_id}"),
                    "imf": m.get("imf", 0.05),
                    "mmf": m.get("mmf", 0.025),
                }
        ZERO_ONE_MARKETS = markets
        ZERO_ONE_MARKETS_UPDATED = time.time()
        print(f"✅ [01 Exchange] Loaded {len(markets)} markets")
    return ZERO_ONE_MARKETS


async def resolve_account_id(wallet_pubkey: str) -> Optional[int]:
    data = await fetch_01_api(f"/user/{wallet_pubkey}")
    if data and "accountIds" in data:
        ids = data["accountIds"]
        if ids:
            return ids[0]
    return None


def load_01_accounts() -> List[ZeroOneAccountConfig]:
    accounts = []
    for i in range(1, 20):
        wallet = os.getenv(f"_01exchange_account_{i}", "").strip()
        if not wallet:
            continue

        if wallet.startswith("0x"):
            print(f"⚠️ [01 Exchange] Account {i}: Ethereum address not supported (need Solana pubkey), skipping")
            continue

        proxy_url = _find_proxy(i)

        accounts.append(ZeroOneAccountConfig(
            id=f"01_{i}",
            name=f"01 Exchange {i}",
            wallet_pubkey=wallet,
            account_id=0,
            proxy_url=proxy_url,
        ))
        proxy_info = f" (via proxy)" if proxy_url else " (direct)"
        print(f"✅ Loaded 01 Exchange Account {i}: wallet={wallet[:8]}...{wallet[-4:]}{proxy_info}")

    return accounts


async def resolve_all_account_ids(accounts: List[ZeroOneAccountConfig]) -> None:
    for account in accounts:
        if account.account_id == 0:
            resolved_id = await resolve_account_id(account.wallet_pubkey)
            if resolved_id is not None:
                account.account_id = resolved_id
                print(f"✅ [{account.name}] Resolved account_id: {resolved_id}")
            else:
                print(f"⚠️ [{account.name}] Failed to resolve account_id for wallet {account.wallet_pubkey[:8]}...")


def normalize_01_positions(account_data: dict, markets: Dict[int, Dict[str, Any]]) -> list:
    raw_positions = account_data.get("positions", [])
    if not raw_positions:
        return []

    margins = account_data.get("margins", {})
    omf = margins.get("omf", 0)
    pn = margins.get("pn", 0)

    normalized = []
    for pos in raw_positions:
        perp = pos.get("perp")
        if not perp:
            continue

        market_id = pos.get("marketId", 0)
        market_info = markets.get(market_id, {})
        symbol = market_info.get("symbol", f"MARKET_{market_id}")
        market_name = symbol.replace("USD", "-PERP")

        base_size = abs(perp.get("baseSize", 0))
        if base_size == 0:
            continue

        is_long = perp.get("isLong", True)
        side = "LONG" if is_long else "SHORT"
        entry_price = perp.get("price", 0)
        size_pnl = perp.get("sizePricePnl", 0)
        funding_pnl = perp.get("fundingPaymentPnl", 0)
        total_pnl = size_pnl + funding_pnl

        notional = base_size * entry_price
        imf = market_info.get("imf", 0.05)
        mmf = market_info.get("mmf", 0.025)
        leverage = round(1.0 / imf, 1) if imf > 0 else 1.0
        margin = notional * imf

        liq_price = 0.0
        if base_size > 0 and omf > 0 and pn > 0:
            margin_ratio = omf / pn if pn > 0 else 0
            if margin_ratio > 0:
                if is_long:
                    liq_price = entry_price * (1 - margin_ratio + mmf)
                else:
                    liq_price = entry_price * (1 + margin_ratio - mmf)
                liq_price = max(0, liq_price)

        normalized.append({
            "market": market_name,
            "side": side,
            "size": str(base_size),
            "value": str(round(notional, 2)),
            "openPrice": entry_price,
            "markPrice": entry_price,
            "liquidationPrice": round(liq_price, 2),
            "unrealisedPnl": total_pnl,
            "midPriceUnrealisedPnl": total_pnl,
            "realisedPnl": 0,
            "margin": round(margin, 2),
            "leverage": str(leverage),
            "status": "OPENED",
            "createdAt": 0,
            "updatedAt": int(time.time() * 1000),
        })

    return normalized


def normalize_01_balance(account_data: dict) -> dict:
    balances = account_data.get("balances", [])
    margins = account_data.get("margins", {})

    total_balance = sum(b.get("amount", 0) for b in balances)

    omf = margins.get("omf", 0)
    imf_val = margins.get("imf", 0)
    mmf_val = margins.get("mmf", 0)
    pn = margins.get("pn", 0)
    pon = margins.get("pon", 0)

    margin_ratio = 0.0
    if pon > 0 and mmf_val > 0:
        margin_ratio = mmf_val / pon

    positions = account_data.get("positions", [])
    total_notional = 0
    total_pnl = 0
    for pos in positions:
        perp = pos.get("perp")
        if perp:
            base_size = abs(perp.get("baseSize", 0))
            price = perp.get("price", 0)
            total_notional += base_size * price
            total_pnl += perp.get("sizePricePnl", 0) + perp.get("fundingPaymentPnl", 0)

    leverage = total_notional / total_balance if total_balance > 0 else 0
    equity = total_balance + total_pnl

    return {
        "collateralName": "USDC",
        "balance": str(round(total_balance, 6)),
        "status": "ACTIVE",
        "equity": str(round(equity, 6)),
        "availableForTrade": str(round(max(0, total_balance - imf_val), 6)),
        "availableForWithdrawal": str(round(max(0, total_balance - imf_val), 6)),
        "unrealisedPnl": str(round(total_pnl, 6)),
        "initialMargin": str(round(imf_val, 6)),
        "maintenanceMargin": str(round(mmf_val, 6)),
        "marginRatio": str(round(margin_ratio, 6)),
        "updatedTime": int(time.time() * 1000),
        "exposure": str(round(total_notional, 2)),
        "leverage": str(round(leverage, 2)),
    }


def normalize_01_orders(account_data: dict, markets: Dict[int, Dict[str, Any]]) -> list:
    raw_orders = account_data.get("orders", [])
    if not raw_orders:
        return []

    normalized = []
    for order in raw_orders:
        market_id = order.get("marketId", 0)
        market_info = markets.get(market_id, {})
        symbol = market_info.get("symbol", f"MARKET_{market_id}")
        market_name = symbol.replace("USD", "-PERP")

        side_raw = order.get("side", "")
        if isinstance(side_raw, str):
            side = "LONG" if side_raw.lower() == "bid" else "SHORT"
        else:
            side = "LONG"

        normalized.append({
            "id": str(order.get("orderId", "")),
            "market": market_name,
            "side": side,
            "type": "LIMIT",
            "price": str(order.get("price", "0")),
            "size": str(order.get("size", "0")),
            "status": "ACTIVE",
            "createdAt": 0,
        })

    return normalized


async def poll_01_account(account: ZeroOneAccountConfig, cache: ZeroOneAccountCache) -> bool:
    if account.account_id == 0:
        resolved_id = await resolve_account_id(account.wallet_pubkey)
        if resolved_id is not None:
            account.account_id = resolved_id
            print(f"✅ [{account.name}] Resolved account_id: {resolved_id}")
        else:
            return False

    markets = await fetch_01_markets()
    account_data = await fetch_01_api(f"/account/{account.account_id}", account.proxy_url)
    if not account_data:
        return False

    changed = False

    positions = normalize_01_positions(account_data, markets)
    balance = normalize_01_balance(account_data)
    orders = normalize_01_orders(account_data, markets)

    if positions != cache.positions:
        cache.positions = positions
        cache.last_update["positions"] = time.time()
        changed = True

    if balance != cache.balance:
        cache.balance = balance
        cache.last_update["balance"] = time.time()
        changed = True

    if orders != cache.orders:
        cache.orders = orders
        cache.last_update["orders"] = time.time()
        changed = True

    return changed
