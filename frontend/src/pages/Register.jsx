// src/pages/Register.jsx
import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Phone } from 'lucide-react';

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: '', email: '', password: '', company_name: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      await register(form.name, form.email, form.password, form.company_name);
      navigate('/app/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  const set = (key) => (e) => setForm(f => ({ ...f, [key]: e.target.value }));

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <div className="logo-circle"><Phone size={26} color="#fff" /></div>
          <h1>Create Account</h1>
          <p>Set up your AI calling workspace</p>
        </div>

        {error && <div className="alert alert-error">⚠️  {error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label>Full Name</label>
              <input id="reg-name" className="form-input" type="text" placeholder="Yash Shah" value={form.name} onChange={set('name')} required />
            </div>
            <div className="form-group">
              <label>Company Name</label>
              <input id="reg-company" className="form-input" type="text" placeholder="SM01 Industries" value={form.company_name} onChange={set('company_name')} />
            </div>
          </div>
          <div className="form-group">
            <label>Email Address</label>
            <input id="reg-email" className="form-input" type="email" placeholder="you@company.com" value={form.email} onChange={set('email')} required />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input id="reg-password" className="form-input" type="password" placeholder="Min. 8 characters" value={form.password} onChange={set('password')} required minLength={8} />
          </div>
          <button id="reg-submit" className="btn btn-primary w-full" type="submit" disabled={loading}>
            {loading ? <span className="spinner" /> : null}
            {loading ? 'Creating account…' : 'Create Account'}
          </button>
        </form>

        <div className="auth-footer">
          Already have an account? <Link to="/app/login">Sign in →</Link>
        </div>
      </div>
    </div>
  );
}
