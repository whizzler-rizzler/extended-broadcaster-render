import os
from typing import List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class AccountConfig(BaseModel):
    name: str
    account_index: int
    api_key_index: int
    private_key: str
    public_key: str
    proxy_url: Optional[str] = None

class Settings(BaseModel):
    lighter_base_url: str = "https://mainnet.zklighter.elliot.ai"
    lighter_ws_url: str = "wss://mainnet.zklighter.elliot.ai/stream"
    
    host: str = "0.0.0.0"
    port: int = 5000
    
    poll_interval: float = 0.5
    cache_ttl: int = 5
    
    rate_limit: str = "100/minute"
    
    accounts: List[AccountConfig] = []

def load_accounts_from_env() -> List[AccountConfig]:
    accounts = []
    env_vars = os.environ
    
    account_prefixes = set()
    for key in env_vars:
        if key.startswith("Lighter_") and "_Account_Index" in key:
            prefix = key.replace("_Account_Index", "")
            account_prefixes.add(prefix)
    
    for prefix in sorted(account_prefixes):
        account_index = env_vars.get(f"{prefix}_Account_Index")
        api_key_index = env_vars.get(f"{prefix}_API_KEY_Index")
        private_key = env_vars.get(f"{prefix}_PRIVATE")
        public_key = env_vars.get(f"{prefix}_PUBLIC")
        
        proxy_key = None
        for key in env_vars:
            if key.startswith(prefix.replace("_Account_Index", "").rsplit("_", 1)[0]) and "PROXY" in key:
                proxy_key = key
                break
        
        proxy_url = env_vars.get(proxy_key) if proxy_key else None
        
        if account_index and private_key:
            accounts.append(AccountConfig(
                name=prefix,
                account_index=int(account_index),
                api_key_index=int(api_key_index) if api_key_index else 2,
                private_key=private_key,
                public_key=public_key or "",
                proxy_url=proxy_url
            ))
    
    return accounts

def get_settings() -> Settings:
    accounts = load_accounts_from_env()
    return Settings(
        lighter_base_url=os.getenv("LIGHTER_BASE_URL", "https://mainnet.zklighter.elliot.ai"),
        lighter_ws_url=os.getenv("LIGHTER_WS_URL", "wss://mainnet.zklighter.elliot.ai/stream"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        poll_interval=float(os.getenv("POLL_INTERVAL", "0.5")),
        cache_ttl=int(os.getenv("CACHE_TTL", "5")),
        rate_limit=os.getenv("RATE_LIMIT", "100/minute"),
        accounts=accounts
    )

settings = get_settings()
