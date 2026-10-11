import { test, expect } from "@playwright/test";
const backend = "http://127.0.0.1:8001";

test.use({ launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] }, permissions: ["microphone"] });

async function start(page, request) {
  const result = await request.post(`${backend}/api/auth/signup`, { data: { full_name: "Input Test", email: `input-${Date.now()}-${Math.random()}@example.com`, password: "Password123", mobile_number: "9876543210", preferred_language: "Tamil", state: "Tamil Nadu", district_city: "Chennai" } });
  const user = await result.json();
  await page.goto("/");
  await page.evaluate(token => localStorage.setItem("caseseva_session_token", token), user.session_token);
  await page.goto("/cases/new");
  return { Authorization: `Bearer ${user.session_token}` };
}

test("Tamil autosave, duplicate files and safe input-only retry", async ({ page, request }) => {
  const headers = await start(page, request);
  const story = "நான் 24,500 செலுத்தினேன். I have the receipt.";
  await page.getByLabel("Your story", { exact: true }).fill(story);
  await expect(page.getByText("Draft saved", { exact: true })).toBeVisible();
  const file = { name: "story.txt", mimeType: "text/plain", buffer: Buffer.from(story) };
  await page.locator('input[type="file"]').setInputFiles(file);
  await expect(page.getByText(/E001: story.txt/)).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles(file);
  await expect(page.getByText(/duplicate upload/)).toBeVisible();
  const id = new URL(page.url()).pathname.split("/")[2];
  const retry = await request.post(`${backend}/api/cases/${id}/input/retry`, { headers });
  expect(retry.ok()).toBeTruthy();
  await expect.poll(async () => (await (await request.get(`${backend}/api/cases/${id}`, { headers })).json()).case.input_status).not.toBe("RUNNING");
  await page.reload();
  await expect(page.getByLabel("Your story", { exact: true })).toHaveValue(story);
  await expect(page.getByRole("button", { name: "Build My Case", exact: true })).toBeVisible();
});

test("browser microphone creates a saved narration without claiming transcription", async ({ page, request }) => {
  const headers = await start(page, request);
  await page.getByRole("button", { name: "Record with microphone" }).click();
  await expect(page.getByRole("button", { name: "Stop recording and upload" })).toBeVisible();
  // Wait for a real MediaRecorder chunk from Chromium's synthetic audio device.
  await page.waitForTimeout(1100);
  await page.getByRole("button", { name: "Stop recording and upload" }).click();
  await expect(page.getByText(/E001: microphone-/)).toBeVisible();
  const id = new URL(page.url()).pathname.split("/")[2];
  const response = await request.get(`${backend}/api/cases/${id}`, { headers });
  const item = (await response.json()).case.evidence[0];
  expect(item.input_source).toBe("MICROPHONE");
  expect(item.extraction.status).toBe("PENDING");
  expect(JSON.stringify(item)).not.toMatch(/AWS|Tesseract|storage_key|bucket/);
});
