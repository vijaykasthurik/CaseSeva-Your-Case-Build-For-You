import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHealth } from "../api";
import { ArrowRight, Scale, FileText, ShieldCheck, Gavel, CheckCircle } from "lucide-react";
import AppHeader from "../components/AppHeader";

export default function HomePage() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getHealth().then(setHealth).catch((requestError) => {
      setError(requestError.message);
    });
  }, []);

  const dotClass = !health && !error
    ? "health-dot health-dot--loading"
    : health
      ? "health-dot health-dot--ok"
      : "health-dot health-dot--error";

  return (
    <div style={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <AppHeader />

      <main style={{ flex: 1 }}>
        {/* ── Hero Editorial ── */}
        <section className="main-container" style={{ paddingTop: "2rem", paddingBottom: "3rem" }}>
          <div className="hero-editorial">
            {/* Left Column */}
            <div>
              <div className="hero-eyebrow">
                <span className="gold-accent-line" style={{ width: 24, height: 2, marginBottom: 0, display: "inline-block" }} />
                LEGAL TECHNOLOGY FOR MODERN CASEWORK
              </div>

              <h1 className="hero-title">
                Your legal rights,<br />
                <span className="gold-highlight">clearly understood.</span>
              </h1>

              <p className="hero-description">
                CaseSeva organizes client casework, checks available legal sources,
                and helps advocates prepare professional documents —
                audited by enrolled advocates.
              </p>

              <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap", marginBottom: "2rem" }}>
                <Link to="/signup">
                  <button type="button" className="btn-primary btn-pill" style={{ padding: "0.85rem 2rem", fontSize: "0.95rem" }}>
                    Get Started <ArrowRight size={18} />
                  </button>
                </Link>
                <Link to="/login">
                  <button type="button" className="btn-secondary btn-pill" style={{ padding: "0.85rem 2rem", fontSize: "0.95rem" }}>
                    Log in
                  </button>
                </Link>
              </div>

              {/* Health status — keeps data-testid intact */}
              <span className="health-status-pill" data-testid="health-status">
                <span className={dotClass} />
                {health
                  ? `Backend status: ${health.status} · Processing: ${health.processing_mode} · Database: ${health.providers?.database} · Storage: ${health.providers?.object_store}`
                  : error
                    ? `Unable to reach backend: ${error}`
                    : "Checking backend health…"}
              </span>
            </div>

            {/* Right Column: Sophisticated Geometric Graphic */}
            <div className="hero-geometric-visual">
              <div className="geometric-panel-1">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <FileText size={20} color="#000" />
                  <span style={{ fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase" }}>INDIAN STATUTES</span>
                </div>
                <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "#333", marginBottom: "0.4rem" }}>Section 35 · Consumer Protection Act, 2019</div>
                <div style={{ fontSize: "0.72rem", color: "#707070", lineHeight: 1.4 }}>Only checked official sources may establish applicable law. Missing coverage requires advocate review.</div>
              </div>

              <div className="geometric-panel-2">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.8rem" }}>
                  <Scale size={20} color="#C0A030" />
                  <span style={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.1em", color: "#C0A030" }}>AUDITED</span>
                </div>
                <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "#FFF", marginBottom: "0.3rem" }}>Advocate Finalization</div>
                <div style={{ fontSize: "0.72rem", color: "#A0A0A0" }}>Human-in-the-loop review by Bar Council enrolled advocates.</div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Editorial Marquee ── */}
        <div className="marquee-strip">
          <div className="marquee-content">
            <span>VERIFIED STATUTORY GROUNDING</span>
            <span>·</span>
            <span>INDIAN CODE RETRIEVAL</span>
            <span>·</span>
            <span>ADVOCATE REVIEW WORKSPACE</span>
            <span>·</span>
            <span>AUTOMATED COMPLAINT DRAFTING</span>
            <span>·</span>
            <span>CONSUMER & LABOUR FORUMS</span>
            <span>·</span>
            <span>VERIFIED STATUTORY GROUNDING</span>
            <span>·</span>
            <span>INDIAN CODE RETRIEVAL</span>
            <span>·</span>
            <span>ADVOCATE REVIEW WORKSPACE</span>
          </div>
        </div>

        {/* ── Editorial Sections ── */}
        <section className="main-container">
          <div className="editorial-number">01 / ARCHITECTURE & PROCESS</div>
          <h2 style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.02em" }}>Designed for legal precision</h2>

          <div className="editorial-grid">
            <div className="editorial-card">
              <Scale size={28} color="#C0A030" style={{ marginBottom: "1.25rem" }} />
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.6rem" }}>Verified Statutes Only</h3>
              <p style={{ fontSize: "0.88rem", color: "var(--gray-text)", lineHeight: 1.6 }}>
                Every provision and citation is retrieved from official Government of India gazettes. No hallucinated section numbers or fictional precedents.
              </p>
            </div>

            <div className="editorial-card">
              <FileText size={28} color="#000000" style={{ marginBottom: "1.25rem" }} />
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.6rem" }}>Advocate-Reviewed Documents</h3>
              <p style={{ fontSize: "0.88rem", color: "var(--gray-text)", lineHeight: 1.6 }}>
                Generates a complete Legal Intelligence Report and statutory complaint draft formatted for the appropriate District or State Commission.
              </p>
            </div>

            <div className="editorial-card">
              <ShieldCheck size={28} color="#C0A030" style={{ marginBottom: "1.25rem" }} />
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.6rem" }}>Advocate Verification</h3>
              <p style={{ fontSize: "0.88rem", color: "var(--gray-text)", lineHeight: 1.6 }}>
                Advocates review facts, statutory sections, and evidence before document finalization. Filing requirements may still need confirmation.
              </p>
            </div>
          </div>
        </section>

        {/* ── Final Editorial Call-To-Action ── */}
        <section style={{ background: "var(--surface-beige)", padding: "5rem 2rem", borderTop: "1px solid var(--gray-light)" }}>
          <div style={{ maxWidth: 800, margin: "0 auto", textAlign: "center" }}>
            <div className="gold-accent-line" style={{ margin: "0 auto 1.5rem" }} />
            <h2 style={{ fontSize: "2.4rem", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: "1rem" }}>
              Experience modern Indian legal casework.
            </h2>
            <p style={{ fontSize: "1.05rem", color: "var(--gray)", marginBottom: "2.5rem" }}>
              Create an account as a client to analyze your case or register as a verified advocate to review incoming matters.
            </p>
            <Link to="/signup">
              <button type="button" className="btn-primary btn-pill" style={{ padding: "1rem 2.5rem", fontSize: "1rem" }}>
                Create Account <ArrowRight size={20} />
              </button>
            </Link>
          </div>
        </section>
      </main>

      {/* ── Footer ── */}
      <footer className="app-footer">
        <div className="footer-container">
          <div>
            <div className="footer-brand">CaseSeva</div>
            <p style={{ fontSize: "0.85rem", color: "var(--gray-text)", maxWidth: "28ch" }}>
              AI-assisted legal representation & statutory analysis for modern Indian courts.
            </p>
          </div>

          <div className="footer-col">
            <div className="footer-col-title">Product</div>
            <ul>
              <li><Link to="/signup">Client Intake</Link></li>
              <li><Link to="/signup">Advocate Workspace</Link></li>
              <li><Link to="/signup">Statute Analysis</Link></li>
            </ul>
          </div>

          <div className="footer-col">
            <div className="footer-col-title">Resources</div>
            <ul>
              <li><a href="#statutes">IndiaCode Retrieval</a></li>
              <li><a href="#forums">Consumer Commissions</a></li>
              <li><a href="#labor">Labour Forums</a></li>
            </ul>
          </div>

          <div className="footer-col">
            <div className="footer-col-title">Legal</div>
            <ul>
              <li><a href="#terms">Terms of Service</a></li>
              <li><a href="#privacy">Privacy Policy</a></li>
              <li><a href="#disclaimer">Advocate Disclaimer</a></li>
            </ul>
          </div>

          <div className="footer-col">
            <div className="footer-col-title">Contact</div>
            <ul>
              <li><a href="mailto:support@caseseva.ai">support@caseseva.ai</a></li>
              <li><a href="#help">Help Desk</a></li>
            </ul>
          </div>
        </div>

        <div style={{ maxWidth: "var(--content-width)", margin: "0 auto", paddingTop: "2rem", borderTop: "1px solid var(--gray-light)", display: "flex", justifyContent: "space-between", fontSize: "0.78rem", color: "var(--gray-text)" }}>
          <span>© {new Date().getFullYear()} CaseSeva.ai. All rights reserved.</span>
          <span>Designed for Indian Courts & Forums</span>
        </div>
      </footer>
    </div>
  );
}
