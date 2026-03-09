import os
import aiohttp
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

NADO_API_BASE = "https://gateway.prod.nado.xyz/v1"
DEFAULT_SUBACCOUNT_SUFFIX = "64656661756c740000000000"

NADO_SYMBOLS: Dict[int, str] = {}
NADO_SYMBOLS_LOADED = False


@dataclass
class NadoAccountConfig:
    id: str
    name: str
    wallet_address: str
    proxy_url: Optional[str] = None


@dataclass
class NadoAccountCache:
    positions: Any = None
    balance: Any = None
    orders: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "orders": 0,
    })


NADO_CACHES: Dict[str, NadoAccountCache] = {}


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


def _build_subaccount(wallet_address: str) -> str:
    addr = wallet_address.lower().replace("0x", "")
    return "0x" + addr + DEFAULT_SUBACCOUNT_SUFFIX


def load_nado_accounts() -> List[NadoAccountConfig]:
    accounts = []
    for i in range(1, 20):
        wallet = os.getenv(f"Reya_{i}_wallet_main", "").strip()
        if not wallet:
            wallet = os.getenv(f"Reya_{i}_wallet_adress", "").strip()
        if not wallet:
            continue

        proxy_url = None
        proxy_raw = os.getenv(f"Nado_{i}_proxy", "").strip()
        if not proxy_raw:
            proxy_raw = os.getenv(f"Rest_account_{i}_proxy", "").strip()
        if proxy_raw:
            proxy_url = _parse_proxy(proxy_raw)

        account = NadoAccountConfig(
            id=f"nado_{i}",
            name=f"Nado {i}",
            wallet_address=wallet,
            proxy_url=proxy_url,
        )
        accounts.append(account)

        if account.id not in NADO_CACHES:
            NADO_CACHES[account.id] = NadoAccountCache()

        proxy_info = f" (proxy: {proxy_url[:30]}...)" if proxy_url else ""
        print(f"✅ Loaded Nado account {i}: {wallet[:10]}...{wallet[-6:]}{proxy_info}")

    print(f"📊 Total Nado accounts loaded: {len(accounts)}")
    return accounts


