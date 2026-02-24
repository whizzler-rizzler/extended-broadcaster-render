# Multi-Account Trading Dashboard

Multi-account trading dashboard (React + Python FastAPI) monitoring real-time accounts across multiple exchanges: Extended (24 accounts), Reya, EdgeX (4 accounts), Hibachi (2 accounts), and GRVT (2 accounts). Total: 31 active accounts.

## Architecture

```
MergedApp/
  backend/
    main.py              - FastAPI application with REST endpoints, WebSocket server, local poller
    edgex_client.py      - EdgeX exchange client (4 accounts) with REST polling
    hibachi_client.py    - Hibachi exchange client (2 accounts) with REST polling
    grvt_client.py       - GRVT exchange client (2 accounts) with cookie-based auth and REST polling
  src/
    components/
      MultiAccountDashboard.tsx  - Main dashboard component
      AccountCardCompact.tsx     - Individual account card component
    hooks/
      useMultiAccountData.ts     - Data fetching hook with WebSocket support
    types/
      multiAccount.ts            - TypeScript type definitions
  vite.config.ts         - Vite config with API proxy to backend
  package.json           - Frontend dependencies
```

## Operating Mode

Backend runs in `FRONTEND_ONLY` mode:
- **Extended/Reya**: Proxied from remote backend (`REMOTE_API_BASE`)
- **EdgeX**: Polled locally (4 accounts)
- **Hibachi**: Polled locally (2 accounts)
- **GRVT**: Polled locally (2 accounts) with cookie-based authentication

## Exchange Integration Details

### GRVT
- **Auth**: Cookie-based – POST to `edge.grvt.io/auth/api_key/login` with `{"api_key": "..."}` and `Cookie: rm=true;`
- **Response**: `Set-Cookie: gravity=...` + `x-grvt-account-id` header; session ~58 minutes
- **Endpoints**: `account_summary`, `positions`, `open_orders` – all POST to `trades.grvt.io/full/v1/`
- **Secrets**: `GRVT_N_api_key`, `GRVT_N_trading_account_ID`, `GRVT_N_Secret_Private_Key`, `GRVT_N_account_ID`
- **Geo-blocking**: API geo-blocked – requires proxy; proxy fallback tries `Rest_account_N_proxy` sequentially
- **Data normalization**: `size` (negative=SHORT), prices in 9 decimal (if >1e6 divide by 1e9), `est_liquidation_price`, `leverage`, `unrealized_pnl`
- **Balance**: `total_equity`, `initial_margin`, `maintenance_margin`, `available_balance`, `spot_balances[].balance`

### Hibachi
- `maintenanceMargin / balance` = margin ratio
- Leverage fallback from `total_notional / balance`
- Secrets: `Hibachi_N_AccountID`, `Hibachi_N_api_key`

### EdgeX
- Errors whitelist/invalid_account_id are API-side issues – not fixable locally
- Secrets: `EdgeX_N_AccountID`, `EdgeX_N_priv_key`, `EdgeX_N_publicKeyYCoordinate`

### Extended
- 24 accounts proxied from remote backend
- Secrets: `Extended_N_{CODE}_API_KEY`, etc.

## Configuration

- `BROADCASTER_MODE` = `FRONTEND_ONLY`
- `REMOTE_API_BASE` = URL of remote backend for Extended/Reya
- `POLL_INTERVAL` = polling interval (default 0.5s)
- Backend runs on port 8000, Frontend (Vite) on port 5000

## Workflows

- **MergedApp Backend**: `cd MergedApp/backend && uvicorn main:app --host 0.0.0.0 --port 8000`
- **MergedApp Frontend**: `cd MergedApp && npm run dev`
