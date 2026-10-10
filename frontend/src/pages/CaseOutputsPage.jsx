import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getMe, getAdvocateCase, listDocuments, getDocument, downloadCaseDocument } from "../api";

export default function CaseOutputsPage() {
  const { caseId } = useParams();
  const [documents, setDocuments] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    (async () => { const { user } = await getMe(); if (user.role === "advocate") await getAdvocateCase(caseId); setDocuments((await listDocuments(caseId)).documents); })().catch(failure => setError(failure.message));
  }, [caseId]);
  return <main className="main-container content-narrow" style={{ paddingBottom: "5rem" }}>
    <h1>Case documents</h1><p>Documents can contain pending requirements. Check the review record and current filing requirements before filing.</p>
    {error && <p role="alert">{error}</p>}
    {!documents.length && <p>No documents are available for your account yet.</p>}
    {documents.map(document => <article key={document.id}><h2>{document.title || (document.type === "client_case_overview" ? "Client Case Overview" : "Professional Legal Draft")}</h2><p>Version {document.version} · {new Date(document.created_at).toLocaleString()}{document.outdated && " · OUTDATED — regeneration required"}</p>
      <button onClick={async () => { try { setSelected((await getDocument(caseId, document.id)).document); } catch (failure) { setError(failure.message); } }}>View</button>
      {["html", "pdf", "docx"].map(format => <button key={format} onClick={async () => { try { await downloadCaseDocument(caseId, document, format); } catch (failure) { setError(failure.message); } }}>Download {format.toUpperCase()}</button>)}
      <ul>{document.consistency?.map((check, index) => <li key={index}>{check.check}: {check.result} — {check.detail}</li>)}</ul>
    </article>)}
    {selected && <iframe title={selected.type === "client_case_overview" ? "Client Case Overview" : "Professional Legal Draft"} sandbox="" srcDoc={selected.html} style={{ width: "100%", height: "800px", border: "1px solid #ddd", marginTop: "2rem" }} />}
  </main>;
}
