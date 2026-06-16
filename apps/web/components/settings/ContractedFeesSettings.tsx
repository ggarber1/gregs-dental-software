"use client";

import { useEffect, useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useInsurancePlans } from "@/lib/api/insurance-plans";
import {
  useContractedFees,
  useSetContractedFee,
  useRevertContractedFee,
  dollarsToCents,
  centsToDollars,
  type ContractedFeeRow,
} from "@/lib/api/contracted-fees";

export function ContractedFeesSettings() {
  const { data: plans = [], isLoading: plansLoading } = useInsurancePlans();
  const [payerId, setPayerId] = useState("");
  const [filter, setFilter] = useState("");

  const { data: rows, isLoading: feesLoading } = useContractedFees(payerId);
  const setFee = useSetContractedFee(payerId);
  const revertFee = useRevertContractedFee(payerId);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const list = rows ?? [];
    if (!q) return list;
    return list.filter(
      (r) => r.code.toLowerCase().includes(q) || r.description.toLowerCase().includes(q),
    );
  }, [rows, filter]);

  const customizedCount = (rows ?? []).filter((r) => r.allowedAmountCents != null).length;
  const totalCount = (rows ?? []).length;

  function commitAmount(row: ContractedFeeRow, raw: string) {
    const cents = dollarsToCents(raw);
    if (cents == null) {
      // Cleared -> revert to default, but only if an override exists.
      if (row.allowedAmountCents != null) revertFee.mutate(row.cdtCodeId);
      return;
    }
    if (cents === row.allowedAmountCents) return; // no change
    setFee.mutate({
      cdtCodeId: row.cdtCodeId,
      body: {
        allowedAmountCents: cents,
        notCovered: row.notCovered,
        requiresPriorAuth: row.requiresPriorAuth,
      },
    });
  }

  function commitNotCovered(row: ContractedFeeRow, checked: boolean) {
    setFee.mutate({
      cdtCodeId: row.cdtCodeId,
      body: {
        allowedAmountCents: checked ? null : row.allowedAmountCents,
        notCovered: checked,
        requiresPriorAuth: row.requiresPriorAuth,
      },
    });
  }

  function commitPriorAuth(row: ContractedFeeRow, checked: boolean) {
    setFee.mutate({
      cdtCodeId: row.cdtCodeId,
      body: {
        allowedAmountCents: row.allowedAmountCents,
        notCovered: row.notCovered,
        requiresPriorAuth: checked,
      },
    });
  }

  // Deduplicate payer IDs — the same payer_id may appear on multiple plans
  // (e.g. different group numbers). Show one entry per unique payer.
  const uniquePayers = useMemo(() => {
    const seen = new Set<string>();
    return plans.filter((p) => {
      if (seen.has(p.payerId)) return false;
      seen.add(p.payerId);
      return true;
    });
  }, [plans]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Contracted Fees</h3>
        {payerId && totalCount > 0 && (
          <p className="text-sm text-muted-foreground">
            {customizedCount} of {totalCount} with allowed amount
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5 max-w-xs">
        <Label>Payer</Label>
        {plansLoading ? (
          <p className="text-sm text-muted-foreground">Loading plans…</p>
        ) : uniquePayers.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No insurance plans configured. Add plans in the Insurance Plans tab first.
          </p>
        ) : (
          <Select value={payerId} onValueChange={setPayerId}>
            <SelectTrigger>
              <SelectValue placeholder="Select a payer…" />
            </SelectTrigger>
            <SelectContent>
              {uniquePayers.map((plan) => (
                <SelectItem key={plan.payerId} value={plan.payerId}>
                  {plan.carrierName}{" "}
                  <span className="font-mono text-xs text-muted-foreground">
                    ({plan.payerId})
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {payerId && (
        <>
          <Input
            className="max-w-xs"
            placeholder="Filter by code or description…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />

          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-24">Code</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="w-40 text-right">Allowed ($)</TableHead>
                  <TableHead className="w-28 text-center">Not covered</TableHead>
                  <TableHead className="w-28 text-center">Prior auth</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {feesLoading ? (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                      Loading…
                    </TableCell>
                  </TableRow>
                ) : filtered.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                      No matching codes.
                    </TableCell>
                  </TableRow>
                ) : (
                  filtered.map((row) => (
                    <ContractedFeeRowItem
                      key={row.cdtCodeId}
                      row={row}
                      onCommitAmount={commitAmount}
                      onCommitNotCovered={commitNotCovered}
                      onCommitPriorAuth={commitPriorAuth}
                    />
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  );
}

function ContractedFeeRowItem({
  row,
  onCommitAmount,
  onCommitNotCovered,
  onCommitPriorAuth,
}: {
  row: ContractedFeeRow;
  onCommitAmount: (row: ContractedFeeRow, raw: string) => void;
  onCommitNotCovered: (row: ContractedFeeRow, checked: boolean) => void;
  onCommitPriorAuth: (row: ContractedFeeRow, checked: boolean) => void;
}) {
  const [value, setValue] = useState(centsToDollars(row.allowedAmountCents));

  // Re-sync the local input when the server value changes (e.g. after toggling
  // "not covered", which nulls the amount). The row instance is reused across
  // refetches because its key (cdtCodeId) is stable, so useState alone is stale.
  useEffect(() => {
    setValue(centsToDollars(row.allowedAmountCents));
  }, [row.allowedAmountCents]);

  return (
    <TableRow>
      <TableCell className="font-mono text-xs">{row.code}</TableCell>
      <TableCell>{row.description}</TableCell>
      <TableCell className="text-right">
        <Input
          className="h-8 text-right text-sm"
          type="number"
          min="0"
          step="0.01"
          placeholder="—"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={() => onCommitAmount(row, value)}
          disabled={row.notCovered}
          aria-label={`Allowed amount for ${row.code}`}
        />
      </TableCell>
      <TableCell className="text-center">
        <input
          type="checkbox"
          className="h-4 w-4 cursor-pointer"
          checked={row.notCovered}
          onChange={(e) => onCommitNotCovered(row, e.target.checked)}
          aria-label={`Not covered for ${row.code}`}
        />
      </TableCell>
      <TableCell className="text-center">
        <input
          type="checkbox"
          className="h-4 w-4 cursor-pointer"
          checked={row.requiresPriorAuth}
          onChange={(e) => onCommitPriorAuth(row, e.target.checked)}
          aria-label={`Prior auth required for ${row.code}`}
        />
      </TableCell>
    </TableRow>
  );
}
