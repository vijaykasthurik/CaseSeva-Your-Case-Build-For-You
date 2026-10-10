import { test, expect } from "@playwright/test";

const uniqueEmail = () => `client-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;

async function fillSignup(page, email = uniqueEmail(), overrides = {}, shouldReachDashboard = true) {
  const form = {
    full_name: "Anita Sharma",
    email,
    mobile_number: "9876543210",
    password: "Password123",
    preferred_language: "English",
    state: "Maharashtra",
    district_city: "Mumbai",
    ...overrides,
  };
  await page.goto("/signup");
  await page.getByLabel("Full name").fill(form.full_name);
  await page.getByLabel("Email").fill(form.email);
  await page.getByLabel("Mobile number").fill(form.mobile_number);
  await page.getByLabel("Password").fill(form.password);
  await page.getByLabel("Preferred language").fill(form.preferred_language);
  await page.getByLabel("State").fill(form.state);
  await page.getByLabel("District / city").fill(form.district_city);
  await page.getByRole("button", { name: "Create account" }).click();
  if (shouldReachDashboard) await page.waitForURL(/\/dashboard$/);
  return form;
}

test("new client signup lands on dashboard", async ({ page }) => {
  const form = await fillSignup(page);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByTestId("dashboard-heading")).toContainText(form.full_name);
});

test("duplicate email shows an error", async ({ page }) => {
  const form = await fillSignup(page);
  await page.getByRole("button", { name: "Logout" }).click();
  await fillSignup(page, form.email, {}, false);
  await expect(page.getByText("Email is already registered.")).toBeVisible();
  await expect(page).toHaveURL(/\/signup$/);
});

test("invalid signup input shows field errors", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Full name").fill("Invalid Client");
  await page.getByLabel("Email").fill("not-an-email");
  await page.getByLabel("Mobile number").fill("123");
  await page.getByLabel("Password").fill("short");
  await page.getByLabel("Preferred language").fill("English");
  await page.getByLabel("State").fill("Delhi");
  await page.getByLabel("District / city").fill("Delhi");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await expect(page.getByText("Enter a valid 10-digit Indian mobile number.")).toBeVisible();
  await expect(page.getByText("Password must be at least 8 characters.")).toBeVisible();
});

test("correct credentials reach dashboard", async ({ page, request }) => {
  const email = uniqueEmail();
  await request.post(`${process.env.TEST_API_BASE_URL || "http://127.0.0.1:8000"}/api/auth/signup`, {
    data: {
      full_name: "Login Client",
      email,
      mobile_number: "9876543210",
      password: "Password123",
      preferred_language: "English",
      state: "Karnataka",
      district_city: "Bengaluru",
    },
  });
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("Password123");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("wrong credentials stay on login", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(uniqueEmail());
  await page.getByLabel("Password").fill("WrongPassword");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("alert")).toContainText("Invalid email or password.");
});

test("logged-out protected route redirects to login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
});

test("session survives page reload", async ({ page }) => {
  await fillSignup(page);
  await page.reload();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByTestId("your-cases")).toBeVisible();
});

test("profile edits persist after reload", async ({ page }) => {
  await fillSignup(page);
  await page.getByRole("link", { name: "Profile" }).click();
  await page.getByLabel("full name").fill("Updated Client Name");
  const patchPromise = page.waitForResponse((resp) => resp.url().includes("/api/auth/me") && resp.request().method() === "PATCH" && resp.status() === 200);
  await page.getByRole("button", { name: "Save profile" }).click();
  await patchPromise;
  await expect(page.getByRole("status")).toContainText("Profile saved successfully.");
  await page.reload();
  await expect(page.getByLabel("full name")).toHaveValue("Updated Client Name");
});

test("logout clears session and protects dashboard", async ({ page }) => {
  await fillSignup(page);
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
});
