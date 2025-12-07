"""
Lighter Dual Account Volume Bot
Atomic LONG+SHORT positions for volume generation
With proxy support to bypass geo-restrictions
"""
import os
import asyncio
import random
import logging
import threading
import time
from typing import Optional
import lighter
from lighter.configuration import Configuration
import nest_asyncio

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LIGHTER_URL = "https://mainnet.zklighter.elliot.ai"
SYMBOL = "BTCUSDC"
TRADE_NOTIONAL_USD = 100  # Trade size in USD (notional value)

def get_proxy_config() -> Optional[str]:
    """Get default proxy URL from environment"""
    proxy = os.environ.get("PROXY_URL") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        logger.info(f"Using proxy: {proxy[:30]}...")
    return proxy

def get_proxy_for_account(account_index: int) -> Optional[str]:
    """Get proxy URL for specific account"""
    if account_index == 382129:
        proxy = os.environ.get("PROXY_ACCOUNT3")
    elif account_index == 497888:
        proxy = os.environ.get("PROXY_ACCOUNT5")
    else:
        proxy = get_proxy_config()
    
    if proxy:
        logger.debug(f"[ACC {account_index}] Using proxy: {proxy[:35]}...")
    return proxy

def create_lighter_config(url: str) -> Configuration:
    """Create Lighter Configuration with proxy if available"""
    config = Configuration(host=url)
    proxy = get_proxy_config()
    if proxy:
        config.proxy = proxy
        logger.info("Proxy configured for Lighter SDK")
    return config



