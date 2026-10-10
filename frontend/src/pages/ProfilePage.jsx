import { useEffect, useState } from "react";
import { ArrowUpRight, Check } from "lucide-react";
import { getMe, updateProfile } from "../api";
import FormErrors from "../components/FormErrors";

export default function ProfilePage() {
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getMe().then((result) => setForm(result.user));
  }, []);

  if (!form) {
    return (
      <main className="main-container" style={{ paddingTop: "3rem", paddingBottom: "3rem" }}>
        <p style={{ color: "var(--text-muted)", fontSize: "0.95rem" }}>Loading account settings…</p>
      </main>
    );
  }

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setSaved(false);
    setFieldErrors({});
    setBusy(true);
    try {
      const result = await updateProfile({
        full_name: form.full_name,
        mobile_number: form.mobile_number,
        preferred_language: form.preferred_language,
        state: form.state,
        district_city: form.district_city,
      });
      setForm(result.user);
      setSaved(true);
    } catch (requestError) {
      setError(requestError.message);
      setFieldErrors(requestError.fields || {});
    } finally {
      setBusy(false);
    }
  };

  const editable = [
    { key: "full_name", label: "full name" },
    { key: "mobile_number", label: "mobile number" },
    { key: "preferred_language", label: "preferred language" },
    { key: "state", label: "state" },
    { key: "district_city", label: "district city" },
  ];

  const isAdvocate = form.role === "advocate";

  return (
    <main className="main-container" style={{ paddingTop: "2.5rem", paddingBottom: "5rem" }}>
      {/* Simple, unadorned header — keeping settings plain */}
      <header style={{ marginBottom: "2rem", borderBottom: "1px solid var(--border-hairline)", paddingBottom: "1rem" }}>
        <span className="eyebrow-label">ACCOUNT SETTINGS</span>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 700, color: "#000000", marginTop: "0.25rem", marginBottom: "0.25rem" }}>
          Your profile
        </h1>
        <p style={{ color: "var(--text-body)", fontSize: "0.92rem" }}>
          Manage your contact credentials and client preferences.
        </p>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "3rem" }}>
        {/* Account Details & Advocate Credentials */}
        <div>
          <span className="eyebrow-label" style={{ marginBottom: "0.75rem" }}>ACCOUNT CREDENTIALS</span>
          <div style={{ display: "grid", gap: "1.25rem", padding: "1.5rem 0", borderTop: "1px solid var(--border-hairline)", borderBottom: "1px solid var(--border-hairline)" }}>
            <div>
              <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                Email Address
              </span>
              <strong style={{ fontSize: "0.95rem", color: "#000000" }}>{form.email}</strong>
              <span style={{ display: "block", fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                Primary login identifier (read-only)
              </span>
            </div>

            <div>
              <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                Account Role
              </span>
              <strong style={{ fontSize: "0.95rem", color: "#000000", textTransform: "capitalize" }}>{form.role}</strong>
            </div>

            {isAdvocate && (
              <div style={{ display: "grid", gap: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--border-hairline)" }}>
                <div>
                  <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                    Bar Council Record
                  </span>
                  <span style={{ color: "#000000", fontWeight: 600, fontSize: "0.9rem" }}>
                    {form.bar_council || "Not specified"} &middot; {form.enrolment_number || "N/A"} ({form.enrolment_year || "N/A"})
                  </span>
                </div>

                <div>
                  <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                    Place of Practice
                  </span>
                  <span style={{ color: "#000000", fontSize: "0.9rem" }}>
                    {form.place_of_practice || "Not specified"}{form.court_region ? ` (${form.court_region})` : ""}
                  </span>
                </div>

                <div>
                  <span style={{ display: "block", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                    Verification Status
                  </span>
                  <span
                    className={form.verification_status === "REJECTED" ? "status-pill status-pill--crimson" : ""}
                    style={{
                      fontSize: "0.85rem",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: form.verification_status === "REJECTED" ? undefined : form.verification_status === "VERIFIED" ? "#000000" : "var(--text-muted)",
                    }}
                  >
                    {form.verification_status === "VERIFIED" ? "✓ Verified by CaseSeva admin review" : form.verification_status === "UNVERIFIED" ? "Unverified" : "Verification Pending"}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Editable Profile Form */}
        <div>
          <span className="eyebrow-label" style={{ marginBottom: "0.75rem" }}>EDIT PROFILE INFORMATION</span>
          <form onSubmit={submit} style={{ display: "grid", gap: "1.25rem", padding: "1.5rem 0", borderTop: "1px solid var(--border-hairline)" }}>
            {editable.map(({ key, label }) => (
              <div key={key}>
                <label className="clean-label" htmlFor={key} style={{ textTransform: "uppercase" }}>
                  {label}
                </label>
                <input
                  id={key}
                  name={key}
                  aria-label={label}
                  className="clean-input"
                  value={form[key] || ""}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                />
                <FormErrors errors={fieldErrors[key]} />
              </div>
            ))}

            {error && (
              <p
                role="alert"
                style={{
                  background: "#FAFAFA",
                  borderLeft: "3px solid #000000",
                  padding: "0.75rem 1rem",
                  fontSize: "0.88rem",
                  color: "#000000",
                  fontWeight: 600,
                  margin: 0,
                }}
              >
                {error}
              </p>
            )}

            {saved && (
              <p
                role="status"
                style={{
                  background: "#FAFAFA",
                  borderLeft: "3px solid #000000",
                  padding: "0.75rem 1rem",
                  fontSize: "0.88rem",
                  color: "#000000",
                  fontWeight: 600,
                  margin: 0,
                }}
              >
                Profile saved successfully.
              </p>
            )}

            <div style={{ paddingTop: "0.5rem" }}>
              <button
                type="submit"
                className="btn-pill-primary"
                disabled={busy}
              >
                <span>{busy ? "Saving..." : "Save profile"}</span>
                <ArrowUpRight size={15} />
              </button>
            </div>
          </form>
        </div>
      </div>
    </main>
  );
}
