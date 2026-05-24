"use client";

import { useState } from "react";
import { Plus, Trash2, Eye, GitCompare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  usePerioCharts,
  usePerioChart,
  useDeletePerioChart,
  useComparePerioCharts,
  type PerioChartSummary,
  type PerioSite,
} from "@/lib/api/perio-charts";
import { PerioChartEntry } from "./PerioChartEntry";
import { cn } from "@/lib/utils";

interface PerioChartTabProps {
  patientId: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(d: string): string {
  const [y, m, day] = d.split("-");
  return `${m}/${day}/${y}`;
}

function statBadge(label: string, value: number, warnAt?: number) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
        warnAt !== undefined && value >= warnAt
          ? "border-red-300 bg-red-50 text-red-700"
          : "border-border bg-muted text-muted-foreground",
      )}
    >
      <span className="font-medium text-foreground">{value}</span>
      <span>{label}</span>
    </span>
  );
}

const BUCCAL_SITES: PerioSite[] = ["db", "b", "mb"];
const LINGUAL_SITES: PerioSite[] = ["dl", "l", "ml"];
const UPPER_TEETH = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16];
const LOWER_TEETH = [17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32];

// ── Comparison view ───────────────────────────────────────────────────────────

function ComparisonView({
  patientId,
  charts,
}: {
  patientId: string;
  charts: PerioChartSummary[];
}) {
  const [aId, setAId] = useState<string>(charts[0]?.id ?? "");
  const [bId, setBId] = useState<string>(charts[1]?.id ?? "");
  const { data: comparison, isLoading } = useComparePerioCharts(
    patientId,
    aId || null,
    bId || null,
  );

  const deltaMap = new Map(
    (comparison?.deltas ?? []).map(d => [`${d.toothNumber}:${d.site}`, d.delta]),
  );

  function deltaClass(delta: number): string {
    if (delta > 0) return "bg-red-50 text-red-700 border-red-300";
    if (delta < 0) return "bg-green-50 text-green-700 border-green-300";
    return "bg-muted text-muted-foreground border-border";
  }

  function renderArchDelta(teeth: number[], isLower: boolean) {
    const topSites = isLower ? LINGUAL_SITES : BUCCAL_SITES;
    const bottomSites = isLower ? BUCCAL_SITES : LINGUAL_SITES;

    function DeltaCell({ tooth, site }: { tooth: number; site: PerioSite }) {
      const ra = comparison?.chartA.readings.find(
        r => r.toothNumber === String(tooth) && r.site === site,
      );
      const rb = comparison?.chartB.readings.find(
        r => r.toothNumber === String(tooth) && r.site === site,
      );
      const delta = deltaMap.get(`${tooth}:${site}`);

      if (!comparison) return <div className="w-7 h-6" />;

      return (
        <div
          title={`A: ${ra?.probingDepthMm ?? 0}  B: ${rb?.probingDepthMm ?? 0}`}
          className={cn(
            "w-7 h-6 flex items-center justify-center rounded border text-xs font-medium",
            delta !== undefined ? deltaClass(delta) : "border-border text-muted-foreground",
          )}
        >
          {delta !== undefined ? (delta > 0 ? `+${delta}` : delta) : "—"}
        </div>
      );
    }

    return (
      <div className="min-w-max">
        <div className="flex items-center h-6 border-b border-border">
          <div className="w-16 shrink-0" />
          {teeth.map(tooth => (
            <div
              key={tooth}
              className="flex border-r border-border/50 last:border-r-0 justify-center"
              style={{ width: 84 }}
            >
              <span className="text-[10px] font-semibold">{tooth}</span>
            </div>
          ))}
        </div>
        {[topSites, bottomSites].map((sitesRow, rowIdx) => (
          <div key={rowIdx} className="flex items-center h-7">
            <div className="w-16 shrink-0 text-[10px] text-muted-foreground text-right pr-2">
              {rowIdx === 0
                ? isLower ? "Lingual" : "Buccal"
                : isLower ? "Buccal" : "Lingual"}
            </div>
            {teeth.map(tooth => (
              <div
                key={tooth}
                className="flex border-r border-border/50 last:border-r-0"
              >
                {sitesRow.map(site => (
                  <div key={site} className="w-7">
                    <DeltaCell tooth={tooth} site={site} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Chart A (baseline)</span>
          <Select value={aId} onValueChange={setAId}>
            <SelectTrigger className="h-8 w-44">
              <SelectValue placeholder="Select…" />
            </SelectTrigger>
            <SelectContent>
              {charts.map(c => (
                <SelectItem key={c.id} value={c.id}>
                  {fmt(c.chartDate)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">Chart B (recent)</span>
          <Select value={bId} onValueChange={setBId}>
            <SelectTrigger className="h-8 w-44">
              <SelectValue placeholder="Select…" />
            </SelectTrigger>
            <SelectContent>
              {charts.map(c => (
                <SelectItem key={c.id} value={c.id}>
                  {fmt(c.chartDate)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {isLoading && (
        <div className="flex justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {comparison && !isLoading && (
        <>
          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-1">
              <div className="h-3 w-5 rounded border border-red-300 bg-red-50" />
              <span>Worse</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-3 w-5 rounded border border-green-300 bg-green-50" />
              <span>Improved</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-3 w-5 rounded border border-border bg-muted" />
              <span>Unchanged</span>
            </div>
            <span className="text-muted-foreground">
              · Hover a cell to see A/B depths
            </span>
          </div>

          <div className="overflow-x-auto rounded-md border border-border p-2">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Upper arch
            </div>
            {renderArchDelta(UPPER_TEETH, false)}
          </div>
          <div className="overflow-x-auto rounded-md border border-border p-2">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Lower arch
            </div>
            {renderArchDelta(LOWER_TEETH, true)}
          </div>
        </>
      )}
    </div>
  );
}

// ── Main tab ──────────────────────────────────────────────────────────────────

export function PerioChartTab({ patientId }: PerioChartTabProps) {
  const { data, isLoading } = usePerioCharts(patientId);
  const { mutate: deleteChart, isPending: isDeleting } = useDeletePerioChart(patientId);

  const [entryOpen, setEntryOpen] = useState(false);
  const [viewChartId, setViewChartId] = useState<string | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const { data: viewChart, isLoading: viewLoading } = usePerioChart(patientId, viewChartId);

  const charts = data?.items ?? [];
  const mostRecent = charts[0];

  return (
    <div className="flex flex-col gap-6">
      {/* Summary + new chart button */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          {mostRecent ? (
            <>
              <p className="text-sm font-medium">
                Most recent chart:{" "}
                <span className="text-muted-foreground">{fmt(mostRecent.chartDate)}</span>
              </p>
              <div className="flex flex-wrap gap-2">
                {statBadge("avg mm", mostRecent.avgProbingDepthMm, 4)}
                {statBadge("sites ≥4mm", mostRecent.sitesGte4mm, 1)}
                {statBadge("sites ≥6mm", mostRecent.sitesGte6mm, 1)}
                {statBadge("bleeding", mostRecent.bleedingSiteCount, 1)}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No perio charts recorded yet.</p>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          {charts.length >= 2 && (
            <Button variant="outline" size="sm" onClick={() => setCompareOpen(true)}>
              <GitCompare className="h-4 w-4" />
              Compare
            </Button>
          )}
          <Button size="sm" onClick={() => setEntryOpen(true)}>
            <Plus className="h-4 w-4" />
            New chart
          </Button>
        </div>
      </div>

      {/* Chart history list */}
      {isLoading && (
        <div className="flex justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {!isLoading && charts.length > 0 && (
        <div className="rounded-lg border border-border">
          <div className="divide-y divide-border">
            {charts.map(chart => (
              <div
                key={chart.id}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
              >
                <div className="flex flex-col gap-1">
                  <span className="text-sm font-medium">{fmt(chart.chartDate)}</span>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="outline" className="text-xs">
                      avg {chart.avgProbingDepthMm}mm
                    </Badge>
                    {chart.sitesGte4mm > 0 && (
                      <Badge variant="secondary" className="text-xs">
                        {chart.sitesGte4mm} sites ≥4mm
                      </Badge>
                    )}
                    {chart.bleedingSiteCount > 0 && (
                      <Badge
                        variant="destructive"
                        className="text-xs bg-red-100 text-red-700 hover:bg-red-100 border-red-300"
                      >
                        {chart.bleedingSiteCount} bleeding
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setViewChartId(chart.id)}
                  >
                    <Eye className="h-4 w-4" />
                    View
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setConfirmDeleteId(chart.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* New chart entry dialog */}
      <Dialog open={entryOpen} onOpenChange={o => !o && setEntryOpen(false)}>
        <DialogContent className="max-w-[98vw] max-h-[95vh] overflow-y-auto w-full">
          <DialogHeader>
            <DialogTitle>New perio chart</DialogTitle>
          </DialogHeader>
          <PerioChartEntry
            patientId={patientId}
            onSaved={() => setEntryOpen(false)}
            onClose={() => setEntryOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {/* View existing chart dialog */}
      <Dialog open={Boolean(viewChartId)} onOpenChange={o => !o && setViewChartId(null)}>
        <DialogContent className="max-w-[98vw] max-h-[95vh] overflow-y-auto w-full">
          <DialogHeader>
            <DialogTitle>
              Perio chart{viewChart ? ` — ${fmt(viewChart.chartDate)}` : ""}
            </DialogTitle>
          </DialogHeader>
          {viewLoading && (
            <div className="flex justify-center py-8">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          )}
          {viewChart && (
            <PerioChartEntry
              patientId={patientId}
              initialChart={viewChart}
              readOnly
              onSaved={() => setViewChartId(null)}
              onClose={() => setViewChartId(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Comparison dialog */}
      <Dialog open={compareOpen} onOpenChange={o => !o && setCompareOpen(false)}>
        <DialogContent className="max-w-[98vw] max-h-[95vh] overflow-y-auto w-full">
          <DialogHeader>
            <DialogTitle>Compare perio charts</DialogTitle>
          </DialogHeader>
          <ComparisonView patientId={patientId} charts={charts} />
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog
        open={Boolean(confirmDeleteId)}
        onOpenChange={o => !o && setConfirmDeleteId(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete perio chart?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will permanently delete the chart and all its readings. This cannot be undone.
          </p>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setConfirmDeleteId(null)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={isDeleting}
              onClick={() => {
                if (!confirmDeleteId) return;
                deleteChart(confirmDeleteId, {
                  onSuccess: () => setConfirmDeleteId(null),
                });
              }}
            >
              {isDeleting ? "Deleting…" : "Delete"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
