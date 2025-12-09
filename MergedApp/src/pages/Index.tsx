import { useState } from "react";
import { Bot, Activity } from "lucide-react";
import { MultiAccountDashboard } from "@/components/MultiAccountDashboard";
import { AccountDetailPanel } from "@/components/AccountDetailPanel";
import { RestAPIDebugPanel } from "@/components/RestAPIDebugPanel";
import { WebSocketDebugPanel } from "@/components/WebSocketDebugPanel";
import { FrequencyMonitor } from "@/components/FrequencyMonitor";
import { LatencyMonitor } from "@/components/LatencyMonitor";
import { TradeHistory } from "@/components/TradeHistory";
import { OpenOrdersPanel } from "@/Orders/OpenOrdersPanel";
import { useMultiAccountData } from "@/hooks/useMultiAccountData";
import { usePublicPricesWebSocket } from "@/hooks/usePublicPricesWebSocket";
import { useTradeHistory } from "@/hooks/useTradeHistory";
import { useBroadcasterStats } from "@/hooks/useBroadcasterStats";

const Index = () => {
  // Multi-account data (auto-detects and manages all accounts)
  const { 
    accounts, 
    activeAccounts, 
    portfolio, 
    isConnected, 
    error,
    lastUpdate,
    lastWsUpdate,
    lastRestUpdate,
    wsMessageCount,
    restRequestCount,
    restFetchDuration,
  } = useMultiAccountData();
  
  // Public prices WebSocket for mark prices
  const { prices: publicPrices } = usePublicPricesWebSocket();
  
  // Trade history (will be extended for multi-account later)
  const tradeHistory = useTradeHistory();
  
  // Broadcaster stats for monitoring
  const broadcasterStats = useBroadcasterStats();
  
  // Selected account for detail view
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const selectedAccount = selectedAccountId ? accounts.get(selectedAccountId) : null;

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-8 space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-lg bg-primary/10 border border-primary/20">
              <Bot className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-primary">
                Multi-Account Control Panel
              </h1>
              <p className="text-sm text-muted-foreground">
                Real-time monitoring for up to 10 accounts
              </p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2 text-sm">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-success animate-pulse' : 'bg-destructive'}`} />
              <span className="text-muted-foreground">
                {isConnected ? '✅ Connected' : '❌ Disconnected'}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              {activeAccounts.length} accounts active • Last: {lastUpdate.toLocaleTimeString('pl-PL')}
            </div>
            {error && (
              <div className="text-xs text-destructive font-mono">{error}</div>
            )}
          </div>
        </div>

        {/* Frequency Monitor */}
        <FrequencyMonitor 
          broadcasterStats={broadcasterStats.stats}
          lastWsUpdate={lastUpdate}
          isWsConnected={isConnected}
          accounts={accounts}
        />

        {/* Multi-Account Dashboard */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-1 h-6 bg-primary rounded-full" />
            <h2 className="text-xl font-bold text-primary">ACCOUNTS</h2>
          </div>
          <MultiAccountDashboard
            accounts={activeAccounts}
            portfolio={portfolio}
            isConnected={isConnected}
            onAccountSelect={setSelectedAccountId}
            selectedAccountId={selectedAccountId}
          />
        </div>

        {/* Selected Account Detail */}
        {selectedAccount && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <div className="w-1 h-6 bg-primary rounded-full" />
              <h2 className="text-xl font-bold text-primary">ACCOUNT DETAILS</h2>
            </div>
            <AccountDetailPanel
              account={selectedAccount}
              onClose={() => setSelectedAccountId(null)}
            />
          </div>
        )}

        {/* Open Orders Section */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-1 h-6 bg-primary rounded-full" />
            <h2 className="text-xl font-bold text-primary">OTWARTE ZLECENIA</h2>
          </div>
          <OpenOrdersPanel accounts={accounts} lastUpdate={lastUpdate} />
        </section>

        {/* Trade History Section */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-1 h-6 bg-primary rounded-full" />
            <h2 className="text-xl font-bold text-primary">HISTORIA TRANSAKCJI</h2>
          </div>
          <TradeHistory trades={tradeHistory.trades} />
        </section>

        {/* Debug Panels */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-1 h-6 bg-destructive rounded-full" />
            <h2 className="text-xl font-bold text-destructive">DEBUG PANELS</h2>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <RestAPIDebugPanel accounts={accounts} />
            <WebSocketDebugPanel />
          </div>
        </div>

        {/* Latency Monitor Panel */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-1 h-6 bg-yellow-500 rounded-full" />
            <h2 className="text-xl font-bold text-yellow-500">LATENCY MONITOR</h2>
          </div>
          <LatencyMonitor
            broadcasterStats={broadcasterStats.stats}
            lastWsUpdate={lastWsUpdate}
            lastRestUpdate={lastRestUpdate}
            wsMessageCount={wsMessageCount}
            restRequestCount={restRequestCount}
            restFetchDuration={restFetchDuration}
            isWsConnected={isConnected}
            statsLastUpdate={broadcasterStats.lastUpdate}
            statsPollInterval={broadcasterStats.pollInterval}
            statsPollDuration={broadcasterStats.lastPollDuration}
          />
        </div>

        {/* Real-time indicator */}
        <div className="mt-8 text-center p-4 bg-primary/10 rounded-lg border border-primary/20">
          <p className="text-lg font-semibold text-primary flex items-center justify-center gap-2">
            <Activity className={`w-5 h-5 ${isConnected ? 'animate-pulse' : ''}`} />
            🔴 LIVE • Multi-Account Stream
          </p>
          <p className="text-sm text-muted-foreground mt-1">
            Auto-detecting accounts • {activeAccounts.length}/10 slots used
          </p>
        </div>
      </div>
    </div>
  );
};

export default Index;
