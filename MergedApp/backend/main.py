from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import aiohttp
import asyncio
import os
from typing import Dict, Any, Set, List, Optional
import json
import time
from datetime import datetime
from dataclasses import dataclass, field
from supabase_client import supabase_client
from margin_alerts import alert_manager, MARGIN_THRESHOLDS

app = FastAPI(title="Extended API Multi-Account Broadcaster")

# ============= BROADCASTER MODE CONFIGURATION =============
BROADCASTER_MODE = os.getenv("BROADCASTER_MODE", "COLLECTOR")
REMOTE_API_BASE = os.getenv("REMOTE_API_BASE", "").rstrip("/")
IS_FRONTEND_ONLY = BROADCASTER_MODE == "FRONTEND_ONLY"

if IS_FRONTEND_ONLY:
    print(f"🌐 Running in FRONTEND_ONLY mode")
    print(f"📡 Proxying API requests to: {REMOTE_API_BASE}")
else:
    print(f"🔄 Running in COLLECTOR mode - polling Extended API directly")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= ACCOUNT CONFIGURATION =============
@dataclass
class AccountConfig:
    id: str
    name: str
    api_key: str
    base_url: str = "https://api.starknet.extended.exchange/api/v1"
    proxy_url: Optional[str] = None  # Optional proxy URL per account

@dataclass 
class AccountCache:
    positions: Any = None
    balance: Any = None
    trades: Any = None
    orders: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "trades": 0,
        "orders": 0,
    })

# Load account configurations from environment variables
def load_accounts() -> List[AccountConfig]:
    import re
    accounts = []
    
    # Auto-detect accounts from environment variables
    # Pattern: Extended_N_XXXXXX_API_KEY where N is account number and XXXXXX is unique code
    api_key_pattern = re.compile(r'^Extended_(\d+)_([A-Za-z0-9]+)_API_KEY$')
    
    # Scan all environment variables to find account API keys
    detected_accounts = {}
    for env_var in os.environ:
        match = api_key_pattern.match(env_var)
        if match:
            account_num = int(match.group(1))
            account_code = match.group(2)
            api_key = os.getenv(env_var)
            if api_key:
                detected_accounts[account_num] = {
                    'code': account_code,
                    'api_key': api_key
                }
    
    print(f"🔍 Detected {len(detected_accounts)} accounts from environment variables")
    
    # Process detected accounts in order
    for i in sorted(detected_accounts.keys()):
        code = detected_accounts[i]['code']
        api_key = detected_accounts[i]['api_key']
        
        # Get proxy URL - supports multiple variable name formats:
        # 1. Extended_N_CODE_Proxy (new format) - regular proxy, NO -staticresidential suffix
        # 2. Extended_N_PROXY_N_URL (old format) - staticresidential proxy, ADD suffix
        # Value formats supported:
        # - Full URL: http://username:password@ip:port/
        # - Legacy: IP:PORT:Username:Password
        proxy_var_new = f"Extended_{i}_{code}_Proxy"
        proxy_var_old = f"Extended_{i}_PROXY_{i}_URL"
        
        # Check which format is used to determine if we need staticresidential suffix
        raw_proxy_new = os.getenv(proxy_var_new)
        raw_proxy_old = os.getenv(proxy_var_old)
        
        # New format (12-25): regular proxy, no suffix needed
        # Old format (1-10): staticresidential proxy, add suffix for legacy format
        use_staticresidential = False
        if raw_proxy_new:
            raw_proxy = raw_proxy_new
            use_staticresidential = False  # New accounts don't need suffix
        elif raw_proxy_old:
            raw_proxy = raw_proxy_old
            use_staticresidential = True   # Old accounts need suffix for legacy format
        else:
            raw_proxy = None
        
        proxy_url = None
        if raw_proxy:
            raw_proxy = raw_proxy.strip()
            if raw_proxy.startswith("http://") or raw_proxy.startswith("https://"):
                # Full URL format - use as-is (user controls the username)
                proxy_url = raw_proxy
                try:
                    at_idx = raw_proxy.find('@')
                    if at_idx > 0:
                        host_part = raw_proxy[at_idx+1:].rstrip('/')
                        print(f"✅ Account {i} proxy: {host_part}")
                    else:
                        print(f"✅ Account {i} proxy: configured (full URL)")
                except:
                    print(f"✅ Account {i} proxy: configured (full URL)")
            else:
                # Legacy format: IP:PORT:Username:Password
                parts = raw_proxy.split(':')
                if len(parts) == 4:
                    ip, port, username, password = parts
                    # Only add -staticresidential for old format accounts (1-10)
                    if use_staticresidential and not username.endswith('-staticresidential'):
                        username = f"{username}-staticresidential"
                    proxy_url = f"http://{username}:{password}@{ip}:{port}"
                    print(f"✅ Account {i} proxy: {ip}:{port} (user: {username})")
                else:
                    print(f"⚠️ Account {i} proxy invalid: expected IP:PORT:User:Pass or full URL, got: {raw_proxy[:30]}...")
        else:
            print(f"⚠️ Account {i}: no proxy ({proxy_var_new} or {proxy_var_old} not set)")
        
        accounts.append(AccountConfig(
            id=f"account_{i}",
            name=f"Extended {i} ({code})",
            api_key=api_key,
            base_url="https://api.starknet.extended.exchange/api/v1",
            proxy_url=proxy_url
        ))
        proxy_info = f" (via proxy)" if proxy_url else " (no proxy)"
        print(f"✅ Loaded Account {i}: Extended_{i}_{code}{proxy_info}")
    
    # Fallback: Try ACCOUNT_N_API_KEY format
    if not accounts:
        for i in range(1, 11):
            api_key = os.getenv(f"ACCOUNT_{i}_API_KEY")
            if api_key:
                name = os.getenv(f"ACCOUNT_{i}_NAME", f"Account {i}")
                base_url = os.getenv(f"ACCOUNT_{i}_BASE_URL", "https://api.starknet.extended.exchange/api/v1")
                accounts.append(AccountConfig(
                    id=f"account_{i}",
                    name=name,
                    api_key=api_key,
                    base_url=base_url.rstrip("/")
                ))
                print(f"✅ Loaded Account {i}: {name}")
    
    # Final fallback: old single-account format
    if not accounts:
        api_key = os.getenv("EXTENDED_API_KEY")
        if api_key:
            accounts.append(AccountConfig(
                id="account_1",
                name="Main Account",
                api_key=api_key,
                base_url=os.getenv("EXTENDED_API_BASE_URL", "https://api.starknet.extended.exchange/api/v1").rstrip("/")
            ))
            print(f"✅ Loaded single account (legacy mode)")
    
    return accounts

