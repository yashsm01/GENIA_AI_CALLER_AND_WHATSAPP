// src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import FileMaster from './pages/FileMaster';
import CallHistory from './pages/CallHistory';
import Settings from './pages/Settings';

function PrivateLayout() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/app/login" replace />;
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <Routes>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="files"     element={<FileMaster />} />
          <Route path="calls"     element={<CallHistory />} />
          <Route path="settings"  element={<Settings />} />
          <Route index            element={<Navigate to="dashboard" replace />} />
        </Routes>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/app/login"    element={<Login />} />
          <Route path="/app/register" element={<Register />} />
          <Route path="/app/*"        element={<PrivateLayout />} />
          <Route path="*"             element={<Navigate to="/app/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
