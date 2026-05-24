"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { useProviders } from "@/lib/api/scheduling";
import {
  useCreatePerioChart,
  type PerioSite,
  type Furcation,
  type PerioChartDetail,
  type PerioReadingCreate,
} from "@/lib/api/perio-charts";

// ── Constants ─────────────────────────────────────────────────────────────────

// Full arches — used for tab order only
const UPPER_TEETH = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16];
const LOWER_TEETH = [17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32];

// Half-arches — used for rendering (8 per grid, no horizontal scroll)
const UPPER_RIGHT = [1, 2, 3, 4, 5, 6, 7, 8];
const UPPER_LEFT  = [9, 10, 11, 12, 13, 14, 15, 16];
const LOWER_LEFT  = [17, 18, 19, 20, 21, 22, 23, 24];
const LOWER_RIGHT = [25, 26, 27, 28, 29, 30, 31, 32];

const BUCCAL: PerioSite[] = ["db", "b", "mb"];
const LINGUAL: PerioSite[] = ["dl", "l", "ml"];

// Furcation is clinically relevant on multi-rooted teeth only
const FURCATION_TEETH = new Set([1, 2, 3, 5, 12, 14, 15, 16, 17, 18, 19, 30, 31, 32]);

// Tab order: upper buccal → upper lingual → lower lingual → lower buccal
const TAB_ORDER: Array<[number, PerioSite]> = [
  ...UPPER_TEETH.flatMap(t => BUCCAL.map(s => [t, s] as [number, PerioSite])),
  ...UPPER_TEETH.flatMap(t => LINGUAL.map(s => [t, s] as [number, PerioSite])),
  ...LOWER_TEETH.flatMap(t => LINGUAL.map(s => [t, s] as [number, PerioSite])),
  ...LOWER_TEETH.flatMap(t => BUCCAL.map(s => [t, s] as [number, PerioSite])),
];

const TAB_NEXT = new Map<string, [number, PerioSite]>(
  TAB_ORDER.slice(0, -1).map(([t, s], i) => [`${t}:${s}`, TAB_ORDER[i + 1]!]),
);
const TAB_PREV = new Map<string, [number, PerioSite]>(
  TAB_ORDER.slice(1).map(([t, s], i) => [`${t}:${s}`, TAB_ORDER[i]!]),
);

// ── Grid sizing — one place to adjust everything ──────────────────────────────

const CELL_W = "w-10";          // 40px per site cell
const TOOTH_W = 120;            // 3 × 40px per tooth column
const INPUT_CLS = "w-10 h-8 rounded border text-center text-sm px-0 [appearance:textfield]";
const ROW_H = "h-9";
const LABEL_CLS =
  "w-24 shrink-0 text-xs text-muted-foreground text-right pr-3 flex items-center justify-end";

// ── Local state types ─────────────────────────────────────────────────────────

interface SiteState {
  depth: string;
  recession: string;
  bleeding: boolean;
  suppuration: boolean;
}

interface ToothExtras {
  mobility: string;
  furcation: Furcation | "";
}

function siteKey(tooth: number, site: PerioSite): string {
  return `${tooth}:${site}`;
}

function emptySite(): SiteState {
  return { depth: "", recession: "", bleeding: false, suppuration: false };
}

function emptyExtras(): ToothExtras {
  return { mobility: "", furcation: "" };
}

// ── Color helpers ─────────────────────────────────────────────────────────────

function depthClass(d: number): string {
  if (d >= 6) return "border-red-400 bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300";
  if (d >= 4) return "border-yellow-400 bg-yellow-50 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300";
  return "border-input bg-background";
}

function calClass(cal: number): string {
  if (cal >= 6) return "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
  if (cal >= 4) return "bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300";
  return "text-muted-foreground";
}

// ── Component ─────────────────────────────────────────────────────────────────

interface PerioChartEntryProps {
  patientId: string;
  initialChart?: PerioChartDetail;
  readOnly?: boolean;
  onSaved: () => void;
  onClose: () => void;
}

