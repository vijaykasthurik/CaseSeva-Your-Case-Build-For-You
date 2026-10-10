import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCase, getCaseStatus, chooseEngine2, grantCaseAccess, getCaseGrants, revokeCaseAccess, uploadEvidence, reprocessInput, migrateCaseWorkflow } from "../api";

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
  return <main className="main-container content-narrow" style={{ paddingBottom: "5rem" }}>
    <h1>Case Overview</h1>
    <p data-testid="case-status">Status: {progress?.status || item.status}</p>
    <p>Processing mode: {progress?.processing_mode}. {progress?.processing_mode === "mock" && "Development only — live AI analysis has not been performed."}</p>
    {error && <p role="alert">{error}</p>}
    {item.workflow_version !== 2 && <section><h2>Upgrade this existing case</h2><p>Your original story, evidence and analysis history will be preserved. Engine 1 will rebuild the Case File under the new verification rules.</p><button onClick={async () => { try { await migrateCaseWorkflow(caseId); setItem((await getCase(caseId)).case); } catch (failure) { setError(failure.message); } }}>Upgrade to the new workflow</button></section>}
    {progress?.error && <p role="alert">{progress.error.message}</p>}
    {progress?.current_stage && <h2>{progress.active_engine}: {progress.current_stage.replaceAll("_", " ")}</h2>}
    <ul aria-label="Processing stages">{Object.entries(progress?.stage_statuses || {}).map(([stage, status]) => <li key={stage}>{stage.replaceAll("_", " ")}: {status}</li>)}</ul>
    {item.engine1_available && <>
      <h2>What your case is about</h2><p>{overview.summary}</p>
      <h2>Key facts</h2><ul>{overview.key_facts?.map((fact, index) => <li key={index}>{fact.text} — {fact.source_status}</li>)}</ul>
      <h2>Applicable Law</h2>{overview.applicable_law?.length ? <ul>{overview.applicable_law.map(law => <li key={law.provision_id}>{law.title}: {law.explanation} <a href={law.source_url} rel="noreferrer" target="_blank">Official source</a> (retrieved {law.retrieved_at})</li>)}</ul> : <p>No applicable law has been verified yet.</p>}
      <h2>Pending Advocate Verification</h2><ul>{overview.pending_advocate_verification?.map((entry, index) => <li key={index}>{entry.type || entry.title}: {entry.reason}</li>)}</ul>
      {overview.forum && <p>Verified forum: {overview.forum.commission_level}</p>}
      {overview.limitation && <p>Verified time limit: {overview.limitation.reasoning}</p>}
      <h2>Missing details and unreadable material</h2><ul>{overview.missing_details?.map((question, index) => <li key={index}>{question}</li>)}</ul>
      <p>{overview.argument_analysis_note}</p>
      {overview.argument_analysis_run && <><h2>Issue readiness</h2><ul>{overview.issue_readiness.map(issue => <li key={issue.issue_id}>{issue.issue_id}: {issue.level}<p>{issue.reasons.join(" ")}</p><p>What would improve it: {issue.improvements.join(" ")}</p></li>)}</ul><h2>Key risks</h2><ul>{overview.key_risks.map((risk, index) => <li key={index}>{risk}</li>)}</ul></>}
      {(!item.engine2_choice || item.engine2_stale) && !progress?.error && !["ENGINE1_RUNNING", "ENGINE2_RUNNING"].includes(item.status) && <section><h2>Do you want to evaluate and strengthen your case with an argument analysis?</h2>
        {[true, false].map(run => <button key={String(run)} className="btn-pill-secondary" onClick={async () => { try { await chooseEngine2(caseId, run); setItem((await getCase(caseId)).case); } catch (failure) { setError(failure.message); } }}>{run ? "Yes, run Engine 2" : "Skip argument analysis"}</button>)}
      </section>}
      {item.engine2_choice && overview.ready_to_find_advocate && <p><Link className="btn-pill-primary" to={`/advocates?caseId=${caseId}`}>Find an advocate</Link></p>}
      <p>{overview.next_step}</p>
    </>}
    {item.status === "DRAFT" && <Link to={`/cases/${caseId}/edit`}>Continue your draft</Link>}
    {["NEEDS_DOCUMENT", "REVIEW_REQUIRED", "LEGAL_CORPUS_NOT_READY"].includes(item.status) && <section><h2>Add missing material or retry processing</h2><input aria-label="Additional evidence" type="file" multiple onChange={async event => { try { for (const file of Array.from(event.target.files)) await uploadEvidence(caseId, file); setItem((await getCase(caseId)).case); } catch (failure) { setError(failure.message); } }} /><button onClick={async () => { try { await reprocessInput(caseId); setItem((await getCase(caseId)).case); } catch (failure) { setError(failure.message); } }}>Reprocess input with Engine 1</button></section>}
    {item.assigned_advocate_id && <section><h2>Case sharing consent</h2>
      <p>Your advocate has accepted. Choose what to share. Case File and argument results may contain information derived from every submitted input.</p>
      {grants.filter(grant => !grant.revoked_at && new Date(grant.expires_at) > new Date()).map(grant => <p key={grant.id}>Shared until {new Date(grant.expires_at).toLocaleString()} <button onClick={async () => { try { await revokeCaseAccess(caseId, grant.id); setGrants((await getCaseGrants(caseId)).grants); } catch (failure) { setError(failure.message); } }}>Revoke access</button></p>)}
      {!grants.some(grant => !grant.revoked_at && new Date(grant.expires_at) > new Date()) && <>
        {["story", "case_file", "engine2", "evidence"].map(scope => <label key={scope} style={{ display: "block" }}><input type="checkbox" checked={scopes.includes(scope)} onChange={event => setScopes(event.target.checked ? [...scopes, scope] : scopes.filter(value => value !== scope))} /> Share {scope.replaceAll("_", " ")}</label>)}
        {scopes.includes("evidence") && item.evidence.map(evidence => <label key={evidence.evidence_id} style={{ display: "block" }}><input type="checkbox" checked={(sharedEvidence || item.evidence.map(entry => entry.evidence_id)).includes(evidence.evidence_id)} onChange={event => { const current = sharedEvidence || item.evidence.map(entry => entry.evidence_id); setSharedEvidence(event.target.checked ? [...current, evidence.evidence_id] : current.filter(value => value !== evidence.evidence_id)); }} />{evidence.evidence_id}: {evidence.filename}</label>)}
        <button className="btn-pill-primary" onClick={async () => { try { await grantCaseAccess(caseId, { scopes, evidence_ids: scopes.includes("evidence") ? sharedEvidence || item.evidence.map(entry => entry.evidence_id) : [], expires_in_hours: 168 }); setGrants((await getCaseGrants(caseId)).grants); } catch (failure) { setError(failure.message); } }}>Grant selected access for 7 days</button>
      </>}
    </section>}
    {item.document_version && <p><Link to={`/cases/${caseId}/documents`}>Download Client Case Overview</Link></p>}
    <p><Link to="/dashboard">Back to dashboard</Link></p>
  </main>;
}