# Load accounts only in COLLECTOR mode
if not IS_FRONTEND_ONLY:
    ACCOUNTS = load_accounts()
    if not ACCOUNTS:
        raise ValueError("No account API keys configured! Set ACCOUNT_1_API_KEY or EXTENDED_API_KEY")
    print(f"🎯 Total accounts configured: {len(ACCOUNTS)}")
else:
    ACCOUNTS = []
    print("🌐 FRONTEND_ONLY mode - no local accounts loaded")

# ============= BROADCASTER GLOBAL STATE =============
# Cache for each account - keyed by account ID
BROADCASTER_CACHES: Dict[str, AccountCache] = {
    account.id: AccountCache() for account in ACCOUNTS
}

# Set of connected WebSocket clients
BROADCAST_CLIENTS: Set[WebSocket] = set()

# Poller state tracking
TRADES_POLL_COUNTER = 0

# ============= ORDER BOOK STREAM STATE =============
ORDERBOOK_CACHE: Dict[str, Any] = {}
ORDERBOOK_LAST_UPDATE: float = 0
ORDERBOOK_WS_CONNECTED: bool = False
ORDERBOOK_MARKETS = ["ETH-PERP", "BTC-PERP", "SOL-PERP", "DOGE-PERP", "XRP-PERP", "ADA-PERP", "AVAX-PERP", "LINK-PERP", "DOT-PERP", "MATIC-PERP"]
EXTENDED_STREAM_URL = "wss://api.starknet.extended.exchange/stream.extended.exchange/v1"
ORDERBOOK_PROXY_URL = os.getenv("ORDERBOOK_PROXY_URL")
ORDERBOOK_DEPTH = 20


# ============= PROXY FUNCTION FOR FRONTEND_ONLY MODE =============
async def proxy_to_remote(endpoint: str, method: str = "GET") -> Dict[str, Any]:
    """Proxy request to remote backend in FRONTEND_ONLY mode."""
    if not REMOTE_API_BASE:
        raise HTTPException(status_code=503, detail="REMOTE_API_BASE not configured")
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{REMOTE_API_BASE}{endpoint}"
            if method == "POST":
                async with session.post(url, timeout=aiohttp.ClientTimeout(total=30.0)) as resp:
                    if resp.status in [200, 201]:
                        return await resp.json()
                    else:
                        raise HTTPException(status_code=resp.status, detail=f"Remote API error: {resp.status}")
            else:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30.0)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        raise HTTPException(status_code=resp.status, detail=f"Remote API error: {resp.status}")
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=503, detail=f"Remote API connection error: {str(e)}")


# ============= UTILITY FUNCTIONS =============
def data_changed(old_data: Any, new_data: Any) -> bool:
    """Compare two data structures to detect changes."""
    if old_data is None and new_data is not None:
        return True
    if old_data is not None and new_data is None:
        return True
    return json.dumps(old_data, sort_keys=True) != json.dumps(new_data, sort_keys=True)


