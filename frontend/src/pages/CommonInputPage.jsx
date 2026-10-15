import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { createCase, getCase, updateCase, submitCase, uploadEvidence, deleteEvidence, retryInput } from "../api";

const stages = [["NEW_CONSULTATION", "New / Consultation"], ["COMPLAINT_FIR", "Complaint / FIR exists"], ["EXISTING_OLD_CASE", "Existing / Old case"]];
const optionalFields = { COMPLAINT_FIR: [["reference_number", "FIR or reference number"], ["station_authority", "Police station or authority"], ["filing_date", "Complaint date"]], EXISTING_OLD_CASE: [["case_number", "Case number"], ["court_authority", "Court or tribunal"], ["current_stage", "Current stage"], ["next_date", "Next hearing date"]] };

export default function CommonInputPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const walkin = useLocation().pathname.startsWith("/advocate/");
  const [client, setClient] = useState({ client_name: "", client_email: "", client_mobile: "", preferred_language: "English", consent: false });
  const id = useRef(caseId);
  const creating = useRef(null);
  const recorder = useRef(null);
  const stream = useRef(null);
  const saveQueue = useRef(Promise.resolve());
  const [stage, setStage] = useState("NEW_CONSULTATION");
  const [story, setStory] = useState("");
  const [details, setDetails] = useState({});
  const [evidence, setEvidence] = useState([]);
  const [ready, setReady] = useState(!caseId);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState("");
  const changed = useRef(false);
  const latest = useRef({ stage, story, details });
  latest.current = { stage, story, details };

  useEffect(() => {
    if (caseId) getCase(caseId).then(({ case: item }) => {
      id.current = item.case_id;
      setStage(item.stage || "NEW_CONSULTATION"); setStory(item.client_story || "");
      setDetails(item.stage_details || {}); setEvidence(item.evidence || []); setReady(true);
    }).catch(error => setMessage(error.message));
    return () => { stream.current?.getTracks().forEach(track => track.stop()); };
  }, [caseId]);

  useEffect(() => {
    if (!evidence.some(item => item.extraction?.status !== "COMPLETED")) return;
    const timer = setInterval(async () => {
      if (!id.current) return;
      try { const result = await getCase(id.current); setEvidence(result.case.evidence || []); }
      catch { /* The next request can recover a temporary connection failure. */ }
    }, 2500);
    return () => clearInterval(timer);
  }, [evidence.some(item => item.extraction?.status !== "COMPLETED")]);

  async function ensureCase() {
    if (id.current) return id.current;
    if (!creating.current) creating.current = createCase(walkin ? { origin: "ADVOCATE_WALK_IN", ...client } : undefined).then(({ case: item }) => {
      id.current = item.case_id;
      window.history.replaceState(null, "", walkin ? `/advocate/intake/${item.case_id}` : `/cases/${item.case_id}/edit`);
      return item.case_id;
    }).finally(() => { creating.current = null; });
    return creating.current;
  }

  function save() {
    const value = { ...latest.current };
    const operation = saveQueue.current.catch(() => {}).then(async () => {
      const activeId = await ensureCase();
      await updateCase(activeId, { stage: value.stage, client_story: value.story, stage_details: value.details });
      setSaved("Draft saved");
      return activeId;
    });
    saveQueue.current = operation;
    return operation;
  }

  useEffect(() => {
    if (!ready || !changed.current) return;
    setSaved("Savingâ€¦");
    const timer = setTimeout(() => save().catch(error => { setSaved("Not saved"); setMessage(error.message); }), 600);
    return () => clearTimeout(timer);
  }, [stage, story, details, ready]);

  async function upload(files, inputSource = "AUTO") {
    setBusy(true); setMessage("");
    try {
      const activeId = await save();
      for (const file of files) {
        const result = await uploadEvidence(activeId, file, "", inputSource);
        setEvidence(result.case.evidence);
      }
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  }

  async function microphone() {
    if (recording) { recorder.current.stop(); setRecording(false); return; }
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error("Microphone recording is unavailable in this browser. Upload an audio file instead.");
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      recorder.current = new MediaRecorder(stream.current);
      recorder.current.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.current.onstop = () => {
        stream.current.getTracks().forEach(track => track.stop());
        const type = recorder.current.mimeType || "audio/webm";
        upload([new File(chunks, `microphone-${Date.now()}.${type.includes("mp4") ? "mp4" : "webm"}`, { type })], "MICROPHONE");
      };
      recorder.current.start(); setRecording(true);
    } catch (error) { stream.current?.getTracks().forEach(track => track.stop()); setRecording(false); setMessage("Microphone recording could not start. Check microphone permission or upload an audio file."); }
  }

  async function submit(event) {
    event.preventDefault(); setBusy(true); setMessage("");
    try { const activeId = await save(); const path = event.nativeEvent.submitter?.value || "understand"; await submitCase(activeId, path); navigate(walkin ? `/advocate/cases/${activeId}` : path === "legal_help" ? `/advocates?caseId=${activeId}` : `/cases/${activeId}`); }
    catch (error) { setMessage([error.message, ...Object.values(error.fields || {})].join(" ")); }
    finally { setBusy(false); }
  }

  if (!ready) return <main className="main-container"><p>{message || "Loading draftâ€¦"}</p></main>;
  return <main className="main-container content-narrow" style={{ paddingBottom: "5rem" }}>
    <h1>Tell us what happened</h1>
    <div style={{ background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: "8px", padding: "1rem 1.25rem", margin: "1rem 0 1.5rem" }}>
      <p style={{ fontWeight: 600, color: "#111827", margin: "0 0 0.25rem 0" }}>You only need to explain what happened.</p>
      <p style={{ fontSize: "0.9rem", color: "#4B5563", margin: 0 }}>
        You do not need to choose a legal category or identify statutes and sections. Write in English, தமிழ் (Tamil), हिन्दी (Hindi), or mixed language. Include what you know; unknown dates or details can remain unknown.
      </p>
    </div>
    <p style={{ fontSize: "0.85rem", color: "#6B7280" }}>AI-assisted case understanding, not legal advice. An advocate reviews the case before any formal step.</p>
    <form onSubmit={submit}>
      {walkin && <fieldset><legend>Walk-in client and consent</legend>{[["client_name", "Client name"], ["client_email", "Client email (optional)"], ["client_mobile", "Client mobile (optional)"], ["preferred_language", "Client preferred language"]].map(([key, label]) => <label key={key} style={{ display: "block" }}>{label}<input value={client[key]} onChange={event => setClient({ ...client, [key]: event.target.value })} /></label>)}<label><input type="checkbox" checked={client.consent} onChange={event => setClient({ ...client, consent: event.target.checked })} /> I have the client's consent to record and process this case. This declaration is recorded under my advocate account.</label></fieldset>}
      <label>What best describes your situation?<select aria-label="Case stage" value={stage} onChange={event => { changed.current = true; setStage(event.target.value); setDetails({}); }}>
        {stages.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label htmlFor="case-story" style={{ display: "block", marginTop: "1.5rem" }}>Your story</label><textarea id="case-story" rows={9} value={story} onChange={event => { changed.current = true; setStory(event.target.value); }} placeholder="What happened? In your own words, explain the events, payments, promises, or defects. Unknown dates or names can stay unknown." />
      <p aria-live="polite">{saved}</p>
      <button type="button" className="btn-pill-secondary" onClick={microphone} disabled={busy}>{recording ? "Stop recording and upload" : "Record with microphone"}</button>
      {recording && <p role="status">Recordingâ€¦ Stop when you are finished.</p>}
      <label style={{ display: "block", margin: "1.5rem 0" }}>Add files / Upload anything
        <input type="file" multiple accept=".pdf,.docx,.txt,.csv,image/*,audio/*,video/*" disabled={busy || recording} onChange={event => { upload(Array.from(event.target.files)); event.target.value = ""; }} />
      </label>
      <p>Up to 10 MB per file. Documents are read when uploaded. Recordings are processed after submission or when you choose Retry reading files. Video processing currently reads audio only.</p>
      <ul>{evidence.map(item => <li key={item.evidence_id}>{item.evidence_id}: {item.filename} — {item.extraction?.status === "COMPLETED" ? "Read" : "Reading pending"}{item.extraction?.review_required && " — extracted text needs checking"}{item.duplicate_of && " (duplicate upload; kept once in the combined text)"} <button type="button" disabled={busy} onClick={async () => {
        try { const result = await deleteEvidence(id.current, item.evidence_id); setEvidence(result.case.evidence); }
        catch (error) { setMessage(error.message); }
      }}>Remove</button></li>)}</ul>
      {evidence.some(item => item.extraction?.status !== "COMPLETED") && <button type="button" disabled={busy || recording} onClick={async () => {
        setBusy(true); setMessage("");
        try { await save(); await retryInput(id.current); setMessage("Your saved files are being read. You can continue when processing finishes."); }
        catch (error) { setMessage(error.message); }
        finally { setBusy(false); }
      }}>Retry reading files</button>}
      <details><summary>Optional case details</summary>
        {[...(optionalFields[stage] || []), ["amount", "Amount (if known)"], ["opposite_party", "Opposite party (if known)"]].map(([key, label]) => <label key={key} style={{ display: "block", margin: "1rem 0" }}>{label}<input value={details[key] || ""} onChange={event => { changed.current = true; setDetails({ ...details, [key]: event.target.value }); }} /></label>)}
      </details>
      {message && <p role="alert">{message}</p>}
      {walkin ? <button value="legal_help" className="btn-pill-primary" disabled={busy || recording} style={{ marginTop: "1.5rem" }}>Save Client Intake</button> : <><button value="understand" className="btn-pill-primary" disabled={busy || recording} style={{ marginTop: "1.5rem" }}>{busy ? "Savingâ€¦" : "Build My Case"}</button><button value="legal_help" className="btn-pill-secondary" disabled={busy || recording}>Get Legal Help</button><p>You can understand your case first or go straight to an advocate. Both choices stay available.</p></>}
    </form>
  </main>;
}
