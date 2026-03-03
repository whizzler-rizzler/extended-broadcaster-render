"""
GRVT (Gravity Markets) Exchange REST API Client
Fetches account data (positions, balances, orders) for GRVT accounts.
Authentication: Cookie-based session via API key login.
API docs: https://api-docs.grvt.io/
"""

import os
import aiohttp
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

GRVT_AUTH_URL = "https://edge.grvt.io/auth/api_key/login"
GRVT_TRADES_URL = "https://trades.grvt.io"


@dataclass
class GrvtAccountConfig:
    id: str
    name: str
    api_key: str
    trading_account_id: str
    account_id: str
    private_key: str = ""
    proxy_url: Optional[str] = None
    session_cookie: Optional[str] = None
    session_account_id: Optional[str] = None
    session_expires: float = 0


@dataclass
class GrvtAccountCache:
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
    candidates = [
        f"GRVT_{account_num}_proxy",
        f"Rest_account_{account_num}_proxy",
    ]
    for i in range(1, 10):
        candidates.append(f"Rest_account_{i}_proxy")
    seen = set()
    for env_name in candidates:
        if env_name in seen:
            continue
        seen.add(env_name)
        raw = os.getenv(env_name, "").strip()
        if raw:
            parsed = _parse_proxy_raw(raw)
            if parsed:
                return parsed
    return None


def load_grvt_accounts() -> List[GrvtAccountConfig]:
    accounts = []
    for i in range(1, 20):
        api_key = (
            os.getenv(f"GRVT_{i}_api_key", "").strip()
            or os.getenv(f"Grvt_{i}_api_key", "").strip()
        )
        trading_account_id = os.getenv(f"GRVT_{i}_trading_account_ID", "").strip()
        account_id = (
            os.getenv(f"GRVT_{i}_account_ID", "").strip()
            or os.getenv(f"Grvt_{i}_account_ID", "").strip()
        )
        private_key = (
            os.getenv(f"GRVT_{i}_Secret_Private_Key", "").strip()
            or os.getenv(f"Grvt_{i}_Secret_Private_Key", "").strip()
        )

        if not api_key or not trading_account_id:
            continue

        proxy_url = _find_proxy(i)

        accounts.append(GrvtAccountConfig(
            id=f"grvt_{i}",
            name=f"GRVT {i}",
            api_key=api_key,
            trading_account_id=trading_account_id,
            account_id=account_id,
            private_key=private_key,
            proxy_url=proxy_url,
        ))
        proxy_info = f" (via proxy)" if proxy_url else " (direct)"
        print(f"✅ Loaded GRVT Account {i}: trading_id={trading_account_id}{proxy_info}")

    return accounts


async def authenticate_grvt(account: GrvtAccountConfig) -> bool:
    if account.session_cookie and time.time() < account.session_expires:
        return True

    timeout = aiohttp.ClientTimeout(total=15.0)
    headers = {
        "Content-Type": "application/json",
        "Cookie": "rm=true;",
    }
    payload = {"api_key": account.api_key}

    async def _do_auth(proxy: Optional[str] = None) -> bool:
        kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout, "json": payload}
        if proxy:
            kwargs["proxy"] = proxy

        async with aiohttp.ClientSession() as session:
            async with session.post(GRVT_AUTH_URL, **kwargs) as response:
                body_text = await response.text()
                via = " via proxy" if proxy else ""

                if response.status == 200:
                    if "not allowed" in body_text.lower() or "failure" in body_text.lower():
                        print(f"⚠️ [{account.name}] GRVT auth{via}: geo-blocked ({body_text[:100]})")
                        return False

                    cookies = response.headers.getall("Set-Cookie", [])
                    for cookie in cookies:
                        if "gravity=" in cookie:
                            account.session_cookie = cookie.split("gravity=")[1].split(";")[0]
                            break

                    grvt_account_id = response.headers.get("x-grvt-account-id", "").strip()
                    if grvt_account_id:
                        account.session_account_id = grvt_account_id

                    if not account.session_account_id and account.account_id:
                        account.session_account_id = account.account_id

                    account.session_expires = time.time() + 3500

                    if account.session_cookie:
                        print(f"✅ [{account.name}] GRVT authenticated (cookie obtained)")
                        return True
                    else:
                        print(f"⚠️ [{account.name}] GRVT auth{via}: 200 but no cookie. Body: {body_text[:200]}")
                        return False
                else:
                    print(f"⚠️ [{account.name}] GRVT auth{via} HTTP {response.status}: {body_text[:200]}")
                    return False

    try:
        if account.proxy_url:
            try:
                result = await _do_auth(account.proxy_url)
                if result:
                    return True
            except Exception as proxy_err:
                print(f"⚠️ [{account.name}] GRVT auth proxy failed ({type(proxy_err).__name__}), trying direct...")
        return await _do_auth(None)
    except Exception as e:
        print(f"❌ [{account.name}] GRVT auth error: {type(e).__name__}: {e}")
        return False