async def fetch_account_api(account: AccountConfig, endpoint: str) -> Dict[str, Any] | None:
    """Fetch data from Extended API for a specific account, using proxy if configured."""
    try:
        async with aiohttp.ClientSession() as session:
            request_kwargs = {
                "headers": {
                    "X-Api-Key": account.api_key,
                    "User-Agent": "extended-broadcaster/3.0-multiacccount",
                    "Content-Type": "application/json",
                },
                "timeout": aiohttp.ClientTimeout(total=15.0)
            }
            
            # Add proxy if configured - this routes the request through the proxy IP
            if account.proxy_url:
                request_kwargs["proxy"] = account.proxy_url
            
            url = f"{account.base_url}{endpoint}"
            
            async with session.get(url, **request_kwargs) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    proxy_info = f" (proxy: {account.proxy_url[:25]}...)" if account.proxy_url else ""
                    print(f"⚠️ [{account.name}][{endpoint}] HTTP {response.status}{proxy_info}")
                    return None
    except Exception as e:
        proxy_info = f" via proxy" if account.proxy_url else ""
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "No error message"
        print(f"❌ [{account.name}][{endpoint}]{proxy_info} {error_type}: {error_msg}")
        return None


async def broadcast_to_clients(message: Dict[str, Any]):
    """Broadcast a message to all connected WebSocket clients."""
    if not BROADCAST_CLIENTS:
        return
    
    disconnected = set()
    message_json = json.dumps(message)
    
    for client in BROADCAST_CLIENTS:
        try:
            await client.send_text(message_json)
        except Exception as e:
            disconnected.add(client)
    
    for client in disconnected:
        BROADCAST_CLIENTS.discard(client)
        print(f"🗑️ [Broadcast] Removed disconnected client (remaining: {len(BROADCAST_CLIENTS)})")


# ============= BACKGROUND POLLERS =============
async def poll_account_fast_data(account: AccountConfig):
    """Poll positions and balance for a single account (4x per second)."""
    cache = BROADCASTER_CACHES[account.id]
    
    positions_task = fetch_account_api(account, "/user/positions")
    balance_task = fetch_account_api(account, "/user/balance")
    
    new_positions, new_balance = await asyncio.gather(
        positions_task, balance_task, return_exceptions=True
    )
    
    changes = []
    
    if not isinstance(new_positions, Exception) and new_positions is not None:
        if data_changed(cache.positions, new_positions):
            cache.positions = new_positions
            cache.last_update["positions"] = time.time()
            changes.append("positions")
    
    if not isinstance(new_balance, Exception) and new_balance is not None:
        if data_changed(cache.balance, new_balance):
            cache.balance = new_balance
            cache.last_update["balance"] = time.time()
            changes.append("balance")
    
    if changes:
        print(f"📊 [{account.name}] Changes: {', '.join(changes)} - broadcasting")
        await broadcast_to_clients({
            "type": "account_update",
            "account_id": account.id,
            "account_name": account.name,
            "positions": cache.positions if "positions" in changes else None,
            "balance": cache.balance if "balance" in changes else None,
            "timestamp": time.time()
        })
        
        # Save to Supabase (async, non-blocking)
        if supabase_client.is_initialized:
            account_idx = int(account.id.split('_')[1])
            
            # Save account snapshot with balance
            if "balance" in changes and cache.balance:
                balance_data = cache.balance.get('data', cache.balance) if isinstance(cache.balance, dict) else cache.balance
                snapshot_data = {
                    "raw_data": {"accounts": [balance_data] if isinstance(balance_data, dict) else balance_data},
                    "active_orders": cache.orders or []
                }
                asyncio.create_task(supabase_client.save_account_snapshot(account_idx, snapshot_data, exchange="extended"))
            
            # Save positions
            if "positions" in changes and cache.positions:
                positions_list = cache.positions.get('data', cache.positions) if isinstance(cache.positions, dict) else cache.positions
                if isinstance(positions_list, list):
                    asyncio.create_task(supabase_client.save_positions(account_idx, positions_list, exchange="extended"))


async def poll_account_trades(account: AccountConfig):
    """Poll closed positions (with PnL) for a single account."""
    cache = BROADCASTER_CACHES[account.id]
    new_trades = await fetch_account_api(account, "/user/positions-history")
    
    if new_trades is not None and data_changed(cache.trades, new_trades):
        cache.trades = new_trades
        cache.last_update["trades"] = time.time()
        print(f"📜 [{account.name}] Trades changed - broadcasting")
        await broadcast_to_clients({
            "type": "trades_update",
            "account_id": account.id,
            "account_name": account.name,
            "trades": new_trades,
            "timestamp": time.time()
        })
        
        # Save trades to Supabase
        if supabase_client.is_initialized:
            account_idx = int(account.id.split('_')[1])
            trades_list = new_trades.get('data', new_trades) if isinstance(new_trades, dict) else new_trades
            if isinstance(trades_list, list):
                for trade in trades_list:
                    asyncio.create_task(supabase_client.save_trade(account_idx, trade, exchange="extended"))


