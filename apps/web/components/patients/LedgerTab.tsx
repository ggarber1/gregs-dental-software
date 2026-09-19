"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  usePatientLedger,
  useRecordPayment,
  useAddAdjustment,
  centsToUsd,
  dollarsToCents,
  type LedgerEntry,
  type LedgerPaymentMethod,
} from "@/lib/api/ledger";
import { apiErrorMessage } from "@/lib/api-client";
import { usePatient } from "@/lib/api/patients";
import {
  downloadStatementPdf,
  fetchStatementPreview,
  lastStatementLabel,
  openBlob,
  statementFilename,
  usePatientStatements,
  useSendStatement,
} from "@/lib/api/statements";
import { toast } from "sonner";

interface LedgerTabProps {
  patientId: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const PAYMENT_METHODS: { value: LedgerPaymentMethod; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "check", label: "Check" },
  { value: "card", label: "Card" },
  { value: "external_terminal", label: "External terminal" },
  { value: "other", label: "Other" },
];

const ENTRY_TYPE_LABEL: Record<LedgerEntry["entryType"], string> = {
  charge: "Charge",
  insurance_payment: "Insurance payment",
  patient_payment: "Patient payment",
  adjustment: "Adjustment",
};

function describeEntry(entry: LedgerEntry): string {
  if (entry.reversesEntryId) return "Reversal";
  const parts: string[] = [ENTRY_TYPE_LABEL[entry.entryType]];
  if (entry.entryType === "patient_payment" && entry.paymentMethod) {
    const method = PAYMENT_METHODS.find((m) => m.value === entry.paymentMethod);
    parts.push(`(${method?.label ?? entry.paymentMethod})`);
  }
  if (entry.memo) parts.push(`— ${entry.memo}`);
  return parts.join(" ");
}

const INPUT_CLASS =
  "rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

// ── Forms ─────────────────────────────────────────────────────────────────────

