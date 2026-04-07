"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { signIn, confirmSignIn, signOut } from "aws-amplify/auth";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type Step = "credentials" | "totp";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("credentials");

  // Clear any stale Amplify session so signIn doesn't throw UserAlreadyAuthenticatedException
  useEffect(() => {
    void signOut({ global: false }).catch(() => {});
  }, []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleCredentials(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const result = await signIn({ username: email, password });

      if (result.nextStep.signInStep === "CONFIRM_SIGN_IN_WITH_TOTP_CODE") {
        setStep("totp");
        return;
      }

      if (result.isSignedIn) {
        await persistSession();
      }
    } catch (err) {
      console.error("[login] signIn error:", err);
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleTotp(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const result = await confirmSignIn({ challengeResponse: totp });

      if (result.isSignedIn) {
        await persistSession();
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  // After Amplify confirms sign-in, fetch the tokens and store them in
  // httpOnly/secure cookies via the session API route.
  async function persistSession() {
    const { fetchAuthSession } = await import("aws-amplify/auth");
    const session = await fetchAuthSession();
    const accessToken = session.tokens?.accessToken?.toString();
    // Amplify doesn't expose refresh tokens directly — the access token
    // cookie is sufficient for Phase 1. Refresh token handling added in Phase 2.
    if (!accessToken) {
      setError("Could not retrieve session tokens. Please try again.");
      return;
    }

    const res = await fetch("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accessToken, refreshToken: "" }),
    });

    if (!res.ok) {
      setError("Failed to establish session. Please try again.");
      return;
    }

    router.push("/dashboard");
  }

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-xl">Dental PMS</CardTitle>
        <CardDescription>
          {step === "credentials" ? "Sign in to your practice account" : "Enter your authenticator code"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        {step === "credentials" ? (
          <form onSubmit={(e) => void handleCredentials(e)} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        ) : (
          <form onSubmit={(e) => void handleTotp(e)} className="flex flex-col gap-4">
            <p className="text-sm text-muted-foreground">
              Open your authenticator app and enter the 6-digit code for this account.
            </p>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="totp" className="text-sm font-medium">
                Authenticator code
              </label>
              <input
                id="totp"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                required
                value={totp}
                onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))}
                className="rounded-md border border-input bg-background px-3 py-2 text-sm tracking-widest focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? "Verifying…" : "Verify"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => { setStep("credentials"); setError(null); }}
            >
              Back
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function getErrorMessage(err: unknown): string {
  if (err && typeof err === "object" && "name" in err) {
    switch ((err as { name: string }).name) {
      case "NotAuthorizedException":
        return "Incorrect email or password.";
      case "UserNotFoundException":
        return "No account found with that email.";
      case "CodeMismatchException":
        return "Invalid authenticator code. Please try again.";
      case "TooManyRequestsException":
        return "Too many attempts. Please wait a moment and try again.";
      case "UserNotConfirmedException":
        return "Account not confirmed. Contact your administrator.";
    }
  }
  return "Something went wrong. Please try again.";
}
