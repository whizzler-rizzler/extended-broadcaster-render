"""
EdgeX Exchange REST API Client
Fetches account data (positions, balances, orders) for EdgeX accounts.
Authentication: ECDSA signature on Stark curve with Keccak256 hashing.
API docs: https://edgex-1.gitbook.io/edgeX-documentation/api
"""

import os
import aiohttp
import time
import random
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from Crypto.Hash import keccak

EDGEX_API_BASE = "https://pro.edgex.exchange"

EC_ORDER = 3618502788666131213697322783095070105526743751716087489154079457884512865583
FIELD_PRIME = 3618502788666131213697322783095070105623107215331596699973092056135872020481
EC_GEN_X = 874739451078007766457464989774322083649278607533249481151382481072868806602
EC_GEN_Y = 152666792071518830868575557812948353041420400780739481342941381225525861407
ALPHA = 1
K_MODULUS = 0x0800000000000010ffffffffffffffffb781126dcae7b2321e66a241adc64d2f

EDGEX_CONTRACT_MAP: Dict[str, str] = {
    "10000001": "BTC-PERP",
    "10000002": "ETH-PERP",
    "10000003": "SOL-PERP",
    "10000004": "DOGE-PERP",
    "10000005": "XRP-PERP",
    "10000006": "ADA-PERP",
    "10000007": "AVAX-PERP",
    "10000008": "LINK-PERP",
    "10000009": "DOT-PERP",
    "10000010": "MATIC-PERP",
    "10000011": "LTC-PERP",
    "10000012": "UNI-PERP",
    "10000013": "APT-PERP",
    "10000014": "ARB-PERP",
    "10000015": "OP-PERP",
    "10000016": "SUI-PERP",
    "10000017": "NEAR-PERP",
    "10000018": "FIL-PERP",
    "10000019": "TIA-PERP",
    "10000020": "WLD-PERP",
}

EDGEX_TICKER_PRICES: Dict[str, float] = {}
EDGEX_TICKER_PRICES_UPDATED: float = 0


def ec_add(p1: Tuple[int, int], p2: Tuple[int, int]) -> Tuple[int, int]:
    if p1 == (0, 0):
        return p2
    if p2 == (0, 0):
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if y1 == y2:
            m = (3 * x1 * x1 + ALPHA) * pow(2 * y1, -1, FIELD_PRIME) % FIELD_PRIME
        else:
            return (0, 0)
    else:
        m = (y2 - y1) * pow(x2 - x1, -1, FIELD_PRIME) % FIELD_PRIME
    x3 = (m * m - x1 - x2) % FIELD_PRIME
    y3 = (m * (x1 - x3) - y1) % FIELD_PRIME
    return (x3, y3)


def ec_multiply(point: Tuple[int, int], scalar: int) -> Tuple[int, int]:
    result = (0, 0)
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = ec_add(result, addend)
        addend = ec_add(addend, addend)
        scalar >>= 1
    return result


def stark_sign(msg_hash: int, priv_key: int) -> Tuple[int, int]:
    while True:
        k = random.randrange(1, EC_ORDER)
        r_point = ec_multiply((EC_GEN_X, EC_GEN_Y), k)
        r = r_point[0] % EC_ORDER
        if r == 0:
            continue
        s = (msg_hash + r * priv_key) * pow(k, -1, EC_ORDER) % EC_ORDER
        if s == 0:
            continue
        return (r, s)


def build_signature(timestamp: int, method: str, path: str,
                    params: Optional[Dict[str, Any]] = None,
                    body: Optional[Dict[str, Any]] = None,
                    priv_key_hex: str = "",
                    pub_key_y_hex: str = "") -> Tuple[str, str]:
    if body:
        body_str = dict_to_sign_string(body)
        sign_content = f"{timestamp}{method}{path}{body_str}"
    elif params:
        param_pairs = []
        for key, value in sorted(params.items()):
            param_pairs.append(f"{key}={value}")
        query_string = "&".join(param_pairs)
        sign_content = f"{timestamp}{method}{path}{query_string}"
    else:
        sign_content = f"{timestamp}{method}{path}"

    k_hash = keccak.new(digest_bits=256)
    k_hash.update(sign_content.encode())
    content_hash = int.from_bytes(k_hash.digest(), 'big')
    msg_hash = content_hash % K_MODULUS

    pk_hex = priv_key_hex
    if pk_hex.startswith("0x"):
        pk_hex = pk_hex[2:]
    priv_key = int(pk_hex, 16)

    r, s = stark_sign(msg_hash, priv_key)

    r_hex = format(r, '064x')
    s_hex = format(s, '064x')

    y_hex = pub_key_y_hex
    if y_hex.startswith("0x"):
        y_hex = y_hex[2:]
    y_hex = y_hex.zfill(64)

    signature = r_hex + s_hex + y_hex
    return signature, str(timestamp)


