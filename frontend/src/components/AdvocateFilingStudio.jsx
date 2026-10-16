import React, { useState, useEffect } from "react";
import {
  getFilingEligibility,
  prepareFilingPackage,
  listFilingPackages,
  downloadFilingBundle,
} from "../api";

export default function AdvocateFilingStudio({ caseId, caseItem, onRefreshCase }) {
  const [eligibility, setEligibility] = useState(null);
  const [packages, setPackages] = useState([]);
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  const loadData = async () => {
    setLoading(true);
    setError("");
    try {
      const [eligRes, pkgsRes] = await Promise.all([
        getFilingEligibility(caseId).catch((err) => ({ error: err.message })),
        listFilingPackages(caseId).catch((err) => []),
      ]);
      setEligibility(eligRes);
      setPackages(Array.isArray(pkgsRes) ? pkgsRes : []);
      if (Array.isArray(pkgsRes) && pkgsRes.length > 0) {
        setSelectedPackage(pkgsRes[0]);
      }
    } catch (err) {
      setError(err.message || "Failed to load filing preparation details.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (caseId) {
      loadData();
    }
  }, [caseId]);

  const handlePrepare = async () => {
    setPreparing(true);
    setError("");
    setSuccessMsg("");
    try {
      const res = await prepareFilingPackage(caseId, {});
      setSuccessMsg(`Filing package v${res.version} successfully prepared! (Readiness: ${res.status})`);
      await loadData();
      if (onRefreshCase) onRefreshCase();
    } catch (err) {
      setError(err.message || "Failed to prepare filing package.");
    } finally {
      setPreparing(false);
    }
  };

  const handleDownload = async (pkg) => {
    if (!pkg) return;
    setDownloading(true);
    try {
      await downloadFilingBundle(caseId, pkg.filing_package_id, `filing_package_${caseId}_v${pkg.version}.zip`);
    } catch (err) {
      setError(err.message || "Failed to download export bundle.");
    } finally {
      setDownloading(false);
    }
  };

  const isEligible = eligibility && eligibility.eligible;
  const legalStatus = eligibility ? eligibility.legal_foundation_status : "PENDING_SOURCE";

  const getStatusBadge = (status) => {
    switch (status) {
      case "READY_FOR_HUMAN_FILING":
        return <span style={{ background: "#2E7D32", color: "#fff", padding: "0.25rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem", fontWeight: "bold" }}>READY FOR HUMAN FILING</span>;
      case "PREPARATION_ONLY":
        return <span style={{ background: "#1565C0", color: "#fff", padding: "0.25rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem", fontWeight: "bold" }}>PREPARATION ONLY (UNVERIFIED LAW / WORKING DRAFT)</span>;
      case "MISSING_REQUIREMENTS":
        return <span style={{ background: "#E65100", color: "#fff", padding: "0.25rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem", fontWeight: "bold" }}>MISSING REQUIREMENTS</span>;
      case "STALE":
        return <span style={{ background: "#C62828", color: "#fff", padding: "0.25rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem", fontWeight: "bold" }}>STALE (INPUT CHANGED)</span>;
      case "SUPERSEDED":
        return <span style={{ background: "#757575", color: "#fff", padding: "0.25rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem", fontWeight: "bold" }}>SUPERSEDED</span>;
      default:
        return <span style={{ background: "#555", color: "#fff", padding: "0.25rem 0.6rem", borderRadius: "4px", fontSize: "0.85rem" }}>{status || "PENDING"}</span>;
    }
  };

  return (
    <section className="card" style={{ marginTop: "2rem", border: "1px solid #004D40", borderRadius: "8px", padding: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #E0E0E0", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
        <div>
          <h2 style={{ margin: 0, color: "#004D40", fontSize: "1.3rem" }}>
            Phase 10 — Safe Filing Preparation Studio
          </h2>
          <p style={{ margin: "0.25rem 0 0", fontSize: "0.88rem", color: "#555" }}>
            Advocate-controlled bundle assembly, evidence indexing, deterministic manifest, and pre-submission safety checks.
          </p>
        </div>
        <button className="btn-secondary" onClick={loadData} disabled={loading} style={{ fontSize: "0.85rem" }}>
          ↻ Refresh
        </button>
      </div>

      {/* Prominent Safety Notice */}
      <div style={{ background: "#E0F2F1", borderLeft: "4px solid #00796B", padding: "0.75rem 1rem", marginBottom: "1.25rem", borderRadius: "4px", fontSize: "0.88rem" }}>
        <strong>Filing Safety Boundary:</strong> Phase 10 prepares filing materials but does NOT submit anything to a court or external filing portal. Only the assigned verified advocate can prepare the filing package. Physical or DSC signatures and filing portal submission remain explicit human actions.
      </div>

      {error && (
        <div style={{ background: "#FFEBEE", color: "#C62828", padding: "0.75rem 1rem", borderRadius: "4px", marginBottom: "1rem", fontSize: "0.88rem" }}>
          {error}
        </div>
      )}

      {successMsg && (
        <div style={{ background: "#E8F5E9", color: "#2E7D32", padding: "0.75rem 1rem", borderRadius: "4px", marginBottom: "1rem", fontSize: "0.88rem" }}>
          {successMsg}
        </div>
      )}

      {/* Eligibility Gate Status */}
      <div style={{ background: "#FAFAFA", border: "1px solid #ECEFF1", borderRadius: "6px", padding: "1rem", marginBottom: "1.5rem" }}>
        <h3 style={{ fontSize: "1.05rem", margin: "0 0 0.5rem", color: "#37474F" }}>Filing Eligibility Gate</h3>
        {eligibility ? (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.75rem", fontSize: "0.85rem" }}>
              <div>
                <strong>Assigned Verified Advocate:</strong>{" "}
                {eligibility.checks?.assigned_advocate && eligibility.checks?.advocate_verified ? "✓ Confirmed" : "✗ Ineligible"}
              </div>
              <div>
                <strong>Active Citizen Consent:</strong>{" "}
                {eligibility.checks?.active_consent ? "✓ Active (Scoped)" : "✗ Missing / Revoked"}
              </div>
              <div>
                <strong>Engine-1 Case File:</strong>{" "}
                {eligibility.checks?.reviewed_engine1_current ? `✓ Current (v${eligibility.engine1_version})` : "✗ Stale / Unreviewed"}
              </div>
              <div>
                <strong>Advocate-Approved Draft:</strong>{" "}
                {eligibility.checks?.draft_approved ? `✓ Approved (v${eligibility.draft_version})` : "✗ Approval Required"}
              </div>
              <div>
                <strong>Legal Foundation Status:</strong>{" "}
                <span style={{ fontWeight: "bold", color: legalStatus === "VERIFIED_AUTHORITY" ? "#2E7D32" : "#E65100" }}>
                  {legalStatus}
                </span>
              </div>
              <div>
                <strong>Engine 2 (Optional):</strong>{" "}
                <span style={{ color: "#555" }}>{eligibility.engine2_disclosure || "Not run"}</span>
              </div>
            </div>

            {!isEligible && eligibility.reasons && eligibility.reasons.length > 0 && (
              <div style={{ marginTop: "0.75rem", padding: "0.5rem 0.75rem", background: "#FFF3E0", borderLeft: "3px solid #FF9800", borderRadius: "2px", fontSize: "0.82rem" }}>
                <strong>Blockers:</strong>
                <ul style={{ margin: "0.25rem 0 0 1rem", padding: 0 }}>
                  {eligibility.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p style={{ fontSize: "0.85rem", color: "#777" }}>Loading eligibility status...</p>
        )}

        <div style={{ marginTop: "1rem", display: "flex", gap: "1rem", alignItems: "center" }}>
          <button
            className="btn-pill-primary"
            style={{ padding: "0.6rem 1.4rem", fontSize: "0.95rem" }}
            disabled={!isEligible || preparing}
            onClick={handlePrepare}
          >
            {preparing ? "Preparing Package..." : "Prepare Filing Package"}
          </button>
          {!isEligible && (
            <span style={{ fontSize: "0.82rem", color: "#777" }}>
              (Must resolve blockers above before preparing filing package)
            </span>
          )}
        </div>
      </div>

      {/* Prepared Packages History */}
      {packages.length > 0 && (
        <div style={{ marginTop: "1.5rem" }}>
          <h3 style={{ fontSize: "1.05rem", margin: "0 0 0.75rem", color: "#37474F" }}>
            Prepared Filing Packages ({packages.length})
          </h3>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
            {packages.map((pkg) => (
              <button
                key={pkg.filing_package_id}
                className={selectedPackage?.filing_package_id === pkg.filing_package_id ? "btn-secondary active" : "btn-secondary"}
                onClick={() => setSelectedPackage(pkg)}
                style={{
                  fontSize: "0.82rem",
                  padding: "0.4rem 0.8rem",
                  borderColor: selectedPackage?.filing_package_id === pkg.filing_package_id ? "#004D40" : "#ccc",
                  background: selectedPackage?.filing_package_id === pkg.filing_package_id ? "#E0F2F1" : "#fff",
                }}
              >
                Package v{pkg.version} ({pkg.status})
              </button>
            ))}
          </div>

          {selectedPackage && (
            <div style={{ border: "1px solid #CFD8DC", borderRadius: "6px", padding: "1.25rem", background: "#fff" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
                <div>
                  <h4 style={{ margin: "0 0 0.25rem", fontSize: "1.1rem" }}>
                    Filing Package v{selectedPackage.version} ({selectedPackage.filing_package_id})
                  </h4>
                  <div style={{ fontSize: "0.82rem", color: "#666" }}>
                    Created: {new Date(selectedPackage.created_at).toLocaleString()} | Bound E1: v{selectedPackage.engine1_case_file_version} | Draft: v{selectedPackage.engine3_draft_version}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  {getStatusBadge(selectedPackage.status)}
                </div>
              </div>

              {/* Package Digest & Integrity */}
              <div style={{ background: "#F5F5F5", padding: "0.6rem 0.8rem", borderRadius: "4px", fontSize: "0.8rem", fontFamily: "monospace", marginBottom: "1rem" }}>
                <strong>Package Digest (SHA-256):</strong> {selectedPackage.package_digest || "N/A"}<br />
                <strong>Draft Integrity Hash:</strong> {selectedPackage.draft_integrity_hash || "N/A"}
              </div>

              {/* Pre-Submission Checklist */}
              {selectedPackage.pre_submission_checklist && selectedPackage.pre_submission_checklist.length > 0 && (
                <div style={{ marginBottom: "1.25rem" }}>
                  <h5 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem" }}>Pre-Submission Checklist</h5>
                  <div style={{ display: "grid", gap: "0.4rem" }}>
                    {selectedPackage.pre_submission_checklist.map((chk, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "0.4rem 0.6rem",
                          borderRadius: "4px",
                          background: chk.status === "PASSED" ? "#F1F8E9" : (chk.status === "WARNING" ? "#FFFDE7" : "#FFEBEE"),
                          fontSize: "0.82rem",
                        }}
                      >
                        <div>
                          <strong>{chk.label}</strong>: <span style={{ color: "#444" }}>{chk.details}</span>
                        </div>
                        <span style={{ fontWeight: "bold", fontSize: "0.75rem", color: chk.status === "PASSED" ? "#2E7D32" : (chk.status === "WARNING" ? "#F57F17" : "#C62828") }}>
                          {chk.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Annexures & Evidence Index */}
              {selectedPackage.annexures && selectedPackage.annexures.length > 0 && (
                <div style={{ marginBottom: "1.25rem" }}>
                  <h5 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem" }}>
                    Indexed Annexures ({selectedPackage.annexures.length})
                  </h5>
                  <table style={{ width: "100%", fontSize: "0.82rem", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ background: "#ECEFF1", textAlign: "left" }}>
                        <th style={{ padding: "0.4rem" }}>Label</th>
                        <th style={{ padding: "0.4rem" }}>Evidence ID</th>
                        <th style={{ padding: "0.4rem" }}>Filename</th>
                        <th style={{ padding: "0.4rem" }}>Source Hash (SHA-256)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedPackage.annexures.map((a, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid #ECEFF1" }}>
                          <td style={{ padding: "0.4rem", fontWeight: "bold" }}>{a.annexure_label}</td>
                          <td style={{ padding: "0.4rem" }}>{a.evidence_id}</td>
                          <td style={{ padding: "0.4rem" }}>{a.filename}</td>
                          <td style={{ padding: "0.4rem", fontFamily: "monospace" }}>{a.source_hash?.slice(0, 16)}...</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Document Manifest */}
              {selectedPackage.document_manifest && selectedPackage.document_manifest.length > 0 && (
                <div style={{ marginBottom: "1.25rem" }}>
                  <h5 style={{ margin: "0 0 0.5rem", fontSize: "0.95rem" }}>
                    Document Manifest ({selectedPackage.document_manifest.length} artifacts)
                  </h5>
                  <table style={{ width: "100%", fontSize: "0.82rem", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ background: "#ECEFF1", textAlign: "left" }}>
                        <th style={{ padding: "0.4rem" }}>Item Type</th>
                        <th style={{ padding: "0.4rem" }}>Filename</th>
                        <th style={{ padding: "0.4rem" }}>Size</th>
                        <th style={{ padding: "0.4rem" }}>Artifact Hash (SHA-256)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedPackage.document_manifest.map((m, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid #ECEFF1" }}>
                          <td style={{ padding: "0.4rem", fontWeight: "bold" }}>{m.item_type}</td>
                          <td style={{ padding: "0.4rem" }}>{m.filename}</td>
                          <td style={{ padding: "0.4rem" }}>{m.size_bytes} B</td>
                          <td style={{ padding: "0.4rem", fontFamily: "monospace" }}>{m.sha256?.slice(0, 16)}...</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Download Bundle Action */}
              <div style={{ borderTop: "1px solid #ECEFF1", paddingTop: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <button
                  className="btn-pill-primary"
                  onClick={() => handleDownload(selectedPackage)}
                  disabled={downloading}
                  style={{ fontSize: "0.9rem", padding: "0.5rem 1.25rem" }}
                >
                  {downloading ? "Downloading Bundle..." : "Download Filing Bundle (ZIP)"}
                </button>
                <span style={{ fontSize: "0.8rem", color: "#666" }}>
                  Contains: approved-draft.pdf, manifest.json, evidence-index.json, annexures, checklist.json, provenance.json
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
