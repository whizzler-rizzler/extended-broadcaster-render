"""
Margin Alert System for Extended Exchange Broadcaster
Sends alerts via Telegram, Pushover, Twilio SMS, and Phone Calls
based on margin ratio thresholds.

Thresholds:
- 70%: Push notification (Telegram + Pushover)
- 80%: Push + SMS
- 90%: Push + SMS + Phone call
- 95%: Push + SMS + Phone call (critical)
"""

import os
import asyncio
import aiohttp
from typing import Dict, Set, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Thresholds configuration
MARGIN_THRESHOLDS = [0.70, 0.80, 0.90, 0.95]

@dataclass
class AlertConfig:
    """Configuration for alert channels"""
    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    # Pushover
    pushover_app_token: str = ""
    pushover_user_key: str = ""
    
    # Twilio
    twilio_sid: str = ""
    twilio_auth_token: str = ""
    phone_number: str = ""
    twilio_from_number: str = ""
    
    def __post_init__(self):
        self.telegram_bot_token = os.environ.get("Telegram_bot_token", "")
        self.telegram_chat_id = os.environ.get("Telegram_id", "")
        self.pushover_app_token = os.environ.get("Pushover_API_token", "") or os.environ.get("Pushover_app_token", "")
        self.pushover_user_key = os.environ.get("Pushover_user_key", "")
        # Twilio: Account SID for API URL, API Key SID + Secret for auth
        self.twilio_account_sid = os.environ.get("Twilio_account_sid", "")
        self.twilio_api_key_sid = os.environ.get("Twilio_sid", "")  # API Key SID (SK...)
        self.twilio_api_key_secret = os.environ.get("Twillio_secret_api", "")  # API Key Secret
        self.phone_number = os.environ.get("Alert_phone_number", "")
        self.twilio_from_number = os.environ.get("Twilio_from_number", "+12184232606")

@dataclass
class AlertState:
    """Tracks which alerts have been sent to prevent spam"""
    # Key: (account_id, threshold) -> last alert time
    sent_alerts: Dict[tuple, datetime] = field(default_factory=dict)
    # Cooldown period between same alerts (30 minutes)
    cooldown_minutes: int = 30
    
    def can_send_alert(self, account_id: str, threshold: float) -> bool:
        key = (account_id, threshold)
        if key not in self.sent_alerts:
            return True
        elapsed = datetime.now() - self.sent_alerts[key]
        return elapsed > timedelta(minutes=self.cooldown_minutes)
    
    def mark_alert_sent(self, account_id: str, threshold: float):
        self.sent_alerts[(account_id, threshold)] = datetime.now()
    
    def reset_for_account(self, account_id: str, threshold: float):
        """Reset alerts when margin drops below threshold"""
        key = (account_id, threshold)
        if key in self.sent_alerts:
            del self.sent_alerts[key]