async def poll_account_orders(account: AccountConfig):
    """Poll orders for a single account (2x per second)."""
    cache = BROADCASTER_CACHES[account.id]
    new_orders = await fetch_account_api(account, "/user/orders?status=ACTIVE")
    
    if new_orders is not None and data_changed(cache.orders, new_orders):
        cache.orders = new_orders
        cache.last_update["orders"] = time.time()
        print(f"📋 [{account.name}] Orders changed - broadcasting")
        await broadcast_to_clients({
            "type": "orders_update",
            "account_id": account.id,
            "account_name": account.name,
            "orders": new_orders,
            "timestamp": time.time()
        })
        
        # Save orders to Supabase
        if supabase_client.is_initialized:
            account_idx = int(account.id.split('_')[1])
            orders_list = new_orders.get('data', new_orders) if isinstance(new_orders, dict) else new_orders
            if isinstance(orders_list, list):
                asyncio.create_task(supabase_client.save_orders(account_idx, orders_list, exchange="extended"))


async def poll_all_accounts_fast():
    """Poll fast data (positions + balance) for all accounts in parallel."""
    await asyncio.gather(*[
        poll_account_fast_data(account) for account in ACCOUNTS
    ], return_exceptions=True)


# ============= ORDER BOOK WEBSOCKET CLIENT =============
async def orderbook_websocket_client():
    """
    Connect to Extended Exchange Order Book stream via WebSocket.
    Subscribes to orderbook channel for all configured markets.
    
    Supports optional proxy via ORDERBOOK_PROXY_URL environment variable.
    If proxy is configured, uses aiohttp with SOCKS/HTTP proxy support.
    """
    global ORDERBOOK_CACHE, ORDERBOOK_LAST_UPDATE, ORDERBOOK_WS_CONNECTED
    
    import random
    
    retry_count = 0
    base_delay = 5
    max_delay = 300
    
    proxy_info = f" via proxy" if ORDERBOOK_PROXY_URL else ""
    print(f"📖 [OrderBook] Will connect to {EXTENDED_STREAM_URL}{proxy_info}")
    
    while True:
        connection_was_successful = False
        
        try:
            print(f"📖 [OrderBook] Connecting (attempt {retry_count + 1})...")
            
            if ORDERBOOK_PROXY_URL:
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(ORDERBOOK_PROXY_URL)
                session = aiohttp.ClientSession(connector=connector)
            else:
                session = aiohttp.ClientSession()
            
            try:
                async with session.ws_connect(
                    EXTENDED_STREAM_URL,
                    heartbeat=30,
                    receive_timeout=60
                ) as ws:
                    ORDERBOOK_WS_CONNECTED = True
                    connection_was_successful = True
                    retry_count = 0
                    print(f"✅ [OrderBook] Connected! Subscribing to {len(ORDERBOOK_MARKETS)} markets...")
                    
                    subscribe_msg = {
                        "type": "subscribe",
                        "channel": "orderbook",
                        "markets": ORDERBOOK_MARKETS
                    }
                    await ws.send_str(json.dumps(subscribe_msg))
                    print(f"📨 [OrderBook] Subscribed to: {', '.join(ORDERBOOK_MARKETS)}")
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                
                                if data.get("type") == "orderbook" or data.get("channel") == "orderbook":
                                    market = data.get("market") or data.get("symbol")
                                    if market:
                                        bids = data.get("bids", [])[:ORDERBOOK_DEPTH]
                                        asks = data.get("asks", [])[:ORDERBOOK_DEPTH]
                                        
                                        ORDERBOOK_CACHE[market] = {
                                            "bids": bids,
                                            "asks": asks,
                                            "timestamp": data.get("timestamp") or time.time(),
                                            "sequence": data.get("sequence")
                                        }
                                        ORDERBOOK_LAST_UPDATE = time.time()
                                        
                                        await broadcast_to_clients({
                                            "type": "orderbook_update",
                                            "market": market,
                                            "bids": bids,
                                            "asks": asks,
                                            "timestamp": time.time()
                                        })
                                
                                elif data.get("type") == "subscribed":
                                    print(f"✅ [OrderBook] Subscription confirmed: {data.get('channel')}")
                                
                                elif data.get("type") == "error":
                                    print(f"⚠️ [OrderBook] Stream error: {data.get('message')}")
                                    
                            except json.JSONDecodeError as e:
                                print(f"⚠️ [OrderBook] Invalid JSON: {e}")
                        
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"⚠️ [OrderBook] WebSocket error: {ws.exception()}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print(f"⚠️ [OrderBook] WebSocket closed by server")
                            break
            finally:
                ORDERBOOK_WS_CONNECTED = False
                await session.close()
                        
        except Exception as e:
            print(f"❌ [OrderBook] WebSocket error: {e}")
        
        ORDERBOOK_WS_CONNECTED = False
        retry_count += 1
        delay = min(base_delay * (2 ** min(retry_count - 1, 6)), max_delay)
        jitter = random.uniform(0.5, 1.5)
        sleep_time = delay * jitter
        print(f"🔄 [OrderBook] Reconnecting in {sleep_time:.1f}s (attempt {retry_count})...")
        await asyncio.sleep(sleep_time)