async def fetch_nado_symbols() -> Dict[int, str]:
    global NADO_SYMBOLS, NADO_SYMBOLS_LOADED
    if NADO_SYMBOLS_LOADED:
        return NADO_SYMBOLS

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{NADO_API_BASE}/query",
                json={"type": "symbols"},
                headers={"Accept-Encoding": "gzip"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        symbols = data["data"]["symbols"]
                        for sym_name, sym_data in symbols.items():
                            NADO_SYMBOLS[sym_data["product_id"]] = sym_name
                        NADO_SYMBOLS_LOADED = True
                        print(f"✅ [Nado] Loaded {len(NADO_SYMBOLS)} symbols")
                        return NADO_SYMBOLS
    except Exception as e:
        print(f"⚠️ [Nado] Failed to load symbols: {e}")

    NADO_SYMBOLS[0] = "USDT0"
    NADO_SYMBOLS[2] = "BTC-PERP"
    NADO_SYMBOLS[4] = "ETH-PERP"
    NADO_SYMBOLS[8] = "SOL-PERP"
    return NADO_SYMBOLS


async def fetch_nado_subaccount_info(account: NadoAccountConfig, proxy: Optional[str] = None) -> Optional[Dict]:
    subaccount = _build_subaccount(account.wallet_address)
    payload = {"type": "subaccount_info", "subaccount": subaccount}
    headers = {"Content-Type": "application/json", "Accept-Encoding": "gzip"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{NADO_API_BASE}/query",
                json=payload,
                headers=headers,
                proxy=proxy,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"⚠️ [{account.name}] Nado HTTP {resp.status}: {text[:200]}")
                    return None
                data = await resp.json()
                if data.get("status") == "success":
                    return data.get("data")
                else:
                    print(f"⚠️ [{account.name}] Nado error: {data.get('error', 'unknown')}")
                    return None
    except Exception as e:
        print(f"❌ [{account.name}] Nado exception: {e}")
        return None


def _x18(value: str) -> float:
    try:
        return int(value) / 1e18
    except (ValueError, TypeError):
        return 0.0


def _get_symbol(product_id: int) -> str:
    return NADO_SYMBOLS.get(product_id, f"UNKNOWN-{product_id}")


def normalize_nado_data(raw: Dict) -> Dict:
    if not raw or not raw.get("exists"):
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

    spot_balances = raw.get("spot_balances", [])
    perp_balances = raw.get("perp_balances", [])
    spot_products = {p["product_id"]: p for p in raw.get("spot_products", [])}
    perp_products = {p["product_id"]: p for p in raw.get("perp_products", [])}
    healths = raw.get("healths", [])

    usdt_balance = 0
    for sb in spot_balances:
        if sb["product_id"] == 0:
            usdt_balance = _x18(sb["balance"]["amount"])
            break

    positions = []
    total_unrealised_pnl = 0
    total_notional = 0

    for pb in perp_balances:
        amount = _x18(pb["balance"]["amount"])
        if abs(amount) < 1e-12:
            continue

        pid = pb["product_id"]
        v_quote = _x18(pb["balance"]["v_quote_balance"])
        symbol = _get_symbol(pid)

        product = perp_products.get(pid, {})
        mark_price = _x18(product.get("risk", {}).get("price_x18", "0"))

        notional = abs(amount) * mark_price
        total_notional += notional

        entry_price = abs(v_quote / amount) if amount != 0 else 0
        side = "SHORT" if amount > 0 else "LONG"

        pnl = -(amount * mark_price + v_quote)

        total_unrealised_pnl += pnl

        positions.append({
            "market": symbol,
            "side": side,
            "size": abs(amount),
            "openPrice": round(entry_price, 2),
            "entryPrice": round(entry_price, 2),
            "markPrice": round(mark_price, 2),
            "unrealisedPnl": round(pnl, 2),
            "midPriceUnrealisedPnl": round(pnl, 2),
            "notional": round(notional, 2),
            "value": str(round(notional, 2)),
            "leverage": 0,
            "liquidationPrice": 0,
            "funding": 0,
            "isolated": False,
            "status": "OPENED",
        })

    equity = usdt_balance + total_unrealised_pnl
    for sb in spot_balances:
        if sb["product_id"] != 0:
            spot_amt = _x18(sb["balance"]["amount"])
            if abs(spot_amt) > 1e-12:
                sp = spot_products.get(sb["product_id"], {})
                spot_price = _x18(sp.get("risk", {}).get("price_x18", "0"))
                equity += spot_amt * spot_price

    unweighted = healths[2] if len(healths) > 2 else {}
    assets = _x18(unweighted.get("assets", "0"))
    liabilities = _x18(unweighted.get("liabilities", "0"))

    margin_ratio = liabilities / assets if assets > 0 else 0
    leverage = total_notional / equity if equity > 0 else 0
    available = equity - liabilities if equity > 0 else 0

    balance_data = {
        "balance": round(usdt_balance, 2),
        "equity": round(equity, 2),
        "availableBalance": round(max(0, available), 2),
        "availableForTrade": str(round(max(0, available), 2)),
        "totalMarginUsed": round(liabilities, 2),
        "marginRatio": str(round(margin_ratio, 6)),
        "leverage": round(leverage, 2),
        "unrealisedPnl": round(total_unrealised_pnl, 2),
        "walletBalance": round(usdt_balance, 2),
    }

    orders = []
    for o in raw.get("open_orders", []):
        pid = o.get("product_id", 0)
        symbol = _get_symbol(pid)
        amount = _x18(o.get("amount", "0"))
        price = _x18(o.get("price_x18", "0"))
        side = "SHORT" if amount > 0 else "LONG"

        orders.append({
            "market": symbol,
            "side": side,
            "price": round(price, 2),
            "size": abs(amount),
            "filledSize": 0,
            "type": "limit",
            "reduceOnly": False,
            "orderId": o.get("digest", ""),
            "createdAt": None,
        })

    return {
        "positions": positions,
        "balance": balance_data,
        "orders": orders,
    }


async def poll_nado_account(account: NadoAccountConfig, cache: NadoAccountCache) -> bool:
    await fetch_nado_symbols()

    raw = await fetch_nado_subaccount_info(account, proxy=account.proxy_url)
    if raw is None:
        return False

    now = time.time()
    normalized = normalize_nado_data(raw)
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
        print(f"📊 [{account.name}] Nado changes detected")

    return changed