def dict_to_sign_string(data: Any) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, bool):
        return str(data).lower()
    if isinstance(data, (int, float)):
        return str(data)
    if isinstance(data, list):
        if len(data) == 0:
            return ""
        values = [dict_to_sign_string(item) for item in data]
        return "&".join(values)
    if isinstance(data, dict):
        sorted_map = {}
        for key, val in data.items():
            sorted_map[key] = dict_to_sign_string(val)
        keys = sorted(sorted_map.keys())
        pairs = [f"{key}={sorted_map[key]}" for key in keys]
        return "&".join(pairs)
    return str(data)


@dataclass
class EdgeXAccountConfig:
    id: str
    name: str
    account_id: str
    priv_key: str
    pub_key_y: str
    proxy_url: Optional[str] = None


@dataclass
class EdgeXAccountCache:
    positions: Any = None
    balance: Any = None
    orders: Any = None
    account_info: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "orders": 0,
        "account_info": 0,
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


def load_edgex_accounts() -> List[EdgeXAccountConfig]:
    accounts = []
    for i in range(1, 20):
        account_id = os.getenv(f"EdgeX_{i}_AccountID", "").strip()
        priv_key = os.getenv(f"EdgeX_{i}_priv_key", "").strip()
        pub_key_y = os.getenv(f"EdgeX_{i}_publicKeyYCoordinate", "").strip()

        if not account_id or not priv_key:
            continue

        proxy_url = parse_rest_proxy(i)

        accounts.append(EdgeXAccountConfig(
            id=f"edgex_{i}",
            name=f"EdgeX {i}",
            account_id=account_id,
            priv_key=priv_key,
            pub_key_y=pub_key_y,
            proxy_url=proxy_url,
        ))
        proxy_info = f" (via Rest_account_{i}_proxy)" if proxy_url else ""
        print(f"✅ Loaded EdgeX Account {i}: ID={account_id[:8]}...{proxy_info}")

    return accounts


async def fetch_edgex_api(account: EdgeXAccountConfig, path: str,
                          method: str = "GET",
                          params: Optional[Dict[str, Any]] = None,
                          body: Optional[Dict[str, Any]] = None) -> Any:
    if params is None:
        params = {}
    if "accountId" not in params and method == "GET":
        params["accountId"] = account.account_id

    timestamp = int(time.time() * 1000)
    signature, ts_str = build_signature(
        timestamp, method, path, params=params, body=body,
        priv_key_hex=account.priv_key,
        pub_key_y_hex=account.pub_key_y,
    )

    headers = {
        "X-edgeX-Api-Timestamp": ts_str,
        "X-edgeX-Api-Signature": signature,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "extended-broadcaster/3.0",
    }

    url = f"{EDGEX_API_BASE}{path}"
    timeout = aiohttp.ClientTimeout(total=15.0)

    async def _do_request(proxy: Optional[str] = None) -> Any:
        kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout}
        if proxy:
            kwargs["proxy"] = proxy

        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, params=params, **kwargs) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == "SUCCESS":
                            return data.get("data")
                        else:
                            print(f"⚠️ [{account.name}][{path}] API error: {data.get('code')} {data.get('msg', '')}")
                            return None
                    else:
                        body_text = await response.text()
                        via = " via proxy" if proxy else ""
                        print(f"⚠️ [{account.name}][{path}]{via} HTTP {response.status}: {body_text[:120]}")
                        return None
            else:
                async with session.post(url, json=body, **kwargs) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == "SUCCESS":
                            return data.get("data")
                        return None
                    else:
                        body_text = await response.text()
                        print(f"⚠️ [{account.name}][{path}] HTTP {response.status}: {body_text[:120]}")
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


async def fetch_edgex_ticker_prices():
    global EDGEX_TICKER_PRICES, EDGEX_TICKER_PRICES_UPDATED
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{EDGEX_API_BASE}/api/v1/public/market/getTickers"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "SUCCESS":
                        tickers = data.get("data", [])
                        prices = {}
                        for ticker in tickers:
                            contract_id = ticker.get("contractId", "")
                            last_price = ticker.get("lastPrice") or ticker.get("oraclePrice")
                            if last_price:
                                market = EDGEX_CONTRACT_MAP.get(contract_id, f"CONTRACT-{contract_id}")
                                prices[contract_id] = float(last_price)
                                prices[market] = float(last_price)
                        EDGEX_TICKER_PRICES = prices
                        EDGEX_TICKER_PRICES_UPDATED = time.time()
                        return prices
    except Exception as e:
        print(f"⚠️ [EdgeX] Failed to fetch ticker prices: {e}")
    return EDGEX_TICKER_PRICES