async def fetch_grvt_api(account: GrvtAccountConfig, endpoint: str,
                          payload: Optional[Dict[str, Any]] = None) -> Any:
    if not account.session_cookie:
        auth_ok = await authenticate_grvt(account)
        if not auth_ok:
            return None

    url = f"{GRVT_TRADES_URL}/full/v1/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"gravity={account.session_cookie}",
    }
    if account.session_account_id:
        headers["X-Grvt-Account-Id"] = account.session_account_id

    if payload is None:
        payload = {}

    timeout = aiohttp.ClientTimeout(total=15.0)

    async def _do_request(proxy: Optional[str] = None) -> Any:
        kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout, "json": payload}
        if proxy:
            kwargs["proxy"] = proxy

        async with aiohttp.ClientSession() as session:
            async with session.post(url, **kwargs) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    account.session_cookie = None
                    account.session_expires = 0
                    print(f"⚠️ [{account.name}][{endpoint}] 401 - session expired, will re-auth")
                    return None
                else:
                    body_text = await response.text()
                    via = " via proxy" if proxy else ""
                    print(f"⚠️ [{account.name}][{endpoint}]{via} HTTP {response.status}: {body_text[:200]}")
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
        print(f"❌ [{account.name}][{endpoint}] {type(e).__name__}: {e}")
        return None


def normalize_grvt_positions(sub_account_data: dict) -> list:
    positions_raw = sub_account_data.get("positions", [])
    if not positions_raw:
        return []

    normalized = []
    for pos in positions_raw:
        instrument = pos.get("instrument", "")
        market = instrument.replace("_Perp", "-PERP").replace("_", "-")

        size_raw = float(pos.get("size", "0"))
        if size_raw == 0:
            continue

        side = "LONG" if size_raw > 0 else "SHORT"
        abs_size = abs(size_raw)

        entry_price_raw = float(pos.get("entry_price", "0"))
        mark_price_raw = float(pos.get("mark_price", "0"))
        entry_price = entry_price_raw / 1e9 if entry_price_raw > 1e6 else entry_price_raw
        mark_price = mark_price_raw / 1e9 if mark_price_raw > 1e6 else mark_price_raw

        notional = abs(float(pos.get("notional", "0")))
        unrealized_pnl = float(pos.get("unrealized_pnl", "0"))

        est_liq_price_raw = float(pos.get("est_liquidation_price", "0"))
        est_liq_price = est_liq_price_raw / 1e9 if est_liq_price_raw > 1e6 else est_liq_price_raw

        leverage = float(pos.get("leverage", "0"))

        pos_margin = notional / leverage if leverage > 0 else 0

        normalized.append({
            "market": market,
            "side": side,
            "size": str(abs_size),
            "value": str(notional),
            "openPrice": entry_price,
            "markPrice": mark_price,
            "liquidationPrice": round(est_liq_price, 2),
            "unrealisedPnl": unrealized_pnl,
            "midPriceUnrealisedPnl": unrealized_pnl,
            "realisedPnl": float(pos.get("realized_pnl", "0")),
            "margin": round(pos_margin, 2),
            "leverage": str(leverage),
            "status": "OPENED",
            "createdAt": 0,
            "updatedAt": int(time.time() * 1000),
        })
    return normalized


