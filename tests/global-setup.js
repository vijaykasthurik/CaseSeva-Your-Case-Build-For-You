import fs from "node:fs";
import path from "node:path";

export default async function globalSetup() {
  const databasePath = path.resolve(".localdev/playwright-database.json");
  if (fs.existsSync(databasePath)) fs.rmSync(databasePath, { force: true });
  const uploadsPath = path.resolve(".localdev/playwright-uploads");
  if (fs.existsSync(uploadsPath)) fs.rmSync(uploadsPath, { recursive: true, force: true });
}
