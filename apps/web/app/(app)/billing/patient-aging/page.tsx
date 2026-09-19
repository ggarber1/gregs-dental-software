"use client";

import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { centsToUsd } from "@/lib/api/reports";
import {
  DEFAULT_MIN_BALANCE_CENTS,
  lastStatementLabel,
  usePatientAgingWorklist,
  useSendStatement,
  type AgingSortBy,
  type PatientAgingRow,
} from "@/lib/api/statements";

const SORT_OPTIONS: { value: AgingSortBy; label: string }[] = [
  { value: "balance", label: "Total balance" },
  { value: "oldest_charge", label: "Oldest charge" },
  { value: "last_statement", label: "Last statement" },
];

const ACTION_CLASS = "text-sm text-primary underline disabled:opacity-50 disabled:no-underline";

function AgingRowActions({ row }: { row: PatientAgingRow }) {
  const send = useSendStatement(row.patientId);
  const emailTitle = row.email ? `Email to ${row.email}` : "Patient has no email on file";
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        className={ACTION_CLASS}
        disabled={!row.email || send.isPending}
        title={emailTitle}
        onClick={() => send.mutate("email")}
      >
        {send.isPending && send.variables === "email" ? "Sending…" : "Send email"}
      </button>
      <button
        type="button"
        className={ACTION_CLASS}
        disabled={send.isPending}
        title="Download PDF for mailing"
        onClick={() => send.mutate("download")}
      >
        {send.isPending && send.variables === "download" ? "Preparing…" : "Download PDF"}
      </button>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex justify-center py-16">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-border py-16 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

export default function PatientAgingPage() {
  const [sortBy, setSortBy] = useState<AgingSortBy>("balance");
  const [showAll, setShowAll] = useState(false);
  const minBalanceCents = showAll ? 1 : DEFAULT_MIN_BALANCE_CENTS;
  const { data, isLoading, isError } = usePatientAgingWorklist({ sortBy, minBalanceCents });
  const rows = data ?? [];

  const totals = rows.reduce(
    (acc, r) => ({
      b0_30: acc.b0_30 + r.buckets.b0_30,
      b31_60: acc.b31_60 + r.buckets.b31_60,
      b61_90: acc.b61_90 + r.buckets.b61_90,
      b90_plus: acc.b90_plus + r.buckets.b90_plus,
      credits: acc.credits + r.creditsCents,
      balance: acc.balance + r.balanceCents,
    }),
    { b0_30: 0, b31_60: 0, b61_90: 0, b90_plus: 0, credits: 0, balance: 0 },
  );

  return (
    <div className="flex flex-col gap-6 p-6">
      <Link href="/billing" className="text-sm text-muted-foreground hover:text-foreground">
        ← Billing
      </Link>
      <PageHeader
        title="Patient A/R"
        description="Patients with an outstanding balance, aged by charge date"
        actions={
          <>
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Sort</span>
              <select
                className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as AgingSortBy)}
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showAll}
                onChange={(e) => setShowAll(e.target.checked)}
              />
              <span>Show balances under {centsToUsd(DEFAULT_MIN_BALANCE_CENTS)}</span>
            </label>
          </>
        }
      />

      {isLoading && <LoadingSpinner />}
      {!isLoading && isError && <EmptyState message="Could not load patient A/R." />}
      {!isLoading && !isError && rows.length === 0 && (
        <EmptyState message="No patients with an outstanding balance." />
      )}

      {!isLoading && !isError && rows.length > 0 && (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Patient</TableHead>
                <TableHead className="text-right">Current</TableHead>
                <TableHead className="text-right">31–60</TableHead>
                <TableHead className="text-right">61–90</TableHead>
                <TableHead className="text-right">90+</TableHead>
                <TableHead className="text-right">Credits</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Last statement</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.patientId}>
                  <TableCell>
                    <Link href={`/patients/${row.patientId}`} className="font-medium hover:underline">
                      {row.patientName}
                    </Link>
                    {!row.email && (
                      <span className="ml-2 text-xs text-muted-foreground">no email</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{centsToUsd(row.buckets.b0_30)}</TableCell>
                  <TableCell className="text-right tabular-nums">{centsToUsd(row.buckets.b31_60)}</TableCell>
                  <TableCell className="text-right tabular-nums">{centsToUsd(row.buckets.b61_90)}</TableCell>
                  <TableCell className="text-right tabular-nums">{centsToUsd(row.buckets.b90_plus)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {centsToUsd(-row.creditsCents)}
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {centsToUsd(row.balanceCents)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {lastStatementLabel(row.lastStatementAt)}
                    {row.lastStatementMethod && (
                      <span className="ml-1 text-xs">
                        ({row.lastStatementMethod === "email" ? "email" : "download"})
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <AgingRowActions row={row} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell>{rows.length} patients</TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.b0_30)}</TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.b31_60)}</TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.b61_90)}</TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.b90_plus)}</TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {centsToUsd(-totals.credits)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.balance)}</TableCell>
                <TableCell colSpan={2} />
              </TableRow>
            </TableFooter>
          </Table>
        </div>
      )}
    </div>
  );
}
