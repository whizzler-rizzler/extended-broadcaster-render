import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Activity, Wifi, Users, Clock, Heart, Server, Database, ChevronDown, ChevronUp } from "lucide-react";
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
  const cacheAgePositions = broadcasterStats?.cache?.positions_age_seconds ?? 0;
  const cacheAgeBalance = broadcasterStats?.cache?.balance_age_seconds ?? 0;
  const cacheAgeTrades = broadcasterStats?.cache?.trades_age_seconds ?? 0;
  const lastPollPositions = broadcasterStats?.last_poll?.positions;
  const lastPollTrades = broadcasterStats?.last_poll?.trades;

  // Account heartbeat data - calculate age locally from accounts data
  const [now, setNow] = useState(Date.now());
  
  // Update "now" every second to recalculate ages
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

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
    return Array.from(accounts.values()).map(acc => {
      const lastUpdateTime = acc.lastUpdate ? new Date(acc.lastUpdate).getTime() : 0;
      // Use Math.max to prevent negative values when server time is slightly ahead
      const ageSeconds = lastUpdateTime > 0 ? Math.max(0, Math.floor((now - lastUpdateTime) / 1000)) : null;
      return {
        id: acc.id,
        name: acc.name,
        timeSinceUpdate: ageSeconds,
        isHealthy: ageSeconds !== null && ageSeconds < 30, // healthy if updated within 30s
        isInitialized: acc.positions.length > 0 || acc.balance !== null
      };
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
        {/* Main Stats Grid - Compact */}
        <div className="grid grid-cols-6 gap-3 text-xs">
          {/* External API Sources */}
          <div className="space-y-1 p-2 bg-muted/30 rounded">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Server className="w-3 h-3 text-primary" />
              <span>Źródła API</span>
            </div>
            <div className="text-lg font-mono font-bold text-primary">
              3
            </div>
            <div className="text-[10px] text-muted-foreground">
              Positions, Balance, Trades
            </div>
          </div>

          {/* Extended API Polling */}
          <div className="space-y-1 p-2 bg-muted/30 rounded">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Activity className="w-3 h-3 text-primary animate-pulse" />
              <span>API Positions</span>
            </div>
            <div className="text-lg font-mono font-bold text-primary">
              4x/s
            </div>
            <div className="text-[10px] text-muted-foreground">
              {lastPollPositions 
                ? new Date(lastPollPositions * 1000).toLocaleTimeString('pl-PL', { hour12: false })
                : 'N/A'
              }
            </div>
          </div>

          {/* Balance API */}
          <div className="space-y-1 p-2 bg-muted/30 rounded">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Database className="w-3 h-3 text-primary/70" />
              <span>API Balance</span>
            </div>
            <div className="text-lg font-mono font-bold text-primary/70">
              4x/s
            </div>
            <div className="text-[10px] text-muted-foreground">
              Cache: {cacheAgeBalance}s
            </div>
          </div>

          {/* Trades Polling */}
          <div className="space-y-1 p-2 bg-muted/30 rounded">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Clock className="w-3 h-3 text-primary/70" />
              <span>API Trades</span>
            </div>
            <div className="text-lg font-mono font-bold text-primary/70">
              1x/5s
            </div>
            <div className="text-[10px] text-muted-foreground">
              {lastPollTrades 
                ? new Date(lastPollTrades * 1000).toLocaleTimeString('pl-PL', { hour12: false })
                : 'N/A'
              }
            </div>
          </div>

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
                title={`${acc.name}\nLast: ${acc.lastUpdate ? new Date(acc.lastUpdate).toLocaleTimeString() : 'Never'}\nAge: ${acc.timeSinceUpdate ?? 'N/A'}s`}
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
