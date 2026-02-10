import { useState } from 'react';
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
  ChevronUp,
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

export const MultiAccountDashboard = ({
  accounts,
  portfolio,
  isConnected,
  onAccountSelect,
  selectedAccountId,
}: MultiAccountDashboardProps) => {
  const [showInactive, setShowInactive] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);
  
  const { points: pointsData, totalPoints, totalLastWeekPoints, isLoading: pointsLoading, refresh: refreshPoints, lastUpdate: pointsLastUpdate, error: pointsError } = useEarnedPoints();

  const activeAccounts = accounts.filter(a => a.isActive);
  const inactiveAccounts = accounts.filter(a => !a.isActive);
  const displayedAccounts = showInactive ? accounts : activeAccounts;

  return (
    <div className="space-y-4">
      {/* Aggregated Portfolio Summary - Two-level with boxes */}
      <Card className="border-primary/30 bg-gradient-to-br from-primary/5 to-primary/10 p-5">
        {/* Top Row: Title + Live status */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Users className="w-6 h-6 text-primary" />
            <span className="text-lg font-bold text-foreground">Multi-Account Portfolio</span>
            <Badge variant="outline" className="text-sm px-3 py-1">
              {portfolio.accountCount} Active
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-success animate-pulse' : 'bg-destructive'}`} />
            <span className="text-sm font-medium text-muted-foreground">
              {isConnected ? 'Live' : 'Offline'}
            </span>
          </div>
        </div>

        {/* Stats Grid - Two rows */}
        <div className="space-y-3">
          {/* Row 1: Main financial stats */}
          <div className="grid grid-cols-4 gap-3">
            {/* Total Equity */}
            <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
              <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                <Wallet className="w-4 h-4 text-primary" />
                Total Equity
              </div>
              <div className="text-2xl font-bold font-mono text-foreground">
                ${portfolio.totalEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>

            {/* Total PnL */}
            <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
              <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                {portfolio.totalPnl >= 0 ? <TrendingUp className="w-4 h-4 text-success" /> : <TrendingDown className="w-4 h-4 text-danger" />}
                Total PnL
              </div>
              <div className={`text-2xl font-bold font-mono ${portfolio.totalPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                {portfolio.totalPnl >= 0 ? '+' : ''}${portfolio.totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>

            {/* Total Notional */}
            <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
              <div className="text-sm text-muted-foreground mb-2">Total Notional</div>
              <div className="text-2xl font-bold font-mono text-foreground">
                ${portfolio.totalNotional.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>

            {/* Volume */}
            <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
              <div className="text-sm text-muted-foreground mb-2">Volume 24h</div>
              <div className="text-2xl font-bold font-mono text-foreground">
                ${portfolio.totalVolume24h.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                7d: ${portfolio.totalVolume7d.toLocaleString(undefined, { notation: 'compact' })} | 30d: ${portfolio.totalVolume30d.toLocaleString(undefined, { notation: 'compact' })}
              </div>
            </div>
          </div>

          {/* Row 2: Position & risk stats + Points */}
          <div className="grid grid-cols-5 gap-3">
            {/* Positions */}
            <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
              <div className="text-sm text-muted-foreground mb-2">Positions</div>
              <div className="text-2xl font-bold font-mono text-foreground">
                {portfolio.totalPositions}
              </div>
            </div>

            {/* Long / Short */}
            <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
              <div className="text-sm text-muted-foreground mb-2">Long / Short</div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold text-success">{portfolio.totalLongPositions}L</span>
                <span className="text-lg text-muted-foreground">/</span>
                <span className="text-2xl font-bold text-danger">{portfolio.totalShortPositions}S</span>
              </div>
            </div>

            {/* Avg Margin */}
            <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
              <div className="text-sm text-muted-foreground mb-2">Avg Margin Ratio</div>
              <div className={`text-2xl font-bold font-mono ${portfolio.averageMarginRatio > 50 ? 'text-danger' : portfolio.averageMarginRatio > 30 ? 'text-warning' : 'text-success'}`}>
                {portfolio.averageMarginRatio.toFixed(2)}%
              </div>
            </div>

            {/* Leverage & Balance */}
            <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
              <div className="text-sm text-muted-foreground mb-2">Leverage & Balance</div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold font-mono text-primary">
                  {(portfolio.totalNotional / (portfolio.totalEquity || 1)).toFixed(2)}x
                </span>
                <span className="text-sm text-muted-foreground">
                  / ${(portfolio.totalEquity * 0.15).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              </div>
            </div>

            {/* Earned Points */}
            <div className={`rounded-lg p-4 border ${pointsError ? 'bg-muted/40 border-border/50' : 'bg-gradient-to-br from-yellow-500/10 to-orange-500/10 border-yellow-500/30'}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Star className={`w-4 h-4 ${pointsError ? 'text-muted-foreground' : 'text-yellow-500'}`} />
                  Punkty
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => refreshPoints()}
                  disabled={pointsLoading}
                  className="h-6 w-6 p-0"
                  title="Odśwież punkty"
                >
                  <RefreshCw className={`w-3 h-3 ${pointsLoading ? 'animate-spin' : ''}`} />
                </Button>
              </div>
              {pointsError || (totalPoints === 0 && !pointsLastUpdate) ? (
                <div className="text-sm text-muted-foreground">
                  Niedostępne
                  <div className="text-xs mt-1">API Extended w budowie</div>
                </div>
              ) : (
                <>
                  <div className="flex items-baseline gap-2">
                    <div>
                      <div className="text-[10px] text-muted-foreground uppercase">Total</div>
                      <div className="text-2xl font-bold font-mono text-yellow-500">
                        {totalPoints.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                    </div>
                    <div className="border-l border-border/50 pl-2">
                      <div className="text-[10px] text-muted-foreground uppercase">Last Week</div>
                      <div className="text-lg font-bold font-mono text-yellow-400">
                        {totalLastWeekPoints.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                      </div>
                    </div>
                  </div>
                  {pointsLastUpdate && (
                    <div className="text-xs text-muted-foreground mt-1">
                      {pointsLastUpdate.toLocaleTimeString('pl-PL')}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Account Cards Grid */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="gap-1 px-2"
            >
              {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              <span className="text-sm font-medium">
                Accounts ({activeAccounts.length} active)
              </span>
            </Button>
          </div>
          
          {inactiveAccounts.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowInactive(!showInactive)}
              className="gap-2"
            >
              {showInactive ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              {showInactive ? 'Hide' : 'Show'} Inactive ({inactiveAccounts.length})
            </Button>
          )}
        </div>

        {isExpanded && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
            {displayedAccounts.length === 0 ? (
              <Card className="col-span-full p-8 text-center">
                <Activity className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                <p className="text-muted-foreground">
                  Waiting for accounts to connect...
                </p>
                <p className="text-xs text-muted-foreground mt-2">
                  Accounts will appear automatically when detected
                </p>
              </Card>
            ) : (
              displayedAccounts.map(account => (
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
    </div>
  );
};
