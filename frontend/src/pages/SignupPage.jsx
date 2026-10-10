import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { setToken, signup, uploadVerificationDocument } from "../api";
import FormErrors from "../components/FormErrors";
import AppHeader from "../components/AppHeader";
import { ArrowUpRight } from "lucide-react";

const initial = {
  full_name: "", email: "", mobile_number: "", password: "",
  preferred_language: "English", state: "", district_city: "",
  role: "client", bar_council: "", enrolment_number: "", enrolment_year: "",
  place_of_practice: "", court_region: "", practice_domains: ["Consumer"], languages: ["English"],
};

export default function SignupPage() {
  const [form, setForm] = useState(initial);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [verificationFiles, setVerificationFiles] = useState([]);
  const navigate = useNavigate();

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    const clientErrors = {};
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) clientErrors.email = "Enter a valid email address.";
    if (!/^[6-9]\d{9}$/.test(form.mobile_number.trim())) clientErrors.mobile_number = "Enter a valid 10-digit Indian mobile number.";
    if (form.password.length < 8) clientErrors.password = "Password must be at least 8 characters.";
    if (form.role === "advocate" && !verificationFiles.length) clientErrors.verification_documents = "Provide supporting enrolment documents for admin review.";
    if (Object.keys(clientErrors).length) {
      setFieldErrors(clientErrors);
      setError("Please fix the highlighted fields.");
      return;
    }
    setLoading(true);
    try {
      const payload = form.role === "advocate"
        ? {
            ...form,
            enrolment_year: Number(form.enrolment_year),
            practice_domains: Array.isArray(form.practice_domains) ? form.practice_domains : form.practice_domains.split(",").map((item) => item.trim()).filter(Boolean),
            languages: Array.isArray(form.languages) ? form.languages : form.languages.split(",").map((item) => item.trim()).filter(Boolean)
          }
        : Object.fromEntries(Object.entries(form).filter(([key]) => !["bar_council", "enrolment_number", "enrolment_year", "place_of_practice", "court_region", "practice_domains", "languages"].includes(key)));
      const result = await signup(payload);
      setToken(result.session_token);
      if (form.role === "advocate") for (const file of verificationFiles) await uploadVerificationDocument(file);
      const target = result.user?.role === "advocate" ? "/advocate/dashboard" : "/dashboard";
      navigate(target, { replace: true });
    } catch (requestError) {
      setError(requestError.message);
      setFieldErrors(requestError.fields || {});
    } finally {
      setLoading(false);
    }
  };

  const field = (name, label, type = "text", placeholder = "") => (
    <div key={name} style={{ marginBottom: "1rem" }}>
      <label htmlFor={name}>
        {label}
        <input
          id={name}
          name={name}
          type={type}
          value={form[name]}
          placeholder={placeholder}
          onChange={(e) => setForm({ ...form, [name]: e.target.value })}
        />
      </label>
      <FormErrors errors={fieldErrors[name]} />
    </div>
  );

  const isAdvocate = form.role === "advocate";

  return (
    <AppHeader>
      <main style={{ flex: 1, padding: "4rem 2rem 5rem", maxWidth: "680px", margin: "0 auto", width: "100%" }}>
        {/* Editorial Heading */}
        <div style={{ marginBottom: "2.5rem" }}>
          <span className="eyebrow-label">INITIALIZE WORKSPACE</span>
          <div className="hairline-gold" />

          <div className="stacked-headline" style={{ marginBottom: "1rem" }}>
            <span className="headline-secondary">CREATE YOUR</span>
            <span className="headline-gold" style={{ fontSize: "clamp(2.2rem, 5vw, 3.2rem)" }}>
              CASESEVA ACCOUNT.
            </span>
          </div>

          <p style={{ fontSize: "1rem", color: "var(--text-body)" }}>
            Select your account role to configure statutory analysis or advocate verification.
          </p>
        </div>

        {/* Role choice upfront - minimal segmented pill */}
        <div style={{ marginBottom: "2rem" }}>
          <span className="eyebrow-label" style={{ marginBottom: "0.5rem" }}>ACCOUNT TYPE</span>
          <div className="role-segmented-control">
            <button
              type="button"
              className={`role-tab-button${!isAdvocate ? " active" : ""}`}
              onClick={() => setForm({ ...form, role: "client" })}
            >
              Client (Casework)
            </button>
            <button
              type="button"
              className={`role-tab-button${isAdvocate ? " active" : ""}`}
              onClick={() => setForm({ ...form, role: "advocate" })}
            >
              Advocate (Licensed Bar)
            </button>
          </div>
        </div>

        {error && (
          <div role="alert">
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={submit} noValidate>
          {/* Hidden role select for Playwright and programmatic compatibility */}
          <label style={{ display: "none" }}>
            Account type
            <select name="role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="client">Client</option>
              <option value="advocate">Advocate</option>
            </select>
          </label>

          {/* Standard Fields */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "0.25rem" }}>
            {field("full_name", "Full name", "text", "Anita Sharma")}
            {field("email", "Email", "email", "name@domain.com")}
            {field("mobile_number", "Mobile number", "text", "9876543210")}
            {field("password", "Password", "password", "••••••••")}
            {field("preferred_language", "Preferred language", "text", "English")}
            
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
              {field("state", "State", "text", "Maharashtra")}
              {field("district_city", "District / city", "text", "Mumbai")}
            </div>
          </div>

          {/* Advocate Specific Fields */}
          {isAdvocate && (
            <div style={{ marginTop: "2rem", paddingTop: "2rem", borderTop: "1px solid var(--border-hairline)" }}>
              <span className="eyebrow-label" style={{ color: "#000000", marginBottom: "1.25rem" }}>
                BAR COUNCIL REGISTRATION DETAILS
              </span>
              
              {field("bar_council", "State Bar Council", "text", "e.g. Bar Council of Maharashtra and Goa")}
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                {field("enrolment_number", "Enrolment / bar registration number", "text", "MAH/1234/2020")}
                {field("enrolment_year", "Enrolment year", "number", "2020")}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                {field("place_of_practice", "Ordinary place of practice", "text", "Mumbai")}
                {field("court_region", "Court / region", "text", "Bombay High Court")}
              </div>

              {field("practice_domains", "Practice domains", "text", "Consumer, Labour")}
              <label>Supporting enrolment documents<input type="file" multiple accept=".pdf,.png,.jpg,.jpeg" onChange={event => setVerificationFiles(Array.from(event.target.files))} /></label>
              {fieldErrors.verification_documents && <p role="alert">{fieldErrors.verification_documents}</p>}
              {field("languages", "Languages", "text", "English, Hindi, Marathi")}
            </div>
          )}

          <button
            type="submit"
            className="btn-pill-primary btn-full"
            disabled={loading}
            style={{ marginTop: "1.5rem", padding: "0.95rem" }}
          >
            <span>{loading ? "Creating account…" : "Create account"}</span>
            <ArrowUpRight size={16} />
          </button>
        </form>

        <div style={{ marginTop: "2.5rem", paddingTop: "1.75rem", borderTop: "1px solid var(--border-hairline)", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.9rem" }}>
          <span style={{ color: "var(--text-muted)" }}>Already registered?</span>
          <Link to="/login" className="btn-text-link">
            Log in to your account
          </Link>
        </div>
      </main>
    </AppHeader>
  );
}