async def poll_all_accounts_trades():
    """Poll trades for all accounts in parallel."""
    await asyncio.gather(*[
        poll_account_trades(account) for account in ACCOUNTS
    ], return_exceptions=True)


async def poll_all_accounts_orders():
    """Poll orders for all accounts in parallel."""
    await asyncio.gather(*[
        poll_account_orders(account) for account in ACCOUNTS
    ], return_exceptions=True)


MARGIN_CHECK_COUNTER = 0  # Check margins every 20 cycles (5 seconds)

async def background_poller():
    """
    Main background task that continuously polls Extended API for all accounts.
    
    With proxies per account, rate limiting is avoided.
    - Fast loop (250ms): positions + balance + orders (4x/sec per account)
    - Trades loop (1000ms): trades (1x/sec per account)
    - Margin check (5s): check margins and send alerts
    """
    global TRADES_POLL_COUNTER, MARGIN_CHECK_COUNTER
    
    # Count accounts with proxies
    proxied_accounts = sum(1 for a in ACCOUNTS if a.proxy_url)
    print(f"🚀 [Broadcaster] Background poller started for {len(ACCOUNTS)} accounts")
    print(f"🔒 Accounts with proxy: {proxied_accounts}/{len(ACCOUNTS)}")
    print(f"⚡ Polling rates: positions/balance/orders 4x/s, trades 1x/s, margin check 1x/5s")
    
    while True:
        try:
            # Fast polling: positions + balance + orders for all accounts (every 250ms = 4x/sec)
            await poll_all_accounts_fast()
            await poll_all_accounts_orders()
            
            # Trades polling: every 4 cycles (1 second)
            TRADES_POLL_COUNTER += 1
            if TRADES_POLL_COUNTER >= 4:
                await poll_all_accounts_trades()
                TRADES_POLL_COUNTER = 0
            
            # Margin check: every 20 cycles (5 seconds)
            MARGIN_CHECK_COUNTER += 1
            if MARGIN_CHECK_COUNTER >= 20:
                await check_margins_and_alert()
                MARGIN_CHECK_COUNTER = 0
            
            await asyncio.sleep(0.25)
            
        except Exception as e:
            print(f"❌ [Broadcaster] Poller error: {e}")
            await asyncio.sleep(0.5)


# ============= STARTUP EVENT =============
@app.on_event("startup")
async def startup_broadcaster():
    if IS_FRONTEND_ONLY:
        print(f"🌐 [Startup] FRONTEND_ONLY mode - proxying to {REMOTE_API_BASE}")
        print("✅ [Startup] Frontend-only broadcaster initialized (no polling)")
        return
    
    print(f"⚡ [Startup] Initializing multi-account broadcaster for {len(ACCOUNTS)} accounts...")
    
    # Initialize Supabase persistence
    if supabase_client.initialize():
        print("✅ [Startup] Supabase persistence enabled")
    else:
        print("⚠️ [Startup] Supabase persistence disabled (no credentials)")
    
    asyncio.create_task(background_poller())
    asyncio.create_task(orderbook_websocket_client())
    print("✅ [Startup] Broadcaster initialized with Order Book stream")


# ============= REST API ENDPOINTS =============
@app.get("/health")
async def health_check():
    if IS_FRONTEND_ONLY:
        return {
            "status": "ok",
            "service": "extended-multi-account-broadcaster",
            "mode": "FRONTEND_ONLY",
            "remote_api": REMOTE_API_BASE
        }
    
    return {
        "status": "ok",
        "service": "extended-multi-account-broadcaster",
        "mode": "COLLECTOR",
        "accounts_configured": len(ACCOUNTS),
        "broadcaster": {
            "connected_clients": len(BROADCAST_CLIENTS),
            "accounts": [
                {
                    "id": account.id,
                    "name": account.name,
                    "cache_initialized": all([
                        BROADCASTER_CACHES[account.id].positions is not None,
                        BROADCASTER_CACHES[account.id].balance is not None,
                    ])
                }
                for account in ACCOUNTS
            ]
        }
    }


