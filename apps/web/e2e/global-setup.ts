/**
 * Playwright global setup — ensures the test Cognito user exists, logs in, and
 * saves auth state.
 *
 * Runs once before all tests. Saves storageState to e2e/.auth/state.json so
 * individual tests can skip the login flow.
 *
 * Required env vars:
 *   E2E_TEST_EMAIL        — Cognito test user email
 *   E2E_TEST_PASSWORD     — Cognito test user password
 *
 * Optional:
 *   COGNITO_USER_POOL_ID  — If set, ensures the Cognito user exists (creates if missing).
 *                           Required in CI; can be omitted locally if the user already exists.
 *   AWS_REGION            — AWS region for Cognito (default: us-east-1)
 *   E2E_BASE_URL          — Override base URL (default: http://localhost:3000)
 */
import {
  AdminCreateUserCommand,
  AdminGetUserCommand,
  AdminSetUserPasswordCommand,
  CognitoIdentityProviderClient,
  UserNotFoundException,
} from "@aws-sdk/client-cognito-identity-provider";
import { chromium, expect, type FullConfig } from "@playwright/test";
import { config as loadEnv } from "dotenv";
import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { AUTH_STATE_PATH } from "./fixtures/paths";

// globalSetup runs before Playwright's own dotenv loading — load manually.
loadEnv({ path: ".env" });
loadEnv({ path: ".env.local", override: true });

async function ensureCognitoUser(email: string, password: string): Promise<void> {
  const userPoolId = process.env.COGNITO_USER_POOL_ID;
  if (!userPoolId) {
    console.warn("[setup] COGNITO_USER_POOL_ID not set — skipping Cognito user creation");
    return;
  }

  const cognito = new CognitoIdentityProviderClient({
    region: process.env.AWS_REGION ?? "us-east-1",
  });

  try {
    await cognito.send(new AdminGetUserCommand({ UserPoolId: userPoolId, Username: email }));
    console.log("[setup] Cognito user already exists");
  } catch (err) {
    if (err instanceof UserNotFoundException) {
      await cognito.send(
        new AdminCreateUserCommand({
          UserPoolId: userPoolId,
          Username: email,
          TemporaryPassword: password,
          MessageAction: "SUPPRESS", // no welcome email
        })
      );
      await cognito.send(
        new AdminSetUserPasswordCommand({
          UserPoolId: userPoolId,
          Username: email,
          Password: password,
          Permanent: true, // skip force-change-password on first login
        })
      );
      console.log("[setup] Cognito user created");
    } else {
      throw err;
    }
  }
}

async function runMigrations(): Promise<void> {
  const apiDir = path.resolve(__dirname, "../../..", "apps/api");
  try {
    execSync("uv run alembic upgrade head", { cwd: apiDir, stdio: "inherit" });
  } catch (err) {
    console.error("[setup] alembic upgrade failed:", err);
    throw err;
  }
}

export default async function globalSetup(config: FullConfig) {
  await runMigrations();

  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:3000";
  const email = process.env.E2E_TEST_EMAIL;
  const password = process.env.E2E_TEST_PASSWORD;

  if (!email || !password) {
    throw new Error(
      "E2E_TEST_EMAIL and E2E_TEST_PASSWORD must be set to run e2e tests."
    );
  }

  // Step 1 — ensure Cognito user exists (idempotent)
  await ensureCognitoUser(email, password);

  // Step 2 — log in via the UI and save storageState
  fs.mkdirSync(path.dirname(AUTH_STATE_PATH), { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto(`${baseURL}/login`);

  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');

  // Handle optional TOTP step
  const result = await Promise.race([
    page.waitForURL(`${baseURL}/dashboard`, { timeout: 15_000 }).then(() => "dashboard"),
    page
      .waitForSelector("#totp", { timeout: 5_000 })
      .then(() => "totp")
      .catch(() => null),
  ]);

  if (result === "totp") {
    throw new Error(
      "Login requires TOTP. Use a Cognito test user without MFA enabled."
    );
  }

  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

  await context.storageState({ path: AUTH_STATE_PATH });
  await browser.close();
}
