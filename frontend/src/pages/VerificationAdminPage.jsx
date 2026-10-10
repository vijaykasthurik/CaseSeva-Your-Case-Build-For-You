import { useState } from "react";
import { listAdminAdvocates, verifyAdvocate, API_BASE_URL, getToken } from "../api";

export default function VerificationAdminPage() {
  const [token, setToken] = useState("");
  const [advocates, setAdvocates] = useState([]);
  const [error, setError] = useState("");
  async function load() {
    setError("");
    try { window.sessionStorage.setItem("admin_token", token); setAdvocates((await listAdminAdvocates()).advocates); }
    catch (failure) { setError(failure.message); }
  }
  async function document(id, index, filename) {
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
      {advocate.verification_documents?.map((file, index) => <button key={index} onClick={() => document(advocate.id, index, file.filename)}>Review {file.filename}</button>)}
      {["VERIFIED", "UNVERIFIED", "VERIFICATION_PENDING"].map(status => <button key={status} onClick={async () => { const reason = window.prompt("Record the review decision and reason:"); if (!reason) return; try { await verifyAdvocate(advocate.id, status, reason); await load(); } catch (failure) { setError(failure.message); } }}>{status}</button>)}
    </article>)}
  </main>;
}
