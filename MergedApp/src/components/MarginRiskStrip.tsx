import { AlertTriangle, ShieldAlert, Shield, ShieldCheck } from 'lucide-react';
import { SingleAccountData } from '@/types/multiAccount';
import { cn } from '@/lib/utils';

interface MarginRiskStripProps {
  accounts: SingleAccountData[];
  onAccountSelect?: (accountId: string) => void;
}

export const MarginRiskStrip = ({ accounts, onAccountSelect }: MarginRiskStripProps) => {
  const riskyAccounts = accounts
    .filter(a => a.isActive && (Number(a.computed.marginRatio) || 0) > 0.7)
    .sort((a, b) => (Number(b.computed.marginRatio) || 0) - (Number(a.computed.marginRatio) || 0));

  if (riskyAccounts.length === 0) return null;

  const getMarginColor = (ratio: number) => {
    if (ratio >= 90) return 'bg-red-500/30 border-red-500/60 text-red-300';
    if (ratio >= 70) return 'bg-red-500/20 border-red-500/40 text-red-400';
    if (ratio >= 40) return 'bg-yellow-500/15 border-yellow-500/30 text-yellow-400';
    return 'bg-muted/30 border-border/50 text-muted-foreground';
  };

  const getIcon = (ratio: number) => {
    if (ratio >= 90) return <ShieldAlert className="w-3.5 h-3.5 text-red-400 animate-pulse" />;
    if (ratio >= 70) return <AlertTriangle className="w-3.5 h-3.5 text-red-400" />;
    if (ratio >= 40) return <Shield className="w-3.5 h-3.5 text-yellow-400" />;
    return <ShieldCheck className="w-3.5 h-3.5 text-muted-foreground" />;
  };

  const getLabel = (ratio: number) => {
    if (ratio >= 90) return 'KRYTYCZNY';
    if (ratio >= 70) return 'WYSOKI';
    if (ratio >= 40) return 'UWAGA';
    return '';
  };

  const criticalCount = riskyAccounts.filter(a => (Number(a.computed.marginRatio) || 0) >= 70).length;
  const warningCount = riskyAccounts.filter(a => {
    const r = Number(a.computed.marginRatio) || 0;
    return r >= 40 && r < 70;
  }).length;

  const shortName = (name: string) => {
    const match = name.match(/Extended (\d+)/);
    return match ? `#${match[1]}` : name.slice(0, 8);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-1 h-6 bg-orange-500 rounded-full" />
          <h2 className="text-xl font-bold text-orange-400">MARGIN RISK</h2>
          <span className="text-sm text-muted-foreground">
            ({riskyAccounts.length} kont z marginem {'>'} 0.7%)
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {criticalCount > 0 && (
            <span className="flex items-center gap-1 text-red-400 font-semibold">
              <ShieldAlert className="w-3.5 h-3.5" />
              {criticalCount} krytycznych ({'\u2265'}70%)
            </span>
          )}
          {warningCount > 0 && (
            <span className="flex items-center gap-1 text-yellow-400">
              <AlertTriangle className="w-3.5 h-3.5" />
              {warningCount} ostrzeżeń (40-70%)
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {riskyAccounts.map(account => {
          const ratio = Number(account.computed.marginRatio) || 0;
          const label = getLabel(ratio);
          const equity = Number(account.computed.equity) || 0;
          const liqPrice = account.positions.length > 0 ? account.positions[0].liquidationPrice : null;
          const markPrice = account.positions.length > 0 ? account.positions[0].markPrice : null;
          const distToLiq = liqPrice && markPrice
            ? ((Math.abs(markPrice - liqPrice) / markPrice) * 100).toFixed(1)
            : null;

          return (
            <button
              key={account.id}
              onClick={() => onAccountSelect?.(account.id)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs font-mono transition-all hover:scale-105 cursor-pointer',
                getMarginColor(ratio)
              )}
              title={`${account.name}\nMargin: ${ratio.toFixed(2)}%\nEquity: $${equity.toFixed(0)}\n${distToLiq ? `Odl. do likwidacji: ${distToLiq}%` : ''}`}
            >
              {getIcon(ratio)}
              <span className="font-semibold">{shortName(account.name)}</span>
              <span className="font-bold">{ratio.toFixed(1)}%</span>
              {label && (
                <span className={cn(
                  'text-[9px] font-bold px-1 rounded',
                  ratio >= 70 ? 'bg-red-500/40' : ratio >= 40 ? 'bg-yellow-500/30' : ''
                )}>
                  {label}
                </span>
              )}
              {distToLiq && ratio >= 40 && (
                <span className="text-[9px] opacity-70">
                  (liq: {distToLiq}%)
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
