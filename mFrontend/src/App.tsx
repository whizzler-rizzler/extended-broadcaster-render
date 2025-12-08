import { useState, useEffect } from 'react';
import { AccountCard } from './components/AccountCard';
import type { PortfolioData } from './types';
import { fetchPortfolio } from './api';
import { formatMoney } from './utils';
import './App.css';

function App() {
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchPortfolio();
        setPortfolio(data);
        setError(null);
      } catch (e) {
        setError('Failed to load portfolio');
        console.error(e);
      }
    };

    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  const agg = portfolio?.aggregated;

  return (
    <div className="app">
      <header className="header">
        <h1>Lighter Broadcaster Dashboard</h1>
        <div className="header-stats">
          <div className="header-stat">
            <div className="header-stat-label">Total Equity</div>
            <div className="header-stat-value">{formatMoney(agg?.total_equity || 0)}</div>
          </div>
          <div className="header-stat">
            <div className="header-stat-label">Total PnL</div>
            <div className={`header-stat-value ${(agg?.total_unrealized_pnl || 0) >= 0 ? '' : 'negative'}`}>
              {formatMoney(agg?.total_unrealized_pnl || 0)}
            </div>
          </div>
          <div className="header-stat">
            <div className="header-stat-label">Accounts</div>
            <div className="header-stat-value">{agg?.accounts_live || 0}/{agg?.accounts_total || 0}</div>
          </div>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <div className="accounts-grid">
        {portfolio?.accounts.map(account => (
          <AccountCard key={account.account_index} account={account} />
        ))}
      </div>
    </div>
  );
}

export default App;
