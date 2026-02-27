# Multi-Account Trading Dashboard

Multi-account trading dashboard (React + Python FastAPI) monitoring real-time accounts across multiple exchanges: Extended (24 accounts), Reya (6 accounts), EdgeX (4 accounts - hidden on frontend), Hibachi (2 accounts), GRVT (4 accounts), 01 Exchange (6 accounts). Total: 46 accounts in API, 42 displayed on frontend (without EdgeX).

## Architecture

```
MergedApp/
  backend/
    main.py              - FastAPI application with REST endpoints, WebSocket server, local poller
    edgex_client.py      - EdgeX exchange client (4 accounts) with REST polling
    hibachi_client.py    - Hibachi exchange client (2 accounts) with REST polling
    grvt_client.py       - GRVT exchange client (4 accounts) with cookie-based auth and REST polling
    reya_client.py       - Reya exchange client (6 accounts) with REST polling
    zero_one_client.py   - 01 Exchange client (6 accounts) with public REST API polling
  src/
    components/
      MultiAccountDashboard.tsx  - Main dashboard component
      AccountCardCompact.tsx     - Individual account card component
      FrequencyMonitor.tsx       - Broadcaster monitor with heartbeats
    hooks/
      useMultiAccountData.ts     - Data fetching hook with WebSocket support
    types/
      multiAccount.ts            - TypeScript type definitions
  vite.config.ts         - Vite config with API proxy to backend
  package.json           - Frontend dependencies
```

## Operating Mode

Backend runs in `FRONTEND_ONLY` mode:
- **Extended**: Proxied from remote backend (`REMOTE_API_BASE`)
- **Reya**: Polled locally (6 accounts)
- **EdgeX**: Polled locally (4 accounts) - hidden on frontend
- **Hibachi**: Polled locally (2 accounts)
- **GRVT**: Polled locally (4 accounts) with cookie-based authentication
- **01 Exchange**: Polled locally (5 accounts) via public REST API

## Exchange Integration Details

### 01 Exchange
- **API**: Public REST API at `https://zo-mainnet.n1.xyz` - NO authentication required for reads
- **Endpoints**: `GET /user/{pubkey}` (resolve account ID), `GET /account/{id}` (balances, positions, orders, margins), `GET /info` (market info)
- **Secrets**: `_01exchange_account_N` = Solana wallet pubkey (not Ethereum addresses)
- **Account resolution**: Wallet pubkey → account_id via `/user/{pubkey}` at startup
- **Data**: USDC balance, perp positions (BTC, ETH, SOL, HYPE, etc.), open orders, margin health
- **Frontend key**: `01_` prefix, exchange name `01exchange`, color `text-cyan-400`

### GRVT
- **Auth**: Cookie-based – POST to `edge.grvt.io/auth/api_key/login` with `{"api_key": "..."}` and `Cookie: rm=true;`
- **Response**: `Set-Cookie: gravity=...` + `x-grvt-account-id` header; session ~58 minutes
- **Endpoints**: `account_summary`, `positions`, `open_orders` – all POST to `trades.grvt.io/full/v1/`
- **Secrets**: `GRVT_N_api_key`, `GRVT_N_trading_account_ID`, `GRVT_N_Secret_Private_Key`, `GRVT_N_account_ID`
- **Geo-blocking**: API geo-blocked – requires proxy; proxy fallback tries `Rest_account_N_proxy` sequentially

### Hibachi
- `maintenanceMargin / balance` = margin ratio
- Leverage fallback from `total_notional / balance`
- Secrets: `Hibachi_N_AccountID` or `Hibachi_N_trading_Account_ID`, `Hibachi_N_api_key` or `Hibachi_N_priv_key`

### Reya
- Secrets: `Reya_N_wallet_main` or `Reya_N_wallet_adress`, `Reya_N_priv_key`

### EdgeX
- Hidden on frontend via `HIDDEN_EXCHANGES` in `useMultiAccountData.ts`, `FrequencyMonitor.tsx`, `MultiAccountDashboard.tsx`
- Secrets: `EdgeX_N_AccountID`, `EdgeX_N_priv_key`, `EdgeX_N_publicKeyYCoordinate`

### Extended
- 24 accounts proxied from remote backend
- Secrets: `Extended_N_{CODE}_API_KEY`, etc.

## Configuration

- `BROADCASTER_MODE` = `FRONTEND_ONLY`
- `REMOTE_API_BASE` = URL of remote backend for Extended
- Backend runs on port 8000, Frontend (Vite) on port 5000

## Workflows

- **MergedApp Backend**: `cd MergedApp/backend && uvicorn main:app --host 0.0.0.0 --port 8000`
- **MergedApp Frontend**: `cd MergedApp && npm run dev`
