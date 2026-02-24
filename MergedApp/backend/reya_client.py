"""
Reya Network REST API Client
Fetches account data (positions, balances, orders) for Reya wallets.
No authentication required - just wallet address in URL path.
API docs: https://docs.reya.xyz/developers/rest-api-reference/wallet-data
"""

import os
import aiohttp
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

REYA_API_BASE = "https://api.reya.xyz/v2"


@dataclass
class ReyaAccountConfig:
    id: str
    name: str
    wallet_address: str
    proxy_url: Optional[str] = None


@dataclass
class ReyaAccountCache:
    positions: Any = None
    balance: Any = None
    orders: Any = None
    accounts: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "orders": 0,
        "accounts": 0,
    })


def load_reya_accounts() -> List[ReyaAccountConfig]:
    accounts = []
    for i in range(1, 20):
        wallet = os.getenv(f"Reya_{i}_wallet_adress", "").strip()
        if not wallet:
            continue
        proxy_raw = os.getenv(f"Reya_{i}_proxy", "").strip()
        proxy_url = None
        if proxy_raw:
            if proxy_raw.startswith("http://") or proxy_raw.startswith("https://"):
                proxy_url = proxy_raw
            else:
                parts = proxy_raw.split(':')
                if len(parts) == 4:
                    ip, port, username, password = parts
                    proxy_url = f"http://{username}:{password}@{ip}:{port}"

        accounts.append(ReyaAccountConfig(
            id=f"reya_{i}",
            name=f"Reya {i}",
            wallet_address=wallet,
            proxy_url=proxy_url,
        ))
        proxy_info = " (via proxy)" if proxy_url else ""
        print(f"✅ Loaded Reya Account {i}: {wallet[:10]}...{wallet[-6:]}{proxy_info}")

    return accounts


async def fetch_reya_api(account: ReyaAccountConfig, endpoint: str) -> Any:
    url = f"{REYA_API_BASE}/wallet/{account.wallet_address}{endpoint}"
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
                    body = await response.text()
                    via = " via proxy" if proxy else ""
                    print(f"⚠️ [{account.name}][{endpoint}]{via} HTTP {response.status}: {body[:120]}")
                    return None

    try:
        if account.proxy_url:
            try:
                result = await _do_request(account.proxy_url)
                if result is not None:
                    return result
            except Exception as proxy_err:
                print(f"⚠️ [{account.name}][{endpoint}] proxy failed ({type(proxy_err).__name__}), trying direct...")
        return await _do_request(None)
    except Exception as e:
        error_type = type(e).__name__
        print(f"❌ [{account.name}][{endpoint}] {error_type}: {e}")
        return None


def normalize_reya_positions(raw_positions: list) -> list:
    if not raw_positions:
        return []
    normalized = []
    for pos in raw_positions:
        qty = float(pos.get("qty", "0"))
        side_raw = pos.get("side", "")
        side = "LONG" if side_raw == "B" else "SHORT" if side_raw == "A" else side_raw
        entry_price = float(pos.get("avgEntryPrice", "0"))
        symbol = pos.get("symbol", "")
        market = symbol.replace("RUSD", "-").rstrip("-")
        if market.endswith("PERP"):
            market = market.replace("PERP", "-PERP")
        if not market:
            market = symbol
        notional = abs(qty * entry_price)

        normalized.append({
            "market": market,
            "side": side,
            "size": str(abs(qty)),
            "value": str(notional),
            "openPrice": entry_price,
            "markPrice": entry_price,
            "liquidationPrice": 0,
            "unrealisedPnl": 0,
            "midPriceUnrealisedPnl": 0,
            "realisedPnl": 0,
            "margin": 0,
            "leverage": "1",
            "status": "OPENED",
            "createdAt": 0,
            "updatedAt": int(time.time() * 1000),
        })
    return normalized


def normalize_reya_balance(raw_balances: list, raw_accounts: list = None) -> dict:
    total_balance = 0.0
    for bal in (raw_balances or []):
        if bal.get("asset", "").upper() in ("RUSD", "USDC", "USD"):
            total_balance += float(bal.get("realBalance", "0"))

    if total_balance == 0 and raw_balances:
        for bal in raw_balances:
            total_balance += float(bal.get("realBalance", "0"))

    return {
        "collateralName": "RUSD",
        "balance": str(total_balance),
        "status": "ACTIVE",
        "equity": str(total_balance),
        "availableForTrade": str(total_balance),
        "availableForWithdrawal": str(total_balance),
        "unrealisedPnl": "0",
        "initialMargin": "0",
        "marginRatio": "0",
        "updatedTime": int(time.time() * 1000),
        "exposure": "0",
        "leverage": "0",
    }


def normalize_reya_orders(raw_orders: list) -> list:
    if not raw_orders:
        return []
    normalized = []
    for order in raw_orders:
        if order.get("status") != "OPEN":
            continue
        side_raw = order.get("side", "")
        side = "BUY" if side_raw == "B" else "SELL" if side_raw == "A" else side_raw
        symbol = order.get("symbol", "")
        market = symbol.replace("RUSD", "-").rstrip("-")
        if market.endswith("PERP"):
            market = market.replace("PERP", "-PERP")
        if not market:
            market = symbol

        normalized.append({
            "id": order.get("orderId", ""),
            "market": market,
            "side": side,
            "type": order.get("orderType", "LIMIT"),
            "price": order.get("limitPx", "0"),
            "size": order.get("qty", "0"),
            "status": "ACTIVE",
            "createdAt": order.get("createdAt", 0),
        })
    return normalized
