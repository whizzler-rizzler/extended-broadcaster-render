import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity, Clock, Zap, Server, Globe, ChevronDown, ChevronUp, Database, Radio } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { BroadcasterStats } from '@/hooks/useBroadcasterStats';

interface LatencyMonitorProps {
  broadcasterStats: BroadcasterStats | null;
  lastWsUpdate: Date;
  lastRestUpdate: Date;
  wsMessageCount: number;
  restRequestCount: number;
  restFetchDuration: number;
  isWsConnected: boolean;
  statsLastUpdate?: Date;
  statsPollInterval?: number;
  statsPollDuration?: number;
}

export const LatencyMonitor = ({
  broadcasterStats,
  lastWsUpdate,
  lastRestUpdate,
  wsMessageCount,
  restRequestCount,
  restFetchDuration,
  isWsConnected,
  statsLastUpdate,
  statsPollInterval,
  statsPollDuration,
}: LatencyMonitorProps) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [wsIntervals, setWsIntervals] = useState<number[]>([]);
  const [restIntervals, setRestIntervals] = useState<number[]>([]);
  const [timeSinceWs, setTimeSinceWs] = useState(0);
  const [timeSinceRest, setTimeSinceRest] = useState(0);
  const [timeSinceStats, setTimeSinceStats] = useState(0);
  const lastWsRef = useRef<number>(lastWsUpdate.getTime());
  const lastRestRef = useRef<number>(lastRestUpdate.getTime());

  // Track WebSocket message intervals
  useEffect(() => {
    const now = lastWsUpdate.getTime();
    const diff = now - lastWsRef.current;
    if (diff > 0 && diff < 30000) {
      setWsIntervals(prev => [...prev.slice(-29), diff]);
    }
    lastWsRef.current = now;
  }, [lastWsUpdate]);

  // Track REST polling intervals
  useEffect(() => {
    const now = lastRestUpdate.getTime();
    const diff = now - lastRestRef.current;
    if (diff > 0 && diff < 30000) {
      setRestIntervals(prev => [...prev.slice(-29), diff]);
    }
    lastRestRef.current = now;
  }, [lastRestUpdate]);

  // Update timers every 100ms
  useEffect(() => {
    const interval = setInterval(() => {
      setTimeSinceWs(Date.now() - lastWsUpdate.getTime());
      setTimeSinceRest(Date.now() - lastRestUpdate.getTime());
      if (statsLastUpdate) {
        setTimeSinceStats(Date.now() - statsLastUpdate.getTime());
      }
    }, 100);
    return () => clearInterval(interval);
  }, [lastWsUpdate, lastRestUpdate, statsLastUpdate]);

  // Calculate stats
  const avgWsInterval = wsIntervals.length > 0 
    ? Math.round(wsIntervals.reduce((a, b) => a + b, 0) / wsIntervals.length) : 0;
  const minWsInterval = wsIntervals.length > 0 ? Math.min(...wsIntervals) : 0;
  const maxWsInterval = wsIntervals.length > 0 ? Math.max(...wsIntervals) : 0;

  const avgRestInterval = restIntervals.length > 0
    ? Math.round(restIntervals.reduce((a, b) => a + b, 0) / restIntervals.length) : 0;
  const minRestInterval = restIntervals.length > 0 ? Math.min(...restIntervals) : 0;
  const maxRestInterval = restIntervals.length > 0 ? Math.max(...restIntervals) : 0;

  const getStatus = (value: number, goodThreshold: number, warnThreshold: number): 'good' | 'warning' | 'bad' => {
    if (value <= goodThreshold) return 'good';
    if (value <= warnThreshold) return 'warning';
    return 'bad';
  };

  const getStatusColor = (status: 'good' | 'warning' | 'bad') => {
    switch (status) {
      case 'good': return 'text-green-400';
      case 'warning': return 'text-yellow-400';
      case 'bad': return 'text-red-400';
    }
  };

  const getStatusBg = (status: 'good' | 'warning' | 'bad') => {
    switch (status) {
      case 'good': return 'bg-green-500/20 border-green-500/30';
      case 'warning': return 'bg-yellow-500/20 border-yellow-500/30';
      case 'bad': return 'bg-red-500/20 border-red-500/30';
    }
  };

  // Backend data from broadcaster stats
  const accounts = broadcasterStats?.accounts || [];
  const activeAccounts = accounts.filter(a => a.positions_age_seconds < 100);
  const minPositionsAge = activeAccounts.length > 0 
    ? Math.min(...activeAccounts.map(a => a.positions_age_seconds)) : 0;
  const minBalanceAge = activeAccounts.length > 0 
    ? Math.min(...activeAccounts.filter(a => a.balance_age_seconds !== null).map(a => a.balance_age_seconds as number)) : 0;
  const backendRate = broadcasterStats?.broadcaster?.extended_api_rate || 'N/A';

  const MetricBox = ({ label, value, unit, status, icon }: { label: string; value: number | string; unit: string; status: 'good' | 'warning' | 'bad'; icon: React.ReactNode }) => (
    <div className={`p-3 rounded-lg border ${getStatusBg(status)} min-h-[80px]`}>
      <div className="flex items-center gap-1.5 mb-1">
        <span className={getStatusColor(status)}>{icon}</span>
        <span className="text-xs text-muted-foreground truncate">{label}</span>
      </div>
      <div className={`text-xl font-bold font-mono ${getStatusColor(status)}`}>
        {value}<span className="text-sm font-normal ml-1">{unit}</span>
      </div>
    </div>
  );

  const IntervalChart = ({ intervals, label, icon }: { intervals: number[]; label: string; icon: React.ReactNode }) => {
    const avg = intervals.length > 0 ? Math.round(intervals.reduce((a, b) => a + b, 0) / intervals.length) : 0;
    const min = intervals.length > 0 ? Math.min(...intervals) : 0;
    const max = intervals.length > 0 ? Math.max(...intervals) : 0;
    
    return (
      <div className="p-3 rounded-lg bg-background/50 border border-border/30">
        <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
          {icon}
          {label}
        </h4>
        <div className="grid grid-cols-3 gap-2 text-xs mb-2">
          <div>
            <span className="text-muted-foreground">Min:</span>
            <span className="ml-1 font-mono text-green-400">{min}ms</span>
          </div>
          <div>
            <span className="text-muted-foreground">Avg:</span>
            <span className="ml-1 font-mono text-yellow-400">{avg}ms</span>
          </div>
          <div>
            <span className="text-muted-foreground">Max:</span>
            <span className="ml-1 font-mono text-red-400">{max}ms</span>
          </div>
        </div>
        <div className="text-xs text-muted-foreground mb-2">
          Samples: {intervals.length}
        </div>
        <div className="flex gap-0.5 h-8 items-end">
          {intervals.slice(-30).map((interval, idx) => {
            const height = Math.min(100, (interval / 1000) * 100);
            const color = interval < 300 ? 'bg-green-500' : interval < 1000 ? 'bg-yellow-500' : 'bg-red-500';
            return (
              <div
                key={idx}
                className={`flex-1 ${color} rounded-t opacity-70`}
                style={{ height: `${Math.max(10, height)}%` }}
                title={`${interval}ms`}
              />
            );
          })}
          {/* Fill empty slots to prevent jumping */}
          {Array.from({ length: Math.max(0, 30 - intervals.length) }).map((_, idx) => (
            <div key={`empty-${idx}`} className="flex-1 bg-border/30 rounded-t" style={{ height: '10%' }} />
          ))}
        </div>
      </div>
    );
  };

  return (
    <Card className="bg-card/50 border-border/50">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Clock className="w-5 h-5 text-primary" />
            Latency & Timing Monitor
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={() => setIsExpanded(!isExpanded)} className="h-8 w-8 p-0">
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>
      </CardHeader>
      
      {isExpanded && (
        <CardContent className="space-y-4">
          {/* SECTION 1: Frontend Polling */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-primary flex items-center gap-2">
              <Globe className="w-4 h-4" />
              FRONTEND POLLING
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
              <MetricBox 
                label="WS Interval (avg)" 
                value={avgWsInterval} 
                unit="ms" 
                status={getStatus(avgWsInterval, 300, 1000)} 
                icon={<Zap className="w-4 h-4" />} 
              />
              <MetricBox 
                label="Time Since WS" 
                value={timeSinceWs} 
                unit="ms" 
                status={getStatus(timeSinceWs, 500, 2000)} 
                icon={<Zap className="w-4 h-4" />} 
              />
              <MetricBox 
                label="REST Interval (avg)" 
                value={avgRestInterval} 
                unit="ms" 
                status={getStatus(avgRestInterval, 300, 1000)} 
                icon={<Radio className="w-4 h-4" />} 
              />
              <MetricBox 
                label="REST Fetch Time" 
                value={restFetchDuration} 
                unit="ms" 
                status={getStatus(restFetchDuration, 200, 500)} 
                icon={<Radio className="w-4 h-4" />} 
              />
              <MetricBox 
                label="Time Since REST" 
                value={timeSinceRest} 
                unit="ms" 
                status={getStatus(timeSinceRest, 500, 2000)} 
                icon={<Radio className="w-4 h-4" />} 
              />
              <MetricBox 
                label="Stats Poll Interval" 
                value={statsPollInterval || 0} 
                unit="ms" 
                status={getStatus(statsPollInterval || 0, 2500, 5000)} 
                icon={<Database className="w-4 h-4" />} 
              />
              <MetricBox 
                label="Stats Fetch Time" 
                value={statsPollDuration || 0} 
                unit="ms" 
                status={getStatus(statsPollDuration || 0, 200, 500)} 
                icon={<Database className="w-4 h-4" />} 
              />
            </div>
          </div>

          {/* SECTION 2: Backend Polling */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-primary flex items-center gap-2">
              <Server className="w-4 h-4" />
              BACKEND POLLING (Broadcaster → Extended API)
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
              <MetricBox 
                label="API Poll Rate" 
                value={backendRate} 
                unit="" 
                status="good" 
                icon={<Server className="w-4 h-4" />} 
              />
              <MetricBox 
                label="Positions Age" 
                value={Math.round(minPositionsAge * 1000)} 
                unit="ms" 
                status={getStatus(minPositionsAge * 1000, 500, 1000)} 
                icon={<Activity className="w-4 h-4" />} 
              />
              <MetricBox 
                label="Balance Age" 
                value={Math.round(minBalanceAge * 1000)} 
                unit="ms" 
                status={getStatus(minBalanceAge * 1000, 500, 1000)} 
                icon={<Activity className="w-4 h-4" />} 
              />
              <MetricBox 
                label="Active Accounts" 
                value={activeAccounts.length} 
                unit={`/${accounts.length}`} 
                status={activeAccounts.length === accounts.length ? 'good' : 'warning'} 
                icon={<Database className="w-4 h-4" />} 
              />
              <MetricBox 
                label="Connected Clients" 
                value={broadcasterStats?.broadcaster?.connected_clients ?? 0} 
                unit="" 
                status="good" 
                icon={<Globe className="w-4 h-4" />} 
              />
            </div>
          </div>

          {/* SECTION 3: Interval Charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <IntervalChart 
              intervals={wsIntervals} 
              label="WebSocket Message Intervals" 
              icon={<Zap className="w-4 h-4 text-primary" />} 
            />
            <IntervalChart 
              intervals={restIntervals} 
              label="REST Polling Intervals" 
              icon={<Radio className="w-4 h-4 text-primary" />} 
            />
          </div>

          {/* SECTION 4: Connection Status Footer */}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground border-t border-border/30 pt-3">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <div className={`w-2 h-2 rounded-full ${isWsConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                WS: {isWsConnected ? 'Connected' : 'Disconnected'}
              </span>
              <span>WS msgs: <span className="font-mono text-primary">{wsMessageCount}</span></span>
              <span>REST reqs: <span className="font-mono text-primary">{restRequestCount}</span></span>
            </div>
            <div className="font-mono flex flex-wrap items-center gap-3">
              <span>WS: {lastWsUpdate.toLocaleTimeString('pl-PL')}</span>
              <span>REST: {lastRestUpdate.toLocaleTimeString('pl-PL')}</span>
              {statsLastUpdate && <span>Stats: {statsLastUpdate.toLocaleTimeString('pl-PL')}</span>}
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
};
