"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import {
  useMedicalHistoryHistory,
  getMedicalHistoryVersion,
  type MedicalHistoryHistoryResponse,
  type MedicalHistoryVersionSummary,
  type MedicalHistoryVersion,
} from "@/lib/api/medical-history";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  patientId: string;
  open: boolean;
  onClose: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ActiveFlags({ flags }: { flags: MedicalHistoryVersionSummary["flags"] }) {
  const active: string[] = [];
  if (flags.flagBloodThinners) active.push("Blood thinner");
  if (flags.flagBisphosphonates) active.push("Bisphosphonate");
  if (flags.flagHeartCondition) active.push("Heart condition");
  if (flags.flagDiabetes) active.push("Diabetes");
  if (flags.flagPacemaker) active.push("Pacemaker");
  if (flags.flagLatexAllergy) active.push("Latex allergy");
  if (active.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {active.map((f) => (
        <Badge key={f} variant="destructive" className="text-xs">
          {f}
        </Badge>
      ))}
    </div>
  );
}

// ── Version snapshot panel ────────────────────────────────────────────────────

function VersionSnapshot({ patientId, versionId }: { patientId: string; versionId: string }) {
  const [data, setData] = useState<MedicalHistoryVersion | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  if (!data && !loading && !error) {
    setLoading(true);
    getMedicalHistoryVersion(patientId, versionId)
      .then((v) => {
        setData(v);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }

  if (loading) return <div className="py-2 text-sm text-muted-foreground">Loading…</div>;
  if (error) return <div className="py-2 text-sm text-destructive">Failed to load version.</div>;
  if (!data) return null;

  return (
    <div className="mt-3 flex flex-col gap-3 rounded-md border bg-muted/30 p-3 text-sm">
      {data.allergies.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground uppercase">Allergies</p>
          <ul className="flex flex-col gap-0.5">
            {data.allergies.map((a, i) => (
              <li key={i}>
                <span className="font-medium">{a.name}</span>
                {a.severity && <span className="text-muted-foreground"> · {a.severity}</span>}
                {a.reaction && <span className="text-muted-foreground"> — {a.reaction}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.medications.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground uppercase">Medications</p>
          <ul className="flex flex-col gap-0.5">
            {data.medications.map((m, i) => (
              <li key={i}>
                <span className="font-medium">{m.name}</span>
                {m.dose && <span className="text-muted-foreground"> · {m.dose}</span>}
                {m.frequency && <span className="text-muted-foreground"> · {m.frequency}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.conditions.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground uppercase">Conditions</p>
          <ul className="flex flex-col gap-0.5">
            {data.conditions.map((c, i) => (
              <li key={i}>
                <span className="font-medium">{c.name}</span>
                {c.icd10Hint && <span className="text-muted-foreground"> ({c.icd10Hint})</span>}
                {c.notes && <span className="text-muted-foreground"> — {c.notes}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.additionalNotes && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground uppercase">Notes</p>
          <p className="whitespace-pre-line text-foreground">{data.additionalNotes}</p>
        </div>
      )}
    </div>
  );
}

// ── Version row ───────────────────────────────────────────────────────────────

function VersionRow({ patientId, summary }: { patientId: string; summary: MedicalHistoryVersionSummary }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="py-3">
      <button
        className="flex w-full items-start justify-between gap-4 text-left"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground font-medium">v{summary.versionNumber}</span>
            <span className="text-sm">{formatDate(summary.recordedAt)}</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {summary.allergyCount > 0 && <span>{summary.allergyCount} allerg{summary.allergyCount === 1 ? "y" : "ies"}</span>}
            {summary.medicationCount > 0 && <span>{summary.medicationCount} med{summary.medicationCount === 1 ? "" : "s"}</span>}
            {summary.conditionCount > 0 && <span>{summary.conditionCount} condition{summary.conditionCount === 1 ? "" : "s"}</span>}
          </div>
          <ActiveFlags flags={summary.flags} />
        </div>
        {expanded ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded && <VersionSnapshot patientId={patientId} versionId={summary.id} />}
    </div>
  );
}

// ── Drawer (Dialog) ───────────────────────────────────────────────────────────

export function MedicalHistoryHistoryDrawer({ patientId, open, onClose }: Props) {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, isError } =
    useMedicalHistoryHistory(patientId);

  const allItems = data?.pages.flatMap((p: MedicalHistoryHistoryResponse) => p.items) ?? [];

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Medical History Versions</DialogTitle>
        </DialogHeader>

        {isLoading && (
          <div className="flex justify-center py-8">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        )}

        {isError && (
          <p className="py-4 text-sm text-destructive">Failed to load history.</p>
        )}

        {!isLoading && !isError && allItems.length === 0 && (
          <p className="py-4 text-sm text-muted-foreground">No versions recorded.</p>
        )}

        {!isLoading && !isError && allItems.length > 0 && (
          <div className="flex flex-col divide-y divide-border">
            {allItems.map((summary: MedicalHistoryVersionSummary) => (
              <VersionRow key={summary.id} patientId={patientId} summary={summary} />
            ))}
          </div>
        )}

        {hasNextPage && (
          <>
            <Separator className="my-2" />
            <Button
              variant="outline"
              size="sm"
              onClick={() => void fetchNextPage()}
              disabled={isFetchingNextPage}
              className="w-full"
            >
              {isFetchingNextPage ? "Loading…" : "Load more"}
            </Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