class MarginAlertManager:
    def __init__(self):
        self.config = AlertConfig()
        self.state = AlertState()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    # ==================== TELEGRAM ====================
    async def send_telegram(self, message: str, is_critical: bool = False) -> bool:
        """Send message via Telegram Bot"""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            logger.warning("Telegram not configured")
            return False
        
        try:
            session = await self.get_session()
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            
            # Add critical prefix for critical alerts
            if is_critical:
                message = f"🚨🚨🚨 CRITICAL 🚨🚨🚨\n\n{message}"
            
            payload = {
                "chat_id": self.config.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            async with session.post(url, json=payload) as resp:
                result = await resp.json()
                if result.get("ok"):
                    logger.info(f"✅ Telegram alert sent")
                    return True
                else:
                    logger.error(f"❌ Telegram error: {result}")
                    return False
        except Exception as e:
            logger.error(f"❌ Telegram exception: {e}")
            return False
    
    # ==================== PUSHOVER ====================
    async def send_pushover(self, title: str, message: str, priority: int = 1) -> bool:
        """
        Send push notification via Pushover
        Priority: -2 (silent) to 2 (emergency)
        """
        if not self.config.pushover_app_token or not self.config.pushover_user_key:
            logger.warning("Pushover not configured")
            return False
        
        try:
            session = await self.get_session()
            url = "https://api.pushover.net/1/messages.json"
            
            payload = {
                "token": self.config.pushover_app_token,
                "user": self.config.pushover_user_key,
                "title": title,
                "message": message,
                "priority": priority,
                "sound": "siren" if priority >= 1 else "pushover"
            }
            
            # Emergency priority requires retry and expire parameters
            if priority == 2:
                payload["retry"] = 60  # Retry every 60 seconds
                payload["expire"] = 3600  # Expire after 1 hour
            
            async with session.post(url, data=payload) as resp:
                result = await resp.json()
                if result.get("status") == 1:
                    logger.info(f"✅ Pushover alert sent (priority={priority})")
                    return True
                else:
                    logger.error(f"❌ Pushover error: {result}")
                    return False
        except Exception as e:
            logger.error(f"❌ Pushover exception: {e}")
            return False
    
    # ==================== TWILIO SMS ====================
    async def send_sms(self, message: str) -> bool:
        """Send SMS via Twilio using API Key authentication"""
        if not all([self.config.twilio_account_sid, self.config.twilio_api_key_sid,
                    self.config.twilio_api_key_secret, self.config.phone_number, 
                    self.config.twilio_from_number]):
            logger.warning("Twilio SMS not configured (missing account_sid, api_key, secret, or phone)")
            return False
        
        try:
            session = await self.get_session()
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.config.twilio_account_sid}/Messages.json"
            
            payload = {
                "To": self.config.phone_number,
                "From": self.config.twilio_from_number,
                "Body": message[:1600]  # SMS limit
            }
            
            # Use API Key SID + Secret for Basic Auth
            auth = aiohttp.BasicAuth(self.config.twilio_api_key_sid, self.config.twilio_api_key_secret)
            
            async with session.post(url, data=payload, auth=auth) as resp:
                result = await resp.json()
                if resp.status in [200, 201]:
                    logger.info(f"✅ SMS sent to {self.config.phone_number}")
                    return True
                else:
                    logger.error(f"❌ Twilio SMS error: {result}")
                    return False
        except Exception as e:
            logger.error(f"❌ Twilio SMS exception: {e}")
            return False
    
    # ==================== TWILIO PHONE CALL ====================
    async def make_phone_call(self, message: str) -> bool:
        """Make phone call via Twilio with TTS message in Polish"""
        if not all([self.config.twilio_account_sid, self.config.twilio_api_key_sid,
                    self.config.twilio_api_key_secret, self.config.phone_number,
                    self.config.twilio_from_number]):
            logger.warning("Twilio Phone not configured (missing account_sid, api_key, secret, or phone)")
            return False
        
        try:
            session = await self.get_session()
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self.config.twilio_account_sid}/Calls.json"
            
            # TwiML for text-to-speech in Polish
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="pl-PL">{message}</Say>
    <Pause length="1"/>
    <Say voice="alice" language="pl-PL">{message}</Say>
