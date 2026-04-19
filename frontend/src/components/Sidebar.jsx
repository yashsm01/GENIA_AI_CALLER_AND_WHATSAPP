// src/components/Sidebar.jsx
import { NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Files, PhoneCall, Settings, LogOut, Phone } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const navItems = [
  { to: '/app/dashboard',  icon: <LayoutDashboard size={17} />, label: 'Dashboard' },
  { to: '/app/files',      icon: <Files size={17} />,           label: 'File Master' },
  { to: '/app/calls',      icon: <PhoneCall size={17} />,       label: 'Call History' },
  { to: '/app/settings',   icon: <Settings size={17} />,        label: 'Settings' },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => { logout(); navigate('/app/login'); };

  return (
    <div className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon"><Phone size={18} color="#fff" /></div>
        <span>AI Caller</span>
      </div>

      {navItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
        >
          {item.icon}
          {item.label}
        </NavLink>
      ))}

      <div className="sidebar-footer">
        <div style={{ padding: '8px 12px', marginBottom: '8px' }}>
          <div style={{ fontSize: '13px', fontWeight: 600 }}>{user?.name}</div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>{user?.email}</div>
        </div>
        <button className="nav-item" onClick={handleLogout} id="sidebar-logout">
          <LogOut size={17} />
          Sign Out
        </button>
      </div>
    </div>
  );
}
