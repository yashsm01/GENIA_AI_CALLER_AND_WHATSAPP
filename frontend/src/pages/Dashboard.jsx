// src/pages/Dashboard.jsx
import { useState, useEffect } from 'react';
import { PhoneCall, Files, TrendingUp, CheckCircle, AlertCircle } from 'lucide-react';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function Dashboard() {
  const { user } = useAuth();
  const [calls, setCalls]     = useState([]);
  const [docs, setDocs]       = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get('/api/calls?limit=5').catch(() => ({ data: [] })),
      api.get('/api/documents').catch(() => ({ data: [] })),
    ]).then(([c, d]) => {
      setCalls(c.data);
      setDocs(d.data);
    }).finally(() => setLoading(false));
  }, []);

  const total      = calls.length;
  const successful = calls.filter(c => c.status === 'completed').length;
  const actions    = calls.reduce((s, c) => s + (c.actions_count || 0), 0);

  const stats = [
    { label: 'Total Calls',     value: total,      icon: <PhoneCall size={20}/>,    cls: 'blue'   },
    { label: 'Completed',       value: successful,  icon: <CheckCircle size={20}/>,  cls: 'green'  },
    { label: 'Actions Taken',   value: actions,     icon: <TrendingUp size={20}/>,   cls: 'purple' },
    { label: 'Documents',       value: docs.length, icon: <Files size={20}/>,        cls: 'orange' },
  ];

  return (
    <div>
      <div className="page-header">
        <h1>Welcome back, {user?.name?.split(' ')[0]} 👋</h1>
        <p>Here's an overview of your AI calling performance.</p>
      </div>

      <div className="card-grid">
        {stats.map(s => (
          <div key={s.label} className="stat-card">
            <div className={`stat-icon ${s.cls}`}>{s.icon}</div>
            <div>
              <div className="stat-label">{s.label}</div>
              <div className="stat-value">{loading ? '—' : s.value}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="section-header">
          <h2>Recent Calls</h2>
        </div>
        {loading ? (
          <div className="empty-state"><div className="spinner" style={{margin:'0 auto'}} /></div>
        ) : calls.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📞</div>
            <h3>No calls yet</h3>
            <p>Once calls come in, they'll appear here with full transcripts and actions.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Caller</th>
                  <th>Language</th>
                  <th>Turns</th>
                  <th>Actions</th>
                  <th>Status</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {calls.map(c => (
                  <tr key={c.id}>
                    <td style={{fontFamily:'monospace'}}>{c.caller_number}</td>
                    <td><span className="badge badge-blue">{c.language.toUpperCase()}</span></td>
                    <td>{c.turn_count}</td>
                    <td>{c.actions_count}</td>
                    <td>
                      <span className={`badge badge-${c.status === 'completed' ? 'success' : 'danger'}`}>
                        {c.status}
                      </span>
                    </td>
                    <td className="text-secondary text-sm">
                      {new Date(c.started_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
