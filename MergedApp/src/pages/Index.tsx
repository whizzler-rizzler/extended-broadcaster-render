import { useState } from "react";
import { Bot, Activity, Bell, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { getApiUrl } from "@/config/api";
import { MultiAccountDashboard } from "@/components/MultiAccountDashboard";
import { AccountDetailPanel } from "@/components/AccountDetailPanel";
import { RestAPIDebugPanel } from "@/components/RestAPIDebugPanel";
import { WebSocketDebugPanel } from "@/components/WebSocketDebugPanel";
import { FrequencyMonitor } from "@/components/FrequencyMonitor";
import { LatencyMonitor } from "@/components/LatencyMonitor";
import { TradeHistoryWeekly } from "@/components/TradeHistoryWeekly";
import { OpenOrdersPanel } from "@/Orders/OpenOrdersPanel";
import { useMultiAccountData } from "@/hooks/useMultiAccountData";
import { usePublicPricesWebSocket } from "@/hooks/usePublicPricesWebSocket";
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
  
  // Broadcaster stats for monitoring
  const broadcasterStats = useBroadcasterStats();
  
  // Selected account for detail view
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const selectedAccount = selectedAccountId ? accounts.get(selectedAccountId) : null;
  
  // Alert test state
  const [alertTestState, setAlertTestState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [alertTestResult, setAlertTestResult] = useState<any>(null);
  
  const handleTestAlert = async () => {
    setAlertTestState('loading');
    try {
      const response = await fetch(getApiUrl('/api/alerts/test'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      setAlertTestResult(data);
      const anySuccess = data.results && (data.results.telegram || data.results.pushover || data.results.sms || data.results.phone_call);
      setAlertTestState(anySuccess ? 'success' : 'error');
      
      // Reset after 5 seconds
      setTimeout(() => {
        setAlertTestState('idle');
        setAlertTestResult(null);
      }, 5000);
    } catch (err) {
      console.error('Alert test error:', err);
      setAlertTestState('error');
      setAlertTestResult({ error: String(err) });
      setTimeout(() => {
        setAlertTestState('idle');
        setAlertTestResult(null);
      }, 5000);
    }
  };

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
          <div className="flex items-center gap-4">
            {/* Alert Test Button */}
            <button
              onClick={handleTestAlert}
              disabled={alertTestState === 'loading'}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                alertTestState === 'idle' 
                  ? 'bg-orange-500/20 border border-orange-500/30 text-orange-400 hover:bg-orange-500/30'
                  : alertTestState === 'loading'
                  ? 'bg-blue-500/20 border border-blue-500/30 text-blue-400'
                  : alertTestState === 'success'
                  ? 'bg-green-500/20 border border-green-500/30 text-green-400'
                  : 'bg-red-500/20 border border-red-500/30 text-red-400'
              }`}
            >
              {alertTestState === 'loading' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : alertTestState === 'success' ? (
                <CheckCircle className="w-4 h-4" />
              ) : alertTestState === 'error' ? (
                <XCircle className="w-4 h-4" />
              ) : (
                <Bell className="w-4 h-4" />
              )}
              {alertTestState === 'idle' && 'Test Alert'}
              {alertTestState === 'loading' && 'Wysyłam...'}
              {alertTestState === 'success' && 'Wysłano!'}
              {alertTestState === 'error' && 'Błąd'}
            </button>
            
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
        </div>
        
        {/* Alert Test Result Details */}
        {alertTestResult && (
          <div className="p-4 rounded-lg border bg-card/50 border-border">
            <h3 className="font-semibold mb-3">Wyniki testu alertów:</h3>
            {alertTestResult.results && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                <div className={`p-3 rounded-lg ${alertTestResult.results.telegram ? 'bg-green-500/20 border-green-500/30' : 'bg-red-500/20 border-red-500/30'} border`}>
                  <div className="text-sm font-medium">Telegram</div>
                  <div className="text-lg">{alertTestResult.results.telegram ? '✅' : '❌'}</div>
                </div>
                <div className={`p-3 rounded-lg ${alertTestResult.results.pushover ? 'bg-green-500/20 border-green-500/30' : 'bg-red-500/20 border-red-500/30'} border`}>
                  <div className="text-sm font-medium">Pushover</div>
                  <div className="text-lg">{alertTestResult.results.pushover ? '✅' : '❌'}</div>
                </div>
                <div className={`p-3 rounded-lg ${alertTestResult.results.sms ? 'bg-green-500/20 border-green-500/30' : 'bg-red-500/20 border-red-500/30'} border`}>
                  <div className="text-sm font-medium">SMS</div>
                  <div className="text-lg">{alertTestResult.results.sms ? '✅' : '❌'}</div>
                </div>
                <div className={`p-3 rounded-lg ${alertTestResult.results.phone_call ? 'bg-green-500/20 border-green-500/30' : 'bg-red-500/20 border-red-500/30'} border`}>
                  <div className="text-sm font-medium">Telefon</div>
                  <div className="text-lg">{alertTestResult.results.phone_call ? '✅' : '❌'}</div>
                </div>
              </div>
            )}
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Szczegóły konfiguracji</summary>
              <pre className="mt-2 font-mono overflow-auto max-h-40 text-muted-foreground bg-background/50 p-2 rounded">
                {JSON.stringify(alertTestResult.config, null, 2)}
              </pre>
            </details>
          </div>
        )}

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
            <h2 className="text-xl font-bold text-primary">HISTORIA TRANSAKCJI & STATYSTYKI</h2>
          </div>
          <TradeHistoryWeekly />
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