export function PerioChartEntry({
  patientId,
  initialChart,
  readOnly = false,
  onSaved,
  onClose,
}: PerioChartEntryProps) {
  const today = new Date().toISOString().split("T")[0]!;

  const [sites, setSites] = useState<Record<string, SiteState>>(() => {
    if (!initialChart) return {};
    const init: Record<string, SiteState> = {};
    for (const r of initialChart.readings) {
      init[`${r.toothNumber}:${r.site}`] = {
        depth: String(r.probingDepthMm),
        recession: r.recessionMm > 0 ? String(r.recessionMm) : "",
        bleeding: r.bleeding,
        suppuration: r.suppuration,
      };
    }
    return init;
  });

  const [toothExtras, setToothExtras] = useState<Record<string, ToothExtras>>(() => {
    if (!initialChart) return {};
    const init: Record<string, ToothExtras> = {};
    const seen = new Set<string>();
    for (const r of initialChart.readings) {
      if (!seen.has(r.toothNumber)) {
        seen.add(r.toothNumber);
        init[r.toothNumber] = {
          mobility: r.mobility !== null ? String(r.mobility) : "",
          furcation: (r.furcation as Furcation | null) ?? "",
        };
      }
    }
    return init;
  });

  const [providerId, setProviderId] = useState(initialChart?.providerId ?? "");
  const [chartDate, setChartDate] = useState(initialChart?.chartDate ?? today);
  const [notes, setNotes] = useState(initialChart?.notes ?? "");
  const [error, setError] = useState<string | null>(null);

  const { data: providers } = useProviders();
  const { mutate: createChart, isPending } = useCreatePerioChart(patientId);

  const depthRefs = useRef<Map<string, HTMLInputElement | null>>(new Map());

  function getSite(tooth: number, site: PerioSite): SiteState {
    return sites[siteKey(tooth, site)] ?? emptySite();
  }

  function getExtras(tooth: number): ToothExtras {
    return toothExtras[String(tooth)] ?? emptyExtras();
  }

  function updateSite(tooth: number, site: PerioSite, patch: Partial<SiteState>) {
    const k = siteKey(tooth, site);
    setSites(prev => ({ ...prev, [k]: { ...(prev[k] ?? emptySite()), ...patch } }));
  }

  function updateExtras(tooth: number, patch: Partial<ToothExtras>) {
    const k = String(tooth);
    setToothExtras(prev => ({ ...prev, [k]: { ...(prev[k] ?? emptyExtras()), ...patch } }));
  }

  function advanceFocus(tooth: number, site: PerioSite, forward: boolean) {
    const map = forward ? TAB_NEXT : TAB_PREV;
    const next = map.get(siteKey(tooth, site));
    if (next) depthRefs.current.get(siteKey(...next))?.focus();
  }

  function handleDepthKeyDown(tooth: number, site: PerioSite) {
    return (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" || (e.key === "Tab" && !e.shiftKey)) {
        if (TAB_NEXT.has(siteKey(tooth, site))) {
          e.preventDefault();
          advanceFocus(tooth, site, true);
        }
      } else if (e.key === "Tab" && e.shiftKey) {
        if (TAB_PREV.has(siteKey(tooth, site))) {
          e.preventDefault();
          advanceFocus(tooth, site, false);
        }
      }
    };
  }

  function handleSubmit() {
    if (!providerId) {
      setError("Select a provider.");
      return;
    }
    const readings: PerioReadingCreate[] = [];
    const extras = toothExtras;

    for (const [tooth, site] of TAB_ORDER) {
      const s = sites[siteKey(tooth, site)];
      const depth = parseInt(s?.depth ?? "");
      if (isNaN(depth) && !s?.bleeding && !s?.suppuration && !s?.recession) continue;

      const ext = extras[String(tooth)] ?? emptyExtras();
      readings.push({
        toothNumber: String(tooth),
        site,
        probingDepthMm: isNaN(depth) ? 0 : depth,
        recessionMm: parseInt(s?.recession ?? "") || 0,
        bleeding: s?.bleeding ?? false,
        suppuration: s?.suppuration ?? false,
        furcation:
          site === "b" && FURCATION_TEETH.has(tooth)
            ? (ext.furcation as Furcation | "") || null
            : null,
        mobility: ext.mobility !== "" ? parseInt(ext.mobility) : null,
      });
    }

    createChart(
      { providerId, chartDate, ...(notes ? { notes } : {}), readings },
      {
        onSuccess: () => { setError(null); onSaved(); },
        onError: () => setError("Failed to save chart. Please try again."),
      },
    );
  }

  // ── Cell renderers ──────────────────────────────────────────────────────────

  function DepthInput({ tooth, site }: { tooth: number; site: PerioSite }) {
    const s = getSite(tooth, site);
    const d = parseInt(s.depth) || 0;
    const k = siteKey(tooth, site);
    return (
      <input
        ref={el => { depthRefs.current.set(k, el); }}
        type="number"
        min={0}
        max={20}
        value={s.depth}
        disabled={readOnly}
        aria-label={`Tooth ${tooth} ${site} probing depth`}
        onChange={e => updateSite(tooth, site, { depth: e.target.value })}
        onKeyDown={handleDepthKeyDown(tooth, site)}
        className={cn(INPUT_CLS, depthClass(d), readOnly && "cursor-default opacity-80")}
      />
    );
  }

  function RecessionInput({ tooth, site }: { tooth: number; site: PerioSite }) {
    const s = getSite(tooth, site);
    return (
      <input
        type="number"
        min={0}
        max={15}
        value={s.recession}
        disabled={readOnly}
        aria-label={`Tooth ${tooth} ${site} recession`}
        onChange={e => updateSite(tooth, site, { recession: e.target.value })}
        className={cn(INPUT_CLS, "border-input bg-background", readOnly && "cursor-default opacity-80")}
      />
    );
  }

  function BleedCell({ tooth, site }: { tooth: number; site: PerioSite }) {
    const s = getSite(tooth, site);
    return (
      <div className="flex flex-col items-center justify-center gap-0.5">
        <label className="flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            checked={s.bleeding}
            disabled={readOnly}
            aria-label={`Tooth ${tooth} ${site} bleeding`}
            onChange={e => updateSite(tooth, site, { bleeding: e.target.checked })}
            className="h-3.5 w-3.5 accent-red-500"
          />
          <span className={cn("text-[10px] leading-none font-medium", s.bleeding ? "text-red-600" : "text-muted-foreground")}>B</span>
        </label>
        <label className="flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            checked={s.suppuration}
            disabled={readOnly}
            aria-label={`Tooth ${tooth} ${site} suppuration`}
            onChange={e => updateSite(tooth, site, { suppuration: e.target.checked })}
            className="h-3.5 w-3.5 accent-orange-500"
          />
          <span className={cn("text-[10px] leading-none font-medium", s.suppuration ? "text-orange-600" : "text-muted-foreground")}>S</span>
        </label>
      </div>
    );
  }

  function CalCell({ tooth, site }: { tooth: number; site: PerioSite }) {
    const s = getSite(tooth, site);
    const cal = (parseInt(s.depth) || 0) + (parseInt(s.recession) || 0);
    return (
      <div className={cn("w-10 h-8 flex items-center justify-center rounded text-sm font-semibold", calClass(cal))}>
        {cal > 0 ? cal : ""}
      </div>
    );
  }

  // ── Arch grid renderer ──────────────────────────────────────────────────────

  function renderHalf(teeth: number[], isLower: boolean) {
    const topSites = isLower ? LINGUAL : BUCCAL;
    const bottomSites = isLower ? BUCCAL : LINGUAL;

    const toothBg = (idx: number) => (idx % 2 === 1 ? "bg-muted/25" : "");
    const toothGroup = (idx: number) =>
      cn("flex border-r border-border last:border-r-0", toothBg(idx));

    function Row({ label, children }: { label: string; children: React.ReactNode }) {
      return (
        <div className={cn("flex items-center", ROW_H)}>
          <div className={LABEL_CLS}>{label}</div>
          <div className="flex">{children}</div>
        </div>
      );
    }

    return (
      <div className="min-w-max">
        {/* Tooth numbers */}
        <div className="flex items-center h-8 border-b-2 border-border">
          <div className={LABEL_CLS} />
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={cn(toothGroup(idx), "relative")}>
              <div className={CELL_W} />
              <div className={CELL_W} />
              <div className={CELL_W} />
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-sm font-bold text-foreground">{tooth}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Site labels (top side) */}
        <div className="flex items-center h-6 border-b border-border bg-muted/10">
          <div className={LABEL_CLS} />
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {topSites.map(site => (
                <div key={site} className={cn(CELL_W, "flex items-center justify-center")}>
                  <span className="text-[10px] text-muted-foreground">{site}</span>
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Top probing depths */}
        <Row label={isLower ? "Depth (L)" : "Depth (B)"}>
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {topSites.map(site => (
                <div key={site} className={CELL_W}>
                  <DepthInput tooth={tooth} site={site} />
                </div>
              ))}
            </div>
          ))}
        </Row>

        {/* Top bleeding / suppuration */}
        <Row label="Bleed / Sup">
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {topSites.map(site => (
                <div key={site} className={CELL_W}>
                  <BleedCell tooth={tooth} site={site} />
                </div>
              ))}
            </div>
          ))}
        </Row>

        {/* Top recession */}
        <Row label="Recession">
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {topSites.map(site => (
                <div key={site} className={CELL_W}>
                  <RecessionInput tooth={tooth} site={site} />
                </div>
              ))}
            </div>
          ))}
        </Row>

        {/* Top CAL */}
        <Row label="CAL">
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {topSites.map(site => (
                <div key={site} className={CELL_W}>
                  <CalCell tooth={tooth} site={site} />
                </div>
              ))}
            </div>
          ))}
        </Row>

        {/* Tooth info: mobility + furcation */}
        <div className="flex items-center h-10 border-y-2 border-border bg-muted/50">
          <div className={LABEL_CLS}>Mob / Furc</div>
          {teeth.map((tooth, idx) => {
            const ext = getExtras(tooth);
            return (
              <div key={tooth} className={cn(toothGroup(idx), "relative")}>
                <div className={CELL_W} />
                <div className={CELL_W} />
                <div className={CELL_W} />
                <div className="absolute inset-0 flex items-center justify-center gap-1.5">
                  <input
                    type="number"
                    min={0}
                    max={3}
                    value={ext.mobility}
                    disabled={readOnly}
                    aria-label={`Tooth ${tooth} mobility`}
                    onChange={e => updateExtras(tooth, { mobility: e.target.value })}
                    placeholder="—"
                    className={cn(
                      "w-8 h-8 rounded border border-input bg-background text-center text-sm px-0 [appearance:textfield]",
                      readOnly && "cursor-default opacity-80",
                    )}
                  />
                  {FURCATION_TEETH.has(tooth) ? (
                    <select
                      value={ext.furcation}
                      disabled={readOnly}
                      aria-label={`Tooth ${tooth} furcation`}
                      onChange={e => updateExtras(tooth, { furcation: e.target.value as Furcation | "" })}
                      className={cn(
                        "h-8 rounded border border-input bg-background text-sm px-1",
                        readOnly && "cursor-default opacity-80",
                      )}
                    >
                      <option value="">—</option>
                      <option value="I">I</option>
                      <option value="II">II</option>
                      <option value="III">III</option>
                    </select>
                  ) : (
                    <div className="w-9" />
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Bottom CAL */}
        <Row label="CAL">
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {bottomSites.map(site => (
                <div key={site} className={CELL_W}>
                  <CalCell tooth={tooth} site={site} />
                </div>
              ))}
            </div>
          ))}
        </Row>

        {/* Bottom recession */}
        <Row label="Recession">
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {bottomSites.map(site => (
                <div key={site} className={CELL_W}>
                  <RecessionInput tooth={tooth} site={site} />
                </div>
              ))}
            </div>
          ))}
        </Row>

        {/* Bottom bleeding / suppuration */}
        <Row label="Bleed / Sup">
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {bottomSites.map(site => (
                <div key={site} className={CELL_W}>
                  <BleedCell tooth={tooth} site={site} />
                </div>
              ))}
            </div>
          ))}
        </Row>

        {/* Site labels (bottom side) */}
        <div className="flex items-center h-6 border-t border-border bg-muted/10">
          <div className={LABEL_CLS} />
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {bottomSites.map(site => (
                <div key={site} className={cn(CELL_W, "flex items-center justify-center")}>
                  <span className="text-[10px] text-muted-foreground">{site}</span>
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Bottom probing depths */}
        <Row label={isLower ? "Depth (B)" : "Depth (L)"}>
          {teeth.map((tooth, idx) => (
            <div key={tooth} className={toothGroup(idx)}>
              {bottomSites.map(site => (
                <div key={site} className={CELL_W}>
                  <DepthInput tooth={tooth} site={site} />
                </div>
              ))}
            </div>
          ))}
        </Row>
      </div>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-6">
      {/* Chart metadata */}
      {!readOnly && (
        <div className="flex flex-wrap gap-4 border-b border-border pb-4">
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Date</Label>
            <Input
              type="date"
              value={chartDate}
              onChange={e => setChartDate(e.target.value)}
              className="h-9 w-40"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Provider</Label>
            <Select value={providerId} onValueChange={setProviderId}>
              <SelectTrigger className="h-9 w-52">
                <SelectValue placeholder="Select provider…" />
              </SelectTrigger>
              <SelectContent>
                {(providers ?? []).map(p => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.fullName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Notes</Label>
            <Input
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Optional chart notes"
              className="h-9 w-64"
            />
          </div>
        </div>
      )}

      {readOnly && initialChart && (
        <div className="flex gap-4 border-b border-border pb-2 text-sm text-muted-foreground">
          <span>Date: <strong className="text-foreground">{initialChart.chartDate}</strong></span>
          {initialChart.notes && (
            <span>Notes: <strong className="text-foreground">{initialChart.notes}</strong></span>
          )}
        </div>
      )}

      {/* Color legend */}
      <div className="flex items-center gap-5 text-sm text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <div className="h-3.5 w-3.5 rounded bg-yellow-100 border border-yellow-400" />
          <span>≥4mm</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-3.5 w-3.5 rounded bg-red-100 border border-red-400" />
          <span>≥6mm</span>
        </div>
        <span>B = bleeding · S = suppuration · Mob = mobility · Furc = furcation</span>
      </div>

      {/* Upper arch — two halves */}
      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Upper arch
        </p>
        <div className="rounded-md border border-border overflow-x-auto">
          <div className="p-3">{renderHalf(UPPER_RIGHT, false)}</div>
        </div>
        <div className="rounded-md border border-border overflow-x-auto">
          <div className="p-3">{renderHalf(UPPER_LEFT, false)}</div>
        </div>
      </div>

      {/* Lower arch — two halves */}
      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Lower arch
        </p>
        <div className="rounded-md border border-border overflow-x-auto">
          <div className="p-3">{renderHalf(LOWER_LEFT, true)}</div>
        </div>
        <div className="rounded-md border border-border overflow-x-auto">
          <div className="p-3">{renderHalf(LOWER_RIGHT, true)}</div>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Footer actions */}
      <div className="flex justify-end gap-2 border-t border-border pt-4">
        <Button variant="outline" onClick={onClose} disabled={isPending}>
          {readOnly ? "Close" : "Cancel"}
        </Button>
        {!readOnly && (
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? "Saving…" : "Save chart"}
          </Button>
        )}
      </div>
    </div>
  );
}
