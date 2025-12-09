import { Card } from "@/components/ui/card";
import { FileText, TrendingUp, TrendingDown } from "lucide-react";

interface AccountData {
  name: string;
  address: string;
  balance: number;
  pnl: number;
  notional: number;
  positions: number;
  vol24h: number;
  vol7d: number;
  volTotal: number;
  ath: number;
  atl: number;
  positionDetails: Array<{
    market: string;
    side: string;
    leverage: string;
    size: string;
    openPrice: number;
    markPrice: number;
    liquidationPrice: number;
    unrealisedPnl: number;
    realisedPnl: number;
    margin: number;
    createdAt: number;
    updatedAt: number;
  }>;
}

interface AccountCardProps {
  account: AccountData;
}

export const AccountCard = ({ account }: AccountCardProps) => {
  return (
    <Card className="p-6 border-primary/20 bg-card/50 backdrop-blur-sm hover:border-primary/40 transition-colors">
      <div className="space-y-4">
        <div className="flex items-start gap-3">
          <FileText className="w-5 h-5 text-primary mt-1" />
          <div className="flex-1">
            <h3 className="font-mono text-sm text-foreground break-all">
              {account.name}
            </h3>
            <p className="text-xs text-muted-foreground">({account.address})</p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-xs text-muted-foreground mb-1">Balance:</div>
            <div className="text-lg font-mono font-bold text-foreground">
              ${account.balance.toFixed(2)}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted-foreground mb-1">PnL:</div>
            <div className={`text-lg font-mono font-bold ${account.pnl >= 0 ? 'text-success' : 'text-danger'}`}>
              {account.pnl >= 0 ? '+' : ''}${account.pnl.toFixed(2)}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted-foreground mb-1">Notional:</div>
            <div className="text-lg font-mono font-bold text-foreground">
              ${account.notional.toFixed(2)}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted-foreground mb-1">Pozycje:</div>
            <div className="text-lg font-mono font-bold text-foreground">
              {account.positions}
            </div>
          </div>
        </div>

        {account.positionDetails && account.positionDetails.length > 0 && (
          <div className="space-y-3 pt-4 border-t border-border/50">
            <div className="text-xs font-semibold text-primary uppercase tracking-wider">
              Active Positions
            </div>
            {account.positionDetails.map((pos, idx) => (
              <div key={idx} className="p-3 rounded-lg bg-background/50 border border-border/30 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-foreground">{pos.market}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                      pos.side === 'LONG' 
                        ? 'bg-success/20 text-success' 
                        : 'bg-danger/20 text-danger'
                    }`}>
                      {pos.side}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary font-semibold">
                      {pos.leverage}x
                    </span>
                  </div>
                  {(() => {
                    const pnl = Number((pos as any).midPriceUnrealisedPnl) || Number(pos.unrealisedPnl) || 0;
                    return (
                      <div className={`text-sm font-bold ${pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                        {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                      </div>
                    );
                  })()}
                </div>
                
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  <div>
                    <div className="text-muted-foreground">Size:</div>
                    <div className="font-mono font-semibold text-foreground">{pos.size}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Entry:</div>
                    <div className="font-mono font-semibold text-foreground">${pos.openPrice.toLocaleString()}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Mark:</div>
                    <div className="font-mono font-semibold text-foreground">${pos.markPrice.toLocaleString()}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Liquidation:</div>
                    <div className="font-mono font-semibold text-danger">${pos.liquidationPrice.toLocaleString()}</div>
                  </div>
                </div>
                
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs pt-2 border-t border-border/20">
                  <div>
                    <div className="text-muted-foreground">Margin:</div>
                    <div className="font-mono font-semibold text-foreground">${pos.margin.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Realised PnL:</div>
                    <div className={`font-mono font-semibold ${pos.realisedPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                      {pos.realisedPnl >= 0 ? '+' : ''}${pos.realisedPnl.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Created:</div>
                    <div className="font-mono text-[10px] text-muted-foreground">
                      {new Date(pos.createdAt).toLocaleTimeString('pl-PL')}
                    </div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Updated:</div>
                    <div className="font-mono text-[10px] text-muted-foreground">
                      {new Date(pos.updatedAt).toLocaleTimeString('pl-PL')}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-border/50">
          <div>
            <div className="text-xs text-muted-foreground mb-1">Vol 24h:</div>
            <div className="text-sm font-mono text-foreground">
              ${account.vol24h}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted-foreground mb-1">Vol 7d:</div>
            <div className="text-sm font-mono text-foreground">
              ${account.vol7d.toLocaleString()}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted-foreground mb-1">Vol Total:</div>
            <div className="text-sm font-mono text-foreground">
              ${account.volTotal.toLocaleString()}
            </div>
          </div>

          <div className="flex gap-4">
            <div>
              <div className="text-xs text-muted-foreground mb-1">ATH:</div>
              <div className="text-sm font-mono text-success flex items-center gap-1">
                <TrendingUp className="w-3 h-3" />
                ${account.ath.toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-1">ATL:</div>
              <div className="text-sm font-mono text-danger flex items-center gap-1">
                <TrendingDown className="w-3 h-3" />
                ${account.atl.toFixed(2)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
};
