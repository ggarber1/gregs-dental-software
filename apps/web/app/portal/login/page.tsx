"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { signIn, signOut, signUp, confirmSignUp } from "aws-amplify/auth";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { configurePortalAmplify, isPortalAmplifyConfigured } from "@/lib/auth/portal-amplify";

type Step = "credentials" | "confirm";

export default function PortalLoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("credentials");
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmationCode, setConfirmationCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authConfigured] = useState(() => isPortalAmplifyConfigured());

  useEffect(() => {
    if (authConfigured) {
      configurePortalAmplify();
      void signOut({ global: false }).catch(() => {});
    }
  }, [authConfigured]);

  async function persistPortalSession() {
    const { fetchAuthSession } = await import("aws-amplify/auth");
    const session = await fetchAuthSession();
    const idToken = session.tokens?.idToken?.toString();
    if (!idToken) {
      setError("Could not retrieve session tokens. Please try again.");
      return false;
    }

    const res = await fetch("/portal/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accessToken: idToken }),
    });

    if (!res.ok) {
      setError("Failed to establish portal session. Please try again.");
      return false;
    }

    return true;
  }

  async function handleCredentialsSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (mode === "sign-up") {
        await signUp({
          username: email,
          password,
          options: { userAttributes: { email } },
        });
        setStep("confirm");
        return;
      }

      const result = await signIn({ username: email, password });
      if (result.isSignedIn) {
        const ok = await persistPortalSession();
        if (ok) router.push("/portal");
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await confirmSignUp({ username: email, confirmationCode });
      const result = await signIn({ username: email, password });
      if (result.isSignedIn) {
        const ok = await persistPortalSession();
        if (ok) router.push("/portal");
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (!authConfigured) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Portal sign-in unavailable</CardTitle>
          <CardDescription>
            Patient portal authentication is not configured yet. Ask your practice to finish setup
            for the dedicated patient Cognito pool.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="mx-auto max-w-md">
      <CardHeader className="text-center">
        <CardTitle className="text-xl">Patient Portal</CardTitle>
        <CardDescription>
          {step === "confirm"
            ? "Enter the verification code sent to your email"
            : mode === "sign-up"
              ? "Create your secure portal account"
              : "Sign in to view your records"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        {step === "confirm" ? (
          <form onSubmit={(e) => void handleConfirmSubmit(e)} className="flex flex-col gap-4">
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={confirmationCode}
              onChange={(e) => setConfirmationCode(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Verification code"
            />
            <Button type="submit" disabled={loading}>
              {loading ? "Verifying..." : "Verify and continue"}
            </Button>
          </form>
        ) : (
          <form onSubmit={(e) => void handleCredentialsSubmit(e)} className="flex flex-col gap-4">
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Email"
            />
            <input
              type="password"
              autoComplete={mode === "sign-up" ? "new-password" : "current-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Password"
            />
            <Button type="submit" disabled={loading}>
              {loading ? "Working..." : mode === "sign-up" ? "Create account" : "Sign in"}
            </Button>
            <button
              type="button"
              className="text-sm text-muted-foreground underline-offset-4 hover:underline"
              onClick={() => setMode(mode === "sign-up" ? "sign-in" : "sign-up")}
            >
              {mode === "sign-up"
                ? "Already have an account? Sign in"
                : "Need an account? Create one after accepting your invite"}
            </button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Something went wrong. Please try again.";
}
