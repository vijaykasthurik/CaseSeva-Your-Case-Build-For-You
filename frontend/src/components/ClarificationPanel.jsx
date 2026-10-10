import { useState } from "react";
import { answerClarifications, uploadEvidence } from "../api";

export default function ClarificationPanel({ caseId, batch, evidence = [], onSaved }) {
  const [answers, setAnswers] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!batch || batch.status !== "WAITING") return null;
  function set(id, changes) { setAnswers(current => ({ ...current, [id]: { ...current[id], ...changes } })); }
  async function submit(event) {
    event.preventDefault(); setError(""); setBusy(true);
    try { await answerClarifications(caseId, batch.questions.map(q => ({ question_id: q.question_id, ...answers[q.question_id] }))); await onSaved?.(); }
    catch (failure) { setError(failure.message); } finally { setBusy(false); }
  }
  return <section><h2>We need a few details to understand your case correctly</h2><p>Answer each question. It is always okay to say you do not know, do not have something, or can provide it later.</p><form onSubmit={submit}>
    {[...new Set(batch.questions.map(q => q.incident_id))].map(incident => <fieldset key={incident}><legend>About this part of the story: {incident}</legend>{batch.questions.filter(q => q.incident_id === incident).map(q => {
      const value = answers[q.question_id] || {};
      return <div key={q.question_id} style={{ margin: "1rem 0" }}><label>{q.question}<select required value={value.response || ""} onChange={e => set(q.question_id, { response: e.target.value })}><option value="">Choose a response</option><option value="ANSWER">I can answer</option><option value="UNKNOWN">I don't know</option><option value="NOT_AVAILABLE">I don't have this</option><option value="LATER">I can provide this later</option></select></label><p>{q.legal_reason}</p>
        {value.response === "ANSWER" && (q.control === "single_choice" ? <select aria-label={`Answer: ${q.question}`} required value={value.value || ""} onChange={e => set(q.question_id, { value: e.target.value })}><option value="">Choose</option>{q.choices.map(choice => <option key={choice}>{choice}</option>)}</select> : q.control === "upload" ? <><input aria-label={`Upload: ${q.question}`} type="file" onChange={async e => { try { const result = await uploadEvidence(caseId, e.target.files[0]); set(q.question_id, { evidence_ids: [result.evidence.evidence_id] }); } catch (failure) { setError(failure.message); } }} />{evidence.map(item => <label key={item.evidence_id}><input type="checkbox" checked={(value.evidence_ids || []).includes(item.evidence_id)} onChange={e => set(q.question_id, { evidence_ids: e.target.checked ? [...(value.evidence_ids || []), item.evidence_id] : value.evidence_ids.filter(id => id !== item.evidence_id) })} />{item.filename}</label>)}</> : <input aria-label={`Answer: ${q.question}`} required type={q.control === "date" || q.control === "month" ? q.control : "text"} value={value.value || ""} onChange={e => set(q.question_id, { value: e.target.value })} />)}
      </div>;
    })}</fieldset>)}
    {error && <p role="alert">{error}</p>}<button disabled={busy}>Save Answers and Continue</button>
  </form></section>;
}