def normalize_grvt_balance(sub_account_data: dict, positions: list = None) -> dict:
    if not sub_account_data:
        return {
            "collateralName": "USDT",
            "balance": "0",
            "status": "UNKNOWN",
            "equity": "0",
            "availableForTrade": "0",
            "availableForWithdrawal": "0",
            "unrealisedPnl": "0",
            "initialMargin": "0",
            "maintenanceMargin": "0",
            "marginRatio": "0",
            "updatedTime": int(time.time() * 1000),
            "exposure": "0",
            "leverage": "0",
        }

    total_equity = float(sub_account_data.get("total_equity", "0"))
    unrealized_pnl = float(sub_account_data.get("unrealized_pnl", "0"))
    initial_margin = float(sub_account_data.get("initial_margin", "0"))
    maintenance_margin = float(sub_account_data.get("maintenance_margin", "0"))
    available_balance = float(sub_account_data.get("available_balance", "0"))

    spot_balances = sub_account_data.get("spot_balances", [])
    raw_balance = 0.0
    for sb in spot_balances:
        raw_balance += float(sb.get("balance", "0"))

    if raw_balance == 0:
        raw_balance = total_equity - unrealized_pnl

    total_exposure = 0.0
    if positions:
        for p in positions:
            total_exposure += float(p.get("value", "0"))

    margin_ratio = 0.0
    if total_equity > 0:
        margin_ratio = maintenance_margin / total_equity

    leverage = 0.0
    if total_equity > 0 and total_exposure > 0:
        leverage = total_exposure / total_equity

    settle_currency = sub_account_data.get("settle_currency", "USDT")

    return {
        "collateralName": settle_currency,
        "balance": str(raw_balance),
        "status": "ACTIVE",
        "equity": str(total_equity),
        "availableForTrade": str(available_balance),
        "availableForWithdrawal": str(available_balance),
        "unrealisedPnl": str(unrealized_pnl),
        "initialMargin": str(initial_margin),
        "maintenanceMargin": str(maintenance_margin),
        "marginRatio": str(round(margin_ratio, 6)),
        "updatedTime": int(time.time() * 1000),
        "exposure": str(total_exposure),
        "leverage": str(round(leverage, 2)),
    }


def normalize_grvt_orders(open_orders_data: list) -> list:
    if not open_orders_data:
        return []
    normalized = []
    for order in open_orders_data:
        legs = order.get("legs", [])
        if not legs:
            continue
        leg = legs[0]
        instrument = leg.get("instrument", "")
        market = instrument.replace("_Perp", "-PERP").replace("_", "-")
        is_buying = leg.get("is_buying_asset", False)
        side = "LONG" if is_buying else "SHORT"
        limit_price_raw = float(leg.get("limit_price", "0"))
        limit_price = limit_price_raw / 1e9 if limit_price_raw > 1e6 else limit_price_raw

        order_id = order.get("order_id", "")
        metadata = order.get("metadata", {})
        client_order_id = metadata.get("client_order_id", "")

        normalized.append({
            "id": str(order_id or client_order_id),
            "market": market,
            "side": side,
            "type": "LIMIT",
            "price": str(limit_price),
            "size": str(leg.get("size", "0")),
            "status": "ACTIVE",
            "createdAt": int(float(metadata.get("create_time", "0")) / 1e6),
        })
    return normalized


