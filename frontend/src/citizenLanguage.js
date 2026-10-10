const messages = {
  DRAFT: ["Draft: continue your case", "Your information is saved. Add your story when you are ready."],
  SUBMITTED: ["Reading your information", "We are preparing the story and files you provided."],
  READY_FOR_ADVOCATE: ["Ready to find an advocate", "Your information is organised. You can choose an advocate without running an analysis."],
  ENGINE1_RUNNING: ["Understanding your case", "We are reading your account and checking what can be established from your information."],
  ENGINE1_DONE: ["Your case explanation is ready", "Read what we understood, then choose a deeper check or find an advocate."],
  AWAITING_CLIENT_INFO: ["We need a few details", "Answer the questions below. Unknown, unavailable and later are valid responses."],
  ENGINE2_RUNNING: ["Checking your case from both sides", "We are checking what may support your position and what may be questioned."],
  ENGINE2_DONE: ["Your deeper case check is ready", "Review the explanation and the evidence that may help, then find an advocate."],
  REVIEW_REQUIRED: ["Professional review or more processing is needed", "Some information could not be established. You can retry or go to an advocate."],
  LEGAL_CORPUS_NOT_READY: ["Verified legal coverage is not ready", "We cannot reliably establish the applicable law for this matter yet. An advocate can review it."],
  NEEDS_DOCUMENT: ["More information may help", "Read the document request. Upload it if available, or tell your advocate that you do not have it."],
  AWAITING_ADVOCATE: ["Waiting for advocate handoff", "After the advocate accepts, review what you want to share and allow access."],
  ADVOCATE_REVIEW: ["Your advocate is reviewing the case", "Your advocate can check the information, ask questions and prepare the next step."],
  ADVOCATE_APPROVED: ["Ready for professional preparation", "Your advocate has reviewed the current case information."],
  GENERATING_DOCUMENTS: ["Your advocate is preparing legal documents", "Professional preparation is in progress. Your client overview will be available when ready."],
  DOCUMENTS_READY: ["Professional preparation completed", "Your advocate will review the documents before deciding whether to file."],
  DOCUMENTS_BLOCKED: ["Professional documents need further review", "Your advocate needs to resolve verification or consistency issues before proceeding."],
  READY_TO_FILE: ["Ready to file", "Your advocate has marked the reviewed documents ready for filing."],
  PREPARING_FOR_FILING: ["Your advocate is preparing the filing", "The papers are being prepared for submission. Ask your advocate about the expected next step."],
  FILED: ["Your advocate reported the case filed", "Your advocate has recorded a filing update. This is not an independently verified court status."],
  FILING_ACKNOWLEDGED: ["Filing acknowledgement reported", "Your advocate reports an acknowledgement of submission. Registry scrutiny may still be pending."],
  DEFECT_CORRECTION_REQUIRED: ["A filing correction is needed", "Your advocate reports that the registry requires a correction or additional document."],
  CORRECTED_REFILED: ["Corrected papers resubmitted", "Your advocate reports that the corrected papers have been submitted again."],
  REGISTERED: ["Case registration reported", "Your advocate reports that the matter has been registered."],
  PENDING: ["Your case is pending", "Your advocate reports that the matter is awaiting its next procedural step."],
  HEARING_SCHEDULED: ["A hearing has been reported", "Review the date and preparation instructions shared by your advocate."],
  ORDER_RECEIVED: ["An order has been received", "Your advocate will explain the order and the next available steps."],
  DELETED: ["Case content deleted", "Your active case content was deleted. Restricted audit records follow the configured retention policy."],
  CLOSED: ["Case closed", "Your advocate has recorded that this matter is closed."],
};
export function citizenStatus(status) {
  const [label, explanation] = messages[status] || ["Your case has an update", "Check the latest update from your advocate for the next step."];
  return { label, explanation, source: "CaseSeva Internal Status" };
}
export const stageLabel = stage => ({ READING_INPUT: "Reading your information", INTAKE_CLEANING: "Reading your information", EVIDENCE_INDEXING: "Reading your documents", FACT_EXTRACTION: "Understanding what happened", TIMELINE_CONSTRUCTION: "Building your timeline", PARTY_IDENTIFICATION: "Identifying people involved", MISSING_INFORMATION: "Checking for missing information", RECONCILIATION: "Analysing your answers", DOMAIN_ROUTER: "Researching applicable law", LEGAL_ISSUE_IDENTIFICATION: "Understanding the legal questions", STATUTE_RETRIEVAL: "Researching applicable law", CITATION_VERIFICATION: "Verifying legal sources", TEMPORAL_LAW_CHECK: "Checking which law applies to the dates", JURISDICTION_FORUM: "Checking where the matter may be heard", LIMITATION_CHECK: "Checking time-limit information", EVIDENCE_ISSUE_MAPPING: "Checking your evidence", CASE_FILE_ASSEMBLY: "Completing your case explanation", CLAIMANT_COUNSEL: "Checking what supports your position", OPPONENT_COUNSEL: "Considering what may be questioned", EVIDENCE_CHALLENGER: "Checking where more proof may help", REBUTTAL: "Considering possible responses", NEUTRAL_EVALUATION: "Summarising matters for professional review", OVERVIEW_BUILDER: "Preparing your overview" })[stage] || "Preparing your case information";
export const readiness = level => ({ "Well supported": "The issue has relevant supporting information and verified legal grounds.", "Partially supported": "Some parts are supported; other parts still need evidence or review.", Thin: "More relevant evidence is needed before this issue can be assessed reliably.", Unresolved: "Important information or verified legal grounds are still unknown." })[level] || "Professional review is needed.";
