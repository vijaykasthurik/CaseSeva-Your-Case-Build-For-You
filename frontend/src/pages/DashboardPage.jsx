import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMe, listCases } from "../api";
import { ArrowUpRight } from "lucide-react";
import AccountActivity from "../components/AccountActivity";
import { citizenStatus } from "../citizenLanguage";

/* Map backend status to status pill class modifier and human-readable label */
const STATUS_META = {
  SUBMITTED: { cls: "grey", label: "Submitted" },
  ENGINE1_RUNNING: { cls: "grey", label: "Understanding your case and checking sources" },
  ENGINE1_DONE: { cls: "gold", label: "Case understanding complete" },
  ENGINE2_RUNNING: { cls: "grey", label: "Argument analysis running" },
  ENGINE2_DONE: { cls: "gold", label: "Case overview available" },
  LEGAL_CORPUS_NOT_READY: { cls: "crimson", label: "Verified legal sources not ready" },
  REVIEW_REQUIRED: { cls: "crimson", label: "Review or additional processing required" },
  NEEDS_DOCUMENT: { cls: "crimson", label: "Additional evidence requested" },
  DRAFT:                  { cls: "grey",     label: "Draft" },
  READY_FOR_ANALYSIS:     { cls: "grey",     label: "Ready for analysis" },
  ANALYZING:              { cls: "grey",     label: "Analysing casework" },
  LEGAL_ANALYSIS_RUNNING: { cls: "grey",     label: "Legal analysis running" },
  AWAITING_PREVIEW_1:     { cls: "grey",     label: "Awaiting review 1" },
  PREVIEW_1_APPROVED:     { cls: "gold",     label: "Review 1 approved" },
  AWAITING_PREVIEW_2:     { cls: "grey",     label: "Awaiting legal review" },
  PREVIEW_2_APPROVED:     { cls: "gold",     label: "Statute verified" },
  AWAITING_ADVOCATE:      { cls: "grey",     label: "Awaiting advocate" },
  ADVOCATE_REVIEW:        { cls: "grey",     label: "Advocate reviewing" },
  DOCUMENTS_READY:        { cls: "gold",     label: "Documents ready" },
  DOCUMENTS_BLOCKED:      { cls: "crimson",  label: "Documents blocked" },
  ANALYSIS_FAILED:        { cls: "crimson",  label: "Analysis failed" },
  LEGAL_ANALYSIS_FAILED:  { cls: "crimson",  label: "Legal review failed" },
  ERROR:                  { cls: "crimson",  label: "Action required" },
};

function StatusPill({ status }) {
  const meta = { cls: STATUS_META[status]?.cls || "grey", label: citizenStatus(status).label };
  return (
    <span className={`status-pill status-pill--${meta.cls}`}>
      {meta.label}
    </span>
  );
}