@app.get("/api/cached-accounts")
async def get_cached_accounts():
    """
    Return cached data for ALL accounts.
    
    ✅ NO rate limits - served from memory
    ✅ Frontend can call 100x/s if needed
    ✅ Zero Extended API calls
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/cached-accounts")
    
    current_time = time.time()
    
    accounts_data = {}
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES[account.id]
        accounts_data[account.id] = {
            "id": account.id,
            "name": account.name,
            "positions": cache.positions,
            "balance": cache.balance,
            "trades": cache.trades,
            "orders": cache.orders,
            "cache_age_ms": {
                "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                "trades": int((current_time - cache.last_update["trades"]) * 1000) if cache.last_update["trades"] > 0 else None,
                "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
            },
            "last_update": cache.last_update.copy()
        }
    
    return {
        "accounts": accounts_data,
        "total_accounts": len(ACCOUNTS),
        "timestamp": current_time
    }


@app.get("/api/cached-account")
async def get_cached_account():
    """
    Return cached data for the first/primary account (backward compatibility).
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/cached-account")
    
    if not ACCOUNTS:
        raise HTTPException(status_code=404, detail="No accounts configured")
    
    account = ACCOUNTS[0]
    cache = BROADCASTER_CACHES[account.id]
    current_time = time.time()
    
    return {
        "account_id": account.id,
        "account_name": account.name,
        "positions": cache.positions,
        "balance": cache.balance,
        "trades": cache.trades,
        "orders": cache.orders,
        "cache_age_ms": {
            "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
            "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
            "trades": int((current_time - cache.last_update["trades"]) * 1000) if cache.last_update["trades"] > 0 else None,
            "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
        }
    }


@app.get("/api/cached-account/{account_id}")
async def get_cached_account_by_id(account_id: str):
    """Return cached data for a specific account by ID."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/cached-account/{account_id}")
    
    if account_id not in BROADCASTER_CACHES:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    
    account = next((a for a in ACCOUNTS if a.id == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    
    cache = BROADCASTER_CACHES[account_id]
    current_time = time.time()
    
    return {
        "account_id": account.id,
        "account_name": account.name,
        "positions": cache.positions,
        "balance": cache.balance,
        "trades": cache.trades,
        "orders": cache.orders,
        "cache_age_ms": {
            "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
            "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
            "trades": int((current_time - cache.last_update["trades"]) * 1000) if cache.last_update["trades"] > 0 else None,
            "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
        }
    }


@app.get("/api/broadcaster/stats")
async def broadcaster_stats():
    """Get broadcaster statistics and monitoring info."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/broadcaster/stats")
    
    current_time = time.time()
    
    accounts_stats = []
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES[account.id]
        accounts_stats.append({
            "id": account.id,
            "name": account.name,
            "positions_initialized": cache.positions is not None,
            "balance_initialized": cache.balance is not None,
            "trades_initialized": cache.trades is not None,
            "orders_initialized": cache.orders is not None,
            "positions_age_seconds": int(current_time - cache.last_update["positions"]) if cache.last_update["positions"] > 0 else None,
            "balance_age_seconds": int(current_time - cache.last_update["balance"]) if cache.last_update["balance"] > 0 else None,
        })
    
    return {
        "broadcaster": {
            "connected_clients": len(BROADCAST_CLIENTS),
            "accounts_configured": len(ACCOUNTS),
            "extended_api_rate": f"~{len(ACCOUNTS) * 6} req/s total ({len(ACCOUNTS)} accounts x 6 endpoints)",
        },
        "accounts": accounts_stats,
        "timestamp": current_time
    }


# ============= WEBSOCKET BROADCAST ENDPOINT =============
@app.websocket("/ws/broadcast")
async def websocket_broadcast(websocket: WebSocket):
    """WebSocket endpoint for broadcasting real-time updates for all accounts."""
    await websocket.accept()
    print(f"✅ [WS] New client connected (total: {len(BROADCAST_CLIENTS) + 1})")
    
    BROADCAST_CLIENTS.add(websocket)
    
    try:
        # Send immediate snapshot of all accounts
        accounts_snapshot = {}
        for account in ACCOUNTS:
            cache = BROADCASTER_CACHES[account.id]
            accounts_snapshot[account.id] = {
                "id": account.id,
                "name": account.name,
                "positions": cache.positions,
                "balance": cache.balance,
                "trades": cache.trades,
                "orders": cache.orders,
            }
        
        snapshot = {
            "type": "snapshot",
            "accounts": accounts_snapshot,
            "total_accounts": len(ACCOUNTS),
            "timestamp": time.time()
        }
        await websocket.send_json(snapshot)
        print(f"📸 [WS] Sent snapshot for {len(ACCOUNTS)} accounts to client")
        
        while True:
            try:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping", "timestamp": time.time()})
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"⚠️ [WS] Error in keep-alive: {e}")
                break
                
    except WebSocketDisconnect:
        print(f"👋 [WS] Client disconnected gracefully")
    except Exception as e:
        print(f"❌ [WS] Connection error: {e}")
    finally:
        BROADCAST_CLIENTS.discard(websocket)
        print(f"🗑️ [WS] Client removed (remaining: {len(BROADCAST_CLIENTS)})")


