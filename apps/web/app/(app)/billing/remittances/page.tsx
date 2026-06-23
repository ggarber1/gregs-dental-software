"use client";

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
import {
  usePollEras,
  useRemittances,
  useResolveUnmatched,
  useUnmatched,
} from "@/lib/api/era";

function centsToUsd(cents: number | null): string {
  return cents == null ? "—" : `$${(cents / 100).toFixed(2)}`;
}

export default function RemittancesPage() {
  const poll = usePollEras();
  const { data: remittances } = useRemittances();
  const { data: unmatched } = useUnmatched(false);
  const resolve = useResolveUnmatched();

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader
        title="Remittances (ERA)"
        description="Pull 835 ERAs from the clearinghouse and auto-post insurance payments."
      />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => poll.mutate()}
          disabled={poll.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {poll.isPending ? "Polling…" : "Poll for ERAs"}
        </button>
        {poll.data && (
          <span className="text-sm text-muted-foreground">
            {poll.data.new} new · {poll.data.matched} matched · {poll.data.unmatched} unmatched
          </span>
        )}
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Remittances</h2>
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Payer</TableHead>
                <TableHead>Trace</TableHead>
                <TableHead className="text-right">Payment</TableHead>
                <TableHead className="text-right">Claims</TableHead>
                <TableHead className="text-right">Matched</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(remittances ?? []).map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.payerName ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{r.traceNumber ?? "—"}</TableCell>
                  <TableCell className="text-right">{centsToUsd(r.paymentCents)}</TableCell>
                  <TableCell className="text-right">{r.claimCount ?? 0}</TableCell>
                  <TableCell className="text-right">{r.matchedCount ?? 0}</TableCell>
                  <TableCell className="text-muted-foreground">{r.paymentDate ?? "—"}</TableCell>
                </TableRow>
              ))}
              {(remittances ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                    No remittances yet. Click &ldquo;Poll for ERAs&rdquo; to fetch.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Unmatched payments</h2>
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Patient Control #</TableHead>
                <TableHead>Payer Claim #</TableHead>
                <TableHead className="text-right">Paid</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(unmatched ?? []).map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-mono text-xs">{u.patientControlNumber ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{u.payerClaimControlNumber ?? "—"}</TableCell>
                  <TableCell className="text-right">{centsToUsd(u.paidCents)}</TableCell>
                  <TableCell className="text-right">
                    <button
                      type="button"
                      onClick={() => resolve.mutate(u.id)}
                      disabled={resolve.isPending}
                      className="text-sm text-primary underline disabled:opacity-50"
                    >
                      Resolve
                    </button>
                  </TableCell>
                </TableRow>
              ))}
              {(unmatched ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                    <Badge variant="secondary">All clear</Badge>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>
    </div>
  );
}
