import { useState, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  Users, 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  Eye,
  EyeOff,
  ChevronDown,
  ChevronRight,
  Wallet,
  Star,
  RefreshCw
} from 'lucide-react';
import { SingleAccountData, AggregatedPortfolio } from '@/types/multiAccount';
import { AccountCardCompact } from './AccountCardCompact';
import { useEarnedPoints } from '@/hooks/useEarnedPoints';

interface MultiAccountDashboardProps {
  accounts: SingleAccountData[];
  portfolio: AggregatedPortfolio;
  isConnected: boolean;
  onAccountSelect?: (accountId: string) => void;
  selectedAccountId?: string | null;
}

interface ExchangeGroup {
  key: string;
  label: string;
  color: string;
  borderColor: string;
  accounts: SingleAccountData[];
  activeAccounts: SingleAccountData[];
}

function getExchangeKey(account: SingleAccountData): string {
  if (account.id.startsWith('reya_')) return 'reya';
  if (account.id.startsWith('pacifica_')) return 'pacifica';
  if (account.id.startsWith('hyperliquid_')) return 'hyperliquid';
  return 'extended';
}

const EXCHANGE_META: Record<string, { label: string; color: string; borderColor: string }> = {
  extended: { label: 'Extended Exchange', color: 'text-blue-400', borderColor: 'border-blue-500/50' },
  reya: { label: 'Reya Network', color: 'text-purple-400', borderColor: 'border-purple-500/50' },
  pacifica: { label: 'Pacifica', color: 'text-teal-400', borderColor: 'border-teal-500/50' },
  hyperliquid: { label: 'Hyperliquid', color: 'text-orange-400', borderColor: 'border-orange-500/50' },
};