# ============= SUPABASE HISTORY ENDPOINTS =============
@app.get("/api/account/{account_id}/history")
async def get_account_history(account_id: int, limit: int = 100):
    """Get historical snapshots from Supabase."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/account/{account_id}/history?limit={limit}")
    
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    history = await supabase_client.get_account_history(account_id, limit, exchange="extended")
    return {"account_id": account_id, "history": history, "count": len(history)}


@app.get("/api/trades/recent")
async def get_recent_trades(account_id: Optional[int] = None, limit: int = 100):
    """Get recent trades from Supabase."""
    if IS_FRONTEND_ONLY:
        query = f"/api/trades/recent?limit={limit}"
        if account_id is not None:
            query += f"&account_id={account_id}"
        return await proxy_to_remote(query)
    
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    if account_id is not None:
        trades = await supabase_client.get_recent_trades(account_id, limit, exchange="extended")
    else:
        trades = await supabase_client.get_all_recent_trades(limit)
    
    return {"account_id": account_id, "trades": trades, "count": len(trades)}


# Legacy endpoints removed - use /api/cached-accounts instead


# ============= STATISTICS ENDPOINTS =============
@app.get("/api/stats/periods")
async def get_stats_periods(account_id: Optional[int] = None):
    """
    Get trading statistics for 24h, 7d, and 30d periods.
    Each period includes: total_pnl, total_volume, trades_count, wins, losses, win_rate
    """
    if IS_FRONTEND_ONLY:
        query = "/api/stats/periods"
        if account_id is not None:
            query += f"?account_id={account_id}"
        return await proxy_to_remote(query)
    
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    stats = await supabase_client.get_period_stats(account_index=account_id)
    return {
        "account_id": account_id,
        "stats": stats,
        "timestamp": time.time()
    }


@app.get("/api/stats/summary")
async def get_stats_summary():
    """
    Get summary statistics for all accounts.
    Includes: current equity (from cache), PnL for 24h/7d/30d, total volume.
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/stats/summary")
    
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    total_equity = 0.0
    accounts_equity = {}
    
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES[account.id]
        if cache.balance:
            balance_data = cache.balance.get('data', cache.balance) if isinstance(cache.balance, dict) else cache.balance
            if isinstance(balance_data, dict):
                equity = balance_data.get('equity') or balance_data.get('totalEquity') or 0
            elif isinstance(balance_data, list) and len(balance_data) > 0:
                equity = balance_data[0].get('equity') or balance_data[0].get('totalEquity') or 0
            else:
                equity = 0
            try:
                equity_val = float(equity)
                total_equity += equity_val
                accounts_equity[account.id] = equity_val
            except (ValueError, TypeError):
                accounts_equity[account.id] = 0
    
    stats = await supabase_client.get_period_stats()
    
    return {
        "total_equity": round(total_equity, 2),
        "accounts_equity": accounts_equity,
        "pnl_24h": stats.get("24h", {}).get("total_pnl", 0),
        "pnl_7d": stats.get("7d", {}).get("total_pnl", 0),
        "pnl_30d": stats.get("30d", {}).get("total_pnl", 0),
        "volume_24h": stats.get("24h", {}).get("total_volume", 0),
        "volume_7d": stats.get("7d", {}).get("total_volume", 0),
        "volume_30d": stats.get("30d", {}).get("total_volume", 0),
        "trades_24h": stats.get("24h", {}).get("trades_count", 0),
        "trades_7d": stats.get("7d", {}).get("trades_count", 0),
        "trades_30d": stats.get("30d", {}).get("trades_count", 0),
        "win_rate_24h": stats.get("24h", {}).get("win_rate", 0),
        "win_rate_7d": stats.get("7d", {}).get("win_rate", 0),
        "win_rate_30d": stats.get("30d", {}).get("win_rate", 0),
        "timestamp": time.time()
    }


@app.get("/api/trades")
async def get_trades_list(account_id: Optional[int] = None, limit: int = 100):
    """
    Get list of trades with PnL and volume.
    Returns: market, side, position_size, entry_price, exit_price, realized_pnl, volume, timestamp
    """
    if IS_FRONTEND_ONLY:
        query = f"/api/trades?limit={limit}"
        if account_id is not None:
            query += f"&account_id={account_id}"
        return await proxy_to_remote(query)
    
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    trades = await supabase_client.get_trades_list(limit=limit, account_index=account_id)
    return {
        "account_id": account_id,
        "trades": trades,
        "count": len(trades),
        "timestamp": time.time()
    }


