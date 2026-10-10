import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAdvocateCase, reviewCaseItem, rerunEngine, generateDocuments, saveAdvocateNote } from "../api";
import { approveReviewedCase, downloadSharedEvidence } from "../api";

export default function AdvocateWorkspacePage() {
  const { caseId } = useParams();
  const [item, setItem] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [startStage, setStartStage] = useState("");
  const load = async () => { const result = await getAdvocateCase(caseId); setItem(result.case); };
  useEffect(() => { load().catch(failure => setError(failure.message)); }, [caseId]);
  useEffect(() => {
    if (!["ENGINE1_RUNNING", "ENGINE2_RUNNING", "GENERATING_DOCUMENTS"].includes(item?.status)) return;
    const timer = setInterval(() => load().catch(failure => setError(failure.message)), 1500);
    return () => clearInterval(timer);
  }, [item?.status]);
  async function action(task) {
    setBusy(true); setError("");
    try { await task(); await load(); } catch (failure) { setError(failure.message); } finally { setBusy(false); }
  }
  function review(kind, targetId, actionName, current = {}) {
    let value = {};
    if (actionName === "edit" || actionName === "verify") {
      const initial = actionName === "verify" ? { ...(kind === "pending" ? { title: current.title || "", explanation: "" } : {}), source_url: "", retrieved_at: "", official_text: "", quote: "" } : (kind === "fact" ? { text: current.text } : kind === "timeline" ? { date: current.date, description: current.description, date_uncertain: current.date_uncertain } : kind === "provision" ? { explanation: current.explanation } : current);
      const input = window.prompt(actionName === "verify" ? "Provide your checked official source, timezone-aware retrieval date, exact text and quote as JSON. For forum/limitation include the case-specific result and basis." : "Enter the corrected values as JSON. Leave unknown details unknown.", JSON.stringify(initial, null, 2));
      if (input === null) return;
      try { value = JSON.parse(input); } catch { setError("The correction must be valid JSON."); return; }
    }
    const reason = window.prompt("Record the reason for this review action:");
    if (!reason) return;
    action(() => reviewCaseItem(caseId, { kind, target_id: targetId, action: actionName, value, reason }));
  }
  if (!item) return <main className="main-container"><h1>Advocate review workspace</h1><p role="alert">{error || "Loading shared case…"}</p><p>Access requires client consent, current verification, and an unexpired grant.</p></main>;
  const file = item.case_file || {};
  const running = ["ENGINE1_RUNNING", "ENGINE2_RUNNING", "GENERATING_DOCUMENTS"].includes(item.status);
  const controls = (kind, id, current) => <span>{["approve", "edit", "remove"].map(name => <button key={name} disabled={busy || running} onClick={() => review(kind, id, name, current)}>{name}</button>)}</span>;
  return <main className="main-container content-narrow" style={{ paddingBottom: "5rem" }}>
    <h1>Advocate review workspace</h1><p>Status: {item.status}</p>
    {error && <p role="alert">{error}</p>}
    {item.processing_error && <p role="alert">{item.processing_error.message}</p>}
    <p>Client consent expires {new Date(item.grant.expires_at).toLocaleString()}. Shared scopes: {item.grant.scopes.join(", ")}.</p>
    {item.documents_outdated && <p role="alert">Earlier documents are outdated. Review the changes and regenerate a new version.</p>}
    {item.client_story !== undefined && <section><h2>Client story</h2><p style={{ whiteSpace: "pre-wrap" }}>{item.client_story}</p></section>}
    <section><h2>Shared evidence, OCR and transcripts</h2>{item.evidence?.map(evidence => <article key={evidence.evidence_id}><h3>{evidence.evidence_id}: {evidence.filename}</h3><p>Extraction: {evidence.extraction?.status || "Not processed"}</p><p style={{ whiteSpace: "pre-wrap" }}>{evidence.extraction?.original_text || evidence.extraction?.reason}</p><button onClick={() => action(() => downloadSharedEvidence(caseId, evidence))}>Download shared original</button>{controls("evidence", evidence.evidence_id, {})}</article>)}</section>
    <section><h2>Engine 1 Case File — version {file.version}</h2>
      <h3>Facts</h3>{file.facts?.filter(value => !value.removed).map(fact => <article key={fact.fact_id}><p>{fact.fact_id}: {fact.text} ({fact.verification_status})</p>{controls("fact", fact.fact_id, fact)}</article>)}
      <h3>Timeline</h3>{file.timeline?.map(event => <article key={event.event_id}><p>{event.date}: {event.description}</p>{controls("timeline", event.event_id, event)}</article>)}
      <h3>Parties</h3><pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(file.parties, null, 2)}</pre>{file.parties && controls("party", "parties", file.parties)}
      <h3>Verified applicable law</h3>{file.applicable_law?.filter(value => !value.removed).map(law => <article key={law.provision_id}><p>{law.provision_id}: {law.title}</p><p>{law.quote}</p><a href={law.source_url} target="_blank" rel="noreferrer">Official source</a><p>Retrieved: {law.retrieved_at}</p>{controls("provision", law.provision_id, law)}</article>)}
      <button disabled={busy || running} onClick={() => { const identifier = window.prompt("Unique authority identifier for this case:"); if (identifier) review("pending", identifier, "verify"); }}>Add authority after manual official-source review</button>
      <h3>Pending Advocate Verification</h3>{file.pending_advocate_verification?.map((pending, index) => <article key={index}><p>{pending.title || pending.type}: {pending.reason}</p>{pending.provision_id && <button disabled={busy || running} onClick={() => review("pending", pending.provision_id, "verify")}>Verify against checked official text</button>}</article>)}
      {["forum", "limitation"].map(kind => <article key={kind}><h3>{kind}</h3><pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(file[kind], null, 2)}</pre>{file[kind] && <><button disabled={busy || running} onClick={() => review(kind, kind, "verify")}>Record verified legal basis</button>{controls(kind, kind, file[kind])}</>}</article>)}
      <h3>Evidence-to-issue mapping</h3>{file.evidence_issue_mapping?.map(mapping => <article key={mapping.issue_id}><p>{mapping.issue_id}: {mapping.status} — {mapping.note}</p>{controls("mapping", mapping.issue_id, mapping)}</article>)}
    </section>
    {item.engine2 && <section><h2>Engine 2 — counsel roles and evaluation</h2><p>These are prompted roles on the same model.</p><pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(item.engine2, null, 2)}</pre>{item.engine2.opponent_counsel?.objections?.map(objection => <article key={objection.objection_id}><p>{objection.text}</p>{controls("argument", objection.objection_id, { text: objection.text })}</article>)}</section>}
    <section><h2>Engine reruns</h2><p>Engine 1 updates the foundation. Engine 2 only updates argumentation. Foundation changes make earlier argument results stale.</p>
      <label>Start stage (leave empty for full engine)<input value={startStage} onChange={event => setStartStage(event.target.value.toUpperCase())} placeholder="EVIDENCE_ISSUE_MAPPING" /></label>
      {[1, 2].map(engine => <button key={engine} disabled={busy || running} onClick={() => action(() => rerunEngine(caseId, engine, startStage || null))}>Rerun Engine {engine}</button>)}
      <ul>{Object.entries(item.stage_statuses || {}).map(([stage, status]) => <li key={stage}>{stage}: {status}</li>)}</ul>
    </section>
    <section><h2>Review notes and approval</h2><textarea value={note} onChange={event => setNote(event.target.value)} /><button disabled={busy || running} onClick={() => action(() => saveAdvocateNote(caseId, note))}>Save review note</button><button disabled={busy || running} onClick={() => action(() => approveReviewedCase(caseId))}>Approve reviewed case</button></section>
    <section><h2>Engine 3 — Professional Legal Draft</h2><p>Only you can run this engine after approving the current Case File. Unverified filing requirements remain marked for confirmation.</p><button disabled={busy || running || item.status !== "ADVOCATE_APPROVED"} onClick={() => action(() => generateDocuments(caseId))}>Generate professional documents</button><p><Link to={`/cases/${caseId}/documents`}>Client Case Overview and Professional Legal Draft downloads</Link></p></section>
    <section><h2>Audit trail</h2><pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(item.advocate_audit || [], null, 2)}</pre></section>
  </main>;
}