function fmt$(v: number, decimals = 0): string {
  return '$' + v.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPnl(v: number): string {
  const prefix = v >= 0 ? '+' : '';
  return prefix + '$' + v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ExchangeSummaryRow({ group, pointsData, expandedExchanges, toggleExchange, showInactive, onAccountSelect, selectedAccountId }: {
  group: ExchangeGroup;
  pointsData: any;
  expandedExchanges: Set<string>;
  toggleExchange: (key: string) => void;
  showInactive: boolean;
  onAccountSelect?: (id: string) => void;
  selectedAccountId?: string | null;
}) {
  const isExpanded = expandedExchanges.has(group.key);
  const displayed = showInactive ? group.accounts : group.activeAccounts;
  const meta = EXCHANGE_META[group.key] || { label: group.key, color: 'text-gray-400', borderColor: 'border-gray-500/50' };

  const stats = useMemo(() => {
    const active = group.activeAccounts;
    let equity = 0, pnl = 0, notional = 0, positions = 0, longs = 0, shorts = 0, marginSum = 0;
    for (const a of active) {
      equity += a.computed.equity;
      pnl += a.computed.totalPnl;
      notional += a.computed.totalNotional;
      positions += a.computed.positionCount;
      longs += a.computed.longPositions;
      shorts += a.computed.shortPositions;
      marginSum += a.computed.marginRatio;
    }
    const avgMargin = active.length > 0 ? marginSum / active.length : 0;
    const leverage = equity > 0 ? notional / equity : 0;
    return { equity, pnl, notional, positions, longs, shorts, avgMargin, leverage };
  }, [group.activeAccounts]);

  return (
    <div>
      <div
        className={`flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/30 border border-border/40 cursor-pointer hover:bg-muted/50 transition-colors`}
        onClick={() => toggleExchange(group.key)}
      >
        {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />}
        
        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${meta.borderColor} ${meta.color} flex-shrink-0`}>
          {meta.label}
        </Badge>
        <span className="text-[11px] text-muted-foreground flex-shrink-0">{group.activeAccounts.length} acc</span>

        <div className="flex items-center gap-3 ml-auto text-xs font-mono flex-shrink-0">
          <span className="text-muted-foreground">
            <Wallet className="w-3 h-3 inline mr-0.5" />{fmt$(stats.equity, 2)}
          </span>
          <span className={stats.pnl >= 0 ? 'text-success' : 'text-danger'}>
            {stats.pnl >= 0 ? <TrendingUp className="w-3 h-3 inline mr-0.5" /> : <TrendingDown className="w-3 h-3 inline mr-0.5" />}
            {fmtPnl(stats.pnl)}
          </span>
          <span className="text-muted-foreground hidden sm:inline">Not: {fmt$(stats.notional)}</span>
          <span className="text-muted-foreground">
            {stats.positions}pos
            {stats.positions > 0 && (
              <span className="ml-1">
                <span className="text-success">{stats.longs}L</span>/<span className="text-danger">{stats.shorts}S</span>
              </span>
            )}
          </span>
          {stats.avgMargin > 0 && (
            <span className={`hidden md:inline ${stats.avgMargin > 50 ? 'text-danger' : stats.avgMargin > 30 ? 'text-warning' : 'text-muted-foreground'}`}>
              M:{stats.avgMargin.toFixed(1)}%
            </span>
          )}
          {stats.leverage > 0 && (
            <span className="text-primary hidden md:inline">{stats.leverage.toFixed(1)}x</span>
          )}
        </div>
      </div>

      {isExpanded && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-3 mt-2 ml-2">
          {displayed.length === 0 ? (
            <div className="col-span-full text-center text-sm text-muted-foreground py-4">
              <Activity className="w-6 h-6 mx-auto mb-1 opacity-50" />
              Waiting for accounts...
            </div>
          ) : (
            displayed.map(account => (
              <AccountCardCompact
                key={account.id}
                account={account}
                isSelected={selectedAccountId === account.id}
                onClick={() => onAccountSelect?.(account.id)}
                accountPoints={pointsData?.accounts?.[account.id]?.points ?? null}
                accountLastWeekPoints={pointsData?.accounts?.[account.id]?.last_week_points ?? null}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

export const MultiAccountDashboard = ({
  accounts,
  portfolio,
  isConnected,
  onAccountSelect,
  selectedAccountId,
}: MultiAccountDashboardProps) => {
  const [showInactive, setShowInactive] = useState(false);
  const [expandedExchanges, setExpandedExchanges] = useState<Set<string>>(new Set());
  
  const { points: pointsData, totalPoints, totalLastWeekPoints, isLoading: pointsLoading, refresh: refreshPoints, lastUpdate: pointsLastUpdate, error: pointsError } = useEarnedPoints();

  const exchangeGroups = useMemo(() => {
    const groupMap = new Map<string, SingleAccountData[]>();
    for (const acc of accounts) {
      const key = getExchangeKey(acc);
      if (!groupMap.has(key)) groupMap.set(key, []);
      groupMap.get(key)!.push(acc);
    }
    const groups: ExchangeGroup[] = [];
    const order = ['extended', 'reya', 'pacifica', 'hyperliquid'];
    for (const key of order) {
      if (groupMap.has(key)) {
        const accs = groupMap.get(key)!;
        const meta = EXCHANGE_META[key] || { label: key, color: 'text-gray-400', borderColor: 'border-gray-500/50' };
        groups.push({
          key,
          label: meta.label,
          color: meta.color,
          borderColor: meta.borderColor,
          accounts: accs,
          activeAccounts: accs.filter(a => a.isActive),
        });
      }
    }
    for (const [key, accs] of groupMap) {
      if (!order.includes(key)) {
        const meta = EXCHANGE_META[key] || { label: key, color: 'text-gray-400', borderColor: 'border-gray-500/50' };
        groups.push({
          key,
          label: meta.label,
          color: meta.color,
          borderColor: meta.borderColor,
          accounts: accs,
          activeAccounts: accs.filter(a => a.isActive),
        });
      }
    }
    return groups;
  }, [accounts]);

  const toggleExchange = (key: string) => {
    setExpandedExchanges(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const inactiveCount = accounts.filter(a => !a.isActive).length;

  return (
    <div className="space-y-3">
      {/* Combined Portfolio Summary - Compact */}
      <Card className="border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 px-4 py-3">
        <div className="flex items-center flex-wrap gap-x-4 gap-y-2">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-primary" />
            <span className="text-sm font-bold text-foreground">Portfolio</span>
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {portfolio.accountCount} Active
            </Badge>
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-success animate-pulse' : 'bg-destructive'}`} />
          </div>

          <div className="flex items-center gap-4 text-sm font-mono ml-auto flex-wrap">
            <div>
              <span className="text-[10px] text-muted-foreground mr-1">Equity</span>
              <span className="font-bold text-foreground">
                {fmt$(portfolio.totalEquity, 2)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-muted-foreground mr-1">PnL</span>
              <span className={`font-bold ${portfolio.totalPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                {fmtPnl(portfolio.totalPnl)}
              </span>
            </div>
            <div className="hidden sm:block">
              <span className="text-[10px] text-muted-foreground mr-1">Notional</span>
              <span className="font-bold text-foreground">{fmt$(portfolio.totalNotional)}</span>
            </div>
            <div>
              <span className="text-[10px] text-muted-foreground mr-1">Pos</span>
              <span className="font-bold text-foreground">{portfolio.totalPositions}</span>
              <span className="ml-1 text-xs">
                <span className="text-success">{portfolio.totalLongPositions}L</span>
                /
                <span className="text-danger">{portfolio.totalShortPositions}S</span>
              </span>
            </div>
            <div className="hidden md:block">
              <span className="text-[10px] text-muted-foreground mr-1">Lev</span>
              <span className="font-bold text-primary">
                {(portfolio.totalNotional / (portfolio.totalEquity || 1)).toFixed(2)}x
              </span>
            </div>

            {/* Points */}
            <div className={`flex items-center gap-1.5 pl-2 border-l ${pointsError ? 'border-border/30' : 'border-yellow-500/30'}`}>
              <Star className={`w-3.5 h-3.5 ${pointsError ? 'text-muted-foreground' : 'text-yellow-500'}`} />
              {pointsError || (totalPoints === 0 && !pointsLastUpdate) ? (
                <span className="text-xs text-muted-foreground">N/A</span>
              ) : (
                <>
                  <span className="font-bold text-yellow-500 text-sm">
                    {totalPoints.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                  <span className="text-[10px] text-yellow-400/70">
                    +{totalLastWeekPoints.toLocaleString(undefined, { maximumFractionDigits: 0 })}/w
                  </span>
                </>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => { e.stopPropagation(); refreshPoints(); }}
                disabled={pointsLoading}
                className="h-5 w-5 p-0 ml-0.5"
                title="Odśwież punkty"
              >
                <RefreshCw className={`w-2.5 h-2.5 ${pointsLoading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {/* Per-Exchange Rows */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between px-1">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Exchanges</span>
          {inactiveCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowInactive(!showInactive)}
              className="h-6 text-[10px] gap-1 px-2"
            >
              {showInactive ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
              {showInactive ? 'Hide' : 'Show'} Inactive ({inactiveCount})
            </Button>
          )}
        </div>

        {exchangeGroups.map(group => (
          <ExchangeSummaryRow
            key={group.key}
            group={group}
            pointsData={pointsData}
            expandedExchanges={expandedExchanges}
            toggleExchange={toggleExchange}
            showInactive={showInactive}
            onAccountSelect={onAccountSelect}
            selectedAccountId={selectedAccountId}
          />
        ))}
      </div>
    </div>
  );
};
