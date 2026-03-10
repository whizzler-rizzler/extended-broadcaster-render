import os
import aiohttp
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

HOTSTUFF_API_URL = "https://api.hotstuff.trade/info"


@dataclass
class HotstuffAccountConfig:
    id: str
    name: str
    wallet_address: str
    proxy_url: Optional[str] = None


@dataclass
class HotstuffAccountCache:
    positions: Any = None
    balance: Any = None
    orders: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "orders": 0,
    })


HOTSTUFF_CACHES: Dict[str, HotstuffAccountCache] = {}


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


def load_hotstuff_accounts() -> List[HotstuffAccountConfig]:
    accounts = []
    for i in range(1, 20):
        wallet = os.getenv(f"Reya_{i}_wallet_main", "").strip()
        if not wallet:
            wallet = os.getenv(f"Reya_{i}_wallet_adress", "").strip()
        if not wallet:
            continue

        proxy_url = None
        proxy_raw = os.getenv(f"Hotstuff_{i}_proxy", "").strip()
        if not proxy_raw:
            proxy_raw = os.getenv(f"Rest_account_{i}_proxy", "").strip()
        if proxy_raw:
            proxy_url = _parse_proxy(proxy_raw)

        account = HotstuffAccountConfig(
            id=f"hotstuff_{i}",
            name=f"Hotstuff {i}",
            wallet_address=wallet,
            proxy_url=proxy_url,
        )
        accounts.append(account)

        if account.id not in HOTSTUFF_CACHES:
            HOTSTUFF_CACHES[account.id] = HotstuffAccountCache()

        proxy_info = f" (proxy: {proxy_url[:30]}...)" if proxy_url else ""
        print(f"✅ Loaded Hotstuff account {i}: {wallet[:10]}...{wallet[-6:]}{proxy_info}")

    print(f"📊 Total Hotstuff accounts loaded: {len(accounts)}")
    return accounts


async def fetch_hotstuff_account_summary(account: HotstuffAccountConfig, proxy: Optional[str] = None) -> Optional[Dict]:
    payload = {"method": "accountSummary", "params": {"user": account.wallet_address}}
    headers = {"Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                HOTSTUFF_API_URL,
                json=payload,
                headers=headers,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"⚠️ [{account.name}] Hotstuff HTTP {resp.status}: {text[:200]}")
                    return None
                data = await resp.json()
                return data
    except Exception as e:
        print(f"❌ [{account.name}] Hotstuff exception: {e}")
        return None


def normalize_hotstuff_data(raw: Dict) -> Dict:
    if not raw:
        return {
            "positions": [],
            "balance": {
                "balance": 0, "equity": 0, "availableBalance": 0,
                "availableForTrade": "0", "totalMarginUsed": 0,
                "marginRatio": "0", "leverage": 0, "unrealisedPnl": 0,
                "walletBalance": 0,
            },
            "orders": [],
        }

    collateral = raw.get("collateral", {})
    usdc_data = collateral.get("USDC", {})
    usdc_balance = usdc_data.get("balance", 0) or 0

    equity = raw.get("total_account_equity", 0) or 0
    margin_balance = raw.get("margin_balance", 0) or 0
    upnl = raw.get("upnl", 0) or 0
    available = raw.get("available_balance", 0) or 0
    init_margin = raw.get("initial_margin", 0) or 0
    maint_margin_util = raw.get("maintenance_margin_utilization", 0) or 0

    vault_balances = raw.get("vault_balances", {})
    vault_total = 0
    if vault_balances:
        for vault_data in vault_balances.values():
            vault_amount = vault_data.get("amount", 0) or 0
            vault_total += vault_amount

    total_balance = usdc_balance + vault_total
    total_equity = equity + vault_total if equity > 0 else vault_total

    perp_positions = raw.get("perp_positions", {})
    positions = []
    total_notional = 0

    for symbol, pos_data in perp_positions.items():
        legs = pos_data.get("legs", [])
        if not legs:
            continue

        leg = legs[0]
        size = leg.get("size", 0) or 0
        if abs(size) < 1e-12:
            continue

        entry_price = leg.get("entry_price", 0) or 0
        notional = leg.get("position_value", 0) or 0
        position_upnl = pos_data.get("upnl", 0) or 0
        liq_price = pos_data.get("liquidation_price", 0) or 0
        mark_price = notional / abs(size) if abs(size) > 1e-12 else 0
        total_notional += notional
        side = "LONG" if size > 0 else "SHORT"
        leverage_val = leg.get("leverage", {})
        lev = leverage_val.get("value", 0) if isinstance(leverage_val, dict) else 0

        positions.append({
            "market": symbol,
            "side": side,
            "size": abs(size),
            "openPrice": round(entry_price, 2),
            "entryPrice": round(entry_price, 2),
            "markPrice": round(mark_price, 2),
            "unrealisedPnl": round(position_upnl, 2),
            "midPriceUnrealisedPnl": round(position_upnl, 2),
            "notional": round(notional, 2),
            "value": str(round(notional, 2)),
            "leverage": lev,
            "liquidationPrice": round(liq_price, 2),
            "funding": 0,
            "isolated": False,
            "status": "OPENED",
        })

    leverage = total_notional / total_equity if total_equity > 0 else 0

    balance_data = {
        "balance": round(total_balance, 2),
        "equity": round(total_equity, 2),
        "availableBalance": round(max(0, available), 2),
        "availableForTrade": str(round(max(0, available), 2)),
        "totalMarginUsed": round(init_margin, 2),
        "marginRatio": str(round(maint_margin_util, 6)),
        "leverage": round(leverage, 2),
        "unrealisedPnl": round(upnl, 2),
        "walletBalance": round(total_balance, 2),
    }

    return {
        "positions": positions,
        "balance": balance_data,
        "orders": [],
    }


async def poll_hotstuff_account(account: HotstuffAccountConfig, cache: HotstuffAccountCache) -> bool:
    raw = await fetch_hotstuff_account_summary(account, proxy=account.proxy_url)
    if raw is None:
        return False

    now = time.time()
    normalized = normalize_hotstuff_data(raw)
    changed = False

    if normalized["positions"] != cache.positions:
        cache.positions = normalized["positions"]
        changed = True
    cache.last_update["positions"] = now

    if normalized["balance"] != cache.balance:
        cache.balance = normalized["balance"]
        changed = True
    cache.last_update["balance"] = now

    if normalized["orders"] != cache.orders:
        cache.orders = normalized["orders"]
        changed = True
    cache.last_update["orders"] = now

    if changed:
        print(f"📊 [{account.name}] Hotstuff changes detected")

    return changed
