import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Activity, Wifi, Users, Heart, ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useState, useMemo } from "react";
import { SingleAccountData } from "@/types/multiAccount";

interface BroadcasterStats {
  broadcaster?: {
    connected_clients: number;
  };
  cache?: {
    positions_age_seconds: number;
    balance_age_seconds: number;
    trades_age_seconds: number;
  };
  last_poll?: {
    positions: number;
    balance: number;
    trades: number;
  };
  accounts?: Array<{
    id: string;
    name: string;
    positions_initialized: boolean;
    balance_initialized: boolean;
    trades_initialized: boolean;
    orders_initialized: boolean;
    positions_age_seconds: number | null;
    balance_age_seconds: number | null;
  }>;
}

interface FrequencyMonitorProps {
  broadcasterStats: BroadcasterStats | null;
  lastWsUpdate: Date | null;
  isWsConnected: boolean;
  accounts?: Map<string, SingleAccountData>;
}

interface ExchangeLatency {
  name: string;
  key: string;
  avgCacheAge: number;
  accountCount: number;
  status: 'green' | 'yellow' | 'red';
}

const EXCHANGE_DISPLAY_NAMES: Record<string, string> = {
  extended: 'Extended',
  reya: 'Reya',
  hibachi: 'Hibachi',
  grvt: 'GRVT',
  '01': '01 Exchange',
  pacifica: 'Pacifica',
  nado: 'Nado',
};

const EXCHANGE_ORDER = ['reya', 'hibachi', 'grvt', '01', 'pacifica', 'nado', 'extended'];
const HIDDEN_EXCHANGES = ['edgex_'];

const getExchangeKey = (id: string): string => {
  if (id.startsWith('01_')) return '01';
  if (id.startsWith('account_')) return 'extended';
  const m = id.match(/^([a-zA-Z]+)/);
  return m ? m[1] : id;
};

const getStatusColor = (ageSeconds: number): 'green' | 'yellow' | 'red' => {
  if (ageSeconds < 3) return 'green';
  if (ageSeconds < 10) return 'yellow';
  return 'red';
};

