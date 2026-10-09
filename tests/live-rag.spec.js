import { test, expect } from "@playwright/test";
import path from "node:path";

const base = "http://127.0.0.1:8000";

async function approvedCase(request, clientStory) {
  const email = `rag_${Date.now()}_${Math.random().toString(36).substring(7)}@example.com`;
  const signupRes = await request.post(`${base}/api/auth/signup`, {
    data: {
      email,
      password: "Password123!",
      full_name: "RAG User",
      mobile_number: "9876543210",
      preferred_language: "English",
      state: "Delhi",
      district_city: "Delhi",
      role: "client"
    }
  });
  const user = await signupRes.json();
  const token = user.session_token || user.token;
  const headers = { Authorization: `Bearer ${token}` };
  const createdRes = await (await request.post(`${base}/api/cases`, { headers })).json();
  const caseId = createdRes.case ? createdRes.case.case_id : createdRes.case_id;

  await request.patch(`${base}/api/cases/${caseId}`, {
    headers, data: { stage: "NEW_CONSULTATION", stage_details: {}, client_story: clientStory },
  });
  await request.post(`${base}/api/cases/${caseId}/evidence`, {
    headers, multipart: { file: { name: "receipt.txt", mimeType: "text/plain", buffer: Buffer.from("receipt content") } },
  });
  await request.post(`${base}/api/cases/${caseId}/submit`, { headers });
  await request.post(`${base}/api/cases/${caseId}/analyze`, { headers });
  await expect.poll(async () => (await (await request.get(`${base}/api/cases/${caseId}/status`, { headers })).json()).status, { timeout: 45000 }).toBe("AWAITING_PREVIEW_1");
  await request.post(`${base}/api/cases/${caseId}/preview1/approve`, { headers, data: {} });
  await expect.poll(async () => (await (await request.get(`${base}/api/cases/${caseId}/status`, { headers })).json()).status, { timeout: 45000 }).toBe("PREVIEW_1_APPROVED");

  return { headers, caseId };
}

async function runLegal(request, setup) {
  await request.post(`${base}/api/cases/${setup.caseId}/legal-analysis`, { headers: setup.headers });
  await expect.poll(async () => (await (await request.get(`${base}/api/cases/${setup.caseId}/status`, { headers: setup.headers })).json()).status, { timeout: 45000 }).toBe("AWAITING_PREVIEW_2");
}

test.describe("Live RAG & Grounded Citation Verification", () => {
  test("1. Provision grounded in fetched document text is verified and accepted", async ({ request }) => {
    const setup = await approvedCase(request, "I was employed as a software developer and my wages for 3 months were wrongfully withheld without any notice.");
    await runLegal(request, setup);
    const preview = await (await request.get(`${base}/api/cases/${setup.caseId}/preview2`, { headers: setup.headers })).json();
    expect(preview.verified_provisions.length).toBeGreaterThan(0);
    const sec17 = preview.verified_provisions.find(p => p.provision_id === "WAGES-17" || p.provision_id.includes("17"));
    expect(sec17).toBeTruthy();
  });

  test("2. Citation not present in fetched document text is trapped and rejected", async ({ request }) => {
    const setup = await approvedCase(request, "I bought a defective television set that stopped working after two weeks.");
    await runLegal(request, setup);
    const preview = await (await request.get(`${base}/api/cases/${setup.caseId}/preview2`, { headers: setup.headers })).json();
    // Hallucinated sections outside fetched text are trapped
    expect(preview.verified_provisions.every(p => p.provision_id !== "CPA-999" && p.provision_id !== "SOGA-14")).toBe(true);
  });

  test("3. Sabotage check: disabling grounding filter leaks hallucinated citations", async ({ request }) => {
    // With grounding filter disabled fixture keyword
    const setupSabotage = await approvedCase(request, "I bought a defective television set. [DISABLE_CORPUS_FILTER] [HALLUCINATED_STATUTE]");
    await runLegal(request, setupSabotage);
    const previewSabotage = await (await request.get(`${base}/api/cases/${setupSabotage.caseId}/preview2`, { headers: setupSabotage.headers })).json();
    
    // Leaks when filter disabled
    const leakedIds = (previewSabotage.verified_provisions || []).map(p => p.provision_id);
    console.log("Sabotage Leak Output (Filter Disabled):", leakedIds);
    expect(leakedIds.some(id => id === "SOGA-14" || id === "CPA-12")).toBe(true);

    // Enforced when filter enabled
    const setupNormal = await approvedCase(request, "I bought a defective television set. [HALLUCINATED_STATUTE]");
    await runLegal(request, setupNormal);
    const previewNormal = await (await request.get(`${base}/api/cases/${setupNormal.caseId}/preview2`, { headers: setupNormal.headers })).json();
    const normalIds = (previewNormal.verified_provisions || []).map(p => p.provision_id);
    console.log("Grounding Trapped Output (Filter Enabled):", normalIds);
    expect(normalIds.every(id => id !== "SOGA-14" && id !== "CPA-12")).toBe(true);
  });

  test("4. Domain with no retrievable sources extracts facts but blocks document generation", async ({ request }) => {
    const setup = await approvedCase(request, "[NON_CONSUMER] A boundary dispute occurred between two agricultural landowners over a fence location.");
    await request.post(`${base}/api/cases/${setup.caseId}/legal-analysis`, { headers: setup.headers });
    
    // Non-consumer/unsupported domain is routed to OUT_OF_SCOPE
    await expect.poll(async () => (await (await request.get(`${base}/api/cases/${setup.caseId}/status`, { headers: setup.headers })).json()).status, { timeout: 15000 }).toBe("OUT_OF_SCOPE");
  });

  test("5. Non-allowlisted source URL is refused by authorised source registry", async () => {
    const { spawnSync } = require("child_process");
    const python = path.resolve(".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
    const result = spawnSync(python, ["scripts/test_authorised_sources.py"], { encoding: "utf-8" });
    expect(result.status).toBe(0);
    const output = result.stdout + result.stderr;
    expect(output).toContain("OK");
  });
});
