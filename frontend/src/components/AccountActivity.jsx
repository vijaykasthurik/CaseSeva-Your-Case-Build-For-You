import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getNotifications, startGuestClaim, confirmGuestClaim } from "../api";

export default function AccountActivity({ professional = false }) {
  const [items, setItems] = useState([]);
  const [caseId, setCaseId] = useState("");
  const [claim, setClaim] = useState(null);
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => { getNotifications().then(result => setItems(result.notifications)).catch(failure => setMessage(failure.message)); }, []);
  return <section><h2>Notifications and recent activity</h2>{items.length ? items.map(item => <article key={item.id}><p>{item.message}</p><small>{new Date(item.created_at).toLocaleString()}</small>{item.case_id && <p><Link to={professional ? `/advocate/review/${item.case_id}` : `/cases/${item.case_id}`}>Open case</Link></p>}</article>) : <p>No new notifications.</p>}
    {!professional && <details><summary>Link a case created by your advocate</summary><p>Use the case reference your advocate gave you. Your account email must match the client email, and a verification code is required.</p><label>Case reference<input value={caseId} onChange={e => setCaseId(e.target.value)} /></label><button onClick={async () => { try { setClaim(await startGuestClaim(caseId)); } catch (failure) { setMessage(failure.message); } }}>Send Verification Code</button>{claim && <><p>{claim.message}</p>{claim.development_only && <p>Development only: {claim.development_code}</p>}<label>Verification code<input value={code} onChange={e => setCode(e.target.value)} /></label><button onClick={async () => { try { const result = await confirmGuestClaim(claim.claim_id, code); setMessage(result.message); window.location.assign(`/cases/${result.case_id}`); } catch (failure) { setMessage(failure.message); } }}>Link Existing Case</button></>}</details>}
    {message && <p role="alert">{message}</p>}
  </section>;
}
