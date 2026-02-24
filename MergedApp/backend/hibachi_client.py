"""
Hibachi Exchange REST API Client
Fetches account data (positions, balances, orders) for Hibachi accounts.
Authentication: Simple API key in Authorization header.
API docs: https://api-doc.hibachi.xyz/
"""

import os
import aiohttp
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

HIBACHI_API_BASE = "https://api.hibachi.xyz"
HIBACHI_DATA_API_BASE = "https://data-api.hibachi.xyz"

HIBACHI_PRICES: Dict[str, float] = {}
HIBACHI_PRICES_UPDATED: float = 0


@dataclass
class HibachiAccountConfig:
    id: str
    name: str
    account_id: str
    api_key: str
    proxy_url: Optional[str] = None


@dataclass
class HibachiAccountCache:
    positions: Any = None
    balance: Any = None
    orders: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "orders": 0,
    })


def parse_rest_proxy(account_num: int) -> Optional[str]:
    proxy_raw = os.getenv(f"Rest_account_{account_num}_proxy", "").strip()
    if not proxy_raw:
        return None
    if proxy_raw.startswith("http://") or proxy_raw.startswith("https://"):
        return proxy_raw
    parts = proxy_raw.split(':')
    if len(parts) == 4:
        ip, port, username, password = parts
        return f"http://{username}:{password}@{ip}:{port}"
    return None


def load_hibachi_accounts() -> List[HibachiAccountConfig]:
    accounts = []
    for i in range(1, 20):
        account_id = os.getenv(f"Hibachi_{i}_AccountID", "").strip()
        public_key = os.getenv(f"Hibachi_{i}_public_key", "").strip()

        if not account_id or not public_key:
            continue

        proxy_url = parse_rest_proxy(i)

        accounts.append(HibachiAccountConfig(
            id=f"hibachi_{i}",
            name=f"Hibachi {i}",
            account_id=account_id,
            api_key=public_key,
            proxy_url=proxy_url,
        ))
        proxy_info = f" (via Rest_account_{i}_proxy)" if proxy_url else ""
        print(f"✅ Loaded Hibachi Account {i}: ID={account_id[:8]}...{proxy_info}")

    return accounts


async def fetch_hibachi_api(account: HibachiAccountConfig, path: str,
                             method: str = "GET",
                             params: Optional[Dict[str, Any]] = None,
                             authenticated: bool = True) -> Any:
    if params is None:
        params = {}

    base_url = HIBACHI_API_BASE if authenticated else HIBACHI_DATA_API_BASE
    url = f"{base_url}{path}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "extended-broadcaster/3.0",
        "Hibachi-Client": "ExtendedBroadcaster/1.0",
    }
    if authenticated:
        headers["Authorization"] = account.api_key

    timeout = aiohttp.ClientTimeout(total=15.0)

    async def _do_request(proxy: Optional[str] = None) -> Any:
        kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout}
        if proxy:
            kwargs["proxy"] = proxy

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, **kwargs) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    body_text = await response.text()
                    via = " via proxy" if proxy else ""
                    print(f"⚠️ [{account.name}][{path}]{via} HTTP {response.status}: {body_text[:150]}")
                    return None

    try:
        if account.proxy_url:
            try:
                result = await _do_request(account.proxy_url)
                if result is not None:
                    return result
            except Exception as proxy_err:
                print(f"⚠️ [{account.name}][{path}] proxy failed ({type(proxy_err).__name__}), trying direct...")
        return await _do_request(None)
    except Exception as e:
        error_type = type(e).__name__
        print(f"❌ [{account.name}][{path}] {error_type}: {e}")
        return None


async def fetch_hibachi_prices():
    global HIBACHI_PRICES, HIBACHI_PRICES_UPDATED
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{HIBACHI_DATA_API_BASE}/market/inventory"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    markets = data.get("markets", [])
                    prices = {}
                    for market in markets:
                        info = market.get("info", {})
                        contract = market.get("contract", {})
                        symbol = contract.get("symbol", "")
                        mark_price = info.get("markPrice") or info.get("lastPrice")
                        if mark_price and symbol:
                            prices[symbol] = float(mark_price)
                    HIBACHI_PRICES = prices
                    HIBACHI_PRICES_UPDATED = time.time()
                    return prices
    except Exception as e:
        print(f"⚠️ [Hibachi] Failed to fetch prices: {e}")
    return HIBACHI_PRICES


