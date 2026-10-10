import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Check, Clock, AlertTriangle, ShieldCheck, FileText, ChevronRight } from "lucide-react";
import {
  acceptAdvocateRequest,
  declineAdvocateRequest,
  getAdvocateCases,
  getAdvocateRequests,
  getMe,
} from "../api";

export default function AdvocateDashboardPage() {
  const [user, setUser] = useState(null);
  const [requests, setRequests] = useState([]);
  const [underReviewCases, setUnderReviewCases] = useState([]);
  const [finalisedCases, setFinalisedCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const meResult = await getMe();
      const currentUser = meResult.user;
      setUser(currentUser);

      const [reqResult, casesResult] = await Promise.all([
        getAdvocateRequests().catch(() => ({ requests: [] })),
        getAdvocateCases().catch(() => ({ under_review: [], finalised: [] })),
      ]);

      setRequests(reqResult.requests || []);
      setUnderReviewCases(casesResult.under_review || []);
      setFinalisedCases(casesResult.finalised || []);
    } catch (err) {
      console.error("Error loading advocate dashboard data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAccept = async (caseId) => {
    setBusy(true);
    try {
      await acceptAdvocateRequest(caseId);
      await loadData();
    } finally {
      setBusy(false);
    }
  };

  const handleDecline = async (caseId) => {
    const reason = window.prompt("Optional reason for declining this case request:") || "";
    setBusy(true);
    try {
      await declineAdvocateRequest(caseId, reason);
      await loadData();
    } finally {
      setBusy(false);
    }
  };

  const isPending = user?.verification_status !== "VERIFIED";

  return (
    <main className="main-container" style={{ paddingTop: "2.5rem", paddingBottom: "5rem" }}>
      {/* Header with Stacked Treatment */}
      <header style={{ marginBottom: "2.5rem" }}>
        <span className="eyebrow-label">ADVOCATE WORKSPACE</span>
        <div className="stacked-headline" style={{ margin: "0.4rem 0 0.75rem 0" }}>
          <div>WELCOME,</div>
          <div className="stacked-headline__accent">
            {user?.full_name ? user.full_name.toUpperCase() : "COUNSEL"}
          </div>
          <div className="hairline-gold" style={{ marginTop: "0.85rem", maxWidth: "160px" }} />
        </div>
        <p style={{ color: "var(--text-body)", fontSize: "0.95rem", maxWidth: "60ch", marginTop: "0.75rem" }}>
          Supervise AI legal intelligence, review grounded statutory grounds, and finalize court-ready deliverables for your clients.
        </p>
      </header>

      {/* PENDING verification alert — explicit and plain explanation */}
      {isPending && (
        <div
          data-testid="verification-pending-banner"
          style={{
            background: "#FAFAFA",
            border: "1px solid #000000",
            padding: "1.5rem 1.75rem",
            marginBottom: "3rem",
            display: "flex",
            alignItems: "flex-start",
            gap: "1.25rem",
          }}
        >
          <Clock size={22} style={{ color: "#000000", flexShrink: 0, marginTop: "0.15rem" }} />
          <div>
            <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "#000000", marginBottom: "0.35rem" }}>
              Account Verification Pending
            </h3>
            <p style={{ fontSize: "0.9rem", color: "var(--text-body)", lineHeight: 1.6 }}>
              Your advocate account is currently awaiting administrative verification.
              <strong> You cannot accept client representation requests</strong> until your enrolment credentials are confirmed through the administrative verification gate. You can still inspect incoming requests in your queue.
            </p>
          </div>
        </div>
      )}

      {/* ── SECTION 1: Pending Requests (FIRST) ── */}
      <section data-testid="pending-requests-section" style={{ marginBottom: "4rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem", paddingBottom: "0.75rem", borderBottom: "2px solid #000000" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "1rem" }}>
            <h2 data-testid="advocate-dashboard-heading" style={{ fontSize: "1.35rem", fontWeight: 700, color: "#000000" }}>
              Pending representation requests
            </h2>
            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 600 }}>
              ({requests.length})
            </span>
          </div>
          <Link
            to="/advocate/inbox"
            className="btn-text-link"
            style={{ fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.04em", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
          >
            <span>Full inbox</span>
            <ArrowUpRight size={14} />
          </Link>
        </div>

        {loading ? (
          <div style={{ padding: "3rem 0", color: "var(--text-muted)", fontSize: "0.9rem" }}>
            Loading pending requests…
          </div>
        ) : requests.length === 0 ? (
          <div style={{ padding: "2.5rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#000000", marginBottom: "0.35rem" }}>
              No pending client requests
            </h3>
            <p style={{ fontSize: "0.9rem", color: "var(--text-muted)", maxWidth: "55ch" }}>
              When clients approve their initial legal intelligence analysis and select your representation, their cases will appear here for your review and acceptance.
            </p>
          </div>
        ) : (
          <div>
            {requests.map((item) => (
              <article
                key={item.case_id}
                data-testid="advocate-request"
                style={{
                  padding: "1.75rem 0",
                  borderBottom: "1px solid var(--border-hairline)",
                  display: "grid",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
                  <div>
                    <span className="eyebrow-label" style={{ marginBottom: "0.35rem" }}>
                      Case #{item.case_id}
                    </span>
                    <h3 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#000000" }}>
                      {item.domain || "Legal Case"}{item.sub_domain ? ` · ${item.sub_domain}` : ""}
                    </h3>
                  </div>

                  <span style={{ fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", fontWeight: 600 }}>
                    Awaiting acceptance
                  </span>
                </div>

                {/* Summary decision metrics */}
                <div style={{ display: "flex", gap: "2.5rem", flexWrap: "wrap", fontSize: "0.9rem", color: "var(--text-body)" }}>
                  <div>
                    <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                      Jurisdiction / Forum
                    </span>
                    <strong style={{ color: "#000000" }}>{item.forum_level || "Jurisdiction pending verification"}</strong>
                  </div>
                  <div>
                    <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                      Evidence Provided
                    </span>
                    <strong style={{ color: "#000000" }}>{item.evidence_count} files attached</strong>
                  </div>
                  <div>
                    <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                      Unresolved Legal Risks
                    </span>
                    <strong style={{ color: item.unresolved_risks_count > 0 ? "var(--status-crimson)" : "#000000" }}>
                      {item.unresolved_risks_count} risk{item.unresolved_risks_count === 1 ? "" : "s"} flagged
                    </strong>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "1.5rem", paddingTop: "0.5rem" }}>
                  <button
                    type="button"
                    className="btn-text-link"
                    style={{ color: "var(--text-muted)", fontSize: "0.88rem" }}
                    onClick={() => handleDecline(item.case_id)}
                    disabled={busy || isPending}
                  >
                    Decline request
                  </button>
                  <button
                    type="button"
                    className="btn-pill-primary"
                    onClick={() => handleAccept(item.case_id)}
                    disabled={busy || isPending}
                  >
                    <span>Accept case</span>
                    <ArrowUpRight size={15} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* ── SECTION 2: Cases Under Review ── */}
      <section data-testid="cases-under-review-section" style={{ marginBottom: "4rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem", paddingBottom: "0.75rem", borderBottom: "2px solid #000000" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "1rem" }}>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "#000000" }}>
              Cases under review
            </h2>
            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 600 }}>
              ({underReviewCases.length})
            </span>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: "3rem 0", color: "var(--text-muted)", fontSize: "0.9rem" }}>
            Loading active reviews…
          </div>
        ) : underReviewCases.length === 0 ? (
          <div style={{ padding: "2.5rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#000000", marginBottom: "0.35rem" }}>
              No active reviews in progress
            </h3>
            <p style={{ fontSize: "0.9rem", color: "var(--text-muted)", maxWidth: "55ch" }}>
              Accepted representation requests move here into your review workspace where you verify AI-grounded legal provisions, evidence mappings, and counter-arguments.
            </p>
          </div>
        ) : (
          <div data-testid="cases-under-review-grid" style={{ display: "grid", gap: "1.75rem" }}>
            {underReviewCases.map((c) => {
              const approved = c.advocate_approved_items || [];
              const removed = c.advocate_removed_items || [];
              const total =
                (c.facts || []).filter((x) => !x.removed).length +
                (c.verified_legal_sections || []).filter((x) => !x.removed).length + 2 +
                (c.arguments?.opponent?.objections || []).length;
              const done = approved.length + removed.length;
              const outstanding = typeof c.outstanding_items_count === "number" ? c.outstanding_items_count : Math.max(total - done, 0);

              return (
                <article
                  key={c.case_id}
                  data-testid="advocate-case-card"
                  style={{
                    padding: "1.75rem 0",
                    borderBottom: "1px solid var(--border-hairline)",
                    display: "grid",
                    gap: "1rem",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
                    <div>
                      <span className="eyebrow-label" style={{ marginBottom: "0.35rem" }}>
                        Case #{c.case_id}
                      </span>
                      <h3 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#000000" }}>
                        {c.legal_domain?.domain || c.domain || "General Law"} &middot; {c.forum?.commission_level || c.forum_level || "Jurisdiction Pending"}
                      </h3>
                    </div>

                    <span
                      className={outstanding > 0 ? "status-pill status-pill--crimson" : ""}
                      style={{
                        fontSize: "0.82rem",
                        fontWeight: 700,
                        letterSpacing: "0.04em",
                        textTransform: "uppercase",
                        color: outstanding === 0 ? "#000000" : undefined,
                      }}
                    >
                      {outstanding === 0 ? "✓ Ready to finalize" : `${outstanding} item${outstanding === 1 ? "" : "s"} outstanding`}
                    </span>
                  </div>

                  <p style={{ fontSize: "0.92rem", color: "var(--text-body)", lineHeight: 1.6, maxWidth: "75ch" }}>
                    {c.client_story?.slice(0, 160) || c.preview || "Client story under review."}…
                  </p>

                  <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "0.5rem" }}>
                    <Link
                      to={`/advocate/review/${c.case_id}`}
                      className="btn-pill-primary"
                      style={{ textDecoration: "none" }}
                    >
                      <span>Open review workspace</span>
                      <ArrowUpRight size={15} />
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* ── SECTION 3: Finalised Cases ── */}
      <section data-testid="finalised-cases-section" style={{ marginBottom: "4rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem", paddingBottom: "0.75rem", borderBottom: "2px solid #000000" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "1rem" }}>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "#000000" }}>
              Finalised cases
            </h2>
            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontWeight: 600 }}>
              ({finalisedCases.length})
            </span>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: "3rem 0", color: "var(--text-muted)", fontSize: "0.9rem" }}>
            Loading finalised cases…
          </div>
        ) : finalisedCases.length === 0 ? (
          <div style={{ padding: "2.5rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#000000", marginBottom: "0.35rem" }}>
              No finalised cases yet
            </h3>
            <p style={{ fontSize: "0.9rem", color: "var(--text-muted)", maxWidth: "55ch" }}>
              Once you approve every legal ground and finalize review, court-ready documents are generated and available here for export.
            </p>
          </div>
        ) : (
          <div data-testid="finalised-cases-grid" style={{ display: "grid", gap: "1.5rem" }}>
            {finalisedCases.map((c) => (
              <article
                key={c.case_id}
                style={{
                  padding: "1.5rem 0",
                  borderBottom: "1px solid var(--border-hairline)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: "1.5rem",
                }}
              >
                <div>
                  <span className="eyebrow-label" style={{ marginBottom: "0.3rem" }}>
                    Case #{c.case_id}
                  </span>
                  <h3 style={{ fontSize: "1.15rem", fontWeight: 700, color: "#000000", marginBottom: "0.25rem" }}>
                    {c.legal_domain?.domain || c.domain || "Legal Case"}
                  </h3>
                  <p style={{ fontSize: "0.88rem", color: "var(--text-muted)" }}>
                    Review finalized &middot; Status: {c.status}
                  </p>
                </div>

                <Link
                  to={`/cases/${c.case_id}/documents`}
                  className="btn-pill-secondary"
                  style={{ textDecoration: "none" }}
                >
                  <FileText size={15} />
                  <span>View documents</span>
                  <ArrowUpRight size={14} />
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* ── SECTION 4: Advocate Profile & Verification Status ── */}
      <section data-testid="advocate-profile-section" style={{ borderTop: "2px solid #000000", paddingTop: "2.5rem" }}>
        <div style={{ marginBottom: "1.5rem" }}>
          <span className="eyebrow-label">ENROLMENT & PRACTICE</span>
          <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "#000000", marginTop: "0.25rem" }}>
            Advocate credentials & verification
          </h2>
        </div>

        {user && (
          <div style={{ display: "grid", gap: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <h3 style={{ fontSize: "1.15rem", fontWeight: 700, color: "#000000" }}>
                  {user.full_name}
                </h3>
                <p style={{ fontSize: "0.9rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                  {user.bar_council || "State Bar Council Enrolled"}
                </p>
              </div>

              <div>
                {user.verification_status === "VERIFIED" ? (
                  <span style={{ fontSize: "0.82rem", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: "#000000", display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                    <Check size={16} />
                    <span>Verified by CaseSeva admin review</span>
                  </span>
                ) : (
                  <span style={{ fontSize: "0.82rem", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                    <Clock size={16} />
                    <span>Pending Verification</span>
                  </span>
                )}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1.5rem", fontSize: "0.9rem", paddingTop: "1.25rem", borderTop: "1px solid var(--border-hairline)" }}>
              <div>
                <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                  Enrolment Record
                </span>
                <strong style={{ color: "#000000" }}>
                  {user.enrolment_number || "Not specified"} ({user.enrolment_year || "N/A"})
                </strong>
              </div>
              <div>
                <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                  Place of Practice
                </span>
                <strong style={{ color: "#000000" }}>
                  {user.place_of_practice || "N/A"}{user.court_region ? ` (${user.court_region})` : ""}
                </strong>
              </div>
              <div>
                <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                  Practice Domains
                </span>
                <strong style={{ color: "#000000" }}>
                  {Array.isArray(user.practice_domains) ? user.practice_domains.join(", ") : user.practice_domains || "General Practice"}
                </strong>
              </div>
              <div>
                <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                  Languages
                </span>
                <strong style={{ color: "#000000" }}>
                  {Array.isArray(user.languages) ? user.languages.join(", ") : user.languages || "English"}
                </strong>
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
