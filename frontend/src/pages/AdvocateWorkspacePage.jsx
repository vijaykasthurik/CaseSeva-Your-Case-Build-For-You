import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getAdvocateCase,
  reviewCaseItem,
  rerunEngine,
  approveReviewedCase,
  downloadSharedEvidence,
  getAdvocateCorrections,
  annotateEvidence,
  getAdvocateNotes,
  addAdvocateNote,
  resolveConflict,
  getEngine3Eligibility,
} from "../api";
import ClarificationPanel from "../components/ClarificationPanel";
import CaseCommunication from "../components/CaseCommunication";
import AdvocateDraftingStudio from "../components/AdvocateDraftingStudio";
import AdvocateFilingStudio from "../components/AdvocateFilingStudio";

export default function AdvocateWorkspacePage() {
  const { caseId } = useParams();
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [noteVisibility, setNoteVisibility] = useState("PRIVATE");
  const [corrections, setCorrections] = useState([]);
  const [notes, setNotes] = useState([]);
  const [engine3Eligibility, setEngine3Eligibility] = useState(null);
  const [startStage, setStartStage] = useState("");

  const load = async () => {
    const result = await getAdvocateCase(caseId);
    setItem(result.case);
    try {
      const [corrRes, notesRes, e3Res] = await Promise.all([
        getAdvocateCorrections(caseId).catch(() => ({ corrections: [] })),
        getAdvocateNotes(caseId).catch(() => ({ notes: [] })),
        getEngine3Eligibility(caseId).catch(() => null),
      ]);
      setCorrections(corrRes.corrections || []);
      setNotes(notesRes.notes || []);
      setEngine3Eligibility(e3Res);
    } catch {
      // Non-blocking supplementary metadata
    }
  };

  useEffect(() => {
    load().catch((failure) => setError(failure.message));
  }, [caseId]);

  useEffect(() => {
    if (!["SUBMITTED", "ENGINE1_RUNNING", "ENGINE2_RUNNING", "GENERATING_DOCUMENTS"].includes(item?.status)) return;
    const timer = setInterval(() => load().catch((failure) => setError(failure.message)), 1500);
    return () => clearInterval(timer);
  }, [item?.status]);

  async function action(task) {
    setBusy(true);
    setError("");
    try {
      await task();
      await load();
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  }

  function review(kind, targetId, actionName, current = {}) {
    let value = {};
    if (actionName === "edit" || actionName === "verify") {
      const initial =
        actionName === "verify"
          ? { ...(kind === "pending" ? { title: current.title || "", explanation: "" } : {}), source_url: "", retrieved_at: "", official_text: "", quote: "" }
          : kind === "fact"
          ? { text: current.text }
          : kind === "timeline"
          ? { date: current.date, description: current.description, date_uncertain: current.date_uncertain }
          : kind === "provision"
          ? { explanation: current.explanation }
          : current;
      const input = window.prompt(
        actionName === "verify"
          ? "Provide checked official source, retrieval date, official text and quote as JSON:"
          : "Enter the corrected values as JSON. Leave unknown details unknown.",
        JSON.stringify(initial, null, 2)
      );
      if (input === null) return;
      try {
        value = JSON.parse(input);
      } catch {
        setError("The correction must be valid JSON.");
        return;
      }
    }
    const reason = window.prompt("Record the reason for this professional review action:");
    if (!reason) return;
    action(() => reviewCaseItem(caseId, { kind, target_id: targetId, action: actionName, value, reason }));
  }

  async function handleAddNote() {
    if (!note.trim()) return;
    action(async () => {
      await addAdvocateNote(caseId, { note, visibility: noteVisibility });
      setNote("");
    });
  }

  async function handleAnnotateEvidence(evidenceId) {
    const text = window.prompt("Enter professional annotation / relevance note for this evidence:");
    if (!text) return;
    const relevance = window.prompt("Relevance rating (HIGH, MEDIUM, LOW) [default: HIGH]:") || "HIGH";
    action(() => annotateEvidence(caseId, evidenceId, { note: text, relevance }));
  }

  async function handleResolveConflict(correctionId, strategy) {
    action(() => resolveConflict(caseId, { correction_id: correctionId, strategy }));
  }

  if (!item) {
    return (
      <main className="main-container" style={{ padding: "3rem 1rem" }}>
        <h1>Advocate Review Workspace</h1>
        <p role="alert" style={{ color: "var(--status-crimson, #c62828)" }}>{error || "Loading shared case…"}</p>
        <p style={{ color: "#666" }}>Access requires active citizen consent, advocate verification, and an unexpired grant.</p>
      </main>
    );
  }

  const file = item.case_file || {};
  const running = ["ENGINE1_RUNNING", "ENGINE2_RUNNING", "GENERATING_DOCUMENTS"].includes(item.status);
  const controls = (kind, id, current) => (
    <span style={{ display: "inline-flex", gap: "0.35rem", marginLeft: "0.5rem" }}>
      {["approve", "edit", "remove"].map((name) => (
        <button
          key={name}
          className="btn-text-link"
          style={{ fontSize: "0.78rem", textTransform: "capitalize", padding: "0.15rem 0.4rem" }}
          disabled={busy || running}
          onClick={() => review(kind, id, name, current)}
        >
          {name}
        </button>
      ))}
    </span>
  );

  return (
    <main className="main-container content-narrow" style={{ paddingBottom: "5rem" }}>
      {/* Workspace Header */}
      <header style={{ marginBottom: "2rem", borderBottom: "1px solid var(--border-hairline, #eee)", paddingBottom: "1rem" }}>
        <span className="eyebrow-label">CITIZEN CASE PROFESSIONAL REVIEW</span>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "1rem", marginTop: "0.4rem" }}>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>
            Case Review Workspace {item.public_case_id ? `(${item.public_case_id})` : `#${caseId}`}
          </h1>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <span style={{ padding: "0.25rem 0.65rem", borderRadius: "3px", fontWeight: 700, background: "#EDE7F6", color: "#4527A0", fontSize: "0.85rem" }}>
              Status: {item.review_status || "NOT_REVIEWED"}
            </span>
            {item.engine3_eligible && (
              <span style={{ padding: "0.25rem 0.65rem", borderRadius: "3px", fontWeight: 700, background: "#E8F5E9", color: "#1B5E20", fontSize: "0.85rem" }}>
                ✓ E3 Eligible
              </span>
            )}
          </div>
        </div>
        <p style={{ color: "#666", fontSize: "0.88rem", marginTop: "0.5rem" }}>
          {item.grant?.permission_type === "WALK_IN_CONSENT"
            ? "Walk-in client consent recorded."
            : `Active citizen consent expires ${item.grant?.expires_at ? new Date(item.grant.expires_at).toLocaleString() : "N/A"}.`}{" "}
          Scopes: {(item.grant?.scopes || []).join(", ")}.
        </p>
      </header>

      {/* Staleness and Warning Banners */}
      {item.engine1_stale && (
        <div role="alert" style={{ background: "#FFF3E0", border: "1px solid #FFE0B2", padding: "1rem 1.25rem", borderRadius: "4px", marginBottom: "1.5rem" }}>
          <strong style={{ color: "#E65100" }}>Engine-1 Case File is STALE:</strong>
          <p style={{ margin: "0.25rem 0 0.5rem", fontSize: "0.9rem", color: "#5D4037" }}>
            Substantive corrections have been recorded. Rerun Engine 1 below to synthesize a new official Case File version incorporating your reviewed values.
          </p>
          <button className="btn-pill-primary" disabled={busy || running} onClick={() => action(() => rerunEngine(caseId, 1, startStage || null))}>
            Rerun Engine 1 Now
          </button>
        </div>
      )}

      {item.engine2_stale && (
        <div style={{ background: "#FBE9E7", border: "1px solid #FFCCBC", padding: "0.85rem 1.15rem", borderRadius: "4px", marginBottom: "1.5rem" }}>
          <strong style={{ color: "#D84315" }}>Prior Engine-2 Report is STALE:</strong>
          <p style={{ margin: "0.25rem 0 0", fontSize: "0.88rem", color: "#4E342E" }}>
            The underlying Case File changed. Adversarial arguments are now stale. You may optionally rerun Engine 2 to refresh challenge analysis.
          </p>
        </div>
      )}

      {error && <p role="alert" style={{ color: "#C62828", background: "#FFEBEE", padding: "0.75rem", borderRadius: "4px" }}>{error}</p>}
      {item.processing_error && <p role="alert" style={{ color: "#C62828" }}>{item.processing_error.message}</p>}

      <CaseCommunication item={item} professional onSaved={load} />
      <ClarificationPanel caseId={caseId} batch={item.clarification} evidence={item.evidence} onSaved={load} />

      {/* Citizen Story */}
      {item.client_story !== undefined && (
        <section style={{ marginBottom: "2rem" }}>
          <h2>Citizen Narrative / Story</h2>
          <div style={{ background: "#FAFAFA", border: "1px solid #EEE", padding: "1rem", borderRadius: "4px", whiteSpace: "pre-wrap", fontSize: "0.92rem", lineHeight: 1.6 }}>
            {item.client_story}
          </div>
        </section>
      )}

      {/* First-Class Advocate Corrections & Conflicts */}
      <section style={{ marginBottom: "2.5rem" }}>
        <h2>Advocate Corrections (First-Class Versioned Audit)</h2>
        <p style={{ color: "#666", fontSize: "0.88rem" }}>
          Corrections never overwrite original AI state silently. Each correction is preserved, version-bound, and evaluated during regeneration.
        </p>
        {corrections.length === 0 ? (
          <p style={{ color: "#888", fontStyle: "italic", fontSize: "0.9rem" }}>No advocate corrections recorded yet.</p>
        ) : (
          <div style={{ display: "grid", gap: "0.85rem", marginTop: "0.75rem" }}>
            {corrections.map((corr) => (
              <div key={corr.correction_id} style={{ border: "1px solid #DDD", padding: "0.85rem 1rem", borderRadius: "4px", background: corr.substantive ? "#FFFDE7" : "#FFF" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap" }}>
                  <strong>{corr.field} &middot; ID: {corr.target_id || "case"}</strong>
                  <span style={{ fontSize: "0.75rem", textTransform: "uppercase", padding: "0.15rem 0.5rem", borderRadius: "3px", background: corr.substantive ? "#FFF59D" : "#E0E0E0" }}>
                    {corr.substantive ? "Substantive Change" : "Non-Substantive"}
                  </span>
                </div>
                <div style={{ fontSize: "0.85rem", margin: "0.4rem 0", color: "#333" }}>
                  <div><em>Original Value:</em> <code>{JSON.stringify(corr.original_value)}</code></div>
                  <div><em>Advocate Correction:</em> <code>{JSON.stringify(corr.advocate_correction)}</code></div>
                  <div><em>Effective Value:</em> <code>{JSON.stringify(corr.effective_value)}</code></div>
                </div>
                <div style={{ fontSize: "0.8rem", color: "#666" }}>
                  <span>Reason: {corr.reason || "None recorded"}</span> &middot; <span>Version: {corr.case_file_version}</span> &middot; <span>Strategy: {corr.conflict_strategy || "KEEP"}</span>
                </div>
                {corr.conflict_status === "CONFLICT_DETECTED" && (
                  <div style={{ marginTop: "0.5rem", padding: "0.5rem", background: "#FFEBEE", border: "1px solid #FFCDD2", borderRadius: "3px" }}>
                    <span style={{ color: "#C62828", fontWeight: 600, fontSize: "0.82rem" }}>Regeneration Conflict Detected! Select resolution strategy:</span>
                    <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.35rem" }}>
                      {["KEEP", "REPLACE", "MERGE"].map((strat) => (
                        <button key={strat} className="btn-text-link" style={{ fontSize: "0.8rem", fontWeight: 700 }} onClick={() => handleResolveConflict(corr.correction_id, strat)}>
                          {strat}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Shared Evidence & Immutable Documents */}
      <section style={{ marginBottom: "2.5rem" }}>
        <h2>Shared Evidence & Professional Annotations</h2>
        <p style={{ color: "#666", fontSize: "0.88rem" }}>
          Original uploaded evidence files are strictly immutable. Annotations, relevance notes, and legal observations are stored as separate auditable layers.
        </p>
        <div style={{ display: "grid", gap: "1rem", marginTop: "0.75rem" }}>
          {(item.evidence || []).map((ev) => (
            <article key={ev.evidence_id} style={{ border: "1px solid #DDD", padding: "1rem", borderRadius: "4px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "1.05rem" }}>{ev.filename}</h3>
                  <span style={{ fontSize: "0.78rem", color: "#666" }}>ID: {ev.evidence_id} &middot; Status: {ev.extraction?.status || "Pending"}</span>
                </div>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button className="btn-text-link" style={{ fontSize: "0.82rem" }} onClick={() => action(() => downloadSharedEvidence(caseId, ev))}>
                    Download Original
                  </button>
                  <button className="btn-text-link" style={{ fontSize: "0.82rem", fontWeight: 600 }} onClick={() => handleAnnotateEvidence(ev.evidence_id)}>
                    + Add Annotation
                  </button>
                </div>
              </div>
              {ev.extraction?.original_text && (
                <div style={{ marginTop: "0.5rem", fontSize: "0.85rem", background: "#F9F9F9", padding: "0.5rem", borderRadius: "3px", maxHeight: "150px", overflowY: "auto" }}>
                  <strong style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#555" }}>Extracted Text:</strong>
                  <p style={{ margin: "0.25rem 0 0", whiteSpace: "pre-wrap" }}>{ev.extraction.original_text}</p>
                </div>
              )}
            </article>
          ))}
        </div>
      </section>

      {/* Structured Engine-1 Case File */}
      <section style={{ marginBottom: "2.5rem" }}>
        <h2>Engine 1 Structured Case File — Version {file.version || "1.0.0"}</h2>

        <h3>Material Facts</h3>
        {(file.facts || []).filter((f) => !f.removed).map((fact) => (
          <article key={fact.fact_id} style={{ borderBottom: "1px solid #EEE", padding: "0.6rem 0", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <p style={{ margin: 0, fontSize: "0.9rem" }}>
              <strong>{fact.fact_id}:</strong> {fact.text} <span style={{ color: "#777", fontSize: "0.8rem" }}>({fact.verification_status || "UNVERIFIED"})</span>
            </p>
            {controls("fact", fact.fact_id, fact)}
          </article>
        ))}

        <h3 style={{ marginTop: "1.5rem" }}>Chronological Timeline</h3>
        {(file.timeline || []).map((event) => (
          <article key={event.event_id || event.date} style={{ borderBottom: "1px solid #EEE", padding: "0.6rem 0", display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <p style={{ margin: 0, fontSize: "0.9rem" }}>
              <strong>{event.date}:</strong> {event.description}
            </p>
            {controls("timeline", event.event_id || event.date, event)}
          </article>
        ))}

        <h3 style={{ marginTop: "1.5rem" }}>Identified Parties</h3>
        <pre style={{ background: "#F5F5F5", padding: "0.75rem", borderRadius: "4px", fontSize: "0.85rem", overflowX: "auto" }}>
          {JSON.stringify(file.parties || [], null, 2)}
        </pre>
        {file.parties && controls("party", "parties", file.parties)}

        <h3 style={{ marginTop: "1.5rem" }}>Verified Applicable Law (Verified Authority Only)</h3>
        {(file.applicable_law || []).filter((l) => !l.removed).length === 0 ? (
          <p style={{ color: "#888", fontStyle: "italic", fontSize: "0.88rem" }}>No statutory provisions verified yet.</p>
        ) : (
          (file.applicable_law || []).filter((l) => !l.removed).map((law) => (
            <article key={law.provision_id} style={{ border: "1px solid #E0E0E0", padding: "0.75rem", borderRadius: "4px", marginBottom: "0.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{law.provision_id}: {law.title}</strong>
                {controls("provision", law.provision_id, law)}
              </div>
              <p style={{ margin: "0.35rem 0", fontSize: "0.88rem" }}>{law.quote}</p>
              {law.source_url && <a href={law.source_url} target="_blank" rel="noreferrer" style={{ fontSize: "0.8rem" }}>Official Source</a>}
            </article>
          ))
        )}

        <h3 style={{ marginTop: "1.5rem" }}>Pending Advocate Verification</h3>
        {(file.pending_advocate_verification || []).length === 0 ? (
          <p style={{ color: "#888", fontStyle: "italic", fontSize: "0.88rem" }}>None pending.</p>
        ) : (
          (file.pending_advocate_verification || []).map((pending, idx) => (
            <div key={idx} style={{ background: "#FFF8E1", padding: "0.5rem 0.75rem", borderRadius: "4px", marginBottom: "0.5rem", fontSize: "0.88rem" }}>
              <strong>{pending.title || pending.type}:</strong> {pending.reason}
              {pending.provision_id && (
                <button className="btn-text-link" style={{ marginLeft: "0.5rem", fontSize: "0.82rem" }} onClick={() => review("pending", pending.provision_id, "verify")}>
                  Verify Against Checked Official Text
                </button>
              )}
            </div>
          ))
        )}

        <h3 style={{ marginTop: "1.5rem" }}>Forum & Limitation</h3>
        {["forum", "limitation"].map((k) => (
          <div key={k} style={{ marginBottom: "0.75rem" }}>
            <strong>{k.toUpperCase()}:</strong>
            <pre style={{ background: "#F5F5F5", padding: "0.5rem", borderRadius: "3px", fontSize: "0.82rem" }}>
              {JSON.stringify(file[k] || {}, null, 2)}
            </pre>
            {file[k] && controls(k, k, file[k])}
          </div>
        ))}
      </section>

      {/* Engine 2 — Optional Challenge Analysis */}
      <section style={{ marginBottom: "2.5rem", borderTop: "1px solid #EEE", paddingTop: "1.5rem" }}>
        <h2>Engine 2 — Challenge / Argument Analysis (Optional)</h2>
        {item.engine2_disclosure && (
          <p style={{ fontStyle: "italic", color: "#666", background: "#F5F5F5", padding: "0.6rem 0.8rem", borderRadius: "4px" }}>
            {item.engine2_disclosure}
          </p>
        )}
        {item.engine2 ? (
          <div>
            <pre style={{ background: "#FAFAFA", padding: "0.75rem", borderRadius: "4px", fontSize: "0.82rem", maxHeight: "250px", overflowY: "auto" }}>
              {JSON.stringify(item.engine2, null, 2)}
            </pre>
          </div>
        ) : (
          <p style={{ color: "#666", fontSize: "0.88rem" }}>
            Case Challenge / Argument Analysis was not run on this Case File. Engine 2 is strictly optional and its absence does not block future Engine 3 drafting.
          </p>
        )}
      </section>

      {/* Engine Rerun Controls */}
      <section style={{ marginBottom: "2.5rem", background: "#F9FBFD", border: "1px solid #D6E4F0", padding: "1.25rem", borderRadius: "4px" }}>
        <h2 style={{ marginTop: 0 }}>Engine Execution & Reruns</h2>
        <p style={{ fontSize: "0.88rem", color: "#455A64" }}>
          Rerunning Engine 1 consumes latest citizen state + valid advocate corrections to build an updated Case File. Old Engine-2 analysis will become stale.
        </p>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
          <button className="btn-pill-primary" disabled={busy || running} onClick={() => action(() => rerunEngine(caseId, 1, startStage || null))}>
            Rerun Engine 1 (Foundation)
          </button>
          <button className="btn-text-link" style={{ fontWeight: 600 }} disabled={busy || running} onClick={() => action(() => rerunEngine(caseId, 2, null))}>
            Optionally Rerun Engine 2 (Challenges)
          </button>
        </div>
      </section>

      {/* Professional Notes (Private vs Citizen-Visible) */}
      <section style={{ marginBottom: "2.5rem" }}>
        <h2>Professional Review Notes</h2>
        <div style={{ display: "grid", gap: "0.75rem" }}>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Record legal analysis, case observations, or client notes…"
            rows={3}
            style={{ width: "100%", padding: "0.75rem", borderRadius: "4px", border: "1px solid #CCC", fontFamily: "inherit" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
            <div style={{ display: "flex", gap: "1rem", fontSize: "0.88rem" }}>
              <label>
                <input
                  type="radio"
                  name="visibility"
                  value="PRIVATE"
                  checked={noteVisibility === "PRIVATE"}
                  onChange={() => setNoteVisibility("PRIVATE")}
                />{" "}
                Private Advocate Note (Internal only)
              </label>
              <label>
                <input
                  type="radio"
                  name="visibility"
                  value="SHARED_WITH_CLIENT"
                  checked={noteVisibility === "SHARED_WITH_CLIENT"}
                  onChange={() => setNoteVisibility("SHARED_WITH_CLIENT")}
                />{" "}
                Citizen-Visible Message
              </label>
            </div>
            <button className="btn-pill-primary" disabled={busy || !note.trim()} onClick={handleAddNote}>
              Save Note
            </button>
          </div>
        </div>

        {/* Notes Listing */}
        {notes.length > 0 && (
          <div style={{ marginTop: "1rem", display: "grid", gap: "0.5rem" }}>
            {notes.map((n) => (
              <div key={n.note_id} style={{ background: n.visibility === "PRIVATE" ? "#F5F5F5" : "#E8F5E9", padding: "0.6rem 0.85rem", borderRadius: "4px", fontSize: "0.85rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.2rem" }}>
                  <strong style={{ fontSize: "0.78rem", textTransform: "uppercase", color: n.visibility === "PRIVATE" ? "#616161" : "#2E7D32" }}>
                    {n.visibility === "PRIVATE" ? "Private Note" : "Shared With Citizen"}
                  </strong>
                  <span style={{ fontSize: "0.75rem", color: "#888" }}>{new Date(n.created_at).toLocaleString()}</span>
                </div>
                <p style={{ margin: 0 }}>{n.note}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Review Finalization / Approval */}
      <section style={{ marginBottom: "2.5rem", borderTop: "1px solid #EEE", paddingTop: "1.5rem" }}>
        <h2>Review Sign-Off & Currentness</h2>
        <p style={{ fontSize: "0.88rem", color: "#666" }}>
          Marking the review as CURRENT certifies that the advocate has reviewed the Engine-1 Case File and that all substantive corrections have been incorporated.
        </p>
        <button
          className="btn-pill-primary"
          disabled={busy || running || item.engine1_stale}
          onClick={() => action(() => approveReviewedCase(caseId))}
        >
          {item.review_status === "REVIEWED_CURRENT" ? "✓ Review Approved & Current" : "Sign Off / Approve Current Review"}
        </button>
        {item.engine1_stale && (
          <p style={{ color: "#E65100", fontSize: "0.82rem", marginTop: "0.35rem" }}>
            Cannot certify review while Engine 1 is stale. Please rerun Engine 1 first.
          </p>
        )}
      </section>

      {/* Engine 3 — Advocate-Ready Drafting Studio */}
      <AdvocateDraftingStudio
        caseId={caseId}
        caseItem={item}
        eligibility={engine3Eligibility}
        onRefreshCase={load}
      />

      {/* Phase 10 — Safe Filing Preparation Studio */}
      <AdvocateFilingStudio
        caseId={caseId}
        caseItem={item}
        onRefreshCase={load}
      />
    </main>
  );
}
