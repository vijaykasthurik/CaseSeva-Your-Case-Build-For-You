export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
export const SESSION_KEY = "caseseva_session_token";

export function getToken() {
  return window.localStorage.getItem(SESSION_KEY);
}

export function setToken(token) {
  window.localStorage.setItem(SESSION_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(SESSION_KEY);
}

async function request(path, options = {}, { redirectOn401 = true } = {}) {
  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", "Bearer " + token);
  const match = path.match(/\/(?:advocate\/)?cases\/([^/?]+)/);
  const access = match && window.sessionStorage.getItem(`case_access_${match[1]}`);
  if (access) headers.set("X-Case-Access", access);
  
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch (err) {
    let detail = `Failed to connect to ${API_BASE_URL}`;
    try {
      // Diagnostic check: test with mode 'no-cors' to distinguish dead server from CORS block
      await fetch(`${API_BASE_URL}/api/health`, { mode: "no-cors" });
      detail = `Connection to ${API_BASE_URL} blocked by CORS policy. Ensure ${window.location.origin} is added to API Gateway AllowedOrigin.`;
    } catch {
      detail = `Backend server not running at ${API_BASE_URL}. Ensure local server is running or check API base URL.`;
    }
    const error = new Error(detail);
    error.isNetworkError = true;
    error.baseUrl = API_BASE_URL;
    throw error;
  }

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : null;
  if (response.status === 401 && redirectOn401) {
    clearToken();
    if (window.location.pathname !== "/login") window.location.assign("/login");
  }
  if (!response.ok) {
    const error = new Error(body?.detail?.message || body?.detail || `Request failed with status ${response.status}`);
    error.status = response.status;
    error.fields = body?.detail?.fields || {};
    throw error;
  }
  return body;
}

export const getHealth = () => request("/api/health", {}, { redirectOn401: false });
export const getNotifications = () => request("/api/notifications");
export const addCaseNote = (id, payload) => request(`/api/advocate/cases/${id}/notes`, { method: "POST", body: JSON.stringify(payload) });
export const requestCaseInformation = (id, payload) => request(`/api/advocate/cases/${id}/information-requests`, { method: "POST", body: JSON.stringify(payload) });
export const answerCaseInformation = (id, requestId, payload) => request(`/api/cases/${id}/information-requests/${requestId}/answer`, { method: "POST", body: JSON.stringify(payload) });
export const saveFilingUpdate = (id, payload) => request(`/api/advocate/cases/${id}/filing`, { method: "POST", body: JSON.stringify(payload) });
export const requestCaseDeletion = id => request(`/api/cases/${id}/deletion-request`, { method: "POST" });
export const startGuestClaim = case_id => request("/api/guest-claims", { method: "POST", body: JSON.stringify({ case_id }) });
export const confirmGuestClaim = (claim_id, code) => request("/api/guest-claims/confirm", { method: "POST", body: JSON.stringify({ claim_id, code }) });

export const signup = (payload) =>
  request("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload),
  }, { redirectOn401: false });

export const login = (payload) =>
  request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  }, { redirectOn401: false });

export const logout = () => request("/api/auth/logout", { method: "POST" });

export const getMe = () => request("/api/auth/me", {}, { redirectOn401: false });

