import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getCase,
  getCaseStatus,
  chooseEngine2,
  grantCaseAccess,
  getCaseGrants,
  revokeCaseAccess,
  uploadEvidence,
  reprocessInput,
  migrateCaseWorkflow,
  startLegalFoundation,
  cancelAdvocateRequest,
  getCaseHandoff,
} from "../api";
import ClarificationPanel from "../components/ClarificationPanel";
import { citizenStatus, stageLabel, readiness, legalStatusExplanation } from "../citizenLanguage";
import CaseCommunication from "../components/CaseCommunication";
import { ArrowLeft, ShieldCheck, AlertCircle, RefreshCw, FileText, CheckCircle2, UserCheck, ShieldAlert, ChevronRight } from "lucide-react";

export default function EngineCasePage() {
  const { caseId } = useParams();
  const [item, setItem] = useState(null);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState("");
  const [grants, setGrants] = useState([]);
  const [scopes, setScopes] = useState(["story", "case_file", "engine2", "evidence"]);
  const [sharedEvidence, setSharedEvidence] = useState(null);
  const [handoff, setHandoff] = useState(null);
  const [showHandoffModal, setShowHandoffModal] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const [data, status] = await Promise.all([getCase(caseId), getCaseStatus(caseId)]);
        if (active) {
          setItem(data.case);
          setProgress(status);
        }
      } catch (failure) {
        if (active) setError(failure.message);
      }
    }
    refresh();
    const timer = setInterval(refresh, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [caseId]);

  useEffect(() => {
    getCaseGrants(caseId)
      .then((result) => setGrants(result.grants || []))
      .catch(() => {});
  }, [caseId, item?.status]);

  if (!item) {
    return (
      <main className="main-container">
        <p role="status">{error || "Loading case details…"}</p>
      </main>
    );
  }

  const overview = item.overview || {};
  const presentation = citizenStatus(progress?.status || item.status);
  if (item.filing_update?.status === item.status) {
    presentation.source = item.filing_update.source_label;
  }

  const legalStatus = legalStatusExplanation(overview.legal_foundation_status || item.legal_foundation_status);
  const isEngineRunning = ["ENGINE1_RUNNING", "LEGAL_FOUNDATION_IN_PROGRESS", "ENGINE2_RUNNING"].includes(item.status);
  const isAwaitingClarification = item.status === "AWAITING_CLIENT_INFO";
  const isStaleEngine2 = overview.engine2_stale || item.engine2_stale;
  const isAdvocateRequested = item.advocate_connection_status === "REQUESTED" || (item.requested_advocate_id && !item.assigned_advocate_id);
  const isAdvocateAccepted = item.advocate_connection_status === "ACCEPTED" || Boolean(item.assigned_advocate_id);

  const activeGrants = grants.filter(
    (g) => !g.revoked_at && (!g.expires_at || new Date(g.expires_at) > new Date())
  );

  async function handleEngine2(run) {
    setActionBusy(true);
    setError("");
    try {
      await chooseEngine2(caseId, run);
      const res = await getCase(caseId);
      setItem(res.case);
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  }

  async function handleCancelAdvocate() {
    setActionBusy(true);
    setError("");
    try {
      await cancelAdvocateRequest(caseId);
      const res = await getCase(caseId);
      setItem(res.case);
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  }

  async function handleGrantConsent() {
    setActionBusy(true);
    setError("");
    try {
      const selectedEvidence = scopes.includes("evidence")
        ? sharedEvidence || (item.evidence || []).map((e) => e.evidence_id)
        : [];
      await grantCaseAccess(caseId, {
        scopes,
        evidence_ids: selectedEvidence,
        expires_in_hours: 168,
      });
      const [caseRes, grantsRes] = await Promise.all([getCase(caseId), getCaseGrants(caseId)]);
      setItem(caseRes.case);
      setGrants(grantsRes.grants || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  }

  async function handleRevokeGrant(grantId) {
    setActionBusy(true);
    setError("");
    try {
      await revokeCaseAccess(caseId, grantId);
      const [caseRes, grantsRes] = await Promise.all([getCase(caseId), getCaseGrants(caseId)]);
      setItem(caseRes.case);
      setGrants(grantsRes.grants || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  }

  async function handleViewHandoff() {
    setError("");
    try {
      const res = await getCaseHandoff(caseId);
      setHandoff(res.handoff);
      setShowHandoffModal(true);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="main-container content-narrow" style={{ paddingBottom: "5rem" }}>
      {/* Back Link */}
      <div style={{ marginBottom: "1.5rem" }}>
        <Link to="/dashboard" style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", textDecoration: "none", color: "var(--text-muted)", fontSize: "0.9rem" }}>
          <ArrowLeft size={16} />
          <span>Back to active cases</span>
        </Link>
      </div>

      {/* Editorial Header */}
      <header style={{ marginBottom: "2rem" }}>
        <span className="eyebrow-label">CASE DOSSIER</span>
        <h1 style={{ fontSize: "2rem", fontWeight: 800, margin: "0.4rem 0 0.5rem" }}>
          Case Overview
        </h1>
        {item.public_case_id && (
          <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: 0 }}>
            Reference: <strong>{item.public_case_id}</strong>
          </p>
        )}
      </header>

      {/* Status Banner */}
      <section style={{ background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: "8px", padding: "1.25rem 1.5rem", marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <span style={{ fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.05em", color: "var(--text-muted)", textTransform: "uppercase" }}>
              CURRENT STATUS
            </span>
            <p data-testid="case-status" style={{ fontSize: "1.15rem", fontWeight: 700, color: "#111827", margin: "0.25rem 0" }}>
              {presentation.label}
            </p>
            <p style={{ fontSize: "0.9rem", color: "#4B5563", margin: 0 }}>
              {presentation.explanation}
            </p>
          </div>
          {progress?.current_stage && isEngineRunning && (
            <div style={{ background: "#EFF6FF", border: "1px solid #BFDBFE", borderRadius: "6px", padding: "0.5rem 0.85rem" }}>
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "#1E40AF", display: "block" }}>PROCESSING STAGE</span>
              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#1D4ED8" }}>{stageLabel(progress.current_stage)}</span>
            </div>
          )}
        </div>
      </section>

      {/* Communications & Clarifications */}
      <CaseCommunication item={item} onSaved={async () => setItem((await getCase(caseId)).case)} />

      {isAwaitingClarification && item.clarification && (
        <section style={{ marginBottom: "2.5rem" }}>
          <ClarificationPanel
            caseId={caseId}
            batch={item.clarification}
            evidence={item.evidence}
            onSaved={async () => setItem((await getCase(caseId)).case)}
          />
        </section>
      )}

      {error && (
        <div role="alert" style={{ background: "#FEF2F2", border: "1px solid #F87171", borderRadius: "6px", padding: "0.85rem 1.25rem", color: "#991B1B", marginBottom: "1.5rem" }}>
          {error}
        </div>
      )}

      {/* Case Journey Tracker */}
      <nav aria-label="Case journey" style={{ margin: "2rem 0" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", display: "block", marginBottom: "0.75rem" }}>
          CITIZEN JOURNEY PROGRESS
        </span>
        <ol style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.5rem", listStyle: "none", padding: 0, margin: 0 }}>
          {[
            { label: "1. Story & Files", active: true, done: Boolean(item.client_story) },
            { label: "2. Understanding", active: item.engine1_available, done: item.engine1_available },
            { label: "3. Legal Sources", active: item.engine1_available, done: overview.legal_foundation_status === "VERIFIED_AUTHORITY" },
            { label: "4. Strengthen Case", active: overview.argument_analysis_run, done: overview.argument_analysis_run && !isStaleEngine2 },
            { label: "5. Legal Help", active: isAdvocateRequested || isAdvocateAccepted, done: isAdvocateAccepted && activeGrants.length > 0 },
          ].map((step, idx) => (
            <li
              key={idx}
              style={{
                background: step.done ? "#F0FDF4" : step.active ? "#F9FAFB" : "#FFFFFF",
                border: step.done ? "1px solid #86EFAC" : step.active ? "1px solid #000000" : "1px solid #E5E7EB",
                borderRadius: "6px",
                padding: "0.6rem 0.75rem",
                fontSize: "0.8rem",
                fontWeight: step.done || step.active ? 700 : 500,
                color: step.done ? "#166534" : step.active ? "#000000" : "#9CA3AF",
              }}
            >
              {step.label}
            </li>
          ))}
        </ol>
      </nav>

      {/* Main Case Overview Content */}
      {item.engine1_available && (
        <div style={{ marginTop: "2.5rem" }}>
          {/* Summary */}
          <section style={{ marginBottom: "2.5rem" }}>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 800, borderBottom: "1px solid #E5E7EB", paddingBottom: "0.5rem" }}>
              What happened
            </h2>
            <p style={{ fontSize: "1rem", lineHeight: 1.6, color: "#1F2937" }}>
              {overview.summary}
            </p>
          </section>

          {/* Key Facts */}
          <section style={{ marginBottom: "2.5rem" }}>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 800, borderBottom: "1px solid #E5E7EB", paddingBottom: "0.5rem" }}>
              Important facts
            </h2>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {overview.key_facts?.map((fact, index) => {
                const badge = {
                  STATED_BY_USER: { text: "From your account", bg: "#EFF6FF", color: "#1E40AF" },
                  SUPPORTED_BY_EVIDENCE: { text: "Supported by documents", bg: "#F0FDF4", color: "#166534" },
                  UNVERIFIED: { text: "Still needs checking", bg: "#FEF2F2", color: "#991B1B" },
                }[fact.source_status] || { text: "Needs review", bg: "#F3F4F6", color: "#4B5563" };

                return (
                  <li key={index} style={{ padding: "0.85rem 0", borderBottom: "1px solid #F3F4F6", display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "1rem" }}>
                    <span style={{ fontSize: "0.95rem", color: "#111827", lineHeight: 1.5 }}>{fact.text}</span>
                    <span style={{ fontSize: "0.75rem", fontWeight: 600, background: badge.bg, color: badge.color, padding: "0.2rem 0.55rem", borderRadius: "10px", whiteSpace: "nowrap" }}>
                      {badge.text}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>

          {/* Timeline */}
          {overview.timeline?.length > 0 && (
            <section style={{ marginBottom: "2.5rem" }}>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 800, borderBottom: "1px solid #E5E7EB", paddingBottom: "0.5rem" }}>
                Timeline of events
              </h2>
              <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {overview.timeline.map((event, index) => (
                  <li key={index} style={{ padding: "0.75rem 0", borderBottom: "1px solid #F3F4F6" }}>
                    <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--text-muted)", display: "block" }}>
                      {event.date || "Date unknown"}
                    </span>
                    <span style={{ fontSize: "0.95rem", color: "#111827" }}>{event.event || event.description}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Parties Involved */}
          {overview.parties?.length > 0 && (
            <section style={{ marginBottom: "2.5rem" }}>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 800, borderBottom: "1px solid #E5E7EB", paddingBottom: "0.5rem" }}>
                People and organizations involved
              </h2>
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {overview.parties.map((party, index) => (
                  <li key={index} style={{ padding: "0.6rem 0", borderBottom: "1px solid #F3F4F6" }}>
                    <strong style={{ color: "#111827" }}>{party.name}</strong>
                    {party.role && <span style={{ color: "var(--text-muted)", marginLeft: "0.5rem" }}>({party.role})</span>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Evidence You Have */}
          <section style={{ marginBottom: "2.5rem" }}>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 800, borderBottom: "1px solid #E5E7EB", paddingBottom: "0.5rem" }}>
              Evidence you have provided
            </h2>
            {item.evidence?.length > 0 ? (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {item.evidence.map((ev) => (
                  <li key={ev.evidence_id} style={{ padding: "0.6rem 0", borderBottom: "1px solid #F3F4F6", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span>
                      <strong>{ev.filename}</strong>{" "}
                      <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>({ev.evidence_id})</span>
                    </span>
                    <span style={{ fontSize: "0.8rem", color: "#059669", fontWeight: 600 }}>Recorded</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.95rem" }}>No files uploaded yet.</p>
            )}
          </section>

          {/* Legal Foundation UX */}
          <section style={{ marginBottom: "2.5rem", background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: "8px", padding: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.75rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 800, margin: 0 }}>Legal sources and status</h2>
              <span className={`status-pill status-pill--${legalStatus.cls}`}>
                {legalStatus.badge}
              </span>
            </div>
            <p style={{ fontSize: "0.95rem", color: "#374151", margin: "0 0 1rem" }}>
              {legalStatus.text}
            </p>

            {overview.applicable_law?.length > 0 ? (
              <div>
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, margin: "1rem 0 0.5rem" }}>Verified Provisions</h3>
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {overview.applicable_law.map((law) => (
                    <li key={law.provision_id} style={{ padding: "0.75rem", background: "#FFFFFF", border: "1px solid #E5E7EB", borderRadius: "6px", marginBottom: "0.5rem" }}>
                      <strong>{law.title}</strong>
                      <p style={{ fontSize: "0.85rem", color: "#4B5563", margin: "0.25rem 0 0" }}>{law.explanation}</p>
                      {law.source_url && (
                        <a href={law.source_url} target="_blank" rel="noreferrer" style={{ fontSize: "0.75rem", color: "#2563EB", textDecoration: "underline", display: "inline-block", marginTop: "0.25rem" }}>
                          Official source publication
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div style={{ background: "#FFFFFF", border: "1px dashed #D1D5DB", borderRadius: "6px", padding: "1rem", fontSize: "0.9rem", color: "#6B7280" }}>
                No statutory authority has been asserted as verified law. CaseSeva operates strictly fail-closed: statutory law is only cited after independent verification by an enrolled advocate.
              </div>
            )}

            {item.case_understanding_status === "READY" && !item.legal_foundation_status && (
              <button
                type="button"
                className="btn-pill-secondary"
                style={{ marginTop: "1rem" }}
                disabled={actionBusy}
                onClick={async () => {
                  try {
                    setActionBusy(true);
                    await startLegalFoundation(caseId);
                    setItem((await getCase(caseId)).case);
                  } catch (err) {
                    setError(err.message);
                  } finally {
                    setActionBusy(false);
                  }
                }}
              >
                Check relevant legal sources
              </button>
            )}
          </section>

          {/* Strengthen My Case (Engine 2) Section */}
          <section style={{ marginBottom: "2.5rem", border: "1px solid #000000", borderRadius: "8px", padding: "1.75rem", background: "#FFFFFF" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "0.5rem" }}>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 800, margin: 0 }}>
                Strengthen My Case
              </h2>
              {overview.argument_analysis_run && !isStaleEngine2 && (
                <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#166534", background: "#DCFCE7", padding: "0.25rem 0.65rem", borderRadius: "12px" }}>
                  Completed
                </span>
              )}
            </div>

            {/* Explanation & Run Controls */}
            {!overview.argument_analysis_run && (
              <div style={{ marginTop: "1rem" }}>
                <p style={{ fontSize: "0.95rem", color: "#374151", lineHeight: 1.5 }}>
                  CaseSeva will examine possible opposing arguments, evidence gaps, contradictions, and preparation risks. It does not predict whether you will win.
                </p>
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "1.25rem" }}>
                  <button
                    type="button"
                    className="btn-pill-primary"
                    disabled={actionBusy || isEngineRunning}
                    onClick={() => handleEngine2(true)}
                  >
                    Strengthen My Case
                  </button>
                  <button
                    type="button"
                    className="btn-pill-secondary"
                    disabled={actionBusy || isEngineRunning}
                    onClick={() => handleEngine2(false)}
                  >
                    Skip This
                  </button>
                </div>
              </div>
            )}

            {/* Stale Warning & Rerun */}
            {isStaleEngine2 && (
              <div style={{ marginTop: "1rem", background: "#FFFBEB", border: "1px solid #FCD34D", borderRadius: "6px", padding: "1rem" }}>
                <p style={{ fontWeight: 600, color: "#92400E", margin: "0 0 0.5rem" }}>
                  Analysis is based on older case information
                </p>
                <p style={{ fontSize: "0.85rem", color: "#78350F", margin: "0 0 1rem" }}>
                  New story details or evidence were added after your last challenge check. You can run Strengthen My Case again to update with your latest information.
                </p>
                <button
                  type="button"
                  className="btn-pill-secondary"
                  disabled={actionBusy || isEngineRunning}
                  onClick={() => handleEngine2(true)}
                >
                  Run again with latest case information
                </button>
              </div>
            )}

            {/* Skipped Disclosure */}
            {item.engine2_choice === "SKIP" && !overview.argument_analysis_run && (
              <div style={{ marginTop: "1rem", padding: "0.85rem", background: "#F9FAFB", borderRadius: "6px", color: "var(--text-muted)", fontSize: "0.9rem" }}>
                Case Challenge / Argument Analysis was not run.
              </div>
            )}

            {/* Completed Challenge Results */}
            {overview.argument_analysis_run && (
              <div style={{ marginTop: "1.5rem" }}>
                <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontStyle: "italic", marginBottom: "1.25rem" }}>
                  {overview.argument_analysis_note}
                </p>

                {/* Key Challenges / Opposing Arguments */}
                {overview.key_challenges?.length > 0 && (
                  <div style={{ marginBottom: "1.5rem" }}>
                    <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#111827", marginBottom: "0.5rem" }}>
                      What the other side may argue
                    </h3>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {overview.key_challenges.map((challenge, idx) => (
                        <li key={idx} style={{ padding: "0.75rem", background: "#FEF2F2", border: "1px solid #FEE2E2", borderRadius: "6px", marginBottom: "0.5rem", fontSize: "0.9rem", color: "#991B1B", lineHeight: 1.4 }}>
                          {challenge}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Evidence Gaps */}
                {overview.evidence_gaps?.length > 0 && (
                  <div style={{ marginBottom: "1.5rem" }}>
                    <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#111827", marginBottom: "0.5rem" }}>
                      Evidence that could help
                    </h3>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {overview.evidence_gaps.map((gap, idx) => (
                        <li key={idx} style={{ padding: "0.6rem 0", borderBottom: "1px solid #F3F4F6", fontSize: "0.9rem", color: "#374151" }}>
                          • {gap}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Preparation Actions */}
                {overview.preparation_actions?.length > 0 && (
                  <div style={{ marginBottom: "1.5rem" }}>
                    <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#111827", marginBottom: "0.5rem" }}>
                      What you can prepare next
                    </h3>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {overview.preparation_actions.map((act, idx) => (
                        <li key={idx} style={{ padding: "0.6rem 0", borderBottom: "1px solid #F3F4F6", fontSize: "0.9rem", color: "#15803D", fontWeight: 500 }}>
                          ✓ {act}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Legal Authority Limitations */}
                {overview.legal_authority_limitations?.length > 0 && (
                  <div style={{ background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: "6px", padding: "0.85rem", fontSize: "0.85rem", color: "#6B7280" }}>
                    <strong>Legal Source Limitations:</strong>
                    <ul style={{ margin: "0.35rem 0 0 1.25rem", padding: 0 }}>
                      {overview.legal_authority_limitations.map((lim, idx) => (
                        <li key={idx}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Get Legal Help Section */}
          <section style={{ marginBottom: "2.5rem", background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: "8px", padding: "1.75rem" }}>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 800, margin: "0 0 0.5rem" }}>
              Get Legal Help
            </h2>
            <p style={{ fontSize: "0.95rem", color: "#4B5563", margin: "0 0 1.25rem", lineHeight: 1.5 }}>
              Connect with an authenticated, Bar Council-enrolled advocate to review your case, conduct formal representation, and prepare court filings.
            </p>

            {/* State: Not yet requested */}
            {!isAdvocateRequested && !isAdvocateAccepted && (
              <div>
                <Link to={`/advocates?caseId=${caseId}`} className="btn-pill-primary" style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", textDecoration: "none" }}>
                  <span>Browse Verified Advocates</span>
                  <ChevronRight size={16} />
                </Link>
              </div>
            )}

            {/* State: Requested, awaiting response */}
            {isAdvocateRequested && !isAdvocateAccepted && (
              <div style={{ background: "#EFF6FF", border: "1px solid #BFDBFE", borderRadius: "6px", padding: "1rem" }}>
                <p style={{ fontWeight: 700, color: "#1E40AF", margin: "0 0 0.25rem" }}>
                  Connection Request Sent
                </p>
                <p style={{ fontSize: "0.9rem", color: "#1D4ED8", margin: "0 0 1rem" }}>
                  Your request is waiting for the advocate to accept. Case documents have not been shared.
                </p>
                <button
                  type="button"
                  className="btn-pill-secondary"
                  disabled={actionBusy}
                  onClick={handleCancelAdvocate}
                >
                  Cancel Request
                </button>
              </div>
            )}

            {/* State: Advocate Accepted -> Explicit Consent Controls */}
            {isAdvocateAccepted && (
              <div style={{ background: "#F0FDF4", border: "1px solid #86EFAC", borderRadius: "6px", padding: "1.25rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                  <CheckCircle2 size={20} color="#15803D" />
                  <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#166534", margin: 0 }}>
                    Advocate Accepted Your Connection
                  </h3>
                </div>
                <p style={{ fontSize: "0.9rem", color: "#14532D", margin: "0 0 1.25rem" }}>
                  The advocate is ready to review your case. <strong>Your case details and evidence have NOT been shared yet.</strong> Choose the exact scopes you wish to share below and grant explicit consent.
                </p>

                {/* Active Grants Display */}
                {activeGrants.length > 0 && (
                  <div style={{ background: "#FFFFFF", border: "1px solid #BBF7D0", borderRadius: "6px", padding: "1rem", marginBottom: "1.25rem" }}>
                    <p style={{ fontWeight: 700, fontSize: "0.9rem", color: "#166534", margin: "0 0 0.5rem" }}>
                      Active Sharing Grant
                    </p>
                    {activeGrants.map((grant) => (
                      <div key={grant.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                        <span style={{ fontSize: "0.85rem", color: "#374151" }}>
                          Valid until {grant.expires_at ? new Date(grant.expires_at).toLocaleString() : "indefinite"}
                          {grant.engine1_case_file_version && ` (Case File v${grant.engine1_case_file_version})`}
                        </span>
                        <div style={{ display: "flex", gap: "0.5rem" }}>
                          <button
                            type="button"
                            className="btn-pill-secondary"
                            style={{ padding: "0.3rem 0.75rem", fontSize: "0.8rem" }}
                            onClick={handleViewHandoff}
                          >
                            View Handoff Record
                          </button>
                          <button
                            type="button"
                            style={{ padding: "0.3rem 0.75rem", fontSize: "0.8rem", background: "#FEE2E2", color: "#991B1B", border: "1px solid #FCA5A5", borderRadius: "4px", cursor: "pointer" }}
                            disabled={actionBusy}
                            onClick={() => handleRevokeGrant(grant.id)}
                          >
                            Revoke Access
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Consent Grant Form */}
                {activeGrants.length === 0 && (
                  <div style={{ background: "#FFFFFF", border: "1px solid #D1D5DB", borderRadius: "6px", padding: "1.25rem" }}>
                    <h4 style={{ fontSize: "0.95rem", fontWeight: 700, margin: "0 0 0.75rem" }}>Select What to Share</h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "1.25rem" }}>
                      {[
                        ["story", "Your factual narrative and written story"],
                        ["case_file", "Structured case understanding, timeline, and parties"],
                        ["engine2", "Strengthen My Case challenge analysis (Engine 2)"],
                        ["evidence", "Uploaded evidence documents"],
                      ].map(([scopeKey, label]) => (
                        <label key={scopeKey} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem", color: "#374151" }}>
                          <input
                            type="checkbox"
                            checked={scopes.includes(scopeKey)}
                            onChange={(e) => {
                              setScopes(
                                e.target.checked
                                  ? [...scopes, scopeKey]
                                  : scopes.filter((s) => s !== scopeKey)
                              );
                            }}
                          />
                          <span>{label}</span>
                        </label>
                      ))}
                    </div>

                    {scopes.includes("evidence") && item.evidence?.length > 0 && (
                      <div style={{ marginBottom: "1.25rem", paddingLeft: "1.5rem" }}>
                        <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-muted)", display: "block", marginBottom: "0.35rem" }}>
                          Select specific documents:
                        </span>
                        {item.evidence.map((ev) => (
                          <label key={ev.evidence_id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", color: "#4B5563" }}>
                            <input
                              type="checkbox"
                              checked={(sharedEvidence || item.evidence.map((e) => e.evidence_id)).includes(ev.evidence_id)}
                              onChange={(e) => {
                                const current = sharedEvidence || item.evidence.map((e) => e.evidence_id);
                                setSharedEvidence(
                                  e.target.checked
                                    ? [...current, ev.evidence_id]
                                    : current.filter((id) => id !== ev.evidence_id)
                                );
                              }}
                            />
                            <span>{ev.filename} ({ev.evidence_id})</span>
                          </label>
                        ))}
                      </div>
                    )}

                    <button
                      type="button"
                      className="btn-pill-primary"
                      disabled={actionBusy || scopes.length === 0}
                      onClick={handleGrantConsent}
                    >
                      Grant Explicit Consent (7 Days)
                    </button>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Add missing material / retry */}
          {["NEEDS_DOCUMENT", "REVIEW_REQUIRED", "LEGAL_CORPUS_NOT_READY", "CASE_UNDERSTANDING_READY", "LEGAL_FOUNDATION_REVIEW_REQUIRED"].includes(item.status) && (
            <section style={{ marginBottom: "2.5rem", borderTop: "1px solid #E5E7EB", paddingTop: "1.5rem" }}>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 700, margin: "0 0 0.5rem" }}>
                Add more information or documents
              </h2>
              <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap" }}>
                <input
                  aria-label="Additional evidence"
                  type="file"
                  multiple
                  onChange={async (event) => {
                    try {
                      setActionBusy(true);
                      for (const file of Array.from(event.target.files)) {
                        await uploadEvidence(caseId, file);
                      }
                      setItem((await getCase(caseId)).case);
                    } catch (failure) {
                      setError(failure.message);
                    } finally {
                      setActionBusy(false);
                    }
                  }}
                />
                <button
                  type="button"
                  className="btn-pill-secondary"
                  disabled={actionBusy}
                  onClick={async () => {
                    try {
                      setActionBusy(true);
                      await reprocessInput(caseId);
                      setItem((await getCase(caseId)).case);
                    } catch (failure) {
                      setError(failure.message);
                    } finally {
                      setActionBusy(false);
                    }
                  }}
                >
                  Resume Analysis
                </button>
              </div>
            </section>
          )}

          {/* Next steps guidance */}
          <div style={{ background: "#F9FAFB", borderLeft: "4px solid #000000", padding: "1rem 1.25rem", margin: "2rem 0" }}>
            <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
              RECOMMENDED NEXT STEP
            </span>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.95rem", color: "#111827", fontWeight: 600 }}>
              {overview.next_step}
            </p>
          </div>
        </div>
      )}

      {/* Handoff Modal */}
      {showHandoffModal && handoff && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "#FFFFFF", padding: "2rem", borderRadius: "8px", maxWidth: "600px", width: "90%", maxHeight: "80vh", overflowY: "auto" }}>
            <h3 style={{ fontSize: "1.25rem", fontWeight: 800, margin: "0 0 1rem" }}>Structured Case Handoff Record</h3>
            <p style={{ fontSize: "0.85rem", color: "#4B5563" }}>
              This is the exact structured contract bound to Case File v{handoff.engine1_case_file_version || 1} that your advocate receives:
            </p>
            <div style={{ background: "#F3F4F6", padding: "1rem", borderRadius: "6px", fontSize: "0.85rem", margin: "1rem 0" }}>
              <p><strong>Case ID:</strong> {handoff.case_id}</p>
              <p><strong>Engine 1 Version:</strong> v{handoff.engine1_case_file_version}</p>
              <p><strong>Engine 2 Status:</strong> {handoff.engine2_disclosure}</p>
              <p><strong>Granted Scopes:</strong> {handoff.consent_scopes?.join(", ")}</p>
              <p><strong>Evidence Count:</strong> {handoff.evidence_references?.length || 0} shared documents</p>
              <p><strong>Legal Source Status:</strong> {handoff.provenance?.legal_foundation_status || "PENDING_SOURCE"}</p>
            </div>
            <button type="button" className="btn-pill-primary" onClick={() => setShowHandoffModal(false)}>
              Close Preview
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
