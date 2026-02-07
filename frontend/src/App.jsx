import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const AccountCard = ({ acc, onStart, onStop, onRefresh }) => {
  const consoleRef = useRef(null);

  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [acc.logs]);

  return (
    <div className={`glass-card account-card ${acc.isRunning ? 'active' : ''}`} data-aos="fade-up">
      <div className="account-header">
        <div className="uid-badge" title={acc.display_name || acc.user_id}>
          {acc.display_name ? acc.display_name.toLowerCase() : (acc.user_id ? acc.user_id.slice(0, 10) + '...' : 'SYNCING...')}
        </div>
        <div className={`status-indicator ${acc.isRunning ? 'running' : ''}`}></div>
      </div>

      <div className="mini-stats">
        <div className="mini-stat">
          <h4>K-Points</h4>
          <p style={{ color: '#ffcc00' }}>{acc.balances.kpoint.toLocaleString()}</p>
        </div>
        <div className="mini-stat">
          <h4>rKGEN</h4>
          <p style={{ color: '#ff0080' }}>{acc.balances.rkgen.toFixed(4)}</p>
        </div>
      </div>

      <div className="acc-controls">
        <button
          className="btn btn-primary acc-btn"
          onClick={() => onStart(acc.id, 'tasks')}
          disabled={acc.isRunning}
        >
          TASKS
        </button>
        <button
          className="btn btn-primary acc-btn"
          onClick={() => onStart(acc.id, 'spin')}
          disabled={acc.isRunning}
        >
          SPIN
        </button>
        {acc.isRunning && (
          <button className="btn btn-secondary acc-btn" onClick={() => onStop(acc.id)} style={{ background: '#ff4d4d' }}>
            STOP
          </button>
        )}
      </div>

      <div className="mini-console" ref={consoleRef}>
        {acc.logs.length === 0 && <span style={{ color: '#555' }}>Waiting for action...</span>}
        {acc.logs.map((log, i) => (
          <div key={i} className="log-line" style={{
            color: log.color && log.color.includes('91m') ? '#ff4d4d' :
              log.color && log.color.includes('92m') ? '#00ff88' :
                log.color && log.color.includes('93m') ? '#ffcc00' :
                  log.color && log.color.includes('96m') ? '#00f2fe' : 'inherit'
          }}>
            {log.clean}
          </div>
        ))}
      </div>
    </div>
  );
};

