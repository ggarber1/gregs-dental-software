"use client";

import { Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppointmentClaims, useSubmitClaim, type Claim } from "@/lib/api/claims";

function centsToUsd(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function statusVariant(status: Claim["status"]): "default" | "secondary" | "destructive" {
  if (status === "submitted" || status === "paid" || status === "acknowledged") return "default";
  if (
    status === "clearinghouse_rejected" ||
    status === "submission_failed" ||
    status === "denied"
  )
    return "destructive";
  return "secondary";
}

export function ClaimPanel({ appointmentId }: { appointmentId: string }) {
  const { data: claims = [], isLoading } = useAppointmentClaims(appointmentId);
  const submit = useSubmitClaim(appointmentId);
  const latest = claims[0];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Insurance Claim</CardTitle>
        <Button size="sm" disabled={submit.isPending} onClick={() => submit.mutate()}>
          <Send className="mr-2 h-4 w-4" />
          {"Submit Claim"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {isLoading && <p className="text-muted-foreground">Loading…</p>}
        {!isLoading && !latest && (
          <p className="text-muted-foreground">
            No claim submitted yet. Submitting bills this appointment&apos;s procedures to the
            patient&apos;s primary insurance.
          </p>
        )}
        {latest && (
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Status</span>
              <Badge variant={statusVariant(latest.status)}>{latest.status}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Total charge</span>
              <span>{centsToUsd(latest.totalChargeCents)}</span>
            </div>
            {latest.submissionErrors && latest.submissionErrors.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-destructive">
                {latest.submissionErrors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {submit.isError && (
          <p className="text-destructive">
            Submission failed. Check that the practice NPI, tax ID, taxonomy, and clearinghouse
            credentials are configured, and that the appointment has procedures.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