def normalize_hibachi_positions(positions_raw: list) -> list:
    if not positions_raw:
        return []
    normalized = []
    for pos in positions_raw:
        quantity = float(pos.get("quantity", "0"))
        if quantity == 0:
            continue

        direction = pos.get("direction", "")
        side = "LONG" if direction.lower() == "long" else "SHORT"
        abs_qty = abs(quantity)
        symbol = pos.get("symbol", "")
        market = symbol.replace("/USDT-P", "-PERP").replace("/", "-")

        open_price = float(pos.get("openPrice", "0"))
        mark_price = float(pos.get("markPrice", "0"))
        notional = float(pos.get("notionalValue", "0"))
        entry_notional = float(pos.get("entryNotional", "0"))

        unrealized_trading = float(pos.get("unrealizedTradingPnl", "0"))
        unrealized_funding = float(pos.get("unrealizedFundingPnl", "0"))
        total_pnl = unrealized_trading + unrealized_funding

        normalized.append({
            "market": market,
            "side": side,
            "size": str(abs_qty),
            "value": str(notional),
            "openPrice": open_price,
            "markPrice": mark_price,
            "liquidationPrice": 0,
            "unrealisedPnl": total_pnl,
            "midPriceUnrealisedPnl": total_pnl,
            "realisedPnl": 0,
            "margin": 0,
            "leverage": str(round(notional / float(pos.get("openPrice", "1")) if open_price > 0 else 0, 1)),
            "status": "OPENED",
            "createdAt": 0,
            "updatedAt": int(time.time() * 1000),
        })
    return normalized


def normalize_hibachi_balance(account_info: dict, positions: list = None) -> dict:
    if not account_info:
        return {
            "collateralName": "USDT",
            "balance": "0",
            "status": "UNKNOWN",
            "equity": "0",
            "availableForTrade": "0",
            "availableForWithdrawal": "0",
            "unrealisedPnl": "0",
            "initialMargin": "0",
            "marginRatio": "0",
            "updatedTime": int(time.time() * 1000),
            "exposure": "0",
            "leverage": "0",
        }

    balance = float(account_info.get("balance", "0"))
    max_withdraw = float(account_info.get("maximalWithdraw", "0"))
    total_notional = float(account_info.get("totalPositionNotional", "0"))
    total_order_notional = float(account_info.get("totalOrderNotional", "0"))
    total_unrealized_pnl = float(account_info.get("totalUnrealizedPnl", "0"))

    used_margin = balance - max_withdraw
    margin_ratio = 0.0
    if balance > 0 and used_margin > 0:
        margin_ratio = used_margin / balance

    leverage = 0.0
    if balance > 0 and total_notional > 0:
        leverage = total_notional / balance

    return {
        "collateralName": "USDT",
        "balance": str(balance),
        "status": "ACTIVE",
        "equity": str(balance),
        "availableForTrade": str(max_withdraw),
        "availableForWithdrawal": str(max_withdraw),
        "unrealisedPnl": str(total_unrealized_pnl),
        "initialMargin": str(used_margin),
        "marginRatio": str(margin_ratio),
        "updatedTime": int(time.time() * 1000),
        "exposure": str(total_notional),
        "leverage": str(round(leverage, 2)),
    }


def normalize_hibachi_orders(raw_orders: list) -> list:
    if not raw_orders:
        return []
    normalized = []
    for order in raw_orders:
        symbol = order.get("symbol", "")
        market = symbol.replace("/USDT-P", "-PERP").replace("/", "-")
        side_raw = order.get("side", "")
        side = "LONG" if side_raw.lower() in ("buy", "bid") else "SHORT"

        normalized.append({
            "id": str(order.get("orderId", "")),
            "market": market,
            "side": side,
            "type": order.get("orderType", "LIMIT"),
            "price": str(order.get("price", "0")),
            "size": str(order.get("quantity", "0")),
            "status": "ACTIVE",
            "createdAt": int(order.get("creationTime", 0)) * 1000,
        })
    return normalized


async def poll_hibachi_account(account: HibachiAccountConfig, cache: HibachiAccountCache) -> bool:
    changed = False

    account_info = await fetch_hibachi_api(
        account, f"/trade/account/info",
        params={"accountId": account.account_id}
    )

    if account_info:
        raw_positions = account_info.get("positions", [])
        positions = normalize_hibachi_positions(raw_positions)
        balance = normalize_hibachi_balance(account_info, positions)

        if positions != cache.positions:
            cache.positions = positions
            cache.last_update["positions"] = time.time()
            changed = True

        if balance != cache.balance:
            cache.balance = balance
            cache.last_update["balance"] = time.time()
            changed = True

    orders_resp = await fetch_hibachi_api(
        account, f"/trade/orders",
        params={"accountId": account.account_id}
    )

    if orders_resp is not None:
        raw_orders = orders_resp if isinstance(orders_resp, list) else orders_resp.get("orders", []) if isinstance(orders_resp, dict) else []
        orders = normalize_hibachi_orders(raw_orders)
        if orders != cache.orders:
            cache.orders = orders
            cache.last_update["orders"] = time.time()
            changed = True

    return changed
