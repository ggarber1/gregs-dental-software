"use client";

import { useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useFeeSchedule,
  useSetFee,
  useRevertFee,
  dollarsToCents,
  centsToDollars,
  type FeeScheduleRow,
} from "@/lib/api/fee-schedule";

export function FeeScheduleSettings() {
  const { data: rows, isLoading } = useFeeSchedule();
  const setFee = useSetFee();
  const revertFee = useRevertFee();
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const list = rows ?? [];
    if (!q) return list;
    return list.filter(
      (r) => r.code.toLowerCase().includes(q) || r.description.toLowerCase().includes(q),
    );
  }, [rows, filter]);

  const customizedCount = (rows ?? []).filter((r) => r.practiceFeeCents != null).length;
  const totalCount = (rows ?? []).length;

  function commit(row: FeeScheduleRow, raw: string) {
    const cents = dollarsToCents(raw);
    if (cents == null) {
      // Cleared (or invalid) -> revert to default, but only if an override exists.
      if (row.practiceFeeCents != null) revertFee.mutate(row.code);
      return;
    }
    if (cents === row.practiceFeeCents) return; // no change
    setFee.mutate({ code: row.code, feeCents: cents });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Fee Schedule</h3>
        <p className="text-sm text-muted-foreground">
          {customizedCount} of {totalCount} customized
        </p>
      </div>

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
              <TableHead className="w-40 text-right">Fee ($)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                  No matching codes.
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((row) => (
                <FeeRow key={row.cdtCodeId} row={row} onCommit={commit} />
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function FeeRow({
  row,
  onCommit,
}: {
  row: FeeScheduleRow;
  onCommit: (row: FeeScheduleRow, raw: string) => void;
}) {
  const [value, setValue] = useState(centsToDollars(row.practiceFeeCents));
  const placeholder = centsToDollars(row.defaultFeeCents) || "—";

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
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={() => onCommit(row, value)}
          aria-label={`Fee for ${row.code}`}
        />
      </TableCell>
    </TableRow>
  );
}