export const updateProfile = (payload) =>
  request("/api/auth/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const createCase = (payload) => request("/api/cases", { method: "POST", ...(payload ? { body: JSON.stringify(payload) } : {}) });
export const listCases = () => request("/api/cases");
export const getCase = (caseId) => request(`/api/cases/${caseId}`);
export const updateCase = (caseId, payload) =>
  request(`/api/cases/${caseId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const submitCase = (caseId, path = "understand") =>
  request(`/api/cases/${caseId}/submit`, { method: "POST", body: JSON.stringify({ path }) });
export const deleteCase = (caseId) =>
  request(`/api/cases/${caseId}`, { method: "DELETE" });
export const uploadEvidence = (caseId, file, description = "", inputSource = "AUTO") => {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("description", description);
  form.append("input_source", inputSource);
  return request(`/api/cases/${caseId}/evidence`, { method: "POST", body: form });
};
export const deleteEvidence = (caseId, evidenceId) =>
  request(`/api/cases/${caseId}/evidence/${evidenceId}`, { method: "DELETE" });
export const updateEvidence = (caseId, evidenceId, description) =>
  request(`/api/cases/${caseId}/evidence/${evidenceId}`, {
    method: "PATCH",
    body: JSON.stringify({ description }),
  });
export const startAnalysis = (caseId) => request(`/api/cases/${caseId}/analyze`, { method: "POST" });
export const retryAnalysis = (caseId) => request(`/api/cases/${caseId}/analyze/retry`, { method: "POST" });
export const getCaseStatus = (caseId) => request(`/api/cases/${caseId}/status`);
export const answerClarifications = (caseId, answers) => request(`/api/cases/${caseId}/clarifications`, { method: "POST", body: JSON.stringify({ answers }) });
export const chooseEngine2 = (caseId, run) => request(`/api/cases/${caseId}/engine2`, { method: "POST", body: JSON.stringify({ run }) });
export const reprocessInput = caseId => request(`/api/cases/${caseId}/reprocess-input`, { method: "POST" });
export const migrateCaseWorkflow = caseId => request(`/api/cases/${caseId}/migrate-workflow`, { method: "POST" });
export const getPreview1 = (caseId) => request(`/api/cases/${caseId}/preview1`);
export const editFact = (caseId, factId, payload) => request(`/api/cases/${caseId}/facts/${factId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const addFact = (caseId, payload) => request(`/api/cases/${caseId}/facts`, { method: "POST", body: JSON.stringify(payload) });
export const editTimeline = (caseId, eventId, payload) => request(`/api/cases/${caseId}/timeline/${eventId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const editParties = (caseId, payload) => request(`/api/cases/${caseId}/parties`, { method: "PATCH", body: JSON.stringify(payload) });
export const approvePreview1 = (caseId) => request(`/api/cases/${caseId}/preview1/approve`, { method: "POST" });
export const rerunPreview1 = (caseId) => request(`/api/cases/${caseId}/preview1/rerun`, { method: "POST" });
export const startLegalAnalysis = (caseId) => request(`/api/cases/${caseId}/legal-analysis`, { method: "POST" });
export const getPreview2 = (caseId) => request(`/api/cases/${caseId}/preview2`);
export const approvePreview2 = (caseId, proceedWithoutDocuments = false) =>
  request(`/api/cases/${caseId}/preview2/approve`, { method: "POST", body: JSON.stringify({ proceed_without_documents: proceedWithoutDocuments }) });
export const resolveDocumentRequest = (caseId, requestId, file) => {
  const form = new FormData();
  form.append("file", file, file.name);
  return request(`/api/cases/${caseId}/evidence-request/${requestId}/resolve`, { method: "POST", body: form });
};
export const correctPreview2Fact = (caseId, factId, text) =>
  request(`/api/cases/${caseId}/preview2/facts/${factId}`, { method: "PATCH", body: JSON.stringify({ text }) });
export const listAdvocates = (filters = {}) => request(`/api/advocates?${new URLSearchParams(filters)}`);
export const requestAdvocate = (caseId, advocateId) => request(`/api/cases/${caseId}/request-advocate`, { method: "POST", body: JSON.stringify({ advocate_id: advocateId }) });
export const cancelAdvocateRequest = (caseId) => request(`/api/cases/${caseId}/cancel-advocate-request`, { method: "POST" });
export const verifyAdvocate = (advocateId, status, reason = "", proof = {}) => request(`/api/admin/advocates/${advocateId}/verification`, { method: "POST", headers: { "X-Admin-Token": window.sessionStorage.getItem("admin_token") || "" }, body: JSON.stringify({ status, reason, ...proof }) });
export const listAdminAdvocates = () => request("/api/admin/advocates", { headers: { "X-Admin-Token": window.sessionStorage.getItem("admin_token") || "" } });
export const getAdvocateRequests = () => request("/api/advocate/requests");
export const getAdvocateCases = () => request("/api/advocate/cases");
export const acceptAdvocateRequest = (caseId) => request(`/api/advocate/requests/${caseId}/accept`, { method: "POST" });
export const declineAdvocateRequest = (caseId, reason = "") => request(`/api/advocate/requests/${caseId}/decline?reason=${encodeURIComponent(reason)}`, { method: "POST" });
export const getAdvocateCase = async (caseId) => {
  const result = await request(`/api/advocate/cases/${caseId}/access-token`, { method: "POST" });
  window.sessionStorage.setItem(`case_access_${caseId}`, result.access_token);
  return request(`/api/advocate/cases/${caseId}`);
};
export const grantCaseAccess = (caseId, payload) => request(`/api/cases/${caseId}/sharing`, { method: "POST", body: JSON.stringify(payload) });
export const getCaseGrants = (caseId) => request(`/api/cases/${caseId}/sharing`);
export const revokeCaseAccess = (caseId, grantId) => request(`/api/cases/${caseId}/sharing/${grantId}`, { method: "DELETE" });
export const uploadVerificationDocument = (file) => { const body = new FormData(); body.append("file", file); return request("/api/auth/advocate-verification-documents", { method: "POST", body }); };
export const reviewCaseItem = (caseId, payload) => request(`/api/advocate/cases/${caseId}/review`, { method: "POST", body: JSON.stringify(payload) });
export const rerunEngine = (caseId, engine, startStage = null) => request(`/api/advocate/cases/${caseId}/rerun`, { method: "POST", body: JSON.stringify({ engine, start_stage: startStage }) });
export const approveReviewedCase = caseId => request(`/api/advocate/cases/${caseId}/approve`, { method: "POST" });
export const downloadSharedEvidence = async (caseId, evidence) => {
  const response = await fetch(`${API_BASE_URL}/api/advocate/cases/${caseId}/evidence/${evidence.evidence_id}`, { headers: { Authorization: `Bearer ${getToken()}`, "X-Case-Access": window.sessionStorage.getItem(`case_access_${caseId}`) || "" } });
  if (!response.ok) throw new Error("Shared evidence download was denied or failed.");
  const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = evidence.filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};
export const approveAdvocateFact = (caseId, factId) => request(`/api/advocate/cases/${caseId}/facts/${factId}/approve`, { method: "POST" });
export const removeAdvocateProvision = (caseId, provisionId) => request(`/api/advocate/cases/${caseId}/provisions/${provisionId}/remove`, { method: "POST" });
export const approveAdvocateProvision = (caseId, provisionId) => request(`/api/advocate/cases/${caseId}/provisions/${provisionId}/approve`, { method: "POST" });
export const editAdvocateFact = (caseId, factId, payload) => request(`/api/advocate/cases/${caseId}/facts/${factId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const editAdvocateProvision = (caseId, provisionId, payload) => request(`/api/advocate/cases/${caseId}/provisions/${provisionId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const editAdvocateForum = (caseId, payload) => request(`/api/advocate/cases/${caseId}/forum`, { method: "PATCH", body: JSON.stringify(payload) });
export const approveAdvocateForum = (caseId) => request(`/api/advocate/cases/${caseId}/forum/approve`, { method: "POST" });
export const editAdvocateLimitation = (caseId, payload) => request(`/api/advocate/cases/${caseId}/limitation`, { method: "PATCH", body: JSON.stringify(payload) });
export const approveAdvocateLimitation = (caseId) => request(`/api/advocate/cases/${caseId}/limitation/approve`, { method: "POST" });
export const editAdvocateArgument = (caseId, objectionId, payload) => request(`/api/advocate/cases/${caseId}/arguments/${objectionId}`, { method: "PATCH", body: JSON.stringify(payload) });
export const approveAdvocateArgument = (caseId, objectionId) => request(`/api/advocate/cases/${caseId}/arguments/${objectionId}/approve`, { method: "POST" });
export const approveAdvocateEvidence = (caseId, evidenceId) => request(`/api/advocate/cases/${caseId}/evidence/${evidenceId}/approve`, { method: "POST" });
export const removeAdvocateEvidence = (caseId, evidenceId) => request(`/api/advocate/cases/${caseId}/evidence/${evidenceId}/remove`, { method: "POST" });
export const createAdvocateDocumentRequest = (caseId, payload) => request(`/api/advocate/cases/${caseId}/document-requests`, { method: "POST", body: JSON.stringify(payload) });
export const saveAdvocateNote = (caseId, note) => request(`/api/advocate/cases/${caseId}/review-note`, { method: "POST", body: JSON.stringify({ note }) });
export const finalizeAdvocateCase = (caseId) => request(`/api/cases/${caseId}/advocate/finalize`, { method: "POST" });
export const generateDocuments = (caseId) => request(`/api/cases/${caseId}/documents/generate`, { method: "POST" });
export const regenerateDocuments = (caseId) => request(`/api/cases/${caseId}/documents/regenerate`, { method: "POST" });
export const listDocuments = (caseId) => request(`/api/cases/${caseId}/documents`);
export const getDocument = (caseId, documentId) => request(`/api/cases/${caseId}/documents/${documentId}`);
export const getDocumentConsistency = (caseId, documentId) => request(`/api/cases/${caseId}/documents/${documentId}/consistency`);
export const overrideDocumentConsistency = (caseId, documentId, reason) => request(`/api/cases/${caseId}/documents/${documentId}/override-consistency`, { method: "POST", body: JSON.stringify({ reason }) });
export const documentDownloadUrl = (caseId, documentId) => `${API_BASE_URL}/api/cases/${caseId}/documents/${documentId}/download`;
export const downloadCaseDocument = async (caseId, document, format) => {
  const response = await fetch(`${documentDownloadUrl(caseId, document.id)}?format=${format}`, { headers: { Authorization: `Bearer ${getToken()}`, "X-Case-Access": window.sessionStorage.getItem(`case_access_${caseId}`) || "" } });
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || "Document download failed."); }
  const url = URL.createObjectURL(await response.blob()); const a = window.document.createElement("a"); a.href = url; a.download = `${document.type}-v${document.version}.${format}`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export const retryInput = caseId => request(`/api/cases/${caseId}/input/retry`, { method: "POST" });
