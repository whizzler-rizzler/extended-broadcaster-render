"""
Lighter Dual Bot - Flask API Server
With proxy support for geo-restriction bypass
"""
import asyncio
import nest_asyncio
import logging
import os
import json
import lighter
from flask import Flask, jsonify, send_file
from flask_cors import CORS
from lighter_bot import bot_instance, LIGHTER_URL, get_proxy_config, get_proxy_for_account

nest_asyncio.apply()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Get the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.after_request
def add_no_cache_headers(response):
    """Add no-cache headers for API responses"""
    if 'application/json' in response.content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.route("/")
def index():
    html_path = os.path.join(BASE_DIR, "index.html")
    try:
        with open(html_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return jsonify({
            "name": "Lighter Dual Bot",
            "status": "online",
            "endpoints": ["/api/lighter-bot/start", "/api/lighter-bot/stop", "/api/lighter-bot/status", "/api/lighter-bot/monitor"]
        })


@app.route("/api/lighter-bot/start", methods=["POST"])
def start_bot():
    try:
        success = bot_instance.start(loop)
        if success:
            return jsonify({"success": True, "message": "Bot started"})
        else:
            return jsonify({"success": False, "message": "Failed to start bot"}), 400
    except Exception as e:
        logger.error(f"Start error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/lighter-bot/stop", methods=["POST"])
def stop_bot():
    try:
        success = bot_instance.stop()
        if success:
            return jsonify({"success": True, "message": "Bot stopped"})
        else:
            return jsonify({"success": False, "message": "Bot not running"}), 400
    except Exception as e:
        logger.error(f"Stop error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/lighter-bot/status", methods=["GET"])
def bot_status():
    return jsonify(bot_instance.get_status())


@app.route("/api/lighter-bot/monitor", methods=["GET"])
def bot_monitor():
    status = bot_instance.get_status()
    proxy = get_proxy_config()
    return jsonify({
        "status": "🟢 LIVE" if status["running"] else "🔴 STOPPED",
        "cycle": status["cycle"],
        "total_volume": f"{status['total_volume_btc']:.4f} BTC",
        "successful_cycles": status["successful_cycles"],
        "failed_cycles": status["failed_cycles"],
        "uptime_minutes": round(status["uptime_seconds"] / 60, 2),
        "cycles_per_minute": status["cycles_per_minute"],
        "account1_direction": status["account1_direction"],
        "account2_direction": status["account2_direction"],
        "recovery_required": status["recovery_required"],
        "trade_notional_usd": f"${status['trade_notional_usd']} per side",
        "trade_size_btc": f"{status['trade_size_btc']:.6f} BTC",
        "btc_price": f"${status['btc_price']:,.2f}",
        "proxy_acc3": "✅ ACTIVE" if os.environ.get("PROXY_ACCOUNT3") else "❌ NONE",
        "proxy_acc5": "✅ ACTIVE" if os.environ.get("PROXY_ACCOUNT5") else "❌ NONE",
        "proxy_status": "✅ SEPARATE PROXIES" if (os.environ.get("PROXY_ACCOUNT3") and os.environ.get("PROXY_ACCOUNT5")) else "⚠️ MISSING PROXY",
        "current_phase": status.get("current_phase", "IDLE"),
        "time_to_next_action": status.get("time_to_next_action", 0),
        "current_hold_time": status.get("current_hold_time", 0)
    })


def fetch_lighter_account(account_index: int) -> dict:
    """Fetch account data from Lighter API via HTTP with account-specific proxy"""
    import requests
    proxy = get_proxy_for_account(account_index)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    
    try:
        url = f"{LIGHTER_URL}/api/v1/account"
        params = {"by": "index", "value": str(account_index)}
        resp = requests.get(url, params=params, proxies=proxies, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("accounts") and len(data["accounts"]) > 0:
                return data["accounts"][0]
    except Exception as e:
        logger.debug(f"Lighter API fetch for {account_index}: {e}")
    return None


def get_volume_stats(account_index: int) -> dict:
    """Get volume stats from internal bot tracking (real data)"""
    return bot_instance.get_volume_stats(account_index)


@app.route("/api/lighter-bot/volume-stats", methods=["GET"])
def get_volume_stats_endpoint():
    """Fetch volume statistics from Lighter WebSocket API for both accounts"""
    try:
        acc1_idx = int(os.environ.get("Lighter_3_account_index", "382129"))
        acc2_idx = int(os.environ.get("Lighter_5_account_index", "497888"))
        
        vol1 = get_volume_stats(acc1_idx)
        vol2 = get_volume_stats(acc2_idx)
        
        return jsonify({
            "account3": {
                "account_index": acc1_idx,
                "daily_volume": vol1.get("daily_volume", 0),
                "weekly_volume": vol1.get("weekly_volume", 0),
                "monthly_volume": vol1.get("monthly_volume", 0),
                "total_volume": vol1.get("total_volume", 0),
                "daily_trades": vol1.get("daily_trades_count", 0),
                "weekly_trades": vol1.get("weekly_trades_count", 0),
                "total_trades": vol1.get("total_trades_count", 0)
            },
            "account5": {
                "account_index": acc2_idx,
                "daily_volume": vol2.get("daily_volume", 0),
                "weekly_volume": vol2.get("weekly_volume", 0),
                "monthly_volume": vol2.get("monthly_volume", 0),
                "total_volume": vol2.get("total_volume", 0),
                "daily_trades": vol2.get("daily_trades_count", 0),
                "weekly_trades": vol2.get("weekly_trades_count", 0),
                "total_trades": vol2.get("total_trades_count", 0)
            },
            "combined": {
                "daily_volume": vol1.get("daily_volume", 0) + vol2.get("daily_volume", 0),
                "weekly_volume": vol1.get("weekly_volume", 0) + vol2.get("weekly_volume", 0),
                "total_volume": vol1.get("total_volume", 0) + vol2.get("total_volume", 0)
            }
        })
    except Exception as e:
        logger.error(f"Error fetching volume stats: {e}")
        return jsonify({
            "error": str(e),
            "account3": {"daily_volume": 0, "weekly_volume": 0, "total_volume": 0},
            "account5": {"daily_volume": 0, "weekly_volume": 0, "total_volume": 0},
            "combined": {"daily_volume": 0, "weekly_volume": 0, "total_volume": 0}
        })


@app.route("/api/lighter-bot/accounts", methods=["GET"])
def get_accounts():
    """Fetch real positions from Lighter exchange via HTTP API"""
    try:
        acc1_idx = os.environ.get("Lighter_3_account_index", "382129")
        acc2_idx = os.environ.get("Lighter_5_account_index", "497888")
        
        result = {
            "account3": {
                "account": f"Account 3 ({acc1_idx})", 
                "position": "FLAT",
                "size": 0,
                "equity": 0, 
                "balance": 0, 
                "pnl": 0,
                "margin": 0,
                "exposure": 0,
                "leverage": 0,
                "volume": 0,
                "direction": bot_instance.account1_direction
            },
            "account5": {
                "account": f"Account 5 ({acc2_idx})", 
                "position": "FLAT",
                "size": 0,
                "equity": 0, 
                "balance": 0, 
                "pnl": 0,
                "margin": 0,
                "exposure": 0,
                "leverage": 0,
                "volume": 0,
                "direction": bot_instance.account2_direction
            }
        }
        
        acc1_data = fetch_lighter_account(int(acc1_idx))
        if acc1_data:
            collateral = float(acc1_data.get("collateral", "0"))
            available = float(acc1_data.get("available_balance", "0"))
            margin_used = collateral - available
            result["account3"]["equity"] = collateral
            result["account3"]["balance"] = available
            result["account3"]["margin"] = margin_used
            result["account3"]["volume"] = float(acc1_data.get("total_volume", "0"))
            
            positions = acc1_data.get("positions", [])
            total_pnl = 0
            total_exposure = 0
            for pos in positions:
                upnl = float(pos.get("unrealized_pnl", "0"))
                total_pnl += upnl
                if pos.get("market_id") == 1 or pos.get("symbol") == "BTCUSDC":
                    sign = pos.get("sign", 0)
                    size = float(pos.get("position", "0"))
                    entry_price = float(pos.get("avg_entry_price", "0"))
                    exposure = size * entry_price
                    total_exposure += exposure
                    if size > 0:
                        direction = "LONG" if sign == 1 else "SHORT"
                        result["account3"]["position"] = direction
                        result["account3"]["size"] = size
            result["account3"]["pnl"] = total_pnl
            result["account3"]["exposure"] = total_exposure
            if collateral > 0 and total_exposure > 0:
                result["account3"]["leverage"] = round(total_exposure / collateral, 2)
        
        acc2_data = fetch_lighter_account(int(acc2_idx))
        if acc2_data:
            collateral = float(acc2_data.get("collateral", "0"))
            available = float(acc2_data.get("available_balance", "0"))
            margin_used = collateral - available
            result["account5"]["equity"] = collateral
            result["account5"]["balance"] = available
            result["account5"]["margin"] = margin_used
            result["account5"]["volume"] = float(acc2_data.get("total_volume", "0"))
            
            positions = acc2_data.get("positions", [])
            total_pnl = 0
            total_exposure = 0
            for pos in positions:
                upnl = float(pos.get("unrealized_pnl", "0"))
                total_pnl += upnl
                if pos.get("market_id") == 1 or pos.get("symbol") == "BTCUSDC":
                    sign = pos.get("sign", 0)
                    size = float(pos.get("position", "0"))
                    entry_price = float(pos.get("avg_entry_price", "0"))
                    exposure = size * entry_price
                    total_exposure += exposure
                    if size > 0:
                        direction = "LONG" if sign == 1 else "SHORT"
                        result["account5"]["position"] = direction
                        result["account5"]["size"] = size
            result["account5"]["pnl"] = total_pnl
            result["account5"]["exposure"] = total_exposure
            if collateral > 0 and total_exposure > 0:
                result["account5"]["leverage"] = round(total_exposure / collateral, 2)
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching accounts: {e}")
        return jsonify({
            "account3": {"account": "Account 3", "position": "Error", "equity": 0, "balance": 0, "pnl": 0},
            "account5": {"account": "Account 5", "position": "Error", "equity": 0, "balance": 0, "pnl": 0},
            "error": str(e)
        })


if __name__ == "__main__":
    logger.info("Starting Lighter Dual Bot server on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
