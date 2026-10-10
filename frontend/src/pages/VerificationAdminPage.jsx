import { useState } from "react";
import { listAdminAdvocates, verifyAdvocate, API_BASE_URL, getToken, getMe } from "../api";

export default function VerificationAdminPage() {
  const [token, setToken] = useState("");
  const [advocates, setAdvocates] = useState([]);
  const [error, setError] = useState("");
  async function load() {
    setError("");
    try { window.sessionStorage.setItem("admin_token", token); setAdvocates((await listAdminAdvocates()).advocates); }
    catch (failure) { setError(failure.message); }
  }
  async function downloadMaterial(id, index, filename) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/admin/advocates/${id}/documents/${index}`, { headers: { Authorization: `Bearer ${getToken()}`, "X-Admin-Token": token } });
      if (!response.ok) throw new Error("Document access denied.");
      const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setError(failure.message); }
  }
  return <main className="main-container content-narrow"><h1>Manual advocate verification</h1><p>Verification is performed by CaseSeva admin review. No automatic Bar Council verification is claimed.</p>
    <label>Admin credential<input type="password" value={token} onChange={event => setToken(event.target.value)} /></label><button onClick={load}>Load submissions</button>
    {error && <p role="alert">{error}</p>}
    {advocates.map(advocate => <article key={advocate.id}><h2>{advocate.full_name}</h2><p>{advocate.enrolment_number} — {advocate.bar_council}</p><p>Status: {advocate.verification_status}</p><p>{advocate.verification_reason}</p>
      {advocate.verification_documents?.map((file, index) => <button key={index} onClick={() => downloadMaterial(advocate.id, index, file.filename)}>Review {file.filename}</button>)}
      {[["VERIFIED", "Verify"], ["UNVERIFIED", "Reject"], ["VERIFICATION_PENDING", "Request additional proof"]].map(([status, label]) => <button key={status} onClick={async () => { const reason = window.prompt("Record the review decision and reason:"); if (!reason) return; try { let proof = {}; if (status === "VERIFIED") { const source = window.prompt("Official verification source URL (registered by the server operator):"); const reference = window.prompt("Official record reference checked:"); if (!source || !reference) return; proof = { official_source_url: source, official_record_reference: reference, reviewer_id: (await getMe()).user.id, reviewed_at: new Date().toISOString() }; } await verifyAdvocate(advocate.id, status, reason, proof); await load(); } catch (failure) { setError(failure.message); } }}>{label}</button>)}
    </article>)}
  </main>;
}