export const FrequencyMonitor = ({ broadcasterStats, lastWsUpdate, isWsConnected, accounts }: FrequencyMonitorProps) => {
  const [wsFrequency, setWsFrequency] = useState<number[]>([]);
  const [lastWsTime, setLastWsTime] = useState<Date | null>(null);
  const [isExpanded, setIsExpanded] = useState(true);

  useEffect(() => {
    if (lastWsUpdate && lastWsTime) {
      const diff = lastWsUpdate.getTime() - lastWsTime.getTime();
      setWsFrequency(prev => [...prev.slice(-9), diff]);
    }
    if (lastWsUpdate) {
      setLastWsTime(lastWsUpdate);
    }
  }, [lastWsUpdate]);

  const avgWs = wsFrequency.length > 0 
    ? Math.round(wsFrequency.reduce((a, b) => a + b, 0) / wsFrequency.length)
    : 0;

  const connectedClients = broadcasterStats?.broadcaster?.connected_clients ?? 0;

  const [now, setNow] = useState(Date.now());
  
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  const exchangeLatencies = useMemo((): ExchangeLatency[] => {
    const exchangeMap = new Map<string, number[]>();

    if (accounts && accounts.size > 0) {
      Array.from(accounts.values())
        .filter(acc => !HIDDEN_EXCHANGES.some(prefix => acc.id.startsWith(prefix)))
        .forEach(acc => {
          const key = getExchangeKey(acc.id);
          const lastUpdateTime = acc.lastUpdate ? new Date(acc.lastUpdate).getTime() : 0;
          const ageSeconds = lastUpdateTime > 0 ? Math.max(0, (now - lastUpdateTime) / 1000) : null;
          if (ageSeconds !== null) {
            if (!exchangeMap.has(key)) exchangeMap.set(key, []);
            exchangeMap.get(key)!.push(ageSeconds);
          }
        });
    } else if (broadcasterStats?.accounts) {
      broadcasterStats.accounts.forEach(acc => {
        const key = getExchangeKey(acc.id);
        const age = acc.positions_age_seconds ?? acc.balance_age_seconds ?? null;
        if (age !== null) {
          if (!exchangeMap.has(key)) exchangeMap.set(key, []);
          exchangeMap.get(key)!.push(age);
        }
      });
    }

    return EXCHANGE_ORDER
      .filter(key => exchangeMap.has(key))
      .map(key => {
        const ages = exchangeMap.get(key)!;
        const avg = ages.reduce((a, b) => a + b, 0) / ages.length;
        return {
          name: EXCHANGE_DISPLAY_NAMES[key] || key,
          key,
          avgCacheAge: Math.round(avg * 10) / 10,
          accountCount: ages.length,
          status: getStatusColor(avg),
        };
      });
  }, [accounts, broadcasterStats, now]);

  const accountHeartbeats = useMemo(() => {
    if (!accounts || accounts.size === 0) {
      // Fallback to broadcaster stats if no local accounts
      const broadcasterAccounts = (broadcasterStats as any)?.accounts || [];
      return broadcasterAccounts.map((acc: any) => {
        const ageSeconds = acc.positions_age_seconds ?? acc.balance_age_seconds ?? null;
        return {
          id: acc.id,
          name: acc.name,
          timeSinceUpdate: ageSeconds,
          isHealthy: ageSeconds !== null && ageSeconds < 60,
          isInitialized: acc.positions_initialized && acc.balance_initialized
        };
      });
    }
    
    // Use local account data - calculate age from lastUpdate timestamp
    const HIDDEN_EXCHANGES = ['edgex_'];
    const extractNum = (id: string): number => {
      const m = id.match(/(\d+)/);
      return m ? parseInt(m[1], 10) : 0;
    };
    const getExchangePrefix = (id: string): string => {
      if (id.startsWith('01_')) return '01';
      if (id.startsWith('account_')) return 'extended';
      const m = id.match(/^([a-zA-Z]+)/);
      return m ? m[1] : id;
    };
    const exchangeOrder = ['reya', 'hibachi', 'grvt', '01', 'pacifica', 'nado', 'extended'];
    return Array.from(accounts.values())
      .filter(acc => !HIDDEN_EXCHANGES.some(prefix => acc.id.startsWith(prefix)))
      .map(acc => {
        const lastUpdateTime = acc.lastUpdate ? new Date(acc.lastUpdate).getTime() : 0;
        const ageSeconds = lastUpdateTime > 0 ? Math.max(0, Math.floor((now - lastUpdateTime) / 1000)) : null;
        return {
          id: acc.id,
          name: acc.name,
          timeSinceUpdate: ageSeconds,
          isHealthy: ageSeconds !== null && ageSeconds < 30,
          isInitialized: acc.positions.length > 0 || acc.balance !== null
        };
      })
      .sort((a, b) => {
        const prefA = getExchangePrefix(a.id);
        const prefB = getExchangePrefix(b.id);
        const orderA = exchangeOrder.indexOf(prefA);
        const orderB = exchangeOrder.indexOf(prefB);
        const rankA = orderA >= 0 ? orderA : exchangeOrder.length;
        const rankB = orderB >= 0 ? orderB : exchangeOrder.length;
        if (rankA !== rankB) return rankA - rankB;
        const accNum = (name: string, id: string) => {
          const m = name.match(/(?:Exchange|Extended|Reya|Hibachi|GRVT|Nado|Account)\s+(\d+)/i);
          if (m) return parseInt(m[1], 10);
          const idM = id.match(/_(\d+)$/);
          if (idM) return parseInt(idM[1], 10);
          return extractNum(id);
        };
        return accNum(a.name || '', a.id) - accNum(b.name || '', b.id);
      });
  }, [accounts, broadcasterStats, now]);

  return (
    <Card className="p-4 border-border/50 bg-card/50 backdrop-blur-sm">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-primary flex items-center gap-2">
            <Activity className="w-4 h-4" />
            BROADCASTER MONITOR
          </h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            className="h-6 px-2"
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </Button>
        </div>
        
        {isExpanded && (
        <>
        {/* Exchange Latencies + WS Stats */}
        <div className={`grid gap-3 text-xs`} style={{ gridTemplateColumns: `repeat(${exchangeLatencies.length + 2}, minmax(0, 1fr))` }}>
          {exchangeLatencies.map(ex => {
            const statusClasses = ex.status === 'green'
              ? 'border-success/40 bg-success/10'
              : ex.status === 'yellow'
                ? 'border-yellow-500/40 bg-yellow-500/10'
                : 'border-destructive/40 bg-destructive/10';
            const textClass = ex.status === 'green'
              ? 'text-success'
              : ex.status === 'yellow'
                ? 'text-yellow-500'
                : 'text-destructive';
            const dotClass = ex.status === 'green'
              ? 'bg-success animate-pulse'
              : ex.status === 'yellow'
                ? 'bg-yellow-500'
                : 'bg-destructive';
            return (
              <div key={ex.key} className={`space-y-1 p-2 rounded border ${statusClasses}`}>
                <div className="flex items-center gap-1 text-muted-foreground">
                  <div className={`w-2 h-2 rounded-full ${dotClass}`} />
                  <span className="truncate">{ex.name}</span>
                </div>
                <div className={`text-lg font-mono font-bold ${textClass}`}>
                  {ex.avgCacheAge}s
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {ex.accountCount} {ex.accountCount === 1 ? 'account' : 'accounts'}
                </div>
              </div>
            );
          })}

          {/* WebSocket Broadcast */}
          <div className="space-y-1 p-2 bg-muted/30 rounded">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Wifi className={`w-3 h-3 ${isWsConnected ? 'text-success animate-pulse' : 'text-destructive'}`} />
              <span>WebSocket</span>
            </div>
            <div className="text-lg font-mono font-bold text-success">
              {avgWs > 0 ? `${avgWs}ms` : '---'}
            </div>
            <div className="text-[10px] text-muted-foreground">
              {lastWsUpdate 
                ? lastWsUpdate.toLocaleTimeString('pl-PL', { hour12: false }) + '.' + lastWsUpdate.getMilliseconds().toString().padStart(3, '0')
                : 'No events'
              }
            </div>
          </div>

          {/* Connected Clients */}
          <div className="space-y-1 p-2 bg-muted/30 rounded">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Users className="w-3 h-3 text-success" />
              <span>WS Clients</span>
            </div>
            <div className="text-lg font-mono font-bold text-success">
              {connectedClients}
            </div>
            <div className="text-[10px] text-muted-foreground">
              Connected
            </div>
          </div>
        </div>

        {/* Account Heartbeats */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Heart className="w-3 h-3 text-danger" />
            <span>Account Heartbeats ({accountHeartbeats.length} accounts)</span>
          </div>
          <div className="grid grid-cols-5 md:grid-cols-10 gap-2">
            {accountHeartbeats.map((acc, i) => (
              <div 
                key={acc.id}
                className={`p-2 rounded text-center ${
                  acc.isHealthy 
                    ? 'bg-success/20 border border-success/30' 
                    : 'bg-destructive/20 border border-destructive/30'
                }`}
                title={`${acc.name}\nAge: ${acc.timeSinceUpdate ?? 'N/A'}s`}
              >
                <div className="text-[10px] font-medium truncate">
                  {acc.name.replace('Account ', 'Acc ')}
                </div>
                <div className={`text-xs font-mono font-bold ${acc.isHealthy ? 'text-success' : 'text-destructive'}`}>
                  {acc.timeSinceUpdate !== null ? `${acc.timeSinceUpdate}s` : '---'}
                </div>
                <div className={`w-2 h-2 mx-auto rounded-full mt-1 ${
                  acc.isHealthy ? 'bg-success animate-pulse' : 'bg-destructive'
                }`} />
              </div>
            ))}
          </div>
        </div>

        {/* WS History bars - Compact */}
        <div className="flex items-center gap-3">
          <div className="text-[10px] text-muted-foreground whitespace-nowrap">WS intervals:</div>
          <div className="flex gap-0.5 h-4 items-end flex-1">
            {wsFrequency.map((val, i) => (
              <div 
                key={i} 
                className="flex-1 bg-success/50 rounded-sm max-w-4"
                style={{ height: `${Math.min((val / 5000) * 100, 100)}%` }}
                title={`${val}ms`}
              />
            ))}
          </div>
          <div className="text-[10px] text-muted-foreground">
            Avg: {avgWs}ms
          </div>
        </div>
        </>
        )}
      </div>
    </Card>
  );
};