function App() {
  const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
  const WS_URL = BACKEND_URL.replace('http', 'ws');

  const [rawTokens, setRawTokens] = useState('');
  const [accounts, setAccounts] = useState([]);
  const [showImport, setShowImport] = useState(true);
  const wsRefs = useRef({});

  const handleImport = async () => {
    const tokens = rawTokens.split('\n').map(t => t.trim()).filter(t => t.length > 10);
    const newAccounts = tokens.map((t, idx) => ({
      id: `acc-${Date.now()}-${idx}`,
      token: t,
      user_id: '',
      balances: { kpoint: 0, rkgen: 0 },
      logs: [],
      isRunning: false,
      type: null
    }));

    setAccounts(prev => [...prev, ...newAccounts]);
    setRawTokens('');
    setShowImport(false);

    // Fetch initial balances
    newAccounts.forEach(acc => fetchBalance(acc));
  };

  const fetchBalance = async (acc) => {
    try {
      const resp = await fetch(`${BACKEND_URL}/api/balance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: acc.token })
      });
      const data = await resp.json();
      if (resp.ok) {
        setAccounts(prev => prev.map(a => a.id === acc.id ? {
          ...a,
          user_id: data.user_id,
          display_name: data.display_name,
          balances: data.balances
        } : a));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const startAccount = (id, type) => {
    const acc = accounts.find(a => a.id === id);
    if (!acc || acc.isRunning) return;

    setAccounts(prev => prev.map(a => a.id === id ? { ...a, isRunning: true, logs: [], type } : a));

    const ws = new WebSocket(`${WS_URL}/ws/${type}`);
    wsRefs.current[id] = ws;

    ws.onopen = () => ws.send(JSON.stringify({ token: acc.token }));
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setAccounts(prev => prev.map(a => {
        if (a.id === id) {
          if (data.type === 'log') {
            return { ...a, logs: [...a.logs.slice(-50), data] };
          }
        }
        return a;
      }));
    };
    ws.onclose = () => {
      setAccounts(prev => prev.map(a => a.id === id ? { ...a, isRunning: false } : a));
      fetchBalance(acc);
    };
  };

  const stopAccount = (id) => {
    if (wsRefs.current[id]) {
      wsRefs.current[id].close();
      delete wsRefs.current[id];
    }
  };

  const runAll = (type) => {
    accounts.forEach(acc => {
      if (!acc.isRunning) startAccount(acc.id, type);
    });
  };

  const stats = {
    totalAccounts: accounts.length,
    runningAccounts: accounts.filter(a => a.isRunning).length,
    totalKPoints: accounts.reduce((sum, a) => sum + a.balances.kpoint, 0),
    totalRKGEN: accounts.reduce((sum, a) => sum + a.balances.rkgen, 0)
  };

  return (
    <div className="app-container">
      <div className="mesh-background">
        <div className="mesh-sphere sphere-1"></div>
        <div className="mesh-sphere sphere-2"></div>
        <div className="mesh-sphere sphere-3"></div>
      </div>
      <header className="header" data-aos="zoom-in">
        <h1>KGEN AUTOMATION</h1>
        <p>By ARKONE for KGen Ecosystem</p>
      </header>

      <section className="login-section glass-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: showImport ? '20px' : '0' }}>
          <h3 style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>Account Management</h3>
          <button
            onClick={() => setShowImport(!showImport)}
            style={{ background: 'transparent', border: 'none', color: 'var(--accent-cyan)', cursor: 'pointer', fontSize: '0.8rem' }}
          >
            {showImport ? 'Hide Import' : 'Show Token Import'}
          </button>
        </div>

        {showImport && (
          <>
            <div className="input-group">
              <label>Batch Token Import (Paste one per line)</label>
              <textarea
                placeholder="eyJhbGci...&#10;eyJhbGci..."
                value={rawTokens}
                onChange={(e) => setRawTokens(e.target.value)}
              />
            </div>
            <button className="btn btn-primary" onClick={handleImport}>
              IMPORT & SYNC ACCOUNTS ({rawTokens.split('\n').filter(t => t.trim()).length})
            </button>
          </>
        )}
      </section>

      {accounts.length > 0 && (
        <>
          <div className="global-controls" data-aos="zoom-in">
            <div className="account-summary">
              <div className="total-stat">
                <label>Accounts</label>
                <span>{stats.totalAccounts}</span>
              </div>
              <div className="total-stat">
                <label>Active</label>
                <span style={{ color: 'var(--success-green)' }}>{stats.runningAccounts}</span>
              </div>
              <div className="total-stat">
                <label>Total KPs</label>
                <span>{stats.totalKPoints.toLocaleString()}</span>
              </div>
              <div className="total-stat">
                <label>Total rKGEN</label>
                <span>{stats.totalRKGEN.toFixed(2)}</span>
              </div>
            </div>

            <div className="global-actions">
              <button className="btn btn-primary" onClick={() => runAll('tasks')} disabled={stats.runningAccounts > 0}>
                RUN TASKS
              </button>
              <button className="btn btn-primary" onClick={() => runAll('spin')} disabled={stats.runningAccounts > 0}>
                RUN SPINS
              </button>
              <button className="btn btn-secondary" onClick={() => { setAccounts([]); setRawTokens(''); }}>
                CLEAR
              </button>
            </div>
          </div>

          <div className="account-grid">
            {accounts.map(acc => (
              <AccountCard
                key={acc.id}
                acc={acc}
                onStart={startAccount}
                onStop={stopAccount}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default App;