function RecordPaymentForm({ patientId }: { patientId: string }) {
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<LedgerPaymentMethod>("cash");
  const [memo, setMemo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recordPayment = useRecordPayment(patientId);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const amountCents = dollarsToCents(amount, false);
    if (amountCents == null) {
      setError("Enter a payment amount greater than $0.");
      return;
    }
    const trimmedMemo = memo.trim();
    recordPayment.mutate(
      {
        amountCents,
        paymentMethod: method,
        ...(trimmedMemo ? { memo: trimmedMemo } : {}),
      },
      {
        onSuccess: () => {
          setAmount("");
          setMemo("");
        },
        onError: () => setError("Failed to record payment."),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground" htmlFor="payment-amount">
          Amount ($)
        </label>
        <input
          id="payment-amount"
          className={`${INPUT_CLASS} w-28`}
          inputMode="decimal"
          placeholder="0.00"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground" htmlFor="payment-method">
          Method
        </label>
        <select
          id="payment-method"
          className={INPUT_CLASS}
          value={method}
          onChange={(e) => setMethod(e.target.value as LedgerPaymentMethod)}
        >
          {PAYMENT_METHODS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-1 flex-col gap-1">
        <label className="text-xs text-muted-foreground" htmlFor="payment-memo">
          Memo (optional)
        </label>
        <input
          id="payment-memo"
          className={`${INPUT_CLASS} w-full`}
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
        />
      </div>
      <button
        type="submit"
        disabled={recordPayment.isPending}
        className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
      >
        {recordPayment.isPending ? "Recording…" : "Record payment"}
      </button>
      {error && <p className="w-full text-xs text-destructive">{error}</p>}
    </form>
  );
}

function AddAdjustmentForm({ patientId }: { patientId: string }) {
  const [amount, setAmount] = useState("");
  const [memo, setMemo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const addAdjustment = useAddAdjustment(patientId);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const amountCents = dollarsToCents(amount, true);
    if (amountCents == null) {
      setError("Enter a non-zero adjustment amount (negative for a credit).");
      return;
    }
    if (!memo.trim()) {
      setError("A memo is required for adjustments.");
      return;
    }
    addAdjustment.mutate(
      { amountCents, memo: memo.trim() },
      {
        onSuccess: () => {
          setAmount("");
          setMemo("");
        },
        onError: () => setError("Failed to add adjustment."),
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground" htmlFor="adjustment-amount">
          Amount ($)
        </label>
        <input
          id="adjustment-amount"
          className={`${INPUT_CLASS} w-28`}
          inputMode="decimal"
          placeholder="-25.00"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </div>
      <div className="flex flex-1 flex-col gap-1">
        <label className="text-xs text-muted-foreground" htmlFor="adjustment-memo">
          Memo (required)
        </label>
        <input
          id="adjustment-memo"
          className={`${INPUT_CLASS} w-full`}
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
        />
      </div>
      <button
        type="submit"
        disabled={addAdjustment.isPending}
        className="rounded-md border border-input px-4 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
      >
        {addAdjustment.isPending ? "Adding…" : "Add adjustment"}
      </button>
      {error && <p className="w-full text-xs text-destructive">{error}</p>}
    </form>
  );
}

// ── Tab ───────────────────────────────────────────────────────────────────────

const STATEMENT_BUTTON_CLASS =
  "rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50 disabled:pointer-events-none";

function StatementActions({
  patientId,
  balanceCents,
  email,
}: {
  patientId: string;
  balanceCents: number;
  email: string | null | undefined;
}) {
  const send = useSendStatement(patientId);
  const [previewing, setPreviewing] = useState(false);
  const hasBalance = balanceCents > 0;
  const balanceTitle = hasBalance ? undefined : "No outstanding balance";

  const preview = async () => {
    setPreviewing(true);
    try {
      const blob = await fetchStatementPreview(patientId);
      openBlob(blob, statementFilename(new Date().toISOString()));
    } catch (err) {
      toast.error(apiErrorMessage(err));
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        className={STATEMENT_BUTTON_CLASS}
        disabled={!hasBalance || previewing}
        title={balanceTitle ?? "Open a PDF preview in a new tab"}
        onClick={() => void preview()}
      >
        {previewing ? "Generating…" : "Preview statement"}
      </button>
      <button
        type="button"
        className={STATEMENT_BUTTON_CLASS}
        disabled={!hasBalance || !email || send.isPending}
        title={balanceTitle ?? (email ? `Email statement to ${email}` : "Patient has no email on file")}
        onClick={() => send.mutate("email")}
      >
        {send.isPending && send.variables === "email" ? "Sending…" : "Email statement"}
      </button>
      <button
        type="button"
        className={STATEMENT_BUTTON_CLASS}
        disabled={!hasBalance || send.isPending}
        title={balanceTitle ?? "Download PDF for mailing"}
        onClick={() => send.mutate("download")}
      >
        {send.isPending && send.variables === "download" ? "Preparing…" : "Download PDF"}
      </button>
    </div>
  );
}

function StatementHistory({ patientId }: { patientId: string }) {
  const [open, setOpen] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const { data, isLoading } = usePatientStatements(patientId);
  const statements = data ?? [];

  const download = async (statement: (typeof statements)[number]) => {
    setDownloadingId(statement.id);
    try {
      await downloadStatementPdf(patientId, statement);
    } catch {
      toast.error("Could not download the statement PDF.");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <h3 className="text-sm font-semibold">
          Statement history
          {!isLoading && (
            <span className="ml-2 font-normal text-muted-foreground">({statements.length})</span>
          )}
        </h3>
        <span className="text-xs text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>

      {open && statements.length === 0 && !isLoading && (
        <p className="text-sm text-muted-foreground">No statements have been sent.</p>
      )}

      {open && statements.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Delivery</th>
                <th className="px-3 py-2 text-right">Balance</th>
                <th className="px-3 py-2">Sent by</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {statements.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-muted-foreground">
                    {s.generatedAt.slice(0, 10)}
                    <span className="ml-2 text-xs">({lastStatementLabel(s.generatedAt)})</span>
                  </td>
                  <td className="px-3 py-2">{s.deliveryMethod === "email" ? "Email" : "Downloaded"}</td>
                  <td className="px-3 py-2 text-right">{centsToUsd(s.balanceCents)}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {s.generatedBy}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      className="text-xs text-primary underline disabled:opacity-50"
                      disabled={downloadingId === s.id}
                      onClick={() => void download(s)}
                    >
                      {downloadingId === s.id ? "…" : "PDF"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function BalanceBadge({ balanceCents }: { balanceCents: number }) {
  if (balanceCents > 0) {
    return <Badge variant="destructive">{centsToUsd(balanceCents)} owed</Badge>;
  }
  if (balanceCents < 0) {
    return <Badge variant="secondary">{centsToUsd(-balanceCents)} credit</Badge>;
  }
  return <Badge variant="secondary">$0.00</Badge>;
}

export function LedgerTab({ patientId }: LedgerTabProps) {
  const { data, isLoading, isError } = usePatientLedger(patientId);
  const { data: patient } = usePatient(patientId);

  const entries = data?.entries ?? [];
  const balanceCents = data?.balanceCents ?? 0;

  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Ledger</h2>
          <div className="flex flex-wrap items-center gap-3">
            <StatementActions
              patientId={patientId}
              balanceCents={balanceCents}
              email={patient?.email}
            />
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Balance</span>
              <BalanceBadge balanceCents={balanceCents} />
            </div>
          </div>
        </div>

        {isLoading && (
          <div className="flex justify-center py-8">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        )}

        {!isLoading && (isError || entries.length === 0) && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No ledger entries.
          </p>
        )}

        {!isLoading && !isError && entries.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Description</th>
                  <th className="px-3 py-2 text-right">Charge</th>
                  <th className="px-3 py-2 text-right">Credit</th>
                  <th className="px-3 py-2 text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const isReversal = Boolean(entry.reversesEntryId);
                  return (
                    <tr
                      key={entry.id}
                      className={`border-b border-border last:border-0 ${
                        isReversal ? "text-muted-foreground line-through" : ""
                      }`}
                    >
                      <td className="px-3 py-2 text-muted-foreground">
                        {entry.postedAt.slice(0, 10)}
                      </td>
                      <td className="px-3 py-2">{describeEntry(entry)}</td>
                      <td className="px-3 py-2 text-right">
                        {entry.amountCents > 0 ? centsToUsd(entry.amountCents) : "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {entry.amountCents < 0 ? centsToUsd(-entry.amountCents) : "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {centsToUsd(entry.runningBalanceCents)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <StatementHistory patientId={patientId} />

      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <h3 className="text-sm font-semibold">Record payment</h3>
        <RecordPaymentForm patientId={patientId} />
      </div>

      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <h3 className="text-sm font-semibold">Add adjustment</h3>
        <AddAdjustmentForm patientId={patientId} />
      </div>
    </div>
  );
}
