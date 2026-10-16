import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  getCase, getCaseStatus, generateDocuments, retryAnalysis, startAnalysis, startLegalAnalysis, cancelAdvocateRequest
} from "../api";
import { ArrowUpRight, Check, AlertCircle, ArrowRight } from "lucide-react";

const STAGE_NAMES = ["INTAKE", "FACT_EXTRACTION", "TIMELINE_CONSTRUCTION", "PARTY_IDENTIFICATION"];

export default function CaseDetailPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [item, setItem] = useState(null);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const refresh = () =>
    getCase(caseId)
      .then((result) => setItem(result.case))
      .catch((err) => setErrorMsg(err.message));

  useEffect(() => {
    refresh();
  }, [caseId]);

  useEffect(() => {
    if (!item || !["ANALYZING", "ANALYSIS_FAILED", "LEGAL_ANALYSIS_RUNNING", "LEGAL_ANALYSIS_FAILED", "GENERATING_DOCUMENTS"].includes(item.status)) return;
    const timer = setInterval(() => {
      getCaseStatus(caseId)
        .then((result) => {
          setStatus(result);
          if (!["ANALYZING", "LEGAL_ANALYSIS_RUNNING", "GENERATING_DOCUMENTS"].includes(result.status)) refresh();
        })
        .catch((err) => setErrorMsg(err.message));
    }, 250);
    return () => clearInterval(timer);
  }, [item?.status, caseId]);

  if (errorMsg) {
    return (
      <main className="main-container">
        <div role="alert" style={{ maxWidth: "680px", margin: "2rem auto" }}>
          <AlertCircle size={18} />
          <span>Error loading case: {errorMsg}</span>
        </div>
      </main>
    );
  }

  if (!item) {
    return (
      <main className="main-container" style={{ textAlign: "center", paddingTop: "5rem" }}>
        <span className="eyebrow-label">INITIALIZING</span>
        <p style={{ color: "var(--text-body)", fontSize: "1.05rem" }}>Loading casework file…</p>
      </main>
    );
  }

  const begin = async () => {
    setBusy(true);
    try {
      await startAnalysis(caseId);
      setStatus(await getCaseStatus(caseId));
      refresh();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setBusy(false);
    }
  };

  const retry = async () => {
    setBusy(true);
    try {
      await retryAnalysis(caseId);
      refresh();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setBusy(false);
    }
  };

  const beginLegal = async () => {
    setBusy(true);
    try {
      await startLegalAnalysis(caseId);
      setStatus(await getCaseStatus(caseId));
      refresh();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setBusy(false);
    }
  };

  const cancelAdvocate = async () => {
    setBusy(true);
    try {
      await cancelAdvocateRequest(caseId);
      refresh();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setBusy(false);
    }
  };

  const beginDocuments = async () => {
    setBusy(true);
    try {
      await generateDocuments(caseId);
      navigate(`/cases/${caseId}/documents`);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="main-container content-narrow" style={{ paddingBottom: "6rem" }}>
      {/* Editorial Stacked Header */}
      <div style={{ marginBottom: "2.5rem" }}>
        <span className="eyebrow-label">CASE MANAGEMENT</span>
        <div className="hairline-gold" />

        <div className="stacked-headline" style={{ marginBottom: "1rem" }}>
          <h1 className="headline-secondary" style={{ margin: 0 }}>
            {item.title || "CASE RECORD"}
          </h1>
          <span className="headline-connective">IDENTIFIER</span>
          <span className="headline-dominant" style={{ fontSize: "clamp(1.8rem, 3.8vw, 2.6rem)" }}>
            {item.case_id.slice(0, 12)}…
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
          <span data-testid="case-status" className="status-pill status-pill--grey" style={{ fontSize: "0.8rem", padding: "0.35rem 0.9rem" }}>
            Status: {item.status}
          </span>
          <span style={{ fontSize: "0.88rem", color: "var(--text-muted)" }}>
            Procedural Stage: <strong>{item.stage || "Not recorded"}</strong>
          </span>
        </div>
      </div>

      <hr className="hairline-rule" style={{ margin: "1.5rem 0 2.5rem" }} />

      {/* Primary Status Banner & Clear Next Action — Never a dead end */}
      <section style={{ marginBottom: "3rem" }}>
        {/* DRAFT */}
        {item.status === "DRAFT" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">NEXT ACTION</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Case intake is incomplete
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              Provide your factual story and supporting documents to proceed to automated legal intake.
            </p>
            <Link to={`/cases/${caseId}/edit`} className="btn-pill-primary">
              <span>Continue editing draft</span>
              <ArrowUpRight size={16} />
            </Link>
          </div>
        )}

        {/* READY_FOR_ANALYSIS */}
        {item.status === "READY_FOR_ANALYSIS" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">NEXT ACTION</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Ready for automated factual intake
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              Your case has been submitted. Launch the analysis pipeline to extract core material facts, timeline events, and party relationships.
            </p>
            <button type="button" className="btn-pill-primary" onClick={begin} disabled={busy}>
              <span>{busy ? "Starting analysis…" : "Start analysis"}</span>
              <ArrowUpRight size={16} />
            </button>
            <div data-testid="analysis-placeholder" style={{ marginTop: "1.5rem" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                Analysis has not started yet.
              </p>
            </div>
          </div>
        )}

        {/* ANALYZING */}
        {item.status === "ANALYZING" && (
          <div data-testid="analysis-progress" style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">PROCESSING</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Factual extraction in progress
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "2rem", maxWidth: "55ch" }}>
              The system is examining your client narrative and evidence attachments. Each stage completes and settles into the record.
            </p>
            <div style={{ display: "flex", flexDirection: "column", borderTop: "1px solid var(--border-hairline)" }}>
              {STAGE_NAMES.map((name) => {
                const st = (status?.stage_statuses || item.stage_statuses || {})[name] || "WAITING";
                const isComplete = st === "COMPLETED";
                return (
                  <div
                    key={name}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "1rem 0",
                      borderBottom: "1px solid var(--border-hairline)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      {isComplete ? <Check size={16} color="#000000" strokeWidth={2.5} /> : <div style={{ width: 16 }} />}
                      <span style={{ fontWeight: isComplete ? 700 : 500, color: isComplete ? "#000000" : "var(--text-body)" }}>
                        {name.replace(/_/g, " ")}
                      </span>
                    </div>
                    <span className="status-pill status-pill--grey" style={{ fontSize: "0.72rem" }}>
                      {st}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ANALYSIS_FAILED */}
        {item.status === "ANALYSIS_FAILED" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">PIPELINE HALTED</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Intake analysis failed
            </h2>
            <p role="alert" style={{ marginBottom: "1.5rem" }}>
              <span>Failed at {item.analysis_error?.stage}: {item.analysis_error?.message}</span>
            </p>
            <button type="button" className="btn-pill-primary" onClick={retry} disabled={busy}>
              <span>{busy ? "Retrying…" : "Retry failed stages"}</span>
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}

        {/* AWAITING_PREVIEW_1 */}
        {item.status === "AWAITING_PREVIEW_1" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">CLIENT AUDIT REQUIRED</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Confirm extracted facts and timeline
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              Review the facts extracted from your statement paired directly with their supporting evidence before any legal citations are retrieved.
            </p>
            <button type="button" className="btn-pill-primary" onClick={() => navigate(`/cases/${caseId}/preview1`)}>
              <span>Review Preview 1</span>
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}

        {/* PREVIEW_1_APPROVED */}
        {item.status === "PREVIEW_1_APPROVED" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">FACTS CONFIRMED</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Ready for legal analysis
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              Factual extraction has been audited and approved. Launch statutory analysis to query official central gazettes, map applicable sections, and evaluate forum jurisdiction.
            </p>
            <button type="button" className="btn-pill-primary" onClick={beginLegal} disabled={busy}>
              <span>{busy ? "Starting legal analysis…" : "Start legal analysis"}</span>
              <ArrowUpRight size={16} />
            </button>
            <div data-testid="analysis-placeholder" style={{ marginTop: "1.5rem" }}>
              <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                Legal analysis will evaluate applicable statutes, limitation periods, legal issues, and opponent objections once started.
              </p>
            </div>
          </div>
        )}

        {/* LEGAL_ANALYSIS_RUNNING */}
        {item.status === "LEGAL_ANALYSIS_RUNNING" && (
          <div data-testid="legal-analysis-progress" style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">RETRIEVING STATUTES</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Legal analysis pipeline running
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "2rem", maxWidth: "55ch" }}>
              Querying authorized statutory acts, verifying provision grounding, identifying issues, and assembling counter-objections.
            </p>
            <div style={{ display: "flex", flexDirection: "column", borderTop: "1px solid var(--border-hairline)" }}>
              {Object.entries(status?.stage_statuses || item.stage_statuses || {})
                .filter(([name]) => !STAGE_NAMES.includes(name))
                .map(([name, st]) => {
                  const isDone = st === "COMPLETED";
                  return (
                    <div
                      key={name}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "1rem 0",
                        borderBottom: "1px solid var(--border-hairline)",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        {isDone ? <Check size={16} color="#000000" strokeWidth={2.5} /> : <div style={{ width: 16 }} />}
                        <span style={{ fontWeight: isDone ? 700 : 500, color: isDone ? "#000000" : "var(--text-body)" }}>
                          {name.replace(/_/g, " ")}
                        </span>
                      </div>
                      <span className="status-pill status-pill--grey" style={{ fontSize: "0.72rem" }}>
                        {st}
                      </span>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {/* LEGAL_ANALYSIS_FAILED */}
        {item.status === "LEGAL_ANALYSIS_FAILED" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">LEGAL AUDIT HALTED</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Legal analysis failed
            </h2>
            <p role="alert" style={{ marginBottom: "1.5rem" }}>
              <span>Failed at {item.legal_analysis_error?.stage}: {item.legal_analysis_error?.message}</span>
            </p>
            <button type="button" className="btn-pill-primary" onClick={beginLegal} disabled={busy}>
              <span>{busy ? "Retrying…" : "Retry legal analysis"}</span>
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}

        {/* AWAITING_PREVIEW_2 */}
        {item.status === "AWAITING_PREVIEW_2" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">STATUTORY REVIEW READY</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Preview 2: review statutory analysis & objections
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              Examine verified statutory provisions, trapped rejected sections, opponent objections paired with counter-rebuttals, and limitation findings.
            </p>
            <button type="button" className="btn-pill-primary" onClick={() => navigate(`/cases/${caseId}/preview2`)}>
              <span>Review Preview 2</span>
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}

        {/* NEEDS_DOCUMENT */}
        {item.status === "NEEDS_DOCUMENT" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">DOCUMENT REQUEST OUTSTANDING</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Additional evidence required
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              The legal pipeline determined that an essential document is missing to substantiate a core legal issue. You may upload it or choose to waive it.
            </p>
            <button type="button" className="btn-pill-primary" onClick={() => navigate(`/cases/${caseId}/preview2`)}>
              <span>Review document request</span>
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}

        {/* PREVIEW_2_APPROVED */}
        {item.status === "PREVIEW_2_APPROVED" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">ANALYSIS FINALIZED</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Legal analysis approved
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              Your casework has statutory backing. Request an enrolled Bar Council advocate to review your case file, audit counter-arguments, and finalize court-ready complaint drafts.
            </p>
            <button
              type="button"
              className="btn-pill-primary"
              onClick={() => navigate(`/advocates?caseId=${caseId}`)}
            >
              <span>Request an advocate</span>
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}

        {/* AWAITING_ADVOCATE */}
        {item.status === "AWAITING_ADVOCATE" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">PENDING ADVOCATE ACCEPTANCE</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Waiting for advocate response
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              Your case has been forwarded to the selected advocate. Case particulars remain confidential until the advocate accepts the request.
            </p>
            <button
              type="button"
              className="btn-text-link"
              onClick={cancelAdvocate}
              disabled={busy}
              style={{ color: "var(--status-crimson)" }}
            >
              {busy ? "Cancelling…" : "Cancel advocate request"}
            </button>
          </div>
        )}

        {/* ADVOCATE_REVIEW */}
        {item.status === "ADVOCATE_REVIEW" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">UNDER ADVOCATE AUDIT</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Advocate is auditing casework
            </h2>
            <p style={{ color: "var(--text-body)", maxWidth: "55ch" }}>
              A verified advocate has accepted your case and is reviewing the verified legal sections, evidence cross-references, and counter-rebuttal points.
            </p>
          </div>
        )}

        {/* ADVOCATE_APPROVED */}
        {item.status === "ADVOCATE_APPROVED" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">ADVOCATE AUDIT COMPLETE</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Advocate finalized casework
            </h2>
            {item.advocate_review_note && (
              <p style={{ fontSize: "0.95rem", color: "#000000", padding: "1rem 0", fontStyle: "italic" }}>
                "{item.advocate_review_note}"
              </p>
            )}
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              All provisions, facts, and forum parameters have been reviewed and approved by your assigned advocate. Professional drafting is managed by your advocate in their workspace.
            </p>
            <div style={{ display: "inline-block", background: "#EFF6FF", border: "1px solid #BFDBFE", borderRadius: "4px", padding: "0.6rem 1rem", fontSize: "0.9rem", color: "#1E40AF" }}>
              ✓ Advocate review complete — Professional drafting in progress by advocate
            </div>
          </div>
        )}

        {/* GENERATING_DOCUMENTS */}
        {item.status === "GENERATING_DOCUMENTS" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">GENERATING OUTPUTS</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Drafting legal complaint and intelligence report
            </h2>
            <p style={{ color: "var(--text-body)", maxWidth: "55ch" }}>
              Assembling pleading draft, annexure indexes, and running multi-point consistency verification…
            </p>
          </div>
        )}

        {/* DOCUMENTS_READY or DOCUMENTS_BLOCKED */}
        {["DOCUMENTS_READY", "DOCUMENTS_BLOCKED"].includes(item.status) && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label">DELIVERABLES ASSEMBLED</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              {item.status === "DOCUMENTS_READY" ? "Court-ready documents ready" : "Documents generated with consistency flag"}
            </h2>
            <p style={{ color: "var(--text-body)", marginBottom: "1.5rem", maxWidth: "55ch" }}>
              Your complaint draft and case intelligence report have been produced and audited against approved evidence.
            </p>
            <button type="button" className="btn-pill-primary" onClick={() => navigate(`/cases/${caseId}/documents`)}>
              <span>View documents</span>
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}

        {/* OUT_OF_SCOPE */}
        {item.status === "OUT_OF_SCOPE" && (
          <div style={{ padding: "2rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
            <span className="eyebrow-label" style={{ color: "var(--text-muted)" }}>STATUTORY SCOPE NOTICE</span>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#000000", marginBottom: "0.5rem" }}>
              Specialized legal consultation recommended
            </h2>
            <p style={{ color: "var(--text-body)", lineHeight: 1.7, marginBottom: "1.5rem", maxWidth: "60ch" }}>
              {item.out_of_scope_message ||
                "CaseSeva currently maintains verified central statutory coverage for Consumer Protection and Labor Wages. Your dispute was categorized into a domain outside our automated gazette coverage. This does not mean your matter lacks legal merit — it means automated section grounding is not supported for this domain, and representation requires an enrolled advocate."}
            </p>
            <button
              type="button"
              className="btn-pill-primary"
              onClick={() => navigate(`/advocates?caseId=${caseId}`)}
            >
              <span>Browse verified advocates</span>
              <ArrowUpRight size={16} />
            </button>
          </div>
        )}
      </section>

      {/* Case Details: Narrative & Evidence sitting directly on white */}
      <section style={{ marginBottom: "3rem" }}>
        <span className="eyebrow-label">RECORDED STATEMENT</span>
        <h3 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#000000", marginBottom: "0.75rem" }}>
          Client Story
        </h3>
        <p style={{ fontSize: "1rem", lineHeight: 1.75, color: "var(--text-body)", whiteSpace: "pre-wrap", marginBottom: "2.5rem" }}>
          {item.client_story || "No story recorded."}
        </p>

        <span className="eyebrow-label">SUPPORTING EVIDENCE</span>
        <h3 style={{ fontSize: "1.2rem", fontWeight: 700, color: "#000000", marginBottom: "0.75rem" }}>
          Attached Documents ({item.evidence.length})
        </h3>
        {item.evidence.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.95rem" }}>No evidence uploaded yet.</p>
        ) : (
          <div style={{ borderTop: "1px solid var(--border-hairline)" }}>
            {item.evidence.map((entry) => (
              <div
                key={entry.evidence_id}
                style={{
                  padding: "1rem 0",
                  borderBottom: "1px solid var(--border-hairline)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <span className="status-pill status-pill--grey" style={{ fontWeight: 800 }}>
                    {entry.evidence_id}
                  </span>
                  <span style={{ fontSize: "0.95rem", fontWeight: 600, color: "#000000" }}>{entry.filename}</span>
                </div>
                {entry.description && (
                  <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>{entry.description}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
