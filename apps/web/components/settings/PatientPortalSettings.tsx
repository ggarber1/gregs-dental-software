"use client";

import { Copy, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function getPortalUrl(): string {
  const configured = process.env.NEXT_PUBLIC_PATIENT_PORTAL_URL;
  if (configured) return configured;
  return "http://localhost:3000/portal";
}

export function PatientPortalSettings() {
  const portalUrl = getPortalUrl();

  async function handleCopyUrl() {
    try {
      await navigator.clipboard.writeText(portalUrl);
    } catch {
      // Ignore clipboard write failures in unsupported contexts.
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base font-semibold">Patient Portal</CardTitle>
          <Badge variant="outline">5.2A</Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Share this URL with patients. Staff can send secure invite links from each patient chart.
          </p>

          <div className="rounded-md border p-3">
            <p className="text-xs text-muted-foreground">Patient-facing URL</p>
            <p className="mt-1 break-all font-mono text-sm">{portalUrl}</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => void handleCopyUrl()}>
              <Copy className="h-4 w-4" />
              Copy URL
            </Button>

            <Button size="sm" variant="outline" asChild>
              <a href={portalUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="h-4 w-4" />
                Open Portal
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
