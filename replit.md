# Extended Exchange Broadcaster Service

A Python-based broadcaster service that acts as a data intermediary for Extended Exchange (Starknet) trading platform.

## Overview

This service monitors Extended Exchange accounts using REST API polling (2x per second), then redistributes the data through its own REST API and WebSocket endpoints with rate limiting and caching.

## Architecture

```
Backend/
  __init__.py
  api.py              - FastAPI application with REST endpoints and WebSocket server
  cache.py            - In-memory caching layer with TTL support
  config.py           - Configuration and environment variable loading
  error_collector.py  - Centralized error tracking and logging
  lighter_client.py   - Lighter SDK wrapper for REST API polling with retry logic
  latency.py          - Latency tracking utilities
  supabase_client.py  - Supabase integration for data persistence
  websocket_client.py - WebSocket client for real-time Lighter updates with reconnect
  websocket_server.py - WebSocket server for broadcasting to clients
mFrontend/            - React frontend (Vite)
main.py               - Application entry point
supabase_schema.sql   - SQL schema for Supabase tables
```

## Features

- **REST API Polling**: Polls Lighter accounts at configurable intervals (default: 0.5s)
- **Active Orders Polling**: Fetches active orders for each account every 2 seconds
- **WebSocket Client**: Real-time updates from Lighter.xyz via proxy (using aiohttp-socks)
- **Caching**: In-memory cache with configurable TTL
- **REST API**: Serves cached account data with rate limiting
- **WebSocket Broadcasting**: Pushes updates to connected clients
- **Status Dashboard**: Visual display of connections, positions, and orders
- **Proxy Support**: Both REST API and WebSocket connections use configured proxies
- **Supabase Persistence**: Optional data persistence to Supabase (snapshots, positions, orders, trades)
- **React Frontend**: Modern dashboard built with Vite/React

## Reconnect & Retry Logic

Both WebSocket and REST API clients use a multi-phase retry strategy:

- **Ping/heartbeat**: WebSocket sends ping every 30 seconds
- **Phase 1**: Retry every 60 seconds (up to 5 attempts)
- **Phase 2**: After 5 failures, retry every 5 minutes
- **No limit**: Retries continue indefinitely until success
- **Auto-reset**: After successful connection, retry state resets to Phase 1

Health status includes:
- Connection state (connected/disconnected)
- Retry phase and attempt count
- Uptime, message counts, error details
- Success rate for REST API

## API Endpoints

### Core Endpoints
- `GET /` - React dashboard
- `GET /health` - Health check
- `GET /api/status` - Service status and metrics
- `GET /api/latency` - Latency metrics
- `GET /api/portfolio` - Aggregated portfolio data

### Account Data
- `GET /api/accounts` - All cached accounts
- `GET /api/accounts/{index}` - Specific account data

### WebSocket Data
- `GET /api/ws/positions` - All positions from WebSocket
- `GET /api/ws/positions/{index}` - Positions for specific account
- `GET /api/ws/orders` - All orders from WebSocket
- `GET /api/ws/orders/{index}` - Orders for specific account
- `GET /api/ws/trades` - All trades from WebSocket
- `GET /api/ws/trades/{index}` - Trades for specific account

### Connection Health
- `GET /api/ws/health` - WebSocket connections health status
- `GET /api/rest/health` - REST API connections health status
- `GET /api/connections/health` - Combined health (WebSocket + REST)
- `POST /api/ws/reconnect` - Force reconnect WebSocket (optional: ?account_index=X)
- `POST /api/rest/reconnect` - Force reset REST retry (optional: ?account_index=X)
- `POST /api/connections/reconnect` - Force reconnect all connections

### Error Logging
- `GET /api/errors` - Recent errors with summary (limit param optional)
- `POST /api/errors/clear` - Clear error log

### Historical Data (Supabase)
- `GET /api/history/accounts/{index}` - Account historical snapshots
- `GET /api/history/trades/{index}` - Trade history
- `GET /api/supabase/status` - Supabase connection status

### WebSocket
- `WS /ws` - WebSocket for real-time updates

### Order Book (Real-time via Extended Stream)
- `GET /api/orderbook` - All cached order books for all markets
- `GET /api/orderbook/{market}` - Order book for specific market (e.g., ETH-PERP)
- `GET /api/orderbook-status` - Order book WebSocket connection status

### Earned Points (polling every 10 minutes)
- `GET /api/points` - All accounts earned points with total sum
- `GET /api/points/{index}` - Points for specific account
- `POST /api/points/refresh` - Force refresh points from Extended API

Note: Points API depends on Extended Exchange `/points/earned` endpoint which is documented but may not be active yet (returns 404). Code is ready to work when endpoint becomes available.

## Configuration

Environment variables for account configuration follow this pattern:
- `Extended_{N}_{CODE}_API_KEY` - API key for account N
- `Extended_{N}_{CODE}_CLIENT_ID` - Client ID
- `Extended_{N}_{CODE}_STARKNET_PRIVATE` - Starknet private key
- `Extended_{N}_{CODE}_STARKNET_PUBLIC` - Starknet public key
- `Extended_{N}_{CODE}_VAULT_NUMBER` - Vault number
- `Extended_{N}_PROXY_{N}_URL` - Proxy URL (see Proxy Configuration below)

### Proxy Configuration

Proxy URLs support two formats:

1. **Full URL format (recommended)**:
   ```
   http://username:password@ip:port/
   ```
   Example: `http://ilbefxoi-staticresidential:mhaamz128dg0@82.27.111.128:5335/`

2. **Legacy format**:
   ```
   IP:PORT:Username:Password
   ```
   Example: `82.27.111.128:5335:ilbefxoi-staticresidential:mhaamz128dg0`

Other settings:
- `POLL_INTERVAL` - Polling interval in seconds (default: 0.5)
- `CACHE_TTL` - Cache TTL in seconds (default: 5)
- `RATE_LIMIT` - API rate limit (default: 100/minute)

Broadcaster mode settings:
- `BROADCASTER_MODE` - Operating mode: `COLLECTOR` (default) or `FRONTEND_ONLY`
  - `COLLECTOR`: Full mode - polls Lighter API, connects WebSocket, caches data, serves frontend
  - `FRONTEND_ONLY`: Lightweight mode - only serves frontend, proxies API requests to remote backend
- `REMOTE_API_BASE` - URL of remote backend (required for FRONTEND_ONLY mode), e.g. `https://your-render-app.onrender.com`

Frontend build settings:
- `VITE_API_BASE` - Build-time API base URL for frontend (empty string for same-origin, or full URL for cross-origin)

Supabase settings (optional):
- `Supabase_Url` - Supabase project URL
- `Supabase_service_role` - Supabase service role key (for server-side access)

## Deployment

Configured for Render.com deployment via GitHub integration. See `render.yaml` for configuration.

## Running Locally

```bash
python main.py
```

The service will start on port 5000 by default.
