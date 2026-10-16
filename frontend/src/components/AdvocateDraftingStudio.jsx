import { useEffect, useState } from "react";
import {
  generateAdvocateDraft,
  listAdvocateDrafts,
  getAdvocateDraft,
  editAdvocateDraft,
  regenerateDraftSection,
  resolveDraftConflict,
  regenerateFullDraft,
  approveAdvocateDraft,
  downloadDraftPdf,
} from "../api";

const DRAFT_TYPES = [
  { value: "complaint_petition", label: "Complaint / Petition Draft" },
  { value: "legal_notice", label: "Legal Notice" },
  { value: "written_representation", label: "Written Representation" },
  { value: "reply_response", label: "Reply / Response" },
  { value: "affidavit", label: "Affidavit / Supporting Statement" },
  { value: "case_brief", label: "Case Brief" },
  { value: "advocate_case_note", label: "Advocate Case Note" },
  { value: "chronology", label: "Chronology of Events" },
  { value: "evidence_annexure", label: "Evidence & Annexure Index" },
  { value: "other", label: "Other Professional Document" },
];

export default function AdvocateDraftingStudio({ caseId, caseItem, eligibility, onRefreshCase }) {
  const [drafts, setDrafts] = useState([]);
  const [selectedDraftId, setSelectedDraftId] = useState("");
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [activeDraft, setActiveDraft] = useState(null);
  const [draftType, setDraftType] = useState("complaint_petition");
  const [draftMode, setDraftMode] = useState("AUTHORITATIVE");
  const [editingSections, setEditingSections] = useState([]);
  const [titleEdit, setTitleEdit] = useState("");
  const [notesEdit, setNotesEdit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadDrafts = async () => {
    try {
      const res = await listAdvocateDrafts(caseId);
      const list = res.drafts || [];
      setDrafts(list);
      if (list.length > 0 && !selectedDraftId) {
        setSelectedDraftId(list[0].draft_id);
      }
    } catch (err) {
      // non-blocking
    }
  };

  const loadActiveDraft = async (draftId, version = null) => {
    if (!draftId) {
      setActiveDraft(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await getAdvocateDraft(caseId, draftId, version);
      const d = res.draft;
      setActiveDraft(d);
      setSelectedVersion(d.version);
      setTitleEdit(d.title || "");
      setNotesEdit(d.professional_notes || "");
      setEditingSections(JSON.parse(JSON.stringify(d.sections || [])));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    loadDrafts();
  }, [caseId]);

  useEffect(() => {
    if (selectedDraftId) {
      loadActiveDraft(selectedDraftId, selectedVersion);
    }
  }, [selectedDraftId]);

  const handleGenerate = async () => {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const res = await generateAdvocateDraft(caseId, {
        draft_type: draftType,
        draft_mode: draftMode,
      });
      setSuccess("New professional draft generated successfully.");
      await loadDrafts();
      setSelectedDraftId(res.draft.draft_id);
      setSelectedVersion(res.draft.version);
      setActiveDraft(res.draft);
      setTitleEdit(res.draft.title || "");
      setNotesEdit(res.draft.professional_notes || "");
      setEditingSections(JSON.parse(JSON.stringify(res.draft.sections || [])));
      if (onRefreshCase) onRefreshCase();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleSaveVersion = async () => {
    if (!selectedDraftId) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const res = await editAdvocateDraft(caseId, selectedDraftId, {
        title: titleEdit,
        professional_notes: notesEdit,
        section_updates: editingSections.map((s) => ({
          section_id: s.section_id,
          heading: s.heading,
          paragraphs: s.paragraphs,
          advocate_notes: s.advocate_notes,
        })),
      });
      setSuccess(`Version ${res.draft.version} saved successfully.`);
      await loadDrafts();
      await loadActiveDraft(selectedDraftId, res.draft.version);
      if (onRefreshCase) onRefreshCase();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerateSection = async (sectionId) => {
    if (!selectedDraftId) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const res = await regenerateDraftSection(caseId, selectedDraftId, sectionId);
      setSuccess(`Section regenerated. Created version ${res.draft.version}.`);
      await loadDrafts();
      await loadActiveDraft(selectedDraftId, res.draft.version);
      if (onRefreshCase) onRefreshCase();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleResolveConflict = async (sectionId, strategy) => {
    if (!selectedDraftId) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const res = await resolveDraftConflict(caseId, selectedDraftId, {
        section_id: sectionId,
        strategy,
      });
      setSuccess(`Conflict resolved using ${strategy}. Created version ${res.draft.version}.`);
      await loadDrafts();
      await loadActiveDraft(selectedDraftId, res.draft.version);
      if (onRefreshCase) onRefreshCase();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerateFull = async () => {
    if (!selectedDraftId) return;
    if (!window.confirm("Regenerate entire draft from latest Case File? Any manual advocate edits will be preserved and flagged for conflict review.")) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const res = await regenerateFullDraft(caseId, selectedDraftId);
      setSuccess(`Draft regenerated. Created version ${res.draft.version}.`);
      await loadDrafts();
      await loadActiveDraft(selectedDraftId, res.draft.version);
      if (onRefreshCase) onRefreshCase();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleApprove = async () => {
    if (!selectedDraftId) return;
    if (!window.confirm("Approve this professional draft? This will create an immutable advocate approval certification with SHA-256 integrity hash and generate an approved PDF artifact.")) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const res = await approveAdvocateDraft(caseId, selectedDraftId);
      setSuccess(`Draft approved by advocate! Certified Version: ${res.draft.version}.`);
      await loadDrafts();
      await loadActiveDraft(selectedDraftId, res.draft.version);
      if (onRefreshCase) onRefreshCase();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!selectedDraftId) return;
    setBusy(true);
    setError("");
    try {
      await downloadDraftPdf(
        caseId,
        selectedDraftId,
        `${activeDraft?.draft_type || "draft"}_v${activeDraft?.version || 1}_approved.pdf`,
        activeDraft?.version
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const updateParagraph = (secIdx, pIdx, value) => {
    const updated = [...editingSections];
    updated[secIdx].paragraphs[pIdx] = value;
    setEditingSections(updated);
  };

  const addParagraph = (secIdx) => {
    const updated = [...editingSections];
    updated[secIdx].paragraphs.push("");
    setEditingSections(updated);
  };

  const removeParagraph = (secIdx, pIdx) => {
    const updated = [...editingSections];
    updated[secIdx].paragraphs.splice(pIdx, 1);
    setEditingSections(updated);
  };

  const moveSection = (secIdx, direction) => {
    const newIdx = secIdx + direction;
    if (newIdx < 0 || newIdx >= editingSections.length) return;
    const updated = [...editingSections];
    const temp = updated[secIdx];
    updated[secIdx] = updated[newIdx];
    updated[newIdx] = temp;
    setEditingSections(updated);
  };

  const insertFormat = (secIdx, pIdx, prefix, suffix = "") => {
    const updated = [...editingSections];
    const current = updated[secIdx].paragraphs[pIdx] || "";
    updated[secIdx].paragraphs[pIdx] = `${current} ${prefix}text${suffix}`;
    setEditingSections(updated);
  };

  const isEligible = eligibility?.eligible;
  const isStale = activeDraft?.status === "STALE_INPUT";

  return (
    <section style={{ marginBottom: "3rem", background: "#FFFFFF", border: "1px solid #D1D5DB", borderRadius: "8px", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem", borderBottom: "1px solid #E5E7EB", paddingBottom: "1rem", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.35rem", color: "#111827", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span>Engine 3 — Advocate Drafting Studio</span>
            <span style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem", borderRadius: "12px", background: "#FEF3C7", color: "#92400E", fontWeight: 700, textTransform: "uppercase" }}>
              Advocate Only
            </span>
          </h2>
          <p style={{ margin: "0.3rem 0 0 0", fontSize: "0.88rem", color: "#6B7280" }}>
            Professional legal document drafting grounded strictly in the verified Case File. AI is an assistant; you own the final output.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <span style={{ padding: "0.35rem 0.75rem", borderRadius: "4px", fontSize: "0.85rem", fontWeight: 700, background: isEligible ? "#DEF7EC" : "#FDE8E8", color: isEligible ? "#03543F" : "#9B1C1C" }}>
            {isEligible ? "✓ Eligible for Drafting" : "⚠ Prerequisites Pending"}
          </span>
        </div>
      </div>

      {error && (
        <div style={{ background: "#FDE8E8", border: "1px solid #F8B4B4", color: "#9B1C1C", padding: "0.75rem 1rem", borderRadius: "6px", marginBottom: "1rem", fontSize: "0.88rem" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {success && (
        <div style={{ background: "#DEF7EC", border: "1px solid #BCF0DA", color: "#03543F", padding: "0.75rem 1rem", borderRadius: "6px", marginBottom: "1rem", fontSize: "0.88rem" }}>
          {success}
        </div>
      )}

      {/* Eligibility Checklist Banner if ineligible */}
      {!isEligible && eligibility && (
        <div style={{ background: "#F9FAFB", border: "1px solid #E5E7EB", padding: "1rem", borderRadius: "6px", marginBottom: "1.5rem" }}>
          <strong style={{ fontSize: "0.9rem", color: "#374151" }}>Drafting Requirements:</strong>
          <ul style={{ margin: "0.5rem 0 0 0", paddingLeft: "1.25rem", fontSize: "0.85rem", color: "#4B5563" }}>
            {eligibility.reasons?.map((r, i) => (
              <li key={i} style={{ color: "#DC2626" }}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Draft Creation Controls */}
      <div style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", padding: "1rem", borderRadius: "6px", marginBottom: "1.5rem", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", alignItems: "end" }}>
        <div>
          <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "#475569", marginBottom: "0.3rem" }}>Document Type</label>
          <select
            value={draftType}
            onChange={(e) => setDraftType(e.target.value)}
            disabled={busy || !isEligible}
            style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #CBD5E1", fontSize: "0.88rem" }}
          >
            {DRAFT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "#475569", marginBottom: "0.3rem" }}>Drafting Mode</label>
          <select
            value={draftMode}
            onChange={(e) => setDraftMode(e.target.value)}
            disabled={busy || !isEligible}
            style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #CBD5E1", fontSize: "0.88rem" }}
          >
            <option value="AUTHORITATIVE">Authoritative (Verified Law Required)</option>
            <option value="FACTUAL_WORKING_DRAFT">Factual Working Draft (Factual grounding only)</option>
          </select>
        </div>

        <div>
          <button
            className="btn-pill-primary"
            onClick={handleGenerate}
            disabled={busy || !isEligible}
            style={{ width: "100%", padding: "0.55rem 1rem" }}
          >
            {busy ? "Processing…" : "+ Generate New Draft"}
          </button>
        </div>
      </div>

      {/* Draft List / Version Selector */}
      {drafts.length > 0 && (
        <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginBottom: "1.5rem", flexWrap: "wrap", background: "#F1F5F9", padding: "0.75rem 1rem", borderRadius: "6px" }}>
          <div>
            <label style={{ fontSize: "0.82rem", fontWeight: 600, color: "#475569", marginRight: "0.5rem" }}>Select Draft:</label>
            <select
              value={selectedDraftId}
              onChange={(e) => {
                setSelectedDraftId(e.target.value);
                setSelectedVersion(null);
              }}
              style={{ padding: "0.4rem 0.75rem", borderRadius: "4px", border: "1px solid #CBD5E1", fontSize: "0.85rem" }}
            >
              {drafts.map((d) => (
                <option key={d.draft_id} value={d.draft_id}>
                  {d.draft_type.replace("_", " ").toUpperCase()} (v{d.current_version}) — {d.status}
                </option>
              ))}
            </select>
          </div>

          {activeDraft && (
            <div>
              <label style={{ fontSize: "0.82rem", fontWeight: 600, color: "#475569", marginRight: "0.5rem" }}>Version History:</label>
              <select
                value={selectedVersion || activeDraft.version}
                onChange={(e) => {
                  const ver = parseInt(e.target.value, 10);
                  setSelectedVersion(ver);
                  loadActiveDraft(selectedDraftId, ver);
                }}
                style={{ padding: "0.4rem 0.75rem", borderRadius: "4px", border: "1px solid #CBD5E1", fontSize: "0.85rem" }}
              >
                {Array.from({ length: activeDraft.version }, (_, i) => i + 1).map((v) => (
                  <option key={v} value={v}>Version {v} {v === activeDraft.version ? "(Current)" : ""}</option>
                ))}
              </select>
            </div>
          )}

          {activeDraft && (
            <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
              <button
                onClick={handleRegenerateFull}
                disabled={busy}
                style={{ padding: "0.4rem 0.75rem", borderRadius: "4px", border: "1px solid #94A3B8", background: "#FFFFFF", cursor: "pointer", fontSize: "0.82rem" }}
              >
                Regenerate Full
              </button>
            </div>
          )}
        </div>
      )}

      {/* Stale Input Warning */}
      {isStale && (
        <div style={{ background: "#FFFBEB", border: "1px solid #FCD34D", color: "#92400E", padding: "0.75rem 1rem", borderRadius: "6px", marginBottom: "1.5rem", fontSize: "0.88rem" }}>
          <strong>⚠ Input Changed (STALE_INPUT):</strong> The underlying Engine 1 Case File was updated after this draft version was generated.
          Your historical draft is preserved. You can continue reviewing or regenerate against the current Case File.
        </div>
      )}

      {/* Active Draft Editor */}
      {activeDraft && (
        <div style={{ border: "1px solid #E2E8F0", borderRadius: "6px", padding: "1.25rem" }}>
          {/* Draft Metadata & Disclosures */}
          <div style={{ borderBottom: "1px solid #E2E8F0", paddingBottom: "1rem", marginBottom: "1.25rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
              <div style={{ flex: 1, minWidth: "280px" }}>
                <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "#64748B", marginBottom: "0.2rem" }}>Document Title</label>
                <input
                  type="text"
                  value={titleEdit}
                  onChange={(e) => setTitleEdit(e.target.value)}
                  style={{ width: "100%", padding: "0.5rem", borderRadius: "4px", border: "1px solid #CBD5E1", fontSize: "1.1rem", fontWeight: 700 }}
                />
              </div>

              <div style={{ textAlign: "right", fontSize: "0.82rem", color: "#64748B" }}>
                <div><strong>Draft Status:</strong> <span style={{ textTransform: "uppercase", fontWeight: 700, color: activeDraft.status === "ADVOCATE_APPROVED" ? "#16A34A" : "#2563EB" }}>{activeDraft.status}</span></div>
                <div>Source E1 Version: <strong>v{activeDraft.engine1_case_file_version}</strong></div>
                <div>Engine 2 Status: <strong>{activeDraft.engine2_status}</strong></div>
              </div>
            </div>

            {/* Disclosures box */}
            {activeDraft.disclosures?.length > 0 && (
              <div style={{ marginTop: "0.75rem", background: "#F8FAFC", padding: "0.5rem 0.75rem", borderRadius: "4px", fontSize: "0.82rem", color: "#475569" }}>
                <strong>Statutory Disclosures:</strong>
                <ul style={{ margin: "0.2rem 0 0 0", paddingLeft: "1.25rem" }}>
                  {activeDraft.disclosures.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Section-by-Section Editor */}
          <div style={{ display: "grid", gap: "1.5rem", marginBottom: "2rem" }}>
            {editingSections.map((sec, secIdx) => (
              <div key={sec.section_id || secIdx} style={{ border: "1px solid #E2E8F0", borderRadius: "6px", padding: "1rem", background: sec.conflict ? "#FEF2F2" : "#FFFFFF" }}>
                {/* Section Header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1 }}>
                    <span style={{ fontSize: "0.75rem", color: "#94A3B8", fontWeight: 700 }}>#{secIdx + 1}</span>
                    <input
                      type="text"
                      value={sec.heading}
                      onChange={(e) => {
                        const updated = [...editingSections];
                        updated[secIdx].heading = e.target.value;
                        setEditingSections(updated);
                      }}
                      style={{ padding: "0.35rem 0.5rem", borderRadius: "4px", border: "1px solid #CBD5E1", fontWeight: 700, fontSize: "0.95rem", flex: 1, maxWidth: "350px" }}
                    />
                    {sec.edited_by_advocate && (
                      <span style={{ fontSize: "0.72rem", background: "#E0E7FF", color: "#3730A3", padding: "0.15rem 0.45rem", borderRadius: "10px", fontWeight: 600 }}>
                        Advocate Edited
                      </span>
                    )}
                  </div>

                  <div style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
                    <button
                      type="button"
                      onClick={() => moveSection(secIdx, -1)}
                      disabled={secIdx === 0}
                      title="Move section up"
                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", border: "1px solid #CBD5E1", background: "#F8FAFC", borderRadius: "3px", cursor: "pointer" }}
                    >
                      ▲
                    </button>
                    <button
                      type="button"
                      onClick={() => moveSection(secIdx, 1)}
                      disabled={secIdx === editingSections.length - 1}
                      title="Move section down"
                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", border: "1px solid #CBD5E1", background: "#F8FAFC", borderRadius: "3px", cursor: "pointer" }}
                    >
                      ▼
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRegenerateSection(sec.section_id)}
                      disabled={busy}
                      style={{ padding: "0.25rem 0.6rem", fontSize: "0.78rem", border: "1px solid #0284C7", background: "#F0F9FF", color: "#0369A1", borderRadius: "4px", cursor: "pointer", fontWeight: 600 }}
                    >
                      ↻ Regenerate Section
                    </button>
                  </div>
                </div>

                {/* Conflict Resolution Block if active conflict */}
                {sec.conflict && (
                  <div style={{ background: "#FEF2F2", border: "1px solid #FCA5A5", padding: "0.85rem", borderRadius: "6px", marginBottom: "1rem" }}>
                    <div style={{ color: "#991B1B", fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.4rem" }}>
                      ⚠ Conflict Detected: AI regeneration proposed changes, but your advocate edits remain authoritative by default.
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", fontSize: "0.82rem", marginBottom: "0.75rem" }}>
                      <div style={{ background: "#FFFFFF", padding: "0.5rem", borderRadius: "4px", border: "1px solid #F87171" }}>
                        <strong style={{ color: "#991B1B" }}>Your Advocate Version (Authoritative):</strong>
                        {sec.conflict.advocate_paragraphs?.map((p, pi) => (
                          <p key={pi} style={{ margin: "0.3rem 0" }}>{p}</p>
                        ))}
                      </div>
                      <div style={{ background: "#FFFFFF", padding: "0.5rem", borderRadius: "4px", border: "1px solid #60A5FA" }}>
                        <strong style={{ color: "#1D4ED8" }}>AI Proposed Regeneration:</strong>
                        {sec.conflict.proposed_paragraphs?.map((p, pi) => (
                          <p key={pi} style={{ margin: "0.3rem 0" }}>{p}</p>
                        ))}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        onClick={() => handleResolveConflict(sec.section_id, "KEEP_ADVOCATE")}
                        disabled={busy}
                        style={{ padding: "0.35rem 0.75rem", background: "#DC2626", color: "#FFF", border: "none", borderRadius: "4px", fontSize: "0.8rem", fontWeight: 700, cursor: "pointer" }}
                      >
                        Keep My Edits (Default)
                      </button>
                      <button
                        onClick={() => handleResolveConflict(sec.section_id, "USE_REGENERATED")}
                        disabled={busy}
                        style={{ padding: "0.35rem 0.75rem", background: "#2563EB", color: "#FFF", border: "none", borderRadius: "4px", fontSize: "0.8rem", fontWeight: 700, cursor: "pointer" }}
                      >
                        Use AI Regeneration
                      </button>
                      <button
                        onClick={() => handleResolveConflict(sec.section_id, "MERGE")}
                        disabled={busy}
                        style={{ padding: "0.35rem 0.75rem", background: "#4B5563", color: "#FFF", border: "none", borderRadius: "4px", fontSize: "0.8rem", fontWeight: 700, cursor: "pointer" }}
                      >
                        Merge Both
                      </button>
                    </div>
                  </div>
                )}

                {/* Paragraphs */}
                <div style={{ display: "grid", gap: "0.5rem" }}>
                  {sec.paragraphs.map((p, pIdx) => (
                    <div key={pIdx} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
                      <textarea
                        value={p}
                        onChange={(e) => updateParagraph(secIdx, pIdx, e.target.value)}
                        rows={Math.max(2, Math.ceil(p.length / 90))}
                        style={{ flex: 1, padding: "0.5rem", borderRadius: "4px", border: "1px solid #CBD5E1", fontSize: "0.88rem", fontFamily: "inherit" }}
                      />
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                        <button
                          type="button"
                          onClick={() => insertFormat(secIdx, pIdx, "**", "**")}
                          title="Bold"
                          style={{ padding: "0.15rem 0.4rem", fontSize: "0.72rem", border: "1px solid #CBD5E1", background: "#FFF", borderRadius: "3px", cursor: "pointer", fontWeight: 700 }}
                        >
                          B
                        </button>
                        <button
                          type="button"
                          onClick={() => insertFormat(secIdx, pIdx, "*", "*")}
                          title="Italic"
                          style={{ padding: "0.15rem 0.4rem", fontSize: "0.72rem", border: "1px solid #CBD5E1", background: "#FFF", borderRadius: "3px", cursor: "pointer", fontStyle: "italic" }}
                        >
                          I
                        </button>
                        <button
                          type="button"
                          onClick={() => removeParagraph(secIdx, pIdx)}
                          title="Delete paragraph"
                          style={{ padding: "0.15rem 0.4rem", fontSize: "0.72rem", border: "1px solid #FCA5A5", background: "#FEF2F2", color: "#B91C1C", borderRadius: "3px", cursor: "pointer" }}
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => addParagraph(secIdx)}
                    style={{ alignSelf: "flex-start", padding: "0.25rem 0.6rem", fontSize: "0.78rem", border: "1px dashed #94A3B8", background: "transparent", borderRadius: "4px", cursor: "pointer", color: "#475569" }}
                  >
                    + Add Paragraph
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Action Bar */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid #E2E8F0", paddingTop: "1.25rem", flexWrap: "wrap", gap: "0.75rem" }}>
            <button
              className="btn-pill-primary"
              onClick={handleSaveVersion}
              disabled={busy}
              style={{ background: "#2563EB" }}
            >
              {busy ? "Saving…" : "Save New Version"}
            </button>

            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
              <button
                className="btn-pill-primary"
                onClick={handleApprove}
                disabled={busy || isStale}
                style={{ background: activeDraft.status === "ADVOCATE_APPROVED" ? "#16A34A" : "#059669" }}
              >
                {activeDraft.status === "ADVOCATE_APPROVED" ? "✓ Approved by Advocate" : "Approve Professional Draft"}
              </button>

              {activeDraft.pdf_artifact && (
                <button
                  type="button"
                  onClick={handleDownloadPdf}
                  disabled={busy}
                  style={{ padding: "0.55rem 1.1rem", borderRadius: "20px", border: "1px solid #059669", background: "#ECFDF5", color: "#065F46", fontWeight: 700, cursor: "pointer", fontSize: "0.88rem" }}
                >
                  📥 Download Approved PDF
                </button>
              )}
            </div>
          </div>

          {/* Approval Record Information */}
          {activeDraft.approval_record && (
            <div style={{ marginTop: "1.25rem", background: "#F0FDF4", border: "1px solid #BBF7D0", padding: "0.75rem 1rem", borderRadius: "6px", fontSize: "0.82rem", color: "#166534" }}>
              <strong>Advocate Approval Certification:</strong>
              <div>Approved by: <code>{activeDraft.approval_record.approved_by_advocate_id}</code> at {new Date(activeDraft.approval_record.approved_at).toLocaleString()}</div>
              <div>Integrity SHA-256 Digest: <code>{activeDraft.approval_record.integrity_hash}</code></div>
              <div>Certified Source Engine-1 Version: <strong>v{activeDraft.approval_record.source_engine1_version}</strong></div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
