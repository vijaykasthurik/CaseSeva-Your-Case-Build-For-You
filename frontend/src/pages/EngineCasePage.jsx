import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCase, getCaseStatus, chooseEngine2, grantCaseAccess, getCaseGrants, revokeCaseAccess, uploadEvidence, reprocessInput, migrateCaseWorkflow } from "../api";
import ClarificationPanel from "../components/ClarificationPanel";
import { citizenStatus, stageLabel, readiness } from "../citizenLanguage";
import CaseCommunication from "../components/CaseCommunication";

export default function EngineCasePage() {
  const { caseId } = useParams();
  const [item, setItem] = useState(null);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState("");
  const [grants, setGrants] = useState([]);
  const [scopes, setScopes] = useState(["story", "case_file", "engine2", "evidence"]);
  const [sharedEvidence, setSharedEvidence] = useState(null);
  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const [data, status] = await Promise.all([getCase(caseId), getCaseStatus(caseId)]);
        if (active) { setItem(data.case); setProgress(status); }
      } catch (failure) { if (active) setError(failure.message); }
    }
    refresh(); const timer = setInterval(refresh, 1500);
    return () => { active = false; clearInterval(timer); };
  }, [caseId]);
  useEffect(() => { getCaseGrants(caseId).then(result => setGrants(result.grants)).catch(() => {}); }, [caseId, item?.status]);
  if (!item) return <main className="main-container"><p role="status">{error || "Loading case…"}</p></main>;
  const overview = item.overview;
  const presentation = citizenStatus(progress?.status || item.status);
  if (item.filing_update?.status === item.status) presentation.source = item.filing_update.source_label;
  return <main className="main-container content-narrow" style={{ paddingBottom: "5rem" }}>
    <h1>Case Overview</h1>
    {item.public_case_id && <p>Case ID: {item.public_case_id}</p>}
    <CaseCommunication item={item} onSaved={async () => setItem((await getCase(caseId)).case)} />
    <ClarificationPanel caseId={caseId} batch={item.clarification} evidence={item.evidence} onSaved={async () => setItem((await getCase(caseId)).case)} />
    <p data-testid="case-status">{presentation.label}</p><p>{presentation.explanation}</p><p>Source: {presentation.source}</p>
    {item.legal_foundation_status === "PENDING" && <p>Verified legal analysis is pending. Case understanding does not establish the applicable law.</p>}
    <p>Processing mode: {progress?.processing_mode}. {progress?.processing_mode === "mock" && "Development only — live AI analysis has not been performed."}</p>
    {error && <p role="alert">{error}</p>}
    {item.workflow_version !== 2 && <section><h2>Upgrade this existing case</h2><p>Your original story, evidence and history will be preserved while we prepare an updated case explanation.</p><button onClick={async () => { try { await migrateCaseWorkflow(caseId); setItem((await getCase(caseId)).case); } catch (failure) { setError(failure.message); } }}>Upgrade to the new workflow</button></section>}
    {progress?.error && <p role="alert">{progress.error.message}</p>}
    {progress?.current_stage && <h2>{stageLabel(progress.current_stage)}</h2>}
    <ol aria-label="Case journey">{["Information received", "Understanding your case", "Checking legal information", "Optional deeper check", "Find an advocate", "Professional review", "Document preparation", "Filing and case updates"].map(label => <li key={label}>{label}</li>)}</ol>
    {item.engine1_available && <>
      <h2>What your case is about</h2><p>{overview.summary}</p>
      <h2>Key facts</h2><ul>{overview.key_facts?.map((fact, index) => <li key={index}>{fact.text} — {{ STATED_BY_USER: "From your account", SUPPORTED_BY_EVIDENCE: "Supported by your documents", UNVERIFIED: "Still needs checking" }[fact.source_status] || "Still needs checking"}</li>)}</ul>
      <h2>Applicable Law</h2>{overview.applicable_law?.length ? <ul>{overview.applicable_law.map(law => <li key={law.provision_id}>{law.title}: {law.explanation} <a href={law.source_url} rel="noreferrer" target="_blank">Official source</a> (retrieved {law.retrieved_at})</li>)}</ul> : <p>No applicable law has been verified yet.</p>}
      <h2>Pending Advocate Verification</h2><ul>{overview.pending_advocate_verification?.map((entry, index) => <li key={index}>{entry.title ? entry.title + ": " : ""}{entry.reason}</li>)}</ul>
      {overview.forum && <p>Verified forum: {overview.forum.commission_level}</p>}
      {overview.limitation && <p>Verified time limit: {overview.limitation.reasoning}</p>}
      <h2>Missing details and unreadable material</h2><ul>{overview.missing_details?.map((question, index) => <li key={index}>{question}</li>)}</ul>
      <p>{overview.argument_analysis_note}</p>
      {overview.argument_analysis_run && <><h2>Issue readiness</h2><ul>{overview.issue_readiness.map(issue => <li key={issue.issue_id}>{issue.level === "Thin" ? "Needs more proof" : issue.level}<p>{readiness(issue.level)}</p><p>{issue.reasons.join(" ")}</p><p>What would improve it: {issue.improvements.join(" ")}</p></li>)}</ul><h2>Key risks</h2><ul>{overview.key_risks.map((risk, index) => <li key={index}>{risk}</li>)}</ul></>}
      {(!item.engine2_choice || item.engine2_stale) && !progress?.error && !["ENGINE1_RUNNING", "ENGINE2_RUNNING"].includes(item.status) && <section><h2>Want to check your case more deeply?</h2><p>CaseSeva can look at your case from both sides, identify what may be questioned and show where more proof may help.</p>
        {[true, false].map(run => <button key={String(run)} className="btn-pill-secondary" onClick={async () => { try { await chooseEngine2(caseId, run); setItem((await getCase(caseId)).case); } catch (failure) { setError(failure.message); } }}>{run ? "Check My Case Further" : "Skip This"}</button>)}
      </section>}
      <p>{overview.next_step}</p>
    </>}
    {item.status === "DRAFT" && <Link to={`/cases/${caseId}/edit`}>Continue your draft</Link>}
    <p><Link className="btn-pill-primary" to={`/advocates?caseId=${caseId}`}>Find an advocate</Link></p>
    {["NEEDS_DOCUMENT", "REVIEW_REQUIRED", "LEGAL_CORPUS_NOT_READY", "CASE_UNDERSTANDING_READY"].includes(item.status) && <section><h2>Add missing material or retry processing</h2><input aria-label="Additional evidence" type="file" multiple onChange={async event => { try { for (const file of Array.from(event.target.files)) await uploadEvidence(caseId, file); setItem((await getCase(caseId)).case); } catch (failure) { setError(failure.message); } }} /><button onClick={async () => { try { await reprocessInput(caseId); setItem((await getCase(caseId)).case); } catch (failure) { setError(failure.message); } }}>Resume Analysis</button></section>}
    {item.assigned_advocate_id && <section><h2>Case sharing consent</h2>
      <p>Your advocate has accepted. Choose what to share. Case understanding and deeper-check results may contain information derived from every submitted input.</p>
      {grants.filter(grant => !grant.revoked_at && new Date(grant.expires_at) > new Date()).map(grant => <p key={grant.id}>Shared until {new Date(grant.expires_at).toLocaleString()} <button onClick={async () => { try { await revokeCaseAccess(caseId, grant.id); setGrants((await getCaseGrants(caseId)).grants); } catch (failure) { setError(failure.message); } }}>Revoke access</button></p>)}
      {!grants.some(grant => !grant.revoked_at && new Date(grant.expires_at) > new Date()) && <>
        {["story", "raw_package", "case_file", "engine2", "evidence"].map(scope => <label key={scope} style={{ display: "block" }}><input type="checkbox" checked={scopes.includes(scope)} onChange={event => setScopes(event.target.checked ? [...scopes, scope] : scopes.filter(value => value !== scope))} /> Share {{ story: "your story", raw_package: "readable input and transcripts", case_file: "case understanding and verified legal information", engine2: "deeper case-checking results", evidence: "selected original files" }[scope]}</label>)}
        {scopes.includes("evidence") && item.evidence.map(evidence => <label key={evidence.evidence_id} style={{ display: "block" }}><input type="checkbox" checked={(sharedEvidence || item.evidence.map(entry => entry.evidence_id)).includes(evidence.evidence_id)} onChange={event => { const current = sharedEvidence || item.evidence.map(entry => entry.evidence_id); setSharedEvidence(event.target.checked ? [...current, evidence.evidence_id] : current.filter(value => value !== evidence.evidence_id)); }} />{evidence.evidence_id}: {evidence.filename}</label>)}
        <button className="btn-pill-primary" onClick={async () => { try { await grantCaseAccess(caseId, { scopes, evidence_ids: scopes.includes("evidence") ? sharedEvidence || item.evidence.map(entry => entry.evidence_id) : [], expires_in_hours: 168 }); setGrants((await getCaseGrants(caseId)).grants); } catch (failure) { setError(failure.message); } }}>Grant selected access for 7 days</button>
      </>}
    </section>}
    {item.document_version && <p><Link to={`/cases/${caseId}/documents`}>Download Client Case Overview</Link></p>}
    <p><Link to="/dashboard">Back to dashboard</Link></p>
  </main>;
}