class LighterDualBot:
    """Volume generation bot using two Lighter accounts"""
    
    def __init__(self):
        self.running = False
        self.cycle = 0
        self.mode = "LIVE"
        self.trade_notional_usd = TRADE_NOTIONAL_USD
        self.account1_direction = "LONG"
        self.account2_direction = "SHORT"
        self.client1: Optional[lighter.SignerClient] = None
        self.client2: Optional[lighter.SignerClient] = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.recovery_required = False
        self.start_time = None
        self.total_volume = 0.0
        self.successful_cycles = 0
        self.failed_cycles = 0
        self.next_action_time = 0
        self.current_phase = "IDLE"
        self.current_hold_time = 0
        self.current_btc_price = 95000.0
        self.volume_history = []
        self.account1_index = 382129
        self.account2_index = 497888
    
    def record_trade(self, account_index: int, usd_volume: float, btc_size: float, side: str):
        """Record a trade for volume tracking"""
        trade = {
            "timestamp": time.time(),
            "account_index": account_index,
            "usd_volume": usd_volume,
            "btc_size": btc_size,
            "side": side
        }
        self.volume_history.append(trade)
        self.total_volume += btc_size
        logger.info(f"📊 Recorded trade: ${usd_volume:.2f} ({btc_size:.6f} BTC) for account {account_index}")
    
    def get_volume_stats(self, account_index: int = None) -> dict:
        """Get volume statistics from internal tracking"""
        now = time.time()
        day_ago = now - 86400
        week_ago = now - 604800
        
        daily_volume = 0.0
        weekly_volume = 0.0
        total_volume = 0.0
        daily_trades = 0
        weekly_trades = 0
        total_trades = 0
        
        for trade in self.volume_history:
            if account_index and trade["account_index"] != account_index:
                continue
            
            usd = trade["usd_volume"]
            ts = trade["timestamp"]
            
            total_volume += usd
            total_trades += 1
            
            if ts >= week_ago:
                weekly_volume += usd
                weekly_trades += 1
            
            if ts >= day_ago:
                daily_volume += usd
                daily_trades += 1
        
        return {
            "daily_volume": daily_volume,
            "weekly_volume": weekly_volume,
            "total_volume": total_volume,
            "daily_trades": daily_trades,
            "weekly_trades": weekly_trades,
            "total_trades": total_trades
        }
        
    async def _load_credentials(self) -> bool:
        """Load credentials from environment (async version)"""
        try:
            api1 = os.environ.get("Lighter_3_API_Key_Index")
            priv1 = os.environ.get("Lighter_3_Priv_key")
            acc1_idx = os.environ.get("Lighter_3_account_index")
            
            api2 = os.environ.get("Lighter_5_API_Key_Index")
            priv2 = os.environ.get("Lighter_5_Priv_key")
            acc2_idx = os.environ.get("Lighter_5_account_index")
            
            if not all([api1, priv1, acc1_idx, api2, priv2, acc2_idx]):
                logger.error(f"❌ Missing credentials!")
                logger.error(f"   Account 3: api={bool(api1)}, priv={bool(priv1)}, acc_idx={bool(acc1_idx)}")
                logger.error(f"   Account 5: api={bool(api2)}, priv={bool(priv2)}, acc_idx={bool(acc2_idx)}")
                return False
            
            self.account1_index = int(acc1_idx)
            self.account2_index = int(acc2_idx)
            
            proxy1 = get_proxy_for_account(self.account1_index)
            proxy2 = get_proxy_for_account(self.account2_index)
            
            self.client1 = lighter.SignerClient(
                url=LIGHTER_URL,
                account_index=self.account1_index,
                api_private_keys={int(api1): priv1}
            )
            
            self.client2 = lighter.SignerClient(
                url=LIGHTER_URL,
                account_index=self.account2_index,
                api_private_keys={int(api2): priv2}
            )
            
            if proxy1:
                self.client1.api_client.configuration.proxy = proxy1
                self.client1.api_client.rest_client.proxy = proxy1
                logger.info(f"✅ Client1 proxy: {proxy1[:45]}...")
            
            if proxy2:
                self.client2.api_client.configuration.proxy = proxy2
                self.client2.api_client.rest_client.proxy = proxy2
                logger.info(f"✅ Client2 proxy: {proxy2[:45]}...")
            
            if not proxy1 or not proxy2:
                logger.warning("⚠️  Missing proxy for one or both accounts!")
            
            logger.info("Both Lighter clients initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")
            return False
    
    async def _fetch_btc_price(self) -> float:
        """Fetch current BTC price from Lighter API"""
        try:
            config = create_lighter_config(LIGHTER_URL)
            api_client = lighter.ApiClient(configuration=config)
            market_api = lighter.MarketApi(api_client)
            
            result = await asyncio.wait_for(
                market_api.market(market_index=1),
                timeout=5.0
            )
            
            if result and hasattr(result, 'markets') and result.markets:
                market = result.markets[0]
                price_str = getattr(market, 'mark_price', None) or getattr(market, 'last_price', None)
                if price_str:
                    price = float(price_str)
                    self.current_btc_price = price
                    logger.info(f"BTC price fetched: ${price:,.2f}")
                    return price
            
            await api_client.close()
        except Exception as e:
            logger.warning(f"Failed to fetch BTC price: {e}, using cached: ${self.current_btc_price:,.2f}")
        
        return self.current_btc_price
    
    async def _get_current_position(self, account_index: int) -> tuple:
        """Get current BTC position size and sign for an account using HTTP API. Returns (size_btc, sign)"""
        import requests
        try:
            proxy = get_proxy_for_account(account_index)
            proxies = {"http": proxy, "https": proxy} if proxy else None
            
            url = f"{LIGHTER_URL}/api/v1/account"
            params = {"by": "index", "value": str(account_index)}
            
            resp = requests.get(url, params=params, proxies=proxies, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get("accounts") and len(data["accounts"]) > 0:
                    acc = data["accounts"][0]
                    positions = acc.get("positions", [])
                    for pos in positions:
                        market_id = int(pos.get("market_id", 0) or 0)
                        if market_id == 1:
                            pos_raw = float(pos.get("position", "0") or "0")
                            pos_size = pos_raw / 1_000_000 if abs(pos_raw) > 100 else pos_raw
                            pos_sign = int(pos.get("sign", 0) or 0)
                            logger.debug(f"[ACC {account_index}] HTTP position: raw={pos_raw}, btc={pos_size:.6f}, sign={pos_sign}")
                            return (abs(pos_size), pos_sign)
                    return (0.0, 0)
                else:
                    logger.debug(f"[ACC {account_index}] No accounts in response")
            else:
                logger.warning(f"[ACC {account_index}] HTTP error: {resp.status_code}")
        except Exception as e:
            logger.debug(f"Get position error for {account_index}: {e}")
        
        return (0.0, 0)
    
    async def _verify_position_change(self, account_index: int, before_size: float, before_sign: int, 
                                       expected_change_btc: float, is_buy: bool, max_wait: int = 10) -> bool:
        """Verify position actually changed after order. Compare before/after state."""
        t0 = time.time()
        
        while time.time() - t0 < max_wait:
            try:
                current_size, current_sign = await self._get_current_position(account_index)
                size_delta = abs(current_size - before_size)
                
                if size_delta >= expected_change_btc * 0.5:
                    logger.info(f"[ACC {account_index}] ✓ Position VERIFIED: before={before_size:.6f}, after={current_size:.6f}, delta={size_delta:.6f}")
                    return True
                
                logger.debug(f"[ACC {account_index}] Waiting for position change: before={before_size:.6f}, current={current_size:.6f}")
                
            except Exception as e:
                logger.debug(f"Position verify poll error: {e}")
            
            await asyncio.sleep(0.5)
        
        logger.warning(f"[ACC {account_index}] Position NOT changed after {max_wait}s (expected delta: {expected_change_btc:.6f})")
        return False
    
    async def _place_market_order_with_notional(self, client: lighter.SignerClient, side: str, 
                                                  notional_usd: float, reduce_only: bool = False, retries: int = 3) -> bool:
        """Place market order using USD notional value with REAL verification"""
        account_index = self.account1_index if client == self.client1 else self.account2_index
        
        btc_price = await self._fetch_btc_price()
        btc_size = notional_usd / btc_price
        
        before_size, before_sign = await self._get_current_position(account_index)
        logger.info(f"[ACC {account_index}] Position BEFORE order: {before_size:.6f} BTC, sign={before_sign}")
        
        for attempt in range(retries):
            try:
                is_ask = (side.lower() == "sell")
                base_amount = int(btc_size * 1_000_000)
                
                if is_ask:
                    avg_execution_price = int(1 * 100)
                else:
                    avg_execution_price = int(500_000 * 100)
                
                client_order_index = int(time.time() * 1000) % (2**32)
                
                logger.info(f"[ACC {account_index}] Placing {side.upper()} order: ${notional_usd} = {btc_size:.6f} BTC @ ${btc_price:,.2f} (limit: ${avg_execution_price/100:,.0f})")
                
                try:
                    result = await asyncio.wait_for(
                        client.create_market_order(
                            market_index=1,
                            client_order_index=client_order_index,
                            base_amount=base_amount,
                            avg_execution_price=avg_execution_price,
                            is_ask=is_ask,
                            reduce_only=reduce_only
                        ),
                        timeout=15.0
                    )
                    logger.info(f"[ACC {account_index}] SDK Response: {result}")
                except asyncio.TimeoutError:
                    logger.warning(f"[ACC {account_index}] Order timeout, retrying...")
                    if attempt < retries - 1:
                        await asyncio.sleep(1)
                        continue
                    raise Exception("Order timeout after retries")
                
                await asyncio.sleep(2)
                
                is_buy = not is_ask
                position_verified = await self._verify_position_change(
                    account_index, before_size, before_sign, btc_size, is_buy, max_wait=10
                )
                
                if position_verified:
                    logger.info(f"[ACC {account_index}] ✓ Position change VERIFIED on exchange")
                    return True
                else:
                    logger.warning(f"[ACC {account_index}] Order sent but position NOT verified - retrying...")
                    if attempt < retries - 1:
                        await asyncio.sleep(1)
                        continue
                    logger.error(f"[ACC {account_index}] Position verification FAILED after {retries} attempts")
                    return False
            
            except Exception as e:
                if attempt < retries - 1:
                    logger.debug(f"Order attempt {attempt+1} failed: {e}")
                    await asyncio.sleep(0.5)
                else:
                    logger.error(f"Order FAILED: {side} ${notional_usd} on account {account_index} -> {e}")
                    return False
        return False
    
    async def _open_positions(self) -> bool:
        """Open atomic LONG+SHORT positions with both as TAKER (MARKET orders)"""
        notional = self.trade_notional_usd
        
        pos1, _ = await self._get_current_position(self.account1_index)
        pos2, _ = await self._get_current_position(self.account2_index)
        
        if abs(pos1) > 0.00001 or abs(pos2) > 0.00001:
            logger.error(f"❌ Cannot open - existing positions! Acc1={pos1:.6f}, Acc2={pos2:.6f}")
            return False
        
        logger.info(f"[CYCLE {self.cycle}] Opening positions: ${notional} each | Account1={self.account1_direction}, Account2={self.account2_direction}")
        
        side1 = "buy" if self.account1_direction == "LONG" else "sell"
        side2 = "buy" if self.account2_direction == "LONG" else "sell"
        
        try:
            order1_result, order2_result = await asyncio.gather(
                self._place_market_order_with_notional(self.client1, side1, notional, reduce_only=False),
                self._place_market_order_with_notional(self.client2, side2, notional, reduce_only=False),
                return_exceptions=False
            )
            order1_success = order1_result is True
            order2_success = order2_result is True
        except Exception as e:
            logger.debug(f"Gather exception during open: {e}")
            order1_success = False
            order2_success = False
        
        if order1_success and order2_success:
            btc_size = notional / self.current_btc_price
            self.record_trade(self.account1_index, notional, btc_size, side1)
            self.record_trade(self.account2_index, notional, btc_size, side2)
            logger.info(f"✅ Both positions opened - ATOMIC | Total Volume: {self.total_volume:.4f} BTC (${2*notional})")
            return True
        
        if order1_success and not order2_success:
            logger.error("Account1 filled but Account2 failed - ROLLING BACK Account1")
            pos1_size, pos1_sign = await self._get_current_position(self.account1_index)
            if abs(pos1_size) > 0.00001:
                rollback_side = "sell" if pos1_sign > 0 else "buy"
                rollback_notional = pos1_size * self.current_btc_price
                rollback_success = False
                for attempt in range(3):
                    if await self._place_market_order_with_notional(self.client1, rollback_side, rollback_notional, reduce_only=False):
                        logger.info("Rollback Account1 successful")
                        rollback_success = True
                        break
                    logger.error(f"Rollback attempt {attempt+1} failed - retrying...")
                    await asyncio.sleep(1)
                if not rollback_success:
                    logger.error("CRITICAL: Rollback Account1 FAILED - EMERGENCY STOP!")
                    self.recovery_required = True
                    return "EMERGENCY_STOP"
            return False
        
        if not order1_success and order2_success:
            logger.error("Account2 filled but Account1 failed - ROLLING BACK Account2")
            pos2_size, pos2_sign = await self._get_current_position(self.account2_index)
            if abs(pos2_size) > 0.00001:
                rollback_side = "sell" if pos2_sign > 0 else "buy"
                rollback_notional = pos2_size * self.current_btc_price
                rollback_success = False
                for attempt in range(3):
                    if await self._place_market_order_with_notional(self.client2, rollback_side, rollback_notional, reduce_only=False):
                        logger.info("Rollback Account2 successful")
                        rollback_success = True
                        break
                    logger.error(f"Rollback attempt {attempt+1} failed - retrying...")
                    await asyncio.sleep(1)
                if not rollback_success:
                    logger.error("CRITICAL: Rollback Account2 FAILED - EMERGENCY STOP!")
                    self.recovery_required = True
                    return "EMERGENCY_STOP"
            return False
        
        logger.error("Both orders failed - no rollback needed")
        return False
    
    async def _close_positions(self) -> bool:
        """Close both positions to ZERO - verify before returning success"""
        logger.info(f"[CYCLE {self.cycle}] Closing all positions to ZERO")
        
        closed_volumes = {}
        
        async def close_account_to_zero(client, account_index, name):
            """Close single account position to zero with verification"""
            initial_size = 0.0
            for attempt in range(5):
                pos_size, pos_sign = await self._get_current_position(account_index)
                
                if attempt == 0:
                    initial_size = pos_size
                
                if abs(pos_size) < 0.00001:
                    logger.info(f"[{name}] ✓ Position is ZERO")
                    if initial_size > 0.00001:
                        closed_volumes[account_index] = initial_size
                    return True
                
                close_side = "sell" if pos_sign > 0 else "buy"
                is_ask = (close_side == "sell")
                base_amount = int(pos_size * 1_000_000)
                
                if is_ask:
                    avg_exec_price = int(1 * 100)
                else:
                    avg_exec_price = int(500_000 * 100)
                
                logger.info(f"[{name}] Closing {pos_size:.6f} BTC via {close_side} (attempt {attempt+1}) [reduce_only=True]")
                
                try:
                    client_order_index = int(time.time() * 1000) % (2**32)
                    result = await asyncio.wait_for(
                        client.create_market_order(
                            market_index=1,
                            client_order_index=client_order_index,
                            base_amount=base_amount,
                            avg_execution_price=avg_exec_price,
                            is_ask=is_ask,
                            reduce_only=True
                        ),
                        timeout=15.0
                    )
                    logger.info(f"[{name}] Close order sent: {result[1] if result else 'None'}")
                except Exception as e:
                    logger.error(f"[{name}] Close order failed: {e}")
                
                await asyncio.sleep(2)
                
                new_size, _ = await self._get_current_position(account_index)
                if abs(new_size) < 0.00001:
                    logger.info(f"[{name}] ✓ Position closed to ZERO")
                    return True
                else:
                    logger.warning(f"[{name}] Position still {new_size:.6f} - retrying...")
            
            logger.error(f"[{name}] ❌ Failed to close position after 5 attempts")
            return False
        
        acc1_closed = await close_account_to_zero(self.client1, self.account1_index, "Account1")
        acc2_closed = await close_account_to_zero(self.client2, self.account2_index, "Account2")
        
        if acc1_closed and acc2_closed:
            for acc_idx, btc_size in closed_volumes.items():
                usd_volume = btc_size * self.current_btc_price
                self.record_trade(acc_idx, usd_volume, btc_size, "close")
            logger.info("✅ Both positions closed to ZERO")
            return True
        
        logger.error(f"❌ Close incomplete: Acc1={acc1_closed}, Acc2={acc2_closed}")
        self.recovery_required = True
        return False
    
    def _switch_directions(self):
        """Switch trading directions for next cycle"""
        self.account1_direction, self.account2_direction = self.account2_direction, self.account1_direction
        logger.info(f"Switched directions: Account1={self.account1_direction}, Account2={self.account2_direction}")
    
    async def _close_existing_positions(self) -> bool:
        """Close any existing positions on both accounts to ZERO before starting.
        Returns True only if BOTH accounts are at zero."""
        logger.info("Checking for existing positions to close...")
        
        all_closed = True
        
        for client, account_index, name in [
            (self.client1, self.account1_index, "Account1"),
            (self.client2, self.account2_index, "Account2")
        ]:
            for attempt in range(5):
                try:
                    pos_size, pos_sign = await self._get_current_position(account_index)
                    
                    if abs(pos_size) < 0.00001:
                        logger.info(f"[{name}] ✓ Position is ZERO")
                        break
                    
                    direction = "LONG" if pos_sign > 0 else "SHORT"
                    close_side = "sell" if pos_sign > 0 else "buy"
                    is_ask = (close_side == "sell")
                    notional_value = pos_size * self.current_btc_price
                    
                    logger.warning(f"[{name}] Closing {direction} position: {pos_size:.6f} BTC (${notional_value:.2f}) - attempt {attempt+1} [reduce_only=True]")
                    
                    base_amount = int(pos_size * 1_000_000)
                    client_order_index = int(time.time() * 1000) % (2**32)
                    
                    if is_ask:
                        avg_exec_price = int(1 * 100)
                    else:
                        avg_exec_price = int(500_000 * 100)
                    
                    result = await asyncio.wait_for(
                        client.create_market_order(
                            market_index=1,
                            client_order_index=client_order_index,
                            base_amount=base_amount,
                            avg_execution_price=avg_exec_price,
                            is_ask=is_ask,
                            reduce_only=True
                        ),
                        timeout=15.0
                    )
                    logger.info(f"[{name}] Close order sent: {result[1] if result else 'None'}")
                    
                    await asyncio.sleep(3)
                    
                    new_size, _ = await self._get_current_position(account_index)
                    if abs(new_size) < 0.00001:
                        logger.info(f"[{name}] ✓ Position closed to ZERO")
                        break
                    else:
                        logger.warning(f"[{name}] Position still {new_size:.6f} - retrying...")
                        pos_size = new_size
                        
                except Exception as e:
                    logger.error(f"[{name}] Close attempt {attempt+1} failed: {e}")
                    await asyncio.sleep(2)
            else:
                final_size, _ = await self._get_current_position(account_index)
                if abs(final_size) >= 0.00001:
                    logger.error(f"[{name}] ❌ FAILED to close position after 5 attempts! Remaining: {final_size:.6f}")
                    all_closed = False
        
        await asyncio.sleep(2)
        
        if all_closed:
            logger.info("✅ All existing positions closed to ZERO")
        else:
            logger.error("❌ CRITICAL: Could not close all positions - bot will NOT start")
        
        return all_closed
    
    async def _run_loop(self):
        """Main bot loop"""
        self.start_time = time.time()
        logger.info("Bot loop started - loading credentials...")
        
        if not await self._load_credentials():
            logger.error("Failed to load credentials")
            self.running = False
            return
        
        logger.info("Credentials loaded, closing any existing positions...")
        if not await self._close_existing_positions():
            logger.error("❌ CRITICAL: Cannot close existing positions - bot will NOT start!")
            self.running = False
            return
        
        logger.info("Starting trading loop...")
        
        while self.running:
            try:
                self.cycle += 1
                logger.info(f"{'='*60}")
                logger.info(f"CYCLE {self.cycle} START | Volume: {self.total_volume:.2f} BTC | Successful: {self.successful_cycles}")
                logger.info(f"{'='*60}")
                
                entry_delay = random.uniform(3, 8)
                self.current_phase = "WAITING_ENTRY"
                self.next_action_time = time.time() + entry_delay
                logger.info(f"Waiting {entry_delay:.1f}s before entry...")
                await asyncio.sleep(entry_delay)
                
                if not self.running:
                    break
                
                self.current_phase = "OPENING"
                open_result = await self._open_positions()
                if open_result == "EMERGENCY_STOP":
                    logger.error(f"🚨 EMERGENCY STOP - rollback failed, manual intervention required ===")
                    self.failed_cycles += 1
                    self.running = False
                    break
                if not open_result:
                    logger.error(f"❌ CYCLE {self.cycle} ABORTED - open failed")
                    self.failed_cycles += 1
                    self.current_phase = "COOLDOWN"
                    self.next_action_time = time.time() + 30
                    await asyncio.sleep(30)
                    continue
                
                hold_time = random.uniform(30, 180)
                self.current_hold_time = hold_time
                self.current_phase = "HOLDING"
                self.next_action_time = time.time() + hold_time
                logger.info(f"⏱️  Holding positions for {hold_time:.1f}s ({hold_time/60:.1f} min)...")
                await asyncio.sleep(hold_time)
                
                if not self.running:
                    break
                
                self.current_phase = "CLOSING"
                if not await self._close_positions():
                    logger.error("🚨 CRITICAL: Close positions failed - STOPPING BOT for manual intervention!")
                    self.failed_cycles += 1
                    self.running = False
                    break
                
                self._switch_directions()
                self.successful_cycles += 1
                self.current_phase = "CYCLE_COMPLETE"
                
                uptime = int(time.time() - self.start_time)
                cycles_per_min = (self.successful_cycles / uptime * 60) if uptime > 0 else 0
                logger.info(f"✅ CYCLE {self.cycle} COMPLETE | Uptime: {uptime}s | Rate: {cycles_per_min:.2f} cycles/min")
                
            except asyncio.CancelledError:
                logger.info("Bot loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in bot loop: {e}")
                await asyncio.sleep(10)
        
        logger.info("Bot loop stopped")
    
    def _run_in_thread(self):
        """Run async loop in separate thread"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self._run_loop())
        except Exception as e:
            logger.error(f"Thread error: {e}")
        finally:
            self._loop.close()
    
    def start(self, loop=None) -> bool:
        """Start the bot"""
        if self.running:
            logger.warning("Bot already running")
            return False
        
        self.running = True
        self.cycle = 0
        self.successful_cycles = 0
        self.failed_cycles = 0
        self.total_volume = 0.0
        self.start_time = time.time()
        
        self._thread = threading.Thread(target=self._run_in_thread, daemon=True)
        self._thread.start()
        
        logger.info(f"🚀 Bot started successfully")
        return True
    
    def stop(self) -> bool:
        """Stop the bot"""
        if not self.running:
            logger.warning("Bot not running")
            return False
        
        self.running = False
        logger.info("Bot stopped")
        return True
    
    def get_status(self) -> dict:
        """Get bot status"""
        uptime = int(time.time() - self.start_time) if self.start_time else 0
        cycles_per_min = (self.successful_cycles / uptime * 60) if uptime > 0 else 0
        time_to_next = max(0, self.next_action_time - time.time()) if self.next_action_time > 0 else 0
        btc_size = self.trade_notional_usd / self.current_btc_price
        return {
            "running": self.running,
            "mode": self.mode,
            "cycle": self.cycle,
            "trade_notional_usd": self.trade_notional_usd,
            "trade_size_btc": round(btc_size, 6),
            "btc_price": round(self.current_btc_price, 2),
            "account1_direction": self.account1_direction,
            "account2_direction": self.account2_direction,
            "recovery_required": self.recovery_required,
            "uptime_seconds": uptime,
            "total_volume_btc": round(self.total_volume, 6),
            "successful_cycles": self.successful_cycles,
            "failed_cycles": self.failed_cycles,
            "cycles_per_minute": round(cycles_per_min, 2),
            "current_phase": self.current_phase,
            "time_to_next_action": round(time_to_next, 1),
            "current_hold_time": round(self.current_hold_time, 1)
        }


bot_instance = LighterDualBot()
