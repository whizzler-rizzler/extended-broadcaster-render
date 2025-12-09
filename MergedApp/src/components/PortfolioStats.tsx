import { Card } from "@/components/ui/card";
import { TrendingUp, Layers, BarChart3, ArrowUp, ArrowDown } from "lucide-react";

interface PortfolioData {
  totalPnl: number;
  realizedPnl: number;
  totalNotional: number;
  activePositions: number;
  leverage: number;
  collateral: number;
  equity: number;
  availableBalance: number;
  marginRatio: number;
  exposure: number;
  volume24h: number;
  volume7d: number;
  volume30d: number;
  longPositions: number;
  longPnl: number;
  longNotional: number;
  shortPositions: number;
  shortPnl: number;
  shortNotional: number;
}

interface PortfolioStatsProps {
  data: PortfolioData;
}

export const PortfolioStats = ({ data }: PortfolioStatsProps) => {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-6 border-border/50 bg-card/50 backdrop-blur-sm">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <span className="text-primary">$</span>
              <span>TOTAL PNL</span>
            </div>
            <div className={`text-4xl font-mono font-bold ${data.totalPnl >= 0 ? 'text-success' : 'text-danger'}`}>
              {data.totalPnl >= 0 ? '+' : ''}${data.totalPnl.toFixed(2)}
            </div>
            <div className="text-sm text-muted-foreground">
              Realised: ${data.realizedPnl.toFixed(2)}
            </div>
          </div>
        </Card>

        <Card className="p-6 border-success/30 bg-card/50 backdrop-blur-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-success/50" />
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <Layers className="w-4 h-4 text-primary" />
              <span>TOTAL NOTIONAL</span>
            </div>
            <div className="text-4xl font-mono font-bold text-foreground">
              ${Math.round(data.totalNotional).toLocaleString()}
            </div>
            <div className="text-sm text-muted-foreground">
              Active Positions: {data.activePositions}
            </div>
          </div>
        </Card>

        <Card className="p-6 border-border/50 bg-card/50 backdrop-blur-sm">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <BarChart3 className="w-4 h-4 text-primary" />
              <span>LEVERAGE & BALANCE</span>
            </div>
            <div className="text-4xl font-mono font-bold text-foreground">
              {data.leverage.toFixed(2)}x
            </div>
            <div className="text-sm text-muted-foreground space-y-1">
              <div>Balance: ${data.collateral.toFixed(2)}</div>
              <div>Equity: ${data.equity.toFixed(2)}</div>
              <div className="text-primary font-semibold">Available: ${data.availableBalance.toFixed(2)}</div>
              <div className={`font-semibold ${data.marginRatio > 0.5 ? 'text-danger' : 'text-success'}`}>
                Margin Ratio: {(data.marginRatio * 100).toFixed(2)}%
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-6 border-border/50 bg-card/50 backdrop-blur-sm">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <BarChart3 className="w-4 h-4" />
              <span>VOLUME</span>
            </div>
            <div className="text-3xl font-mono font-bold text-foreground">
              ${data.volume24h.toLocaleString()}
            </div>
            <div className="text-sm text-muted-foreground space-y-1">
              <div>7d: ${data.volume7d.toLocaleString()} | 30d: ${data.volume30d.toLocaleString()}</div>
            </div>
          </div>
        </Card>

        <Card className="p-6 border-success/30 bg-card/50 backdrop-blur-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-success/50" />
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <ArrowUp className="w-4 h-4 text-success" />
              <span>LONG POSITIONS</span>
            </div>
            <div className="text-3xl font-mono font-bold text-foreground">
              {data.longPositions} pos
            </div>
            <div className="text-sm text-muted-foreground space-y-1">
              <div>Notional: ${Math.round(data.longNotional).toLocaleString()}</div>
              <div className={`font-semibold ${data.longPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                PnL: {data.longPnl >= 0 ? '+' : ''}${data.longPnl.toFixed(2)}
              </div>
            </div>
          </div>
        </Card>

        <Card className="p-6 border-danger/30 bg-card/50 backdrop-blur-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-danger/50" />
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-muted-foreground text-sm">
              <ArrowDown className="w-4 h-4 text-danger" />
              <span>SHORT POSITIONS</span>
            </div>
            <div className="text-3xl font-mono font-bold text-foreground">
              {data.shortPositions} pos
            </div>
            <div className="text-sm text-muted-foreground space-y-1">
              <div>Notional: ${Math.round(data.shortNotional).toLocaleString()}</div>
              <div className={`font-semibold ${data.shortPnl >= 0 ? 'text-success' : 'text-danger'}`}>
                PnL: {data.shortPnl >= 0 ? '+' : ''}${data.shortPnl.toFixed(2)}
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
