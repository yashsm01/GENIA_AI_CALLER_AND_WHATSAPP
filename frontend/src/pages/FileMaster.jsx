// src/pages/FileMaster.jsx — Upload and manage brochures / documents
import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, FileText, X, Check } from 'lucide-react';
import api from '../api/client';

const EMPTY_FORM = {
  intent_key: '', name: '', url: '', description: '',
  whatsapp_caption: '', email_subject: '', email_body: '',
};

export default function FileMaster() {
  const [docs, setDocs]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing]   = useState(null); // null = create, obj = edit
  const [form, setForm]         = useState(EMPTY_FORM);
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState('');
  const [success, setSuccess]   = useState('');

  const load = () => {
    setLoading(true);
    api.get('/api/documents')
      .then(r => setDocs(r.data))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const openCreate = () => { setEditing(null); setForm(EMPTY_FORM); setError(''); setShowModal(true); };
  const openEdit   = (d) => {
    setEditing(d);
    setForm({
      intent_key: d.intent_key, name: d.name, url: d.url, description: d.description,
      whatsapp_caption: d.whatsapp_caption, email_subject: d.email_subject, email_body: d.email_body,
    });
    setError(''); setShowModal(true);
  };

  const handleSave = async (e) => {
    e.preventDefault(); setError(''); setSaving(true);
    try {
      if (editing) {
        await api.put(`/api/documents/${editing.id}`, form);
        setSuccess('Document updated successfully!');
      } else {
        await api.post('/api/documents', form);
        setSuccess('Document added successfully!');
      }
      setShowModal(false); load();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id, name) => {
    if (!confirm(`Delete "${name}"? The AI will no longer share this document.`)) return;
    await api.delete(`/api/documents/${id}`);
    load();
  };

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  return (
    <div>
      <div className="page-header">
        <h1>File Master</h1>
        <p>Manage the brochures and documents your AI can send to callers.</p>
      </div>

      {success && <div className="alert alert-success"><Check size={16} /> {success}</div>}

      <div className="section-header">
        <h2>Your Documents ({docs.length})</h2>
        <button id="add-doc-btn" className="btn btn-primary" onClick={openCreate}>
          <Plus size={16} /> Add Document
        </button>
      </div>

      {loading ? (
        <div className="empty-state"><div className="spinner" style={{margin:'0 auto'}} /></div>
      ) : docs.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📄</div>
          <h3>No documents yet</h3>
          <p>Add a product brochure and the AI will be able to send it to callers automatically.</p>
          <button className="btn btn-primary" onClick={openCreate}><Plus size={16} /> Add First Document</button>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Intent Key</th>
                <th>Document Name</th>
                <th>URL</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {docs.map(d => (
                <tr key={d.id}>
                  <td>
                    <code style={{background:'var(--bg-card-hover)',padding:'2px 8px',borderRadius:'6px',fontSize:'12px',color:'var(--accent)'}}>
                      {d.intent_key}
                    </code>
                  </td>
                  <td>
                    <div style={{display:'flex',alignItems:'center',gap:'8px'}}>
                      <FileText size={15} style={{color:'var(--text-secondary)',flexShrink:0}} />
                      {d.name}
                    </div>
                  </td>
                  <td>
                    <a href={d.url} target="_blank" rel="noreferrer"
                       style={{color:'var(--accent)',fontSize:'13px',maxWidth:'200px',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',display:'block'}}>
                      {d.url}
                    </a>
                  </td>
                  <td>
                    <span className={`badge ${d.is_active ? 'badge-success' : 'badge-danger'}`}>
                      {d.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    <div className="flex gap-2">
                      <button className="btn btn-secondary btn-sm" onClick={() => openEdit(d)}><Pencil size={13}/> Edit</button>
                      <button className="btn btn-danger btn-sm" onClick={() => handleDelete(d.id, d.name)}><Trash2 size={13}/></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ─── Modal ─────────────────────────────────────────────── */}
      {showModal && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal">
            <div className="modal-header">
              <h2>{editing ? 'Edit Document' : 'Add Document'}</h2>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowModal(false)}><X size={15}/></button>
            </div>

            {error && <div className="alert alert-error">⚠️  {error}</div>}

            <form onSubmit={handleSave}>
              <div className="form-row">
                <div className="form-group">
                  <label>Intent Key *</label>
                  <input id="doc-intent-key" className="form-input" placeholder="e.g. fan, wire" value={form.intent_key} onChange={set('intent_key')} required disabled={!!editing} />
                  <span className="text-sm text-secondary" style={{marginTop:'4px',display:'block'}}>The word users say on the call ("send me the fan brochure")</span>
                </div>
                <div className="form-group">
                  <label>Document Name *</label>
                  <input id="doc-name" className="form-input" placeholder="Fan Brochure 2026" value={form.name} onChange={set('name')} required />
                </div>
              </div>

              <div className="form-group">
                <label>Document URL *</label>
                <input id="doc-url" className="form-input" type="url" placeholder="https://yourcompany.com/brochures/fan.pdf" value={form.url} onChange={set('url')} required />
              </div>

              <div className="form-group">
                <label>Description (optional)</label>
                <input id="doc-desc" className="form-input" placeholder="Short description for reference" value={form.description} onChange={set('description')} />
              </div>

              <div className="divider" />

              <div className="form-group">
                <label>WhatsApp Caption</label>
                <textarea id="doc-whatsapp" className="form-input" placeholder="🌀 *Fan Brochure 2026*&#10;Please find our latest Fan product catalog." value={form.whatsapp_caption} onChange={set('whatsapp_caption')} />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Email Subject</label>
                  <input id="doc-email-subject" className="form-input" placeholder="Your Fan Brochure — SM01" value={form.email_subject} onChange={set('email_subject')} />
                </div>
                <div className="form-group">
                  <label>Email Body</label>
                  <input id="doc-email-body" className="form-input" placeholder="Dear Customer, find the brochure at {url}" value={form.email_body} onChange={set('email_body')} />
                </div>
              </div>

              <div className="flex gap-2 mt-4">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                <button id="doc-save-btn" type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? <span className="spinner" /> : <Check size={15} />}
                  {saving ? 'Saving…' : (editing ? 'Update Document' : 'Add Document')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
