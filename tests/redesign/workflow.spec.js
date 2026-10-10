import { test, expect } from "@playwright/test";
const backend = "http://127.0.0.1:8001";

async function signup(page, request) {
  const response = await request.post(`${backend}/api/auth/signup`, { data: { full_name: "Workflow Client", email: `redesign-${Date.now()}-${Math.random()}@example.com`, password: "Password123", mobile_number: "9876543210", preferred_language: "English", state: "Tamil Nadu", district_city: "Chennai" } });
  const account = await response.json();
  await page.goto("/");
  await page.evaluate(token => localStorage.setItem("caseseva_session_token", token), account.session_token);
  return { Authorization: `Bearer ${account.session_token}` };
}

test("single-screen story-only submission, real progress, optional arguments and client consent", async ({ page, request }) => {
  const headers = await signup(page, request);
  await page.goto("/cases/new");
  await page.getByLabel("Your story", { exact: true }).fill("I paid for a service and need help explaining my dispute.");
  await expect(page.getByLabel("Case stage")).toBeVisible();
  await expect(page.getByRole("button", { name: "Record with microphone" })).toBeVisible();
  await page.getByRole("button", { name: "Submit case", exact: true }).click();
  await expect(page).toHaveURL(/\/cases\/[a-f0-9]{32}$/);
  const id = new URL(page.url()).pathname.split("/").pop();
  await expect(page.getByTestId("case-status")).toContainText("REVIEW_REQUIRED", { timeout: 30000 });
  await expect(page.getByText("Development only — live AI analysis has not been performed.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Applicable Law", exact: true })).toBeVisible();
  await expect(page.getByText("No applicable law has been verified yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve preview/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Skip argument analysis" }).click();
  await expect(page.getByText("Adversarial case-strengthening analysis was not run on the current Case File.")).toBeVisible();
  await page.getByRole("link", { name: "Find an advocate", exact: true }).click();
  await expect(page.getByText("Verified by CaseSeva admin review").first()).toBeVisible();
  // Exercise the request/accept APIs; consent remains an explicit client action in the UI.
  expect((await request.post(`${backend}/api/cases/${id}/request-advocate`, { headers, data: { advocate_id: "seed-verified-advocate" } })).ok()).toBeTruthy();
  const advocate = await (await request.post(`${backend}/api/auth/login`, { data: { email: "demo.advocate@caseseva.local", password: "DemoPassword123" } })).json();
  const advocateHeaders = { Authorization: `Bearer ${advocate.session_token}` };
  expect((await request.post(`${backend}/api/advocate/requests/${id}/accept`, { headers: advocateHeaders })).ok()).toBeTruthy();
  expect((await request.post(`${backend}/api/advocate/cases/${id}/access-token`, { headers: advocateHeaders })).status()).toBe(403);
  await page.goto(`/cases/${id}`);
  await page.getByRole("button", { name: "Grant selected access for 7 days" }).click();
  await expect(page.getByRole("button", { name: "Revoke access" })).toBeVisible();
  const access = await (await request.post(`${backend}/api/advocate/cases/${id}/access-token`, { headers: advocateHeaders })).json();
  expect((await request.get(`${backend}/api/advocate/cases/${id}`, { headers: { ...advocateHeaders, "X-Case-Access": access.access_token } })).ok()).toBeTruthy();
  expect((await request.post(`${backend}/api/cases/${id}/documents/generate`, { headers })).status()).toBe(403);
  await page.getByRole("button", { name: "Revoke access" }).click();
  await expect(page.getByRole("button", { name: "Grant selected access for 7 days" })).toBeVisible();
  expect((await request.get(`${backend}/api/advocate/cases/${id}`, { headers: { ...advocateHeaders, "X-Case-Access": access.access_token } })).status()).toBe(403);
});

test("Engine 2 remains separate and clients cannot read professional outputs", async ({ page, request }) => {
  const headers = await signup(page, request);
  const created = await (await request.post(`${backend}/api/cases`, { headers })).json();
  const id = created.case.case_id;
  await request.patch(`${backend}/api/cases/${id}`, { headers, data: { stage: "COMPLAINT_FIR", client_story: "There is a dispute. Dates and parties still need checking." } });
  await request.post(`${backend}/api/cases/${id}/submit`, { headers });
  await expect.poll(async () => (await (await request.get(`${backend}/api/cases/${id}/status`, { headers })).json()).status).toBe("REVIEW_REQUIRED");
  await page.goto(`/cases/${id}`);
  await page.getByRole("button", { name: "Yes, run Engine 2" }).click();
  await expect(page.getByTestId("case-status")).toContainText("ENGINE2_DONE", { timeout: 30000 });
  const result = await (await request.get(`${backend}/api/cases/${id}`, { headers })).json();
  expect(result.case.engine2).toBeUndefined();
  expect(result.case.arguments).toBeUndefined();
  expect(Object.keys(result.case.stage_statuses)).not.toContain("STATUTE_RETRIEVAL");
  await expect(page.getByRole("heading", { name: "Issue readiness", exact: true })).toBeVisible();
  expect((await request.get(`${backend}/api/cases/${id}/preview2`, { headers })).status()).toBe(410);
  expect((await request.get(`${backend}/api/cases/${id}/documents`, { headers })).ok()).toBeTruthy();
});