def get_edgex_mark_price(contract_id: str) -> Optional[float]:
    return EDGEX_TICKER_PRICES.get(contract_id)


def normalize_edgex_positions(raw_positions: list) -> list:
    if not raw_positions:
        return []
    normalized = []
    for pos in raw_positions:
        open_size_str = pos.get("openSize", "0")
        open_size = float(open_size_str)
        if open_size == 0:
            continue

        contract_id = pos.get("contractId", "")
        market = EDGEX_CONTRACT_MAP.get(contract_id, f"CONTRACT-{contract_id}")

        side = "LONG" if open_size > 0 else "SHORT"
        abs_size = abs(open_size)

        open_value = abs(float(pos.get("openValue", "0")))
        entry_price = open_value / abs_size if abs_size > 0 else 0

        mark_price = get_edgex_mark_price(contract_id) or entry_price
        notional = abs_size * mark_price

        if side == "LONG":
            unrealised_pnl = abs_size * (mark_price - entry_price)
        else:
            unrealised_pnl = abs_size * (entry_price - mark_price)

        normalized.append({
            "market": market,
            "side": side,
            "size": str(abs_size),
            "value": str(notional),
            "openPrice": entry_price,
            "markPrice": mark_price,
            "liquidationPrice": 0,
            "unrealisedPnl": unrealised_pnl,
            "midPriceUnrealisedPnl": unrealised_pnl,
            "realisedPnl": 0,
            "margin": 0,
            "leverage": pos.get("longTermStat", {}).get("currentLeverage", "1") if side == "LONG"
                        else pos.get("shortTermStat", {}).get("currentLeverage", "1"),
            "status": "OPENED",
            "createdAt": 0,
            "updatedAt": int(time.time() * 1000),
        })
    return normalized


def normalize_edgex_balance(account_info: dict, positions: list = None) -> dict:
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

    total_equity = float(account_info.get("totalEquityValue", "0"))
    available = float(account_info.get("availableAmount", "0"))
    initial_margin = float(account_info.get("initialMarginRequirement", "0"))
    maintenance_margin = float(account_info.get("maintenanceMarginRequirement", "0"))
    total_value = float(account_info.get("totalValue", "0"))

    total_unrealised_pnl = 0.0
    total_exposure = 0.0
    if positions:
        for pos in positions:
            total_unrealised_pnl += float(pos.get("unrealisedPnl", 0))
            total_exposure += abs(float(pos.get("value", 0)))

    margin_ratio = 0.0
    if total_equity > 0 and initial_margin > 0:
        margin_ratio = initial_margin / total_equity

    leverage = 0.0
    if total_equity > 0 and total_exposure > 0:
        leverage = total_exposure / total_equity

    return {
        "collateralName": "USDT",
        "balance": str(total_value),
        "status": "ACTIVE" if account_info.get("status") == "NORMAL" else account_info.get("status", "UNKNOWN"),
        "equity": str(total_equity),
        "availableForTrade": str(available),
        "availableForWithdrawal": str(available),
        "unrealisedPnl": str(total_unrealised_pnl),
        "initialMargin": str(initial_margin),
        "marginRatio": str(margin_ratio),
        "updatedTime": int(time.time() * 1000),
        "exposure": str(total_exposure),
        "leverage": str(round(leverage, 2)),
    }


def normalize_edgex_orders(raw_orders: list) -> list:
    if not raw_orders:
        return []
    normalized = []
    for order in raw_orders:
        status = order.get("status", "")
        if status not in ("OPEN", "PENDING", "UNKNOWN_ORDER_STATUS"):
            continue
        contract_id = order.get("contractId", "")
        market = EDGEX_CONTRACT_MAP.get(contract_id, f"CONTRACT-{contract_id}")
        side = order.get("side", "UNKNOWN")
        if side == "UNKNOWN_ORDER_SIDE":
            side = "UNKNOWN"

        normalized.append({
            "id": order.get("id", ""),
            "market": market,
            "side": side,
            "type": order.get("type", "LIMIT"),
            "price": order.get("price", "0"),
            "size": order.get("size", "0"),
            "status": "ACTIVE",
            "createdAt": int(order.get("createdTime", "0")),
        })
    return normalized
