import { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { ArrowUpRight, Check, Filter, Search, ArrowLeft } from "lucide-react";
import { listAdvocates, requestAdvocate } from "../api";

export default function AdvocateDirectoryPage() {
  const [advocates, setAdvocates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useSearchParams();
  const [confirmingAdvocate, setConfirmingAdvocate] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [requesting, setRequesting] = useState(false);

  const navigate = useNavigate();
  const caseId = search.get("caseId");

  const load = () => {
    setLoading(true);
    setErrorMsg("");
    listAdvocates({
      domain: search.get("domain") || "",
      state: search.get("state") || "",
      language: search.get("language") || "",
    })
      .then((result) => setAdvocates(result.advocates || []))
      .catch((err) => setErrorMsg(err.message || "Failed to load advocates."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [search]);

  const choose = (advocate) => {
    if (!caseId) return;
    setErrorMsg("");
    setConfirmingAdvocate(advocate);
  };

  const confirmRequest = async () => {
    if (!confirmingAdvocate || !caseId) return;
    setRequesting(true);
    setErrorMsg("");
    try {
      await requestAdvocate(caseId, confirmingAdvocate.id);
      navigate(`/cases/${caseId}`);
    } catch (err) {
      setErrorMsg(err.message || "Failed to submit advocate request.");
      setConfirmingAdvocate(null);
    } finally {
      setRequesting(false);
    }
  };

  return (
    <main className="main-container" style={{ paddingTop: "2.5rem", paddingBottom: "5rem" }}>
      {/* Header */}
      <header style={{ marginBottom: "2.5rem" }}>
        <span className="eyebrow-label">REPRESENTATION DIRECTORY</span>
        <div className="stacked-headline" style={{ margin: "0.4rem 0 0.75rem 0" }}>
          <div>ENROLLED COUNSEL /</div>
          <div className="stacked-headline__accent">ADVOCATE DIRECTORY</div>
          <div className="hairline-gold" style={{ marginTop: "0.85rem", maxWidth: "160px" }} />
        </div>
        <p style={{ color: "var(--text-body)", fontSize: "0.95rem", maxWidth: "60ch", marginTop: "0.75rem" }}>
          Connect with authenticated legal practitioners admitted to State Bar Councils for supervisory review, drafting sign-off, and formal representation.
        </p>
      </header>

      {/* Case Context Banner when arriving from a specific case */}
      {caseId && (
        <div
          style={{
            background: "#FAFAFA",
            border: "1px solid #000000",
            padding: "1.25rem 1.5rem",
            marginBottom: "2.5rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div>
            <span className="eyebrow-label" style={{ marginBottom: "0.2rem" }}>SELECTING REPRESENTATION</span>
            <p style={{ fontSize: "0.95rem", fontWeight: 700, color: "#000000" }}>
              Requesting counsel for Case #{caseId}
            </p>
          </div>
          <button
            type="button"
            className="btn-text-link"
            onClick={() => navigate(`/cases/${caseId}`)}
            style={{ fontSize: "0.85rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
          >
            <ArrowLeft size={14} />
            <span>Back to case dossier</span>
          </button>
        </div>
      )}

      {/* Error Alert */}
      {errorMsg && (
        <div
          role="alert"
          style={{
            background: "#FAFAFA",
            borderLeft: "3px solid var(--status-crimson)",
            padding: "1rem 1.25rem",
            marginBottom: "2rem",
          }}
        >
          <p style={{ color: "var(--status-crimson)", fontSize: "0.9rem", fontWeight: 600 }}>
            {errorMsg}
          </p>
        </div>
      )}

      {/* Filter Bar — Responsive and sitting on white */}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          setSearch({
            caseId: caseId || "",
            domain: data.get("domain") || "",
            state: data.get("state") || "",
            language: data.get("language") || "",
          });
        }}
        style={{
          borderTop: "1px solid var(--border-hairline)",
          borderBottom: "1px solid var(--border-hairline)",
          padding: "1.5rem 0",
          marginBottom: "2.5rem",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "1.25rem",
          alignItems: "end",
        }}
      >
        <div>
          <label className="clean-label" htmlFor="domain">PRACTICE DOMAIN</label>
          <input
            id="domain"
            name="domain"
            className="clean-input"
            placeholder="e.g. Consumer, Labour"
            defaultValue={search.get("domain") || ""}
          />
        </div>

        <div>
          <label className="clean-label" htmlFor="state">STATE / JURISDICTION</label>
          <input
            id="state"
            name="state"
            className="clean-input"
            placeholder="e.g. Tamil Nadu, Delhi"
            defaultValue={search.get("state") || ""}
          />
        </div>

        <div>
          <label className="clean-label" htmlFor="language">LANGUAGE</label>
          <input
            id="language"
            name="language"
            className="clean-input"
            placeholder="e.g. English, Tamil, Hindi"
            defaultValue={search.get("language") || ""}
          />
        </div>

        <button
          type="submit"
          className="btn-pill-primary"
          style={{ height: "42px", justifyContent: "center" }}
        >
          <span>Filter</span>
          <ArrowUpRight size={14} />
        </button>
      </form>

      {/* Advocates List */}
      {loading ? (
        <div style={{ padding: "4rem 0", color: "var(--text-muted)", fontSize: "0.92rem" }}>
          Searching verified advocate directory…
        </div>
      ) : advocates.length === 0 ? (
        <section style={{ padding: "4rem 0", borderBottom: "1px solid var(--border-hairline)" }}>
          <span className="eyebrow-label">DIRECTORY STATUS</span>
          <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "#000000", margin: "0.35rem 0 0.5rem 0" }}>
            No verified advocates match these filters
          </h2>
          <p style={{ color: "var(--text-body)", fontSize: "0.92rem", lineHeight: 1.6, maxWidth: "56ch" }}>
            No enrolled legal practitioners currently match your selected practice domain, state, or language criteria. Try clearing or broadening your search filters to view counsel in nearby jurisdictions.
          </p>
        </section>
      ) : (
        <div>
          {advocates.map((advocate) => (
            <article
              key={advocate.id}
              data-testid="advocate-card"
              style={{
                padding: "2rem 0",
                borderBottom: "1px solid var(--border-hairline)",
                display: "grid",
                gap: "1rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: "1rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#000000", marginBottom: "0.25rem" }}>
                    {advocate.full_name}
                  </h2>
                  <p style={{ fontSize: "0.9rem", color: "var(--text-body)" }}>
                    {advocate.bar_council} &middot; Enrolled {advocate.enrolment_year}
                  </p>
                </div>

                {/* Verified status — default state on this page, marked with weight and neutral check rather than gold */}
                <span style={{ fontSize: "0.82rem", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: "#000000", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                  <Check size={15} />
                  <span>Verified by CaseSeva admin review</span>
                </span>
              </div>

              {/* Details & tags */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1.25rem", fontSize: "0.88rem", color: "var(--text-body)" }}>
                <div>
                  <span style={{ display: "block", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                    Practice Location
                  </span>
                  <strong style={{ color: "#000000" }}>
                    {advocate.place_of_practice}{advocate.court_region ? ` (${advocate.court_region})` : ""}
                  </strong>
                </div>

                <div>
                  <span style={{ display: "block", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                    Practice Domains
                  </span>
                  <span style={{ color: "#000000", fontWeight: 600 }}>
                    {Array.isArray(advocate.practice_domains) ? advocate.practice_domains.join(", ") : advocate.practice_domains || "General Practice"}
                  </span>
                </div>

                <div>
                  <span style={{ display: "block", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                    Languages
                  </span>
                  <span style={{ color: "var(--text-body)" }}>
                    {Array.isArray(advocate.languages) ? advocate.languages.join(", ") : advocate.languages || "English"}
                  </span>
                </div>
              </div>

              {/* Action Button if client is selecting representation for a case */}
              {caseId && (
                <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "0.5rem" }}>
                  <button
                    type="button"
                    className="btn-pill-primary"
                    onClick={() => choose(advocate)}
                  >
                    <span>Request advocate</span>
                    <ArrowUpRight size={15} />
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      {/* Confirmation Modal */}
      {confirmingAdvocate && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.5)",
            backdropFilter: "blur(2px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: "1.5rem",
          }}
        >
          <div
            style={{
              background: "#FFFFFF",
              border: "1px solid #000000",
              maxWidth: "520px",
              width: "100%",
              padding: "2.5rem 2rem",
            }}
          >
            <span className="eyebrow-label">FORMAL ENGAGEMENT</span>
            <h2 style={{ fontSize: "1.3rem", fontWeight: 700, color: "#000000", margin: "0.35rem 0 1rem 0" }}>
              Confirm Advocate Request
            </h2>
            <p style={{ fontSize: "0.92rem", color: "var(--text-body)", lineHeight: 1.6, marginBottom: "1.5rem" }}>
              Are you sure you want to request representation from <strong>{confirmingAdvocate.full_name}</strong> ({confirmingAdvocate.bar_council}) for Case #{caseId}?
              Once requested, counsel will review your unsealed case narrative and evidence annexures before accepting.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "1.5rem" }}>
              <button
                type="button"
                className="btn-text-link"
                style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}
                onClick={() => setConfirmingAdvocate(null)}
                disabled={requesting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-pill-primary"
                onClick={confirmRequest}
                disabled={requesting}
              >
                <span>{requesting ? "Submitting..." : "Confirm & Send Request"}</span>
                <ArrowUpRight size={15} />
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