export default function DashboardPage() {
  const [cases, setCases] = useState(null);
  const [user, setUser] = useState(null);

  useEffect(() => {
    getMe().then((result) => setUser(result.user)).catch(() => {});
    listCases().then((result) => setCases(result.cases)).catch(() => setCases([]));
  }, []);

  return (
    <main className="main-container">
      <AccountActivity />
      {/* Editorial Stacked Headline Greeting */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "2rem", marginBottom: "3rem" }}>
        <div>
          <span className="eyebrow-label">CLIENT WORKSPACE</span>
          <div className="hairline-gold" />
          
          <div className="stacked-headline" style={{ marginBottom: "0.5rem" }}>
            <h1
              data-testid="dashboard-heading"
              className="headline-dominant"
              style={{ margin: 0, textTransform: "uppercase" }}
            >
              WELCOME{user ? `, ${user.full_name}` : ""}
            </h1>
            <span className="headline-connective">YOUR ACTIVE</span>
            <span className="headline-gold">LEGAL CASEWORK.</span>
          </div>
          
          <p style={{ fontSize: "1.05rem", color: "var(--text-body)", maxWidth: "48ch" }}>
            Review grounded statutory citations, track advocate finalization, and manage court-ready filings.
          </p>
        </div>

        {/* Primary Unmissable Black Pill Action */}
        <Link to="/cases/new" className="btn-pill-primary" style={{ padding: "0.95rem 2.4rem", fontSize: "1rem" }}>
          <span>Start a new case</span>
          <ArrowUpRight size={18} />
        </Link>
      </div>

      <hr className="hairline-rule" style={{ margin: "1rem 0 2.5rem" }} />

      {/* Cases Section */}
      <section data-testid="your-cases">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1.75rem" }}>
          <h2 style={{ fontSize: "1.35rem", fontWeight: 800, letterSpacing: "-0.02em", color: "#000000" }}>
            Your cases
          </h2>
          {cases !== null && (
            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 600 }}>
              {cases.length} case{cases.length !== 1 ? "s" : ""} on record
            </span>
          )}
        </div>

        <div data-testid="case-list">
          {/* Empty State */}
          {cases?.length === 0 && (
            <div className="empty-state" data-testid="empty-cases">
              <span className="eyebrow-label" style={{ marginBottom: "0.5rem" }}>NO CASEWORK FOUND</span>
              <p className="empty-state__title">Begin your first case inquiry</p>
              <p className="empty-state__body">
                CaseSeva analyzes your factual narrative against verified Indian central statutes, retrieves grounded sections, and prepares court-ready draft pleadings for advocate review.
              </p>
              <Link to="/cases/new" className="btn-pill-primary">
                <span>Start a new case</span>
                <ArrowUpRight size={16} />
              </Link>
            </div>
          )}

          {/* Loading Skeleton */}
          {cases === null && (
            <div style={{ borderTop: "1px solid var(--border-hairline)" }}>
              {[1, 2, 3].map((i) => (
                <div key={i} style={{ padding: "1.75rem 0", borderBottom: "1px solid var(--border-hairline)", opacity: 0.4 }}>
                  <div style={{ height: 18, width: "45%", background: "#EAEAEA", borderRadius: 3, marginBottom: 10 }} />
                  <div style={{ height: 14, width: "70%", background: "#F2F2F2", borderRadius: 3 }} />
                </div>
              ))}
            </div>
          )}

          {/* Editorial Case List — direct on white with clean hairline separators, NO cards */}
          {cases?.length > 0 && (
            <div className="editorial-case-list">
              {cases.map((item) => (
                <Link to={`/cases/${item.case_id}`} key={item.case_id} style={{ textDecoration: "none" }}>
                  <article className="case-card" data-testid="case-card">
                    <div className="case-card__top">
                      <h2 className="case-card__title">{item.title}</h2>
                      <StatusPill status={item.status} />
                    </div>
                    <p className="case-card__preview">{item.preview || "No narrative details recorded yet."}</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center", marginTop: "0.75rem", fontSize: "0.8rem" }}>
                      <span style={{ color: "var(--text-muted)", marginRight: "0.5rem" }}>
                        Updated: {item.updated_at ? new Date(item.updated_at).toLocaleDateString() : "Recently"}
                      </span>
                      {item.clarification_needed && (
                        <span style={{ padding: "0.2rem 0.55rem", background: "#FEF2F2", color: "#991B1B", border: "1px solid #FCA5A5", borderRadius: "12px", fontWeight: 600 }}>
                          Details requested
                        </span>
                      )}
                      {item.engine1_available && (
                        <span style={{ padding: "0.2rem 0.55rem", background: "#F0FDF4", color: "#166534", border: "1px solid #86EFAC", borderRadius: "12px", fontWeight: 600 }}>
                          Case Understanding v{item.engine1_version || 1}
                        </span>
                      )}
                      {item.engine2_state === "RUN" && (
                        <span style={{ padding: "0.2rem 0.55rem", background: "#F5F3FF", color: "#5B21B6", border: "1px solid #DDD6FE", borderRadius: "12px", fontWeight: 600 }}>
                          Strengthened
                        </span>
                      )}
                      {item.engine2_state === "STALE" && (
                        <span style={{ padding: "0.2rem 0.55rem", background: "#FFFBEB", color: "#92400E", border: "1px solid #FCD34D", borderRadius: "12px", fontWeight: 600 }}>
                          Strengthen: Rerun available
                        </span>
                      )}
                      {item.advocate_connection_status === "REQUESTED" && (
                        <span style={{ padding: "0.2rem 0.55rem", background: "#EFF6FF", color: "#1E40AF", border: "1px solid #93C5FD", borderRadius: "12px", fontWeight: 600 }}>
                          Advocate Requested
                        </span>
                      )}
                      {item.advocate_connection_status === "CONNECTED" && (
                        <span style={{ padding: "0.2rem 0.55rem", background: "#ECFDF5", color: "#065F46", border: "1px solid #6EE7B7", borderRadius: "12px", fontWeight: 600 }}>
                          Advocate Connected
                        </span>
                      )}
                    </div>
                  </article>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
