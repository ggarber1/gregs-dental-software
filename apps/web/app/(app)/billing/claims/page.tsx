"use client";

import { useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useClaimsList, type Claim } from "@/lib/api/claims";

const ALL_STATUSES: Array<Claim["status"] | ""> = [
  "",
  "draft",
  "submitted",
  "clearinghouse_rejected",
  "submission_failed",
  "acknowledged",
  "pending",
  "paid",
  "partially_paid",
  "denied",
  "appealing",
];

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

function centsToUsd(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function ClaimsPage() {
  const [status, setStatus] = useState<Claim["status"] | "">("");
  const { data, isLoading } = useClaimsList(status || undefined);

  const claims = data ?? [];

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader
        title="Claims"
        description="Track and manage submitted insurance claims."
      />

      <div className="flex items-center gap-3">
        <label htmlFor="status-filter" className="text-sm text-muted-foreground">
          Filter by status
        </label>
        <select
          id="status-filter"
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          value={status}
          onChange={(e) => setStatus(e.target.value as Claim["status"] | "")}
        >
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s === "" ? "All statuses" : s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {!isLoading && claims.length === 0 && (
        <div className="rounded-lg border border-border py-16 text-center">
          <p className="text-sm text-muted-foreground">
            {status ? `No claims with status "${status.replace(/_/g, " ")}".` : "No claims found."}
          </p>
        </div>
      )}

      {!isLoading && claims.length > 0 && (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Claim #</TableHead>
                <TableHead>Payer</TableHead>
                <TableHead className="text-right">Charge</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Submitted</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {claims.map((claim) => (
                <TableRow key={claim.id}>
                  <TableCell className="font-mono text-xs">{claim.patientControlNumber}</TableCell>
                  <TableCell className="text-muted-foreground">{claim.payerId}</TableCell>
                  <TableCell className="text-right">{centsToUsd(claim.totalChargeCents)}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(claim.status)}>
                      {claim.status.replace(/_/g, " ")}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {claim.submittedAt ? claim.submittedAt.slice(0, 10) : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
