// src/pages/CallHistory.jsx
import { useState, useEffect } from 'react';
import { PhoneCall, ChevronRight, X } from 'lucide-react';
import api from '../api/client';

export default function CallHistory() {
  const [calls, setCalls]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail]   = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    api.get('/api/calls?limit=100')
      .then(r => setCalls(r.data))
      .finally(() => setLoading(false));
  }, []);

  const openDetail = async (call) => {
    setSelected(call); setDetail(null); setDetailLoading(true);
    try {
      const { data } = await api.get(`/api/calls/${call.id}`);
      setDetail(data);
    } finally { setDetailLoading(false); }
  };

  const statusBadge = (s) => {
    const cls = s === 'completed' ? 'success' : s === 'failed' ? 'danger' : 'warning';
    return <span className={`badge badge-${cls}`}>{s}</span>;
  };

  const fmt = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
  };

  return (
    <div>
      <div className="page-header">
        <h1>Call History</h1>
        <p>Review all AI calling sessions, transcripts, and actions.</p>
      </div>

      {loading ? (
        <div className="empty-state"><div className="spinner" style={{margin:'0 auto'}} /></div>
      ) : calls.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📞</div>
          <h3>No calls recorded yet</h3>
          <p>Call your Twilio number to start a session. Logs will appear here automatically.</p>
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
                <th>Date & Time</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {calls.map(c => (
                <tr key={c.id} style={{cursor:'pointer'}} onClick={() => openDetail(c)}>
                  <td style={{fontFamily:'monospace',fontSize:'13px'}}>{c.caller_number}</td>
                  <td><span className="badge badge-blue">{c.language?.toUpperCase()}</span></td>
                  <td>{c.turn_count}</td>
                  <td>
                    {c.actions_count > 0
                      ? <span className="badge badge-purple">{c.actions_count} action{c.actions_count > 1 ? 's': ''}</span>
                      : <span className="text-secondary text-sm">—</span>}
                  </td>
                  <td>{statusBadge(c.status)}</td>
                  <td className="text-secondary text-sm">{fmt(c.started_at)}</td>
                  <td><ChevronRight size={16} style={{color:'var(--text-secondary)'}} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ─── Detail Side Panel ─────────────────────────────────── */}
      {selected && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setSelected(null)}>
          <div className="modal" style={{maxWidth:'600px'}}>
            <div className="modal-header">
              <h2>Call Detail</h2>
              <button className="btn btn-secondary btn-sm" onClick={() => setSelected(null)}><X size={15}/></button>
            </div>

            {detailLoading ? (
              <div className="empty-state"><div className="spinner" style={{margin:'0 auto'}} /></div>
            ) : detail ? (
              <>
                <div className="card-grid" style={{marginBottom:'16px'}}>
                  {[
                    ['Caller', detail.caller_number],
                    ['Language', detail.language?.toUpperCase()],
                    ['Turns', detail.turn_count],
                    ['Status', detail.status],
                  ].map(([l, v]) => (
                    <div key={l} style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'12px 16px'}}>
                      <div className="stat-label">{l}</div>
                      <div style={{fontWeight:600,marginTop:'4px'}}>{v}</div>
                    </div>
                  ))}
                </div>

                {detail.actions_taken?.length > 0 && (
                  <>
                    <h3 style={{fontSize:'14px',fontWeight:600,marginBottom:'10px'}}>Actions Taken</h3>
                    {detail.actions_taken.map((a, i) => (
                      <div key={i} style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'10px 14px',marginBottom:'8px',fontSize:'13px'}}>
                        <span className="badge badge-blue" style={{marginRight:'8px'}}>{a.action}</span>
                        <span className="text-secondary">{a.result}</span>
                      </div>
                    ))}
                  </>
                )}

                {detail.transcript_summary && (
                  <>
                    <div className="divider" />
                    <h3 style={{fontSize:'14px',fontWeight:600,marginBottom:'10px'}}>Transcript Summary</h3>
                    <div style={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:'var(--radius-sm)',padding:'14px',fontSize:'13px',lineHeight:'1.6',color:'var(--text-secondary)',whiteSpace:'pre-wrap'}}>
                      {detail.transcript_summary}
                    </div>
                  </>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
