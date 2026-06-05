"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { signIn, signOut, signUp, confirmSignUp } from "aws-amplify/auth";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { completePortalInvite, usePortalInvite } from "@/lib/api/portal";
import { configurePortalAmplify, isPortalAmplifyConfigured } from "@/lib/auth/portal-amplify";

type Step = "loading" | "invite" | "confirm" | "complete";

export default function PortalAcceptPage() {
  const router = useRouter();
  const params = useParams<{ token: string }>();
  const token = params.token;
  const { data: invite, error: inviteError, isLoading } = usePortalInvite(token);
  const [step, setStep] = useState<Step>("loading");
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

  useEffect(() => {
    if (isLoading) {
      setStep("loading");
      return;
    }
    if (inviteError || !invite) {
      setStep("invite");
      return;
    }
    setStep("invite");
  }, [invite, inviteError, isLoading]);

  async function persistPortalSession() {
    const { fetchAuthSession } = await import("aws-amplify/auth");
    const session = await fetchAuthSession();
    const idToken = session.tokens?.idToken?.toString();
    if (!idToken) {
      throw new Error("Could not retrieve session tokens.");
    }

    const res = await fetch("/portal/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accessToken: idToken }),
    });

    if (!res.ok) {
      throw new Error("Failed to establish portal session.");
    }
  }

  async function handleCreateAccount(e: React.FormEvent) {
    e.preventDefault();
    if (!invite) return;

    setError(null);
    setLoading(true);

    try {
      await signUp({
        username: invite.email,
        password,
        options: { userAttributes: { email: invite.email } },
      });
      setStep("confirm");
    } catch (err) {
      if (err instanceof Error && err.name === "UsernameExistsException") {
        const result = await signIn({ username: invite.email, password });
        if (result.isSignedIn) {
          await persistPortalSession();
          await completePortalInvite(token);
          router.push("/portal");
          return;
        }
      }
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault();
    if (!invite) return;

    setError(null);
    setLoading(true);

    try {
      await confirmSignUp({ username: invite.email, confirmationCode });
      const result = await signIn({ username: invite.email, password });
      if (result.isSignedIn) {
        await persistPortalSession();
        await completePortalInvite(token);
        router.push("/portal");
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (step === "loading") {
    return <p className="text-sm text-muted-foreground">Checking your invite...</p>;
  }

  if (inviteError || !invite) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Invite unavailable</CardTitle>
          <CardDescription>
            This portal invite is invalid, expired, or has already been used.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (!authConfigured) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Portal setup incomplete</CardTitle>
          <CardDescription>
            Your invite is valid, but patient authentication has not been configured yet.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>Welcome, {invite.patientFirstName}</CardTitle>
        <CardDescription>
          {invite.practiceName} invited you to create a secure patient portal account for{" "}
          {invite.email}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        {step === "confirm" ? (
          <form onSubmit={(e) => void handleConfirm(e)} className="flex flex-col gap-4">
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
              {loading ? "Verifying..." : "Verify and open portal"}
            </Button>
          </form>
        ) : (
          <form onSubmit={(e) => void handleCreateAccount(e)} className="flex flex-col gap-4">
            <input
              type="email"
              value={invite.email}
              readOnly
              className="rounded-md border bg-muted px-3 py-2 text-sm text-muted-foreground"
            />
            <input
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm"
              placeholder="Create a password"
            />
            <Button type="submit" disabled={loading}>
              {loading ? "Creating account..." : "Create portal account"}
            </Button>
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
