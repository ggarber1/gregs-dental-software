"use client";

import { useState } from "react";
import Link from "next/link";
import { Copy, ExternalLink, Mail, Settings } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface PatientPortalAccessCardProps {
  patientId: string;
  patientEmail: string | null;
}

function getPortalUrl(): string {
  const configured = process.env.NEXT_PUBLIC_PATIENT_PORTAL_URL;
  if (configured) return configured;
  return "http://localhost:3000/portal";
}

export function PatientPortalAccessCard({ patientId, patientEmail }: PatientPortalAccessCardProps) {
  const portalUrl = getPortalUrl();
  const canInviteByEmail = Boolean(patientEmail);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");

  async function handleCopyPortalUrl() {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(portalUrl);
      } else {
        // Fallback for browsers/contexts without Clipboard API support.
        const textArea = document.createElement("textarea");
        textArea.value = portalUrl;
        textArea.style.position = "fixed";
        textArea.style.opacity = "0";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        const copied = document.execCommand("copy");
        document.body.removeChild(textArea);
        if (!copied) throw new Error("copy failed");
      }
      setCopyStatus("copied");
      window.setTimeout(() => setCopyStatus("idle"), 1500);
    } catch {
      setCopyStatus("failed");
      window.setTimeout(() => setCopyStatus("idle"), 2000);
    }
  }

  function handleSendInvite() {
    if (!patientEmail) return;
    const subject = encodeURIComponent("Your patient portal access");
    const body = encodeURIComponent(
      `Hi,\n\nUse this secure portal link to access your account:\n${portalUrl}\n\nThanks.`,
    );
    window.location.href = `mailto:${patientEmail}?subject=${subject}&body=${body}`;
  }

  function copyButtonLabel() {
    if (copyStatus === "copied") return "Copied";
    if (copyStatus === "failed") return "Copy failed";
    return "Copy Portal URL";
  }

  function copyStatusMessage() {
    if (copyStatus === "copied") return "Portal URL copied to clipboard.";
    if (copyStatus === "failed") return "Browser blocked clipboard access. Copy from Portal Settings.";
    return null;
  }

  const statusMessage = copyStatusMessage();

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-semibold">Portal Access</CardTitle>
        <Badge variant="outline">Preview</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Manage portal enrollment from the patient chart. Invite sending is in preview mode.
        </p>

        <div className="rounded-md border p-3 text-xs">
          <p className="font-medium">Patient ID</p>
          <p className="mt-0.5 font-mono text-muted-foreground">{patientId}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!canInviteByEmail}
            onClick={handleSendInvite}
            title={!canInviteByEmail ? "Add an email address to enable invite sending." : undefined}
          >
            <Mail className="h-4 w-4" />
            Send Portal Invite
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

        {statusMessage && <p className="text-xs text-muted-foreground">{statusMessage}</p>}

        {!canInviteByEmail && (
          <p className="text-xs text-muted-foreground">
            Add a patient email in Contact to enable email-based invites.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
