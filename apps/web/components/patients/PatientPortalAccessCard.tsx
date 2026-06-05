"use client";

import { useState } from "react";
import Link from "next/link";
import { Copy, ExternalLink, Mail, Settings } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { usePortalStatus, useSendPortalInvite } from "@/lib/api/portal";

interface PatientPortalAccessCardProps {
  patientId: string;
  patientEmail: string | null;
}

function getPortalUrl(): string {
  const configured = process.env.NEXT_PUBLIC_PATIENT_PORTAL_URL;
  if (configured) return configured;
  return "http://localhost:3000/portal";
}

function statusLabel(status: string | undefined): string {
  switch (status) {
    case "active":
      return "Active";
    case "invited":
      return "Invited";
    case "revoked":
      return "Revoked";
    default:
      return "Not enrolled";
  }
}

export function PatientPortalAccessCard({ patientId, patientEmail }: PatientPortalAccessCardProps) {
  const portalUrl = getPortalUrl();
  const canInviteByEmail = Boolean(patientEmail);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const [inviteCopyStatus, setInviteCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const { data: portalStatus, isLoading } = usePortalStatus(patientId);
  const sendInvite = useSendPortalInvite();

  async function handleCopyPortalUrl() {
    await copyText(portalUrl, setCopyStatus);
  }

  async function handleCopyInviteUrl() {
    if (!inviteUrl) return;
    await copyText(inviteUrl, setInviteCopyStatus);
  }

  async function copyText(value: string, setStatus: (status: "idle" | "copied" | "failed") => void) {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const textArea = document.createElement("textarea");
        textArea.value = value;
        textArea.style.position = "fixed";
        textArea.style.opacity = "0";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        const copied = document.execCommand("copy");
        document.body.removeChild(textArea);
        if (!copied) throw new Error("copy failed");
      }
      setStatus("copied");
      window.setTimeout(() => setStatus("idle"), 1500);
    } catch {
      setStatus("failed");
      window.setTimeout(() => setStatus("idle"), 2000);
    }
  }

  async function handleSendInvite() {
    if (!patientEmail) return;
    setActionMessage(null);
    setInviteUrl(null);

    try {
      const result = await sendInvite.mutateAsync({ patientId });
      if (result.status === "active") {
        setActionMessage("Patient already has an active portal account.");
      } else if (result.inviteUrl) {
        setInviteUrl(result.inviteUrl);
        setActionMessage(
          "Invite created. Email only sends when SES is configured — copy the invite link below.",
        );
      } else {
        setActionMessage("Invite created.");
      }
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Failed to send portal invite.");
    }
  }

  function copyButtonLabel() {
    if (copyStatus === "copied") return "Copied";
    if (copyStatus === "failed") return "Copy failed";
    return "Copy Portal URL";
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-semibold">Portal Access</CardTitle>
        <Badge variant="outline">{statusLabel(portalStatus?.status)}</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Send a secure invite link to connect this patient chart to the patient portal.
        </p>

        <div className="rounded-md border p-3 text-xs">
          <p className="font-medium">Enrollment</p>
          {isLoading ? (
            <p className="mt-0.5 text-muted-foreground">Loading portal status...</p>
          ) : (
            <div className="mt-1 space-y-1 text-muted-foreground">
              <p>Status: {statusLabel(portalStatus?.status)}</p>
              {portalStatus?.email && <p>Invite email: {portalStatus.email}</p>}
              {portalStatus?.inviteExpiresAt && portalStatus.status === "invited" && (
                <p>Invite expires: {new Date(portalStatus.inviteExpiresAt).toLocaleString()}</p>
              )}
              {portalStatus?.enrolledAt && portalStatus.status === "active" && (
                <p>Enrolled: {new Date(portalStatus.enrolledAt).toLocaleString()}</p>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!canInviteByEmail || sendInvite.isPending || portalStatus?.status === "active"}
            onClick={() => void handleSendInvite()}
            title={
              !canInviteByEmail
                ? "Add an email address to enable invite sending."
                : portalStatus?.status === "active"
                  ? "Patient already has an active portal account."
                  : undefined
            }
          >
            <Mail className="h-4 w-4" />
            {sendInvite.isPending ? "Sending..." : "Send Portal Invite"}
          </Button>

          <Button size="sm" variant="outline" onClick={() => void handleCopyPortalUrl()}>
            <Copy className="h-4 w-4" />
            {copyButtonLabel()}
          </Button>

          <Button size="sm" variant="outline" asChild>
            <a href={portalUrl} target="_blank" rel="noreferrer">
              <ExternalLink className="h-4 w-4" />
              Open Portal
            </a>
          </Button>

          <Button size="sm" variant="ghost" asChild>
            <Link href="/settings?tab=patient-portal">
              <Settings className="h-4 w-4" />
              Portal Settings
            </Link>
          </Button>
        </div>

        {actionMessage && <p className="text-xs text-muted-foreground">{actionMessage}</p>}

        {inviteUrl && (
          <div className="space-y-2 rounded-md border border-dashed p-3">
            <p className="text-xs font-medium">Invite link (dev)</p>
            <p className="break-all font-mono text-xs text-muted-foreground">{inviteUrl}</p>
            <Button size="sm" variant="outline" onClick={() => void handleCopyInviteUrl()}>
              <Copy className="h-4 w-4" />
              {inviteCopyStatus === "copied"
                ? "Copied"
                : inviteCopyStatus === "failed"
                  ? "Copy failed"
                  : "Copy Invite Link"}
            </Button>
          </div>
        )}

        {!canInviteByEmail && (
          <p className="text-xs text-muted-foreground">
            Add a patient email in Contact to enable email-based invites.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
