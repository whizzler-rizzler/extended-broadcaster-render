import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  X, 
  TrendingUp, 
  TrendingDown,
  Wallet,
  Activity,
  Clock,
  Target,
  BarChart3
} from 'lucide-react';
import { SingleAccountData } from '@/types/multiAccount';
import { cn } from '@/lib/utils';
import { useMemo } from 'react';

interface AccountDetailPanelProps {
  account: SingleAccountData;
  onClose: () => void;
}

export const AccountDetailPanel = ({ account, onClose }: AccountDetailPanelProps) => {
  const { computed, balance, positions, orders, trades, name, id, lastUpdate } = account;

  const formatPrice = (price: number) => {
    return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  // Calculate performance metrics from trades
  const performanceMetrics = useMemo(() => {
    const now = Date.now();
    const oneDay = 24 * 60 * 60 * 1000;
    const sevenDays = 7 * oneDay;
    const thirtyDays = 30 * oneDay;

    const calculatePnLForPeriod = (periodMs: number | null) => {
      const filteredTrades = periodMs 
        ? trades.filter(t => (now - t.createdTime) <= periodMs)
        : trades;
      
      let totalPnL = 0;
      let wins = 0;
      let losses = 0;

      filteredTrades.forEach(trade => {
        // Calculate PnL from trade value and fee
        const value = Number(trade.value) || 0;
        const fee = Number(trade.fee) || 0;
        const tradePnL = trade.side === 'SELL' ? value - fee : -(value + fee);
        
        // For realized PnL, we need to look at closed positions
        // Using fee as proxy for realized - positive trades are wins
        if (value > 0) {
          if (trade.side === 'SELL') {
            wins++;
            totalPnL += value - fee;
          } else {
            losses++;
            totalPnL -= (value + fee);
          }
        }
      });

      const totalTrades = wins + losses;
      const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;

      return { pnl: totalPnL, wins, losses, winRate, totalTrades };
    };

    return {
      day1: calculatePnLForPeriod(oneDay),
      day7: calculatePnLForPeriod(sevenDays),
      day30: calculatePnLForPeriod(thirtyDays),
      total: calculatePnLForPeriod(null),
    };
  }, [trades]);

  return (
    <Card className="border-primary/30">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              {name}
              <Badge variant="outline" className="text-xs font-mono">{id}</Badge>
            </CardTitle>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Last update: {lastUpdate.toLocaleTimeString('pl-PL')}
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Balance Overview */}
        {balance && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground flex items-center gap-1">
                <Wallet className="w-3 h-3" />
                Balance
              </div>
              <div className="text-lg font-bold font-mono">
                ${formatPrice(parseFloat(balance.balance || '0'))}
              </div>
            </div>
            
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Equity</div>
              <div className="text-lg font-bold font-mono">
                ${formatPrice(computed.equity)}
              </div>
            </div>
            
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Available</div>
              <div className="text-lg font-bold font-mono text-success">
                ${formatPrice(parseFloat(balance.availableForTrade || '0'))}
              </div>
            </div>
            
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Margin Ratio</div>
              <div className={cn(
                'text-lg font-bold font-mono',
                computed.marginRatio > 50 ? 'text-danger' : computed.marginRatio > 30 ? 'text-warning' : 'text-success'
              )}>
                {computed.marginRatio.toFixed(2)}%
              </div>
            </div>
          </div>
        )}

        {/* PnL Summary */}
        <div className="grid grid-cols-3 gap-4 p-4 rounded-lg bg-muted/30">
          <div className="text-center">
            <div className="text-xs text-muted-foreground mb-1">Total PnL</div>
            <div className={cn(
              'text-xl font-bold font-mono flex items-center justify-center gap-1',
              computed.totalPnl >= 0 ? 'text-success' : 'text-danger'
            )}>
              {computed.totalPnl >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
              ${formatPrice(Math.abs(computed.totalPnl))}
            </div>
          </div>
          
          <div className="text-center">
            <div className="text-xs text-muted-foreground mb-1">Long PnL</div>
            <div className={cn(
              'text-lg font-bold font-mono',
              computed.longPnl >= 0 ? 'text-success' : 'text-danger'
            )}>
              {computed.longPnl >= 0 ? '+' : ''}{formatPrice(computed.longPnl)}
            </div>
            <div className="text-xs text-muted-foreground">{computed.longPositions} positions</div>
          </div>
          
          <div className="text-center">
            <div className="text-xs text-muted-foreground mb-1">Short PnL</div>
            <div className={cn(
              'text-lg font-bold font-mono',
              computed.shortPnl >= 0 ? 'text-success' : 'text-danger'
            )}>
              {computed.shortPnl >= 0 ? '+' : ''}{formatPrice(computed.shortPnl)}
            </div>
            <div className="text-xs text-muted-foreground">{computed.shortPositions} positions</div>
          </div>
        </div>

        {/* Performance Metrics */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-primary" />
            Performance
          </h4>
          
          <div className="grid grid-cols-4 gap-3">
            <div className="p-3 rounded-lg bg-background/50 border border-border/30 text-center">
              <div className="text-xs text-muted-foreground mb-1">1 Day</div>
              <div className={cn(
                'text-sm font-bold font-mono',
                performanceMetrics.day1.pnl >= 0 ? 'text-success' : 'text-danger'
              )}>
                {performanceMetrics.day1.pnl >= 0 ? '+' : ''}${formatPrice(performanceMetrics.day1.pnl)}
              </div>
              <div className="text-xs text-muted-foreground">{performanceMetrics.day1.totalTrades} trades</div>
            </div>
            
            <div className="p-3 rounded-lg bg-background/50 border border-border/30 text-center">
              <div className="text-xs text-muted-foreground mb-1">7 Days</div>
              <div className={cn(
                'text-sm font-bold font-mono',
                performanceMetrics.day7.pnl >= 0 ? 'text-success' : 'text-danger'
              )}>
                {performanceMetrics.day7.pnl >= 0 ? '+' : ''}${formatPrice(performanceMetrics.day7.pnl)}
              </div>
              <div className="text-xs text-muted-foreground">{performanceMetrics.day7.totalTrades} trades</div>
            </div>
            
            <div className="p-3 rounded-lg bg-background/50 border border-border/30 text-center">
              <div className="text-xs text-muted-foreground mb-1">30 Days</div>
              <div className={cn(
                'text-sm font-bold font-mono',
                performanceMetrics.day30.pnl >= 0 ? 'text-success' : 'text-danger'
              )}>
                {performanceMetrics.day30.pnl >= 0 ? '+' : ''}${formatPrice(performanceMetrics.day30.pnl)}
              </div>
              <div className="text-xs text-muted-foreground">{performanceMetrics.day30.totalTrades} trades</div>
            </div>
            
            <div className="p-3 rounded-lg bg-background/50 border border-border/30 text-center">
              <div className="text-xs text-muted-foreground mb-1">Total</div>
              <div className={cn(
                'text-sm font-bold font-mono',
                performanceMetrics.total.pnl >= 0 ? 'text-success' : 'text-danger'
              )}>
                {performanceMetrics.total.pnl >= 0 ? '+' : ''}${formatPrice(performanceMetrics.total.pnl)}
              </div>
              <div className="text-xs text-muted-foreground">{performanceMetrics.total.totalTrades} trades</div>
            </div>
          </div>
          
          {/* Win Rate */}
          <div className="p-3 rounded-lg bg-muted/30 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4 text-primary" />
              <span className="text-sm font-medium">Win Rate (Total)</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-xs text-muted-foreground">
                <span className="text-success">{performanceMetrics.total.wins}W</span>
                {' / '}
                <span className="text-danger">{performanceMetrics.total.losses}L</span>
              </div>
              <div className={cn(
                'text-lg font-bold font-mono',
                performanceMetrics.total.winRate >= 50 ? 'text-success' : 'text-danger'
              )}>
                {performanceMetrics.total.winRate.toFixed(1)}%
              </div>
            </div>
          </div>
        </div>

        {/* Active Positions */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            Active Positions ({positions.length})
          </h4>
          
          {positions.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No active positions
            </p>
          ) : (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {positions.map((pos, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg bg-background/50 border border-border/30 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-bold">{pos.market}</span>
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-xs',
                          pos.side === 'LONG' ? 'border-success text-success' : 'border-danger text-danger'
                        )}
                      >
                        {pos.side}
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        {pos.leverage}x
                      </Badge>
                    </div>
                    {(() => {
                      const pnl = Number((pos as any).midPriceUnrealisedPnl) || Number(pos.unrealisedPnl) || 0;
                      return (
                        <div className={cn(
                          'font-bold font-mono',
                          pnl >= 0 ? 'text-success' : 'text-danger'
                        )}>
                          {pnl >= 0 ? '+' : ''}${formatPrice(pnl)}
                        </div>
                      );
                    })()}
                  </div>
                  
                  <div className="grid grid-cols-4 gap-2 text-xs">
                    <div>
                      <div className="text-muted-foreground">Size</div>
                      <div className="font-mono font-semibold">{pos.size}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Entry</div>
                      <div className="font-mono font-semibold">${formatPrice(pos.openPrice)}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Mark</div>
                      <div className="font-mono font-semibold">${formatPrice(pos.markPrice)}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Liq.</div>
                      <div className="font-mono font-semibold text-danger">${formatPrice(pos.liquidationPrice)}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Orders Preview */}
        {orders.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Open Orders ({orders.length})</h4>
            <div className="text-xs text-muted-foreground">
              {orders.slice(0, 3).map((order, idx) => (
                <div key={idx} className="flex justify-between py-1">
                  <span>{order.market} {order.side}</span>
                  <span className="font-mono">${order.price} x {order.size}</span>
                </div>
              ))}
              {orders.length > 3 && (
                <div className="text-center">+{orders.length - 3} more orders</div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