async def poll_grvt_account(account: GrvtAccountConfig, cache: GrvtAccountCache) -> bool:
    changed = False

    auth_ok = await authenticate_grvt(account)
    if not auth_ok:
        return False

    summary = await fetch_grvt_api(account, "account_summary", {
        "sub_account_id": account.trading_account_id
    })

    if summary and isinstance(summary, dict):
        result = summary.get("result", summary)

        positions = normalize_grvt_positions(result)
        balance = normalize_grvt_balance(result, positions)

        if positions != cache.positions:
            cache.positions = positions
            cache.last_update["positions"] = time.time()
            changed = True

        if balance != cache.balance:
            cache.balance = balance
            cache.last_update["balance"] = time.time()
            changed = True

    orders_resp = await fetch_grvt_api(account, "open_orders", {
        "sub_account_id": account.trading_account_id,
        "kind": ["PERPETUAL"],
    })

    if orders_resp is not None:
        result = orders_resp.get("result", orders_resp)
        raw_orders = result if isinstance(result, list) else result.get("orders", []) if isinstance(result, dict) else []
        orders = normalize_grvt_orders(raw_orders)
        if orders != cache.orders:
            cache.orders = orders
            cache.last_update["orders"] = time.time()
            changed = True

    return changed


_GRVT_POINTS_AUTH_EXPIRED = "__auth_expired__"


async def _grvt_points_request(account_name: str, url: str, headers: dict, proxy: Optional[str] = None) -> Any:
    timeout = aiohttp.ClientTimeout(total=15.0)
    kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout, "json": {}}
    if proxy:
        kwargs["proxy"] = proxy
    async with aiohttp.ClientSession() as session:
        async with session.post(url, **kwargs) as response:
            if response.status == 200:
                return await response.json()
            if response.status == 401:
                return _GRVT_POINTS_AUTH_EXPIRED
            body = await response.text()
            via = " via proxy" if proxy else ""
            print(f"⚠️ [{account_name}][points]{via} HTTP {response.status}: {body[:120]}")
            return None


async def fetch_grvt_points(account: GrvtAccountConfig, cache: GrvtAccountCache) -> Dict[str, Any] | None:
    if not account.session_cookie:
        auth_ok = await authenticate_grvt(account)
        if not auth_ok:
            return None

    headers = {
        "Content-Type": "application/json",
        "Cookie": f"gravity={account.session_cookie}",
    }
    if account.session_account_id:
        headers["X-Grvt-Account-Id"] = account.session_account_id

    for base_url in ["https://edge.grvt.io", GRVT_TRADES_URL]:
        url = f"{base_url}/full/v1/get_point_summary"
        try:
            result_data = None
            if account.proxy_url:
                try:
                    result_data = await _grvt_points_request(account.name, url, headers, account.proxy_url)
                except Exception:
                    pass

            if result_data is _GRVT_POINTS_AUTH_EXPIRED:
                result_data = None

            if result_data is None:
                result_data = await _grvt_points_request(account.name, url, headers)

            if result_data is _GRVT_POINTS_AUTH_EXPIRED:
                account.session_cookie = None
                account.session_expires = 0
                print(f"⚠️ [{account.name}] GRVT points 401 - session expired, will re-auth")
                auth_ok = await authenticate_grvt(account)
                if not auth_ok:
                    return None
                headers["Cookie"] = f"gravity={account.session_cookie}"
                if account.session_account_id:
                    headers["X-Grvt-Account-Id"] = account.session_account_id
                result_data = await _grvt_points_request(account.name, url, headers)
                if result_data is _GRVT_POINTS_AUTH_EXPIRED or result_data is None:
                    continue

            if result_data is not None:
                result = result_data.get("result", result_data) if isinstance(result_data, dict) else {}
                total_points = float(result.get("total_points", 0))
                community_points = float(result.get("community_referral_points", 0))
                return {
                    "points": total_points,
                    "community_points": community_points,
                    "last_update": time.time(),
                    "account_name": account.name,
                }
        except Exception as e:
            print(f"⚠️ [{account.name}] GRVT points {base_url} error: {e}")
            continue

    return None
