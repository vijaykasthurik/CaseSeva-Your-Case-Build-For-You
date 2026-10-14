import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { clearToken, getHealth, getMe, logout } from "../api";
import { ArrowUpRight } from "lucide-react";
import AppFooter from "./AppFooter";

export default function AppHeader({ children }) {
  const [user, setUser] = useState(null);
  const [health, setHealth] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    getMe().then((result) => setUser(result.user)).catch(() => {});
    getHealth().then(setHealth).catch(() => {});
  }, []);

  const signOut = async () => {
    try { await logout(); }
    finally { clearToken(); window.sessionStorage.clear(); navigate("/login", { replace: true }); }
  };

  const isAdvocate = user?.role === "advocate";

  return (
    <div style={{ minHeight: "100dvh", display: "flex", flexDirection: "column", background: "#FFFFFF" }}>
      <header className="app-header">
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Link to={user ? (isAdvocate ? "/advocate/dashboard" : "/dashboard") : "/"} className="app-header__brand">
            <span>CaseSeva</span>
          </Link>
          {health?.processing_mode && (
            <span
              className="status-pill status-pill--grey"
              style={{ fontSize: "0.68rem", padding: "0.15rem 0.5rem" }}
              title={`Processing: ${health.processing_mode}; database: ${health.providers?.database}; storage: ${health.providers?.object_store}`}
            >
              {health.processing_mode}
            </span>
          )}
        </div>

        <nav className="app-header__nav">
          {user ? (
            <>
              <span className="app-header__user-pill" data-testid="header-user">
                {user.full_name}
              </span>
              {isAdvocate ? (
                <>
                  <Link to="/advocate/dashboard" className="app-header__link">Dashboard</Link>
                  <Link to="/advocate/inbox" className="app-header__link">Inbox</Link>
                </>
              ) : (
                <>
                  <Link to="/dashboard" className="app-header__link">Dashboard</Link>
                  <Link to="/advocates" className="app-header__link">Advocates</Link>
                </>
              )}
              <Link to="/profile" className="app-header__link">Profile</Link>
              <button type="button" className="btn-ghost" onClick={signOut}>
                Logout
              </button>
            </>
          ) : (
            <>
              <Link to="/" className="app-header__link">Home</Link>
              <Link to="/login" className="app-header__link">Log in</Link>
              <Link
                to="/signup"
                className="btn-pill-primary"
                style={{ padding: "0.55rem 1.4rem", fontSize: "0.85rem", gap: "0.35rem" }}
              >
                <span>Get Started</span>
                <ArrowUpRight size={15} />
              </Link>
            </>
          )}
        </nav>
      </header>

      {children && (
        <>
          <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            {children}
          </div>
          <AppFooter />
        </>
      )}
    </div>
  );
}
