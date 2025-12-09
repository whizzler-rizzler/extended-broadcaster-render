import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle
} from 'lucide-react';
import { SingleAccountData } from '@/types/multiAccount';
import { cn } from '@/lib/utils';

interface AccountCardCompactProps {
  account: SingleAccountData;
  isSelected?: boolean;
  onClick?: () => void;
}

export const AccountCardCompact = ({
  account,
  isSelected,
  onClick,
}: AccountCardCompactProps) => {
  const { computed, balance, isActive, name, id, positions, lastUpdate } = account;
  const pnl = Number(computed.totalPnl) || 0;
  const equity = Number(computed.equity) || 0;
  const marginRatio = Number(computed.marginRatio) || 0;
  const positionCount = computed.positionCount;

  // Status indicators
  const isHealthy = marginRatio < 30;
  const isWarning = marginRatio >= 30 && marginRatio < 50;
  const isDanger = marginRatio >= 50;

  // Time since last update
  const timeSinceUpdate = Math.floor((Date.now() - lastUpdate.getTime()) / 1000);
  const isStale = timeSinceUpdate > 30;

  return (
    <Card
      className={cn(
        'p-4 cursor-pointer transition-all duration-200 hover:shadow-lg',
        'border-border/50 hover:border-primary/40',
        isSelected && 'ring-2 ring-primary border-primary',
        !isActive && 'opacity-50',
        isDanger && 'border-danger/50 bg-danger/5',
        isWarning && 'border-warning/50 bg-warning/5'
      )}
      onClick={onClick}
    >
      <div className="space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-base truncate">{name}</h3>
              {isActive ? (
                <CheckCircle2 className="w-4 h-4 text-success flex-shrink-0" />
              ) : (
                <XCircle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              )}
            </div>
            <p className="text-[10px] text-muted-foreground/70 font-mono" title={id}>
              {id.startsWith('0x') ? `${id.slice(0, 6)}...${id.slice(-4)}` : id}
            </p>
          </div>
          
          {/* Status Badge */}
          <Badge
            variant="outline"
            className={cn(
              'text-[10px] px-1.5',
              isHealthy && 'border-success/50 text-success',
              isWarning && 'border-warning/50 text-warning',
              isDanger && 'border-danger/50 text-danger'
            )}
          >
            {isDanger && <AlertTriangle className="w-3 h-3 mr-1" />}
            {marginRatio.toFixed(1)}%
          </Badge>
        </div>

        {/* Main Stats */}
        <div className="grid grid-cols-3 gap-3">
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Equity</div>
            <div className="text-lg font-bold font-mono">
              ${equity.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </div>
          </div>
          
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Volume 24h</div>
            <div className="text-lg font-bold font-mono">
              ${computed.volume24h.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </div>
            <div className="text-[9px] text-muted-foreground">
              7d: ${computed.volume7d.toLocaleString(undefined, { notation: 'compact' })} | 30d: ${computed.volume30d.toLocaleString(undefined, { notation: 'compact' })}
            </div>
          </div>
          
          <div>
            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">PnL</div>
            <div className={cn(
              'text-lg font-bold font-mono flex items-center gap-1',
              pnl >= 0 ? 'text-success' : 'text-danger'
            )}>
              {pnl >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
            </div>
          </div>
        </div>

        {/* Secondary Stats */}
        <div className="flex items-center justify-between text-xs border-t border-border/50 pt-2">
          <div className="flex items-center gap-3">
            <div>
              <span className="text-muted-foreground">Positions: </span>
              <span className="font-mono font-semibold">{positionCount}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-success font-mono">{computed.longPositions}L</span>
              <span className="text-muted-foreground">/</span>
              <span className="text-danger font-mono">{computed.shortPositions}S</span>
            </div>
          </div>
          
          <div className="flex items-center gap-1">
            <Activity className={cn(
              'w-3 h-3',
              isStale ? 'text-warning' : 'text-success'
            )} />
            <span className={cn(
              'text-[10px]',
              isStale ? 'text-warning' : 'text-muted-foreground'
            )}>
              {isStale ? `${timeSinceUpdate}s ago` : 'Live'}
            </span>
          </div>
        </div>

        {/* Position Preview (if any) */}
        {positions.length > 0 && (
          <div className="space-y-1 border-t border-border/50 pt-2">
              {positions.slice(0, 2).map((pos, idx) => {
                // Use midPriceUnrealisedPnl if available, fallback to unrealisedPnl
                const pnl = Number((pos as any).midPriceUnrealisedPnl) || Number(pos.unrealisedPnl) || 0;
                return (
                  <div key={idx} className="flex items-center justify-between text-[10px]">
                    <div className="flex items-center gap-1">
                      <span className={cn(
                        'px-1 rounded font-semibold',
                        pos.side === 'LONG' ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'
                      )}>
                        {pos.side.charAt(0)}
                      </span>
                      <span className="font-mono">{pos.market}</span>
                    </div>
                    <span className={cn(
                      'font-mono',
                      pnl >= 0 ? 'text-success' : 'text-danger'
                    )}>
                      {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
                    </span>
                  </div>
                );
              })}
            {positions.length > 2 && (
              <div className="text-[10px] text-muted-foreground text-center">
                +{positions.length - 2} more positions
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
};