# ============= ORDER BOOK ENDPOINTS =============
@app.get("/api/orderbook")
async def get_orderbook():
    """
    Get cached order book data for all markets.
    Real-time data from Extended Exchange WebSocket stream.
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/orderbook")
    
    return {
        "markets": ORDERBOOK_CACHE,
        "connected": ORDERBOOK_WS_CONNECTED,
        "last_update": ORDERBOOK_LAST_UPDATE,
        "cache_age_ms": int((time.time() - ORDERBOOK_LAST_UPDATE) * 1000) if ORDERBOOK_LAST_UPDATE > 0 else None,
        "subscribed_markets": ORDERBOOK_MARKETS,
        "timestamp": time.time()
    }


@app.get("/api/orderbook/{market}")
async def get_orderbook_market(market: str):
    """
    Get cached order book data for a specific market.
    Example: /api/orderbook/ETH-PERP
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/orderbook/{market}")
    
    market_upper = market.upper()
    
    if market_upper not in ORDERBOOK_CACHE:
        available = list(ORDERBOOK_CACHE.keys()) if ORDERBOOK_CACHE else ORDERBOOK_MARKETS
        raise HTTPException(
            status_code=404, 
            detail=f"Market {market_upper} not found. Available: {', '.join(available)}"
        )
    
    book = ORDERBOOK_CACHE[market_upper]
    return {
        "market": market_upper,
        "bids": book.get("bids", []),
        "asks": book.get("asks", []),
        "sequence": book.get("sequence"),
        "last_update": book.get("timestamp"),
        "connected": ORDERBOOK_WS_CONNECTED,
        "timestamp": time.time()
    }


@app.get("/api/orderbook-status")
async def get_orderbook_status():
    """Get order book WebSocket connection status."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/orderbook-status")
    
    return {
        "connected": ORDERBOOK_WS_CONNECTED,
        "stream_url": EXTENDED_STREAM_URL,
        "subscribed_markets": ORDERBOOK_MARKETS,
        "cached_markets": list(ORDERBOOK_CACHE.keys()),
        "last_update": ORDERBOOK_LAST_UPDATE,
        "cache_age_ms": int((time.time() - ORDERBOOK_LAST_UPDATE) * 1000) if ORDERBOOK_LAST_UPDATE > 0 else None,
        "timestamp": time.time()
    }


# ============= MARGIN ALERTS ENDPOINTS =============
@app.get("/api/alerts/status")
async def get_alerts_status():
    """Get margin alert system status and configuration."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/alerts/status")
    
    return {
        "enabled": True,
        "thresholds": MARGIN_THRESHOLDS,
        "channels": {
            "telegram": bool(alert_manager.config.telegram_bot_token and alert_manager.config.telegram_chat_id),
            "pushover": bool(alert_manager.config.pushover_app_token and alert_manager.config.pushover_user_key),
            "sms": bool(alert_manager.config.twilio_sid and alert_manager.config.twilio_auth_token),
            "phone": bool(alert_manager.config.phone_number)
        },
        "cooldown_minutes": alert_manager.state.cooldown_minutes,
        "active_alerts": len(alert_manager.state.sent_alerts),
        "timestamp": time.time()
    }


@app.post("/api/alerts/test")
async def test_alerts():
    """Test all notification channels."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/alerts/test", method="POST")
    
    results = await alert_manager.test_all_channels()
    return {
        "success": any([results["telegram"], results["pushover"], results["sms"], results["phone_call"]]),
        "results": results,
        "timestamp": time.time()
    }


@app.get("/api/alerts/margins")
async def get_current_margins():
    """Get current margin ratios for all accounts."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/alerts/margins")
    
    margins = []
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES.get(account.id)
        if cache and cache.balance:
            balance_data = cache.balance.get("data", {}) if isinstance(cache.balance, dict) else {}
            margin_ratio = float(balance_data.get("marginRatio", 0))
            equity = float(balance_data.get("equity", 0))
            margins.append({
                "account_id": account.id,
                "account_name": account.name,
                "margin_ratio": margin_ratio,
                "margin_percent": round(margin_ratio * 100, 2),
                "equity": round(equity, 2),
                "threshold_triggered": alert_manager.get_threshold_level(margin_ratio)
            })
    
    return {
        "accounts": margins,
        "thresholds": MARGIN_THRESHOLDS,
        "timestamp": time.time()
    }


async def check_margins_and_alert():
    """Check all account margins and send alerts if needed."""
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES.get(account.id)
        if cache and cache.balance:
            balance_data = cache.balance.get("data", {}) if isinstance(cache.balance, dict) else {}
            margin_ratio = float(balance_data.get("marginRatio", 0))
            equity = float(balance_data.get("equity", 0))
            
            if margin_ratio > 0:
                try:
                    result = await alert_manager.check_and_alert(
                        account.id, 
                        account.name, 
                        margin_ratio, 
                        equity
                    )
                    if result.get("alerts_sent"):
                        print(f"🚨 Alert sent for {account.name}: {result['alerts_sent']}")
                except Exception as e:
                    print(f"❌ Error checking margin for {account.name}: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