</Response>"""
            
            payload = {
                "To": self.config.phone_number,
                "From": self.config.twilio_from_number,
                "Twiml": twiml
            }
            
            # Use API Key SID + Secret for Basic Auth
            auth = aiohttp.BasicAuth(self.config.twilio_api_key_sid, self.config.twilio_api_key_secret)
            
            async with session.post(url, data=payload, auth=auth) as resp:
                result = await resp.json()
                if resp.status in [200, 201]:
                    logger.info(f"✅ Phone call initiated to {self.config.phone_number}")
                    return True
                else:
                    logger.error(f"❌ Twilio Call error: {result}")
                    return False
        except Exception as e:
            logger.error(f"❌ Twilio Call exception: {e}")
            return False
    
    # ==================== MAIN ALERT LOGIC ====================
    def get_threshold_level(self, margin_ratio: float) -> Optional[float]:
        """Get the highest threshold that margin exceeds"""
        for threshold in reversed(MARGIN_THRESHOLDS):
            if margin_ratio >= threshold:
                return threshold
        return None
    
    async def check_and_alert(self, account_id: str, account_name: str, 
                               margin_ratio: float, equity: float) -> Dict:
        """
        Check margin ratio and send appropriate alerts
        Returns dict with results of each channel
        """
        results = {
            "account_id": account_id,
            "account_name": account_name,
            "margin_ratio": margin_ratio,
            "equity": equity,
            "threshold_triggered": None,
            "alerts_sent": []
        }
        
        threshold = self.get_threshold_level(margin_ratio)
        
        if threshold is None:
            # Below all thresholds - reset alert state for lower thresholds
            for t in MARGIN_THRESHOLDS:
                self.state.reset_for_account(account_id, t)
            return results
        
        results["threshold_triggered"] = threshold
        
        # Check if we can send (cooldown)
        if not self.state.can_send_alert(account_id, threshold):
            results["cooldown_active"] = True
            return results
        
        # Build message
        margin_pct = margin_ratio * 100
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        message = (
            f"⚠️ MARGIN ALERT ⚠️\n\n"
            f"{account_name}\n"
            f"Margin: {margin_pct:.1f}%\n"
            f"{timestamp}"
        )
        
        plain_message = (
            f"MARGIN ALERT\n"
            f"{account_name}\n"
            f"Margin: {margin_pct:.1f}%\n"
            f"{timestamp}"
        )
        
        call_message = (
            f"Uwaga! Alarm margin dla konta {account_name}. "
            f"Margin wynosi {margin_pct:.0f} procent. "
            f"Equity wynosi {equity:.0f} dolarów."
        )
        
        is_critical = threshold >= 0.90
        
        # 70%+: Telegram + Pushover
        if threshold >= 0.70:
            tg_result = await self.send_telegram(message, is_critical)
            if tg_result:
                results["alerts_sent"].append("telegram")
            
            priority = 2 if threshold >= 0.95 else (1 if threshold >= 0.90 else 0)
            po_result = await self.send_pushover(
                f"Margin Alert: {account_name}",
                plain_message,
                priority
            )
            if po_result:
                results["alerts_sent"].append("pushover")
        
        # 80%+: SMS
        if threshold >= 0.80:
            sms_result = await self.send_sms(plain_message)
            if sms_result:
                results["alerts_sent"].append("sms")
        
        # 90%+: Phone call
        if threshold >= 0.90:
            call_result = await self.make_phone_call(call_message)
            if call_result:
                results["alerts_sent"].append("phone_call")
        
        # Mark alert as sent
        self.state.mark_alert_sent(account_id, threshold)
        
        return results
    
    async def test_all_channels(self) -> Dict:
        """Test all notification channels"""
        results = {
            "telegram": False,
            "pushover": False,
            "sms": False,
            "phone_call": False,
            "config": {
                "telegram_configured": bool(self.config.telegram_bot_token and self.config.telegram_chat_id),
                "pushover_configured": bool(self.config.pushover_app_token and self.config.pushover_user_key),
                "twilio_configured": bool(self.config.twilio_account_sid and self.config.twilio_api_key_sid and self.config.twilio_api_key_secret),
                "phone_configured": bool(self.config.phone_number)
            }
        }
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        test_message = (
            "⚠️ MARGIN ALERT ⚠️\n\n"
            "TEST ACCOUNT\n"
            "Margin: 85.0%\n"
            f"{timestamp}"
        )
        
        plain_message = (
            "MARGIN ALERT\n"
            "TEST ACCOUNT\n"
            "Margin: 85.0%\n"
            f"{timestamp}"
        )
        call_message = "To jest test systemu alertów Extended Broadcaster. Jeśli słyszysz tę wiadomość, system działa poprawnie."
        
        # Test all channels in parallel
        telegram_task = self.send_telegram(test_message, is_critical=False)
        pushover_task = self.send_pushover("Test Alert", plain_message, priority=0)
        sms_task = self.send_sms(plain_message)
        call_task = self.make_phone_call(call_message)
        
        tg, po, sms, call = await asyncio.gather(
            telegram_task, pushover_task, sms_task, call_task,
            return_exceptions=True
        )
        
        results["telegram"] = tg if isinstance(tg, bool) else False
        results["pushover"] = po if isinstance(po, bool) else False
        results["sms"] = sms if isinstance(sms, bool) else False
        results["phone_call"] = call if isinstance(call, bool) else False
        
        return results
    
    def get_config_status(self) -> dict:
        """Zwraca szczegółowy status konfiguracji wszystkich kanałów"""
        return {
            "telegram": {
                "configured": bool(self.config.telegram_bot_token and self.config.telegram_chat_id),
                "bot_token_set": bool(self.config.telegram_bot_token),
                "bot_token_preview": self.config.telegram_bot_token[:10] + "..." if self.config.telegram_bot_token else "BRAK",
                "chat_id_set": bool(self.config.telegram_chat_id),
                "chat_id": self.config.telegram_chat_id if self.config.telegram_chat_id else "BRAK"
            },
            "pushover": {
                "configured": bool(self.config.pushover_app_token and self.config.pushover_user_key),
                "app_token_set": bool(self.config.pushover_app_token),
                "app_token_preview": self.config.pushover_app_token[:10] + "..." if self.config.pushover_app_token else "BRAK",
                "user_key_set": bool(self.config.pushover_user_key),
                "user_key_preview": self.config.pushover_user_key[:10] + "..." if self.config.pushover_user_key else "BRAK"
            },
            "twilio_sms": {
                "configured": bool(self.config.twilio_account_sid and self.config.twilio_api_key_sid and 
                                   self.config.twilio_api_key_secret and self.config.phone_number),
                "account_sid_set": bool(self.config.twilio_account_sid),
                "account_sid_preview": self.config.twilio_account_sid[:10] + "..." if self.config.twilio_account_sid else "BRAK",
                "api_key_sid_set": bool(self.config.twilio_api_key_sid),
                "api_key_sid_preview": self.config.twilio_api_key_sid[:10] + "..." if self.config.twilio_api_key_sid else "BRAK",
                "api_secret_set": bool(self.config.twilio_api_key_secret),
                "phone_number": self.config.phone_number if self.config.phone_number else "BRAK",
                "from_number": self.config.twilio_from_number if self.config.twilio_from_number else "BRAK"
            },
            "twilio_call": {
                "configured": bool(self.config.twilio_account_sid and self.config.twilio_api_key_sid and 
                                   self.config.twilio_api_key_secret and self.config.phone_number),
            },
            "env_vars_expected": {
                "Telegram_bot_token": "Telegram_bot_token",
                "Telegram_id": "Telegram_id",
                "Pushover_app_token": "Pushover_app_token lub Pushover_API_token",
                "Pushover_user_key": "Pushover_user_key",
                "Twilio_account_sid": "Twilio_account_sid",
                "Twilio_sid": "Twilio_sid (API Key SID - SK...)",
                "Twillio_secret_api": "Twillio_secret_api (API Key Secret)",
                "Alert_phone_number": "Alert_phone_number",
                "Twilio_from_number": "Twilio_from_number (opcjonalnie)"
            }
        }
    
    async def test_telegram_only(self) -> dict:
        """Test tylko Telegram z logami"""
        result = {
            "channel": "telegram",
            "config": self.get_config_status()["telegram"],
            "success": False,
            "error": None
        }
        
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            result["error"] = "Brak konfiguracji: Telegram_bot_token lub Telegram_id"
            return result
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_message = f"🧪 TEST ALERTU 🧪\nExtended Broadcaster\nCzas: {timestamp}\n\nJeśli widzisz tę wiadomość, alerty działają poprawnie!"
        
        try:
            result["success"] = await self.send_telegram(test_message)
            if not result["success"]:
                result["error"] = "Wysłanie nie powiodło się - sprawdź logi serwera"
        except Exception as e:
            result["error"] = str(e)
        
        return result


# Global instance
alert_manager = MarginAlertManager()
