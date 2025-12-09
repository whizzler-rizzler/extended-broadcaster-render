import { Card } from "@/components/ui/card";

interface ExtendedData {
  balance?: {
    balance: string;
    equity: string;
    unrealisedPnl: string;
    realisedPnl?: string;
    marginRatio: string;
    leverage: string;
    collateralName: string;
  };
  positions?: Array<{
    market: string;
    side: string;
    size: string;
    openPrice: string;
    markPrice: string;
    unrealisedPnl: string;
    leverage: string;
  }>;
  lastUpdate: Record<string, string>;
}

interface ExtendedDataPanelProps {
  data: ExtendedData;
}

export const ExtendedDataPanel = ({ data }: ExtendedDataPanelProps) => {
  console.log('🎨 ExtendedDataPanel render:', {
    hasBalance: !!data.balance,
    hasPositions: !!data.positions,
    lastUpdateKeys: Object.keys(data.lastUpdate).length,
    sampleTimestamp: data.lastUpdate['balance']
  });

  const formatValue = (value: string | undefined) => {
    if (!value || value === "-") return "-";
    const num = parseFloat(value);
    if (isNaN(num)) return value;
    return num.toFixed(2);
  };

  const formatTime = (timestamp: string | undefined) => {
    return timestamp || "-";
  };

  return (
    <div className="space-y-4">
      <Card className="bg-black border-primary/30 overflow-hidden">
        <div className="bg-primary text-black px-4 py-2 font-bold grid grid-cols-3 gap-4">
          <div>Field</div>
          <div>Value</div>
          <div className="text-right">Last Update</div>
        </div>

        {/* ACCOUNT / BALANCE */}
        <div className="border-t border-primary/30 bg-primary/10">
          <div className="px-4 py-2 font-bold text-primary flex items-center gap-2">
            <span>🔒</span>
            <span>ACCOUNT / BALANCE</span>
          </div>
        </div>

        <div className="divide-y divide-primary/20">
          <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
            <div className="text-primary">Balance</div>
            <div className="text-foreground font-mono">
              {data.balance ? `$${formatValue(data.balance.balance)}` : "-"}
            </div>
            <div className="text-muted-foreground text-right text-xs">
              {formatTime(data.lastUpdate['balance'])}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
            <div className="text-primary">Equity</div>
            <div className="text-foreground font-mono">
              {data.balance ? `$${formatValue(data.balance.equity)}` : "-"}
            </div>
            <div className="text-muted-foreground text-right text-xs">
              {formatTime(data.lastUpdate['equity'])}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
            <div className="text-primary">Unrealised PnL</div>
            <div className={`font-mono ${data.balance && parseFloat(data.balance.unrealisedPnl) < 0 ? 'text-destructive' : 'text-success'}`}>
              {data.balance ? `$${formatValue(data.balance.unrealisedPnl)}` : "-"}
            </div>
            <div className="text-muted-foreground text-right text-xs">
              {formatTime(data.lastUpdate['unrealisedPnl'])}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
            <div className="text-primary">Realised PnL</div>
            <div className="text-foreground font-mono">
              {data.balance?.realisedPnl ? `$${formatValue(data.balance.realisedPnl)}` : "-"}
            </div>
            <div className="text-muted-foreground text-right text-xs">
              {formatTime(data.lastUpdate['realisedPnl'])}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
            <div className="text-primary">Margin Ratio</div>
            <div className="text-foreground font-mono">
              {data.balance ? `${(parseFloat(data.balance.marginRatio) * 100).toFixed(2)}%` : "-"}
            </div>
            <div className="text-muted-foreground text-right text-xs">
              {formatTime(data.lastUpdate['marginRatio'])}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
            <div className="text-primary">Leverage</div>
            <div className="text-foreground font-mono">
              {data.balance ? `${formatValue(data.balance.leverage)}x` : "-"}
            </div>
            <div className="text-muted-foreground text-right text-xs">
              {formatTime(data.lastUpdate['leverage'])}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
            <div className="text-primary">Collateral Name</div>
            <div className="text-foreground font-mono">
              {data.balance?.collateralName || "-"}
            </div>
            <div className="text-muted-foreground text-right text-xs">
              {formatTime(data.lastUpdate['collateralName'])}
            </div>
          </div>
        </div>

        {/* POSITIONS */}
        {data.positions && data.positions.length > 0 && data.positions.map((position, index) => (
          <div key={index}>
            <div className="border-t border-primary/30 bg-primary/10">
              <div className="px-4 py-2 font-bold text-primary flex items-center gap-2">
                <span>📊</span>
                <span>POSITION #{index + 1}</span>
              </div>
            </div>

            <div className="divide-y divide-primary/20">
              <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
                <div className="text-primary">Market</div>
                <div className="text-foreground font-mono">{position.market}</div>
                <div className="text-muted-foreground text-right text-xs">
                  {formatTime(data.lastUpdate[`position_${index}_market`])}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
                <div className="text-primary">Side</div>
                <div className={`font-mono ${position.side === 'LONG' ? 'text-success' : 'text-destructive'}`}>
                  {position.side}
                </div>
                <div className="text-muted-foreground text-right text-xs">
                  {formatTime(data.lastUpdate[`position_${index}_side`])}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
                <div className="text-primary">Size</div>
                <div className="text-foreground font-mono">{position.size}</div>
                <div className="text-muted-foreground text-right text-xs">
                  {formatTime(data.lastUpdate[`position_${index}_size`])}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
                <div className="text-primary">Entry Price</div>
                <div className="text-foreground font-mono">${formatValue(position.openPrice)}</div>
                <div className="text-muted-foreground text-right text-xs">
                  {formatTime(data.lastUpdate[`position_${index}_openPrice`])}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
                <div className="text-primary">Mark Price</div>
                <div className="text-foreground font-mono">${formatValue(position.markPrice)}</div>
                <div className="text-muted-foreground text-right text-xs">
                  {formatTime(data.lastUpdate[`position_${index}_markPrice`])}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
                <div className="text-primary">Position PnL</div>
                <div className={`font-mono ${parseFloat(position.unrealisedPnl) < 0 ? 'text-destructive' : 'text-success'}`}>
                  ${formatValue(position.unrealisedPnl)}
                </div>
                <div className="text-muted-foreground text-right text-xs">
                  {formatTime(data.lastUpdate[`position_${index}_unrealisedPnl`])}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 px-4 py-2 text-sm hover:bg-primary/5">
                <div className="text-primary">Position Leverage</div>
                <div className="text-foreground font-mono">{position.leverage}x</div>
                <div className="text-muted-foreground text-right text-xs">
                  {formatTime(data.lastUpdate[`position_${index}_leverage`])}
                </div>
              </div>
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
};
