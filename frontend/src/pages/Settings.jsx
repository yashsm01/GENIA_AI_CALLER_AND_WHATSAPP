// src/pages/Settings.jsx
import { useState, useEffect } from 'react';
import { Check, Eye, EyeOff } from 'lucide-react';
import api from '../api/client';

function Section({ title, children }) {
  return (
    <div className="card" style={{marginBottom:'20px'}}>
      <h2 style={{fontSize:'15px',fontWeight:700,marginBottom:'20px',color:'var(--text-primary)'}}>{title}</h2>
      {children}
    </div>
  );
}

function SecretInput({ id, label, value, onChange, placeholder }) {
  const [show, setShow] = useState(false);
  return (
    <div className="form-group">
      <label>{label}</label>
      <div style={{position:'relative'}}>
        <input id={id} className="form-input" type={show ? 'text' : 'password'} placeholder={placeholder} value={value} onChange={onChange} style={{paddingRight:'40px'}} />
        <button type="button" onClick={() => setShow(s => !s)} style={{position:'absolute',right:'10px',top:'50%',transform:'translateY(-50%)',background:'none',border:'none',cursor:'pointer',color:'var(--text-secondary)'}}>
          {show ? <EyeOff size={16}/> : <Eye size={16}/>}
        </button>
      </div>
    </div>
  );
}

export default function Settings() {
  const [form, setForm] = useState({
    name:'', company_name:'', default_language:'en', voice_mode:'multilingual',
    twilio_phone:'', twilio_sid:'', twilio_token:'', whatsapp_number:'',
    openai_key:'', elevenlabs_key:'', elevenlabs_voice_id:'', elevenlabs_agent_id:'',
    smtp_host:'', smtp_port:'587', smtp_user:'', smtp_pass:'',
  });
  const [pwForm, setPwForm]   = useState({ current_password:'', new_password:'' });
  const [saving, setSaving]   = useState(false);
  const [pwSaving, setPwSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/settings').then(r => {
      const d = r.data;
      setForm(f => ({ ...f,
        name: d.name, company_name: d.company_name,
        twilio_phone: d.twilio_phone, whatsapp_number: d.whatsapp_number,
        default_language: d.default_language, voice_mode: d.voice_mode,
      }));
    }).finally(() => setLoading(false));
  }, []);

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  const handleSave = async (e) => {
    e.preventDefault(); setError(''); setSaving(true);
    try {
      await api.put('/api/settings', form);
      setSuccess('Settings saved and credentials synced!');
      setTimeout(() => setSuccess(''), 4000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Save failed.');
    } finally { setSaving(false); }
  };

  const handlePwChange = async (e) => {
    e.preventDefault(); setError(''); setPwSaving(true);
    try {
      await api.put('/api/settings/password', pwForm);
      setPwForm({ current_password:'', new_password:'' });
      setSuccess('Password updated!');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Password change failed.');
    } finally { setPwSaving(false); }
  };

  if (loading) return <div className="empty-state"><div className="spinner" style={{margin:'0 auto'}} /></div>;

  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
        <p>Configure your company profile, API credentials, and delivery preferences.</p>
      </div>

      {success && <div className="alert alert-success"><Check size={16}/> {success}</div>}
      {error   && <div className="alert alert-error">⚠️  {error}</div>}

      <form onSubmit={handleSave}>
        <Section title="🏢 Company Profile">
          <div className="form-row">
            <div className="form-group">
              <label>Your Name</label>
              <input id="set-name" className="form-input" value={form.name} onChange={set('name')} placeholder="Yash Shah" />
            </div>
            <div className="form-group">
              <label>Company Name</label>
              <input id="set-company" className="form-input" value={form.company_name} onChange={set('company_name')} placeholder="SM01 Industries" />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Default Language</label>
              <select id="set-lang" className="form-input" value={form.default_language} onChange={set('default_language')}>
                <option value="en">English</option>
                <option value="hi">Hindi</option>
                <option value="gu">Gujarati</option>
              </select>
            </div>
            <div className="form-group">
              <label>Voice Mode</label>
              <select id="set-voice-mode" className="form-input" value={form.voice_mode} onChange={set('voice_mode')}>
                <option value="multilingual">Multilingual (Recommended)</option>
                <option value="per_language">Per Language</option>
              </select>
            </div>
          </div>
        </Section>

        <Section title="📞 Twilio Credentials">
          <div className="form-row">
            <SecretInput id="set-twilio-sid"   label="Account SID"  value={form.twilio_sid}   onChange={set('twilio_sid')}   placeholder="ACxxxxxxxxxxxxxxxx" />
            <SecretInput id="set-twilio-token" label="Auth Token"   value={form.twilio_token} onChange={set('twilio_token')} placeholder="51e5a3..." />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Twilio Phone Number</label>
              <input id="set-twilio-phone" className="form-input" value={form.twilio_phone} onChange={set('twilio_phone')} placeholder="+12182170603" />
              <span className="text-sm text-secondary" style={{marginTop:'4px',display:'block'}}>This is how inbound calls are routed to your account</span>
            </div>
            <div className="form-group">
              <label>WhatsApp Sender Number</label>
              <input id="set-whatsapp" className="form-input" value={form.whatsapp_number} onChange={set('whatsapp_number')} placeholder="+14155238886" />
            </div>
          </div>
        </Section>

        <Section title="🤖 AI Credentials">
          <SecretInput id="set-openai-key"    label="OpenAI API Key"         value={form.openai_key}          onChange={set('openai_key')}          placeholder="sk-proj-..." />
          <div className="form-row">
            <SecretInput id="set-el-key"      label="ElevenLabs API Key"     value={form.elevenlabs_key}      onChange={set('elevenlabs_key')}      placeholder="sk_..." />
            <SecretInput id="set-voice-id"    label="ElevenLabs Voice ID"    value={form.elevenlabs_voice_id} onChange={set('elevenlabs_voice_id')} placeholder="O9GyUq..." />
          </div>
          <div className="form-group">
            <label>ElevenLabs Agent ID (ConvAI — optional)</label>
            <input id="set-agent-id" className="form-input" value={form.elevenlabs_agent_id} onChange={set('elevenlabs_agent_id')} placeholder="Leave blank to use standard pipeline" />
          </div>
        </Section>

        <Section title="📧 Email (SMTP)">
          <div className="form-row">
            <div className="form-group">
              <label>SMTP Host</label>
              <input id="set-smtp-host" className="form-input" value={form.smtp_host} onChange={set('smtp_host')} placeholder="smtp.gmail.com" />
            </div>
            <div className="form-group">
              <label>SMTP Port</label>
              <input id="set-smtp-port" className="form-input" value={form.smtp_port} onChange={set('smtp_port')} placeholder="587" />
            </div>
          </div>
          <div className="form-row">
            <SecretInput id="set-smtp-user" label="SMTP Username / Email" value={form.smtp_user} onChange={set('smtp_user')} placeholder="you@gmail.com" />
            <SecretInput id="set-smtp-pass" label="SMTP Password / App Password" value={form.smtp_pass} onChange={set('smtp_pass')} placeholder="••••••••" />
          </div>
        </Section>

        <button id="save-settings-btn" type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? <span className="spinner" /> : <Check size={16} />}
          {saving ? 'Saving…' : 'Save All Settings'}
        </button>
      </form>

      <div className="divider" />

      <Section title="🔒 Change Password">
        <form onSubmit={handlePwChange}>
          <div className="form-row">
            <SecretInput id="set-pw-current" label="Current Password" value={pwForm.current_password} onChange={e => setPwForm(f => ({...f,current_password:e.target.value}))} placeholder="••••••••" />
            <SecretInput id="set-pw-new"     label="New Password"     value={pwForm.new_password}     onChange={e => setPwForm(f => ({...f,new_password:e.target.value}))}     placeholder="Min. 8 chars" />
          </div>
          <button id="change-pw-btn" type="submit" className="btn btn-secondary" disabled={pwSaving}>
            {pwSaving ? <span className="spinner" /> : null}
            {pwSaving ? 'Updating…' : 'Update Password'}
          </button>
        </form>
      </Section>
    </div>
  );
}
