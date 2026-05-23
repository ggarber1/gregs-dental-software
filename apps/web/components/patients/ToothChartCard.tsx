"use client";

import { useMemo, useState } from "react";
import { Printer, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  useToothChart,
  useDeleteToothCondition,
  type ToothCondition,
  type ConditionType,
  type NotationSystem,
  type ToothSurface,
} from "@/lib/api/tooth-chart";
import type { TreatmentPlanItem } from "@/lib/api/treatment-plans";
import { ToothConditionForm } from "./ToothConditionForm";
import { highestUrgency, urgencyBadgeColor } from "./toothChartHelpers";

export { hasTreatmentPlannedItem } from "./toothChartHelpers";

// ── Constants ─────────────────────────────────────────────────────────────────

// Universal numbering, display order left-to-right (patient right = viewer left)
const UPPER_TEETH = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16];
const LOWER_TEETH = [32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17];
const DECIDUOUS_UPPER = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"];
const DECIDUOUS_LOWER = ["T", "S", "R", "Q", "P", "O", "N", "M", "L", "K"];

// FDI equivalents for universal 1-32
const UNIVERSAL_TO_FDI: Record<number, string> = {
  1: "18", 2: "17", 3: "16", 4: "15", 5: "14", 6: "13", 7: "12", 8: "11",
  9: "21", 10: "22", 11: "23", 12: "24", 13: "25", 14: "26", 15: "27", 16: "28",
  17: "38", 18: "37", 19: "36", 20: "35", 21: "34", 22: "33", 23: "32", 24: "31",
  25: "41", 26: "42", 27: "43", 28: "44", 29: "45", 30: "46", 31: "47", 32: "48",
};

// Priority order for coloring when a tooth has multiple conditions (type only)
const CONDITION_PRIORITY: ConditionType[] = [
  "missing",
  "implant",
  "crown",
  "bridge_abutment",
  "bridge_pontic",
  "root_canal",
  "decay",
  "fracture",
  "existing_restoration",
  "watch",
  "other",
];

const CONDITION_COLORS: Record<ConditionType, string> = {
  missing: "bg-gray-400 text-gray-700",
  implant: "bg-yellow-300 text-yellow-800",
  crown: "bg-green-200 text-green-800",
  bridge_abutment: "bg-green-200 text-green-800",
  bridge_pontic: "bg-green-100 text-green-700",
  root_canal: "bg-purple-200 text-purple-800",
  decay: "bg-red-300 text-red-900",
  fracture: "bg-orange-300 text-orange-900",
  existing_restoration: "bg-blue-200 text-blue-800",
  watch: "bg-red-100 text-red-700",
  other: "bg-gray-200 text-gray-600",
};

const CONDITION_LABELS: Record<ConditionType, string> = {
  missing: "Missing",
  implant: "Implant",
  crown: "Crown",
  bridge_abutment: "Bridge abutment",
  bridge_pontic: "Bridge pontic",
  root_canal: "Root canal",
  decay: "Decay",
  fracture: "Fracture",
  existing_restoration: "Restoration",
  watch: "Watch",
  other: "Other",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function primaryConditionType(conditions: ToothCondition[]): ConditionType | null {
  if (conditions.length === 0) return null;
  for (const type of CONDITION_PRIORITY) {
    if (conditions.some((c) => c.conditionType === type)) return type;
  }
  return conditions[0]?.conditionType ?? null;
}

function toothLabel(toothNum: number, notation: NotationSystem): string {
  return notation === "fdi" ? (UNIVERSAL_TO_FDI[toothNum] ?? String(toothNum)) : String(toothNum);
}

// ── Hover-card helpers (exported for unit tests) ──────────────────────────────

// Suppressed when the tooth is the currently-selected one (the detail panel
// takes over) or when no tooth is hovered.
export function shouldShowHoverCard(
  hoveredTooth: string | null,
  selectedTooth: string | null,
  toothNumber: string,
): boolean {
  if (hoveredTooth !== toothNumber) return false;
  if (selectedTooth === toothNumber) return false;
  return true;
}

export function formatHoverConditionLine(condition: ToothCondition): string {
  const label = CONDITION_LABELS[condition.conditionType];
  return condition.surface ? `${label} (${condition.surface})` : label;
}

// ── Surface helpers (exported for testing) ────────────────────────────────────

// Anterior teeth (incisors + canines) — universal numbering 6-11 (upper) and
// 22-27 (lower). These present an incisal edge (I) instead of an occlusal
// surface (O). Anything else is treated as a posterior.
const ANTERIOR_UNIVERSAL: ReadonlySet<number> = new Set([
  6, 7, 8, 9, 10, 11, 22, 23, 24, 25, 26, 27,
]);

export function isAnteriorTooth(toothNumber: string): boolean {
  const n = parseInt(toothNumber, 10);
  if (isNaN(n)) return false;
  return ANTERIOR_UNIVERSAL.has(n);
}

export function centerSurfaceCode(toothNumber: string): "O" | "I" {
  return isAnteriorTooth(toothNumber) ? "I" : "O";
}

// The five surface cells displayed inside each tooth button, in the order
// they'll be rendered into the 3×3 grid (top, left, center, right, bottom).
export interface SurfaceCell {
  surface: ToothSurface;
  label: string;
}

export function surfaceCellsForTooth(toothNumber: string): SurfaceCell[] {
  const center = centerSurfaceCode(toothNumber);
  return [
    { surface: "B", label: "B" },
    { surface: "M", label: "M" },
    { surface: center, label: center },
    { surface: "D", label: "D" },
    { surface: "L", label: "L" },
  ];
}

// Conditions with an empty `surfaces` array (e.g. crowns, missing teeth) are
// treated as whole-tooth and fill every cell. Higher-priority conditions win
// per surface.
export function surfaceFillColors(
  conditions: ToothCondition[],
  toothNumber: string,
): Record<ToothSurface, string | null> {
  const center = centerSurfaceCode(toothNumber);
  const allSurfaces: ToothSurface[] = ["B", "M", center, "D", "L"];
  const out: Record<ToothSurface, string | null> = {
    B: null,
    M: null,
    O: null,
    D: null,
    L: null,
    I: null,
  };

  const sorted = [...conditions].sort((a, b) => {
    const ai = CONDITION_PRIORITY.indexOf(a.conditionType);
    const bi = CONDITION_PRIORITY.indexOf(b.conditionType);
    return (ai === -1 ? Infinity : ai) - (bi === -1 ? Infinity : bi);
  });

  for (const cond of sorted) {
    const color = CONDITION_COLORS[cond.conditionType];
    const targets =
      cond.surfaces.length === 0
        ? allSurfaces
        : cond.surfaces.filter((s) => allSurfaces.includes(s));
    for (const s of targets) {
      if (out[s] === null) out[s] = color;
    }
  }

  return out;
}

// ── ToothButton ───────────────────────────────────────────────────────────────

interface ToothButtonProps {
  toothNumber: string;
  conditions: ToothCondition[];
  treatmentItems: TreatmentPlanItem[];
  notation: NotationSystem;
  isUpper: boolean;
  isSelected: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

function ToothButton({
  toothNumber,
  conditions,
  treatmentItems,
  notation,
  isUpper,
  isSelected,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: ToothButtonProps) {
  const numericTooth = parseInt(toothNumber, 10);
  const displayLabel = isNaN(numericTooth)
    ? toothNumber
    : toothLabel(numericTooth, notation);

  const primaryType = primaryConditionType(conditions);
  const hasMultiple = conditions.length > 1;
  const isMissing = primaryType === "missing";
  const hasTreatmentPlan = treatmentItems.length > 0;
  const planUrgency = highestUrgency(treatmentItems);

  // Status overlay (full-tooth tint) for treatment_planned / completed_today
  let statusOverlay = "";
  if (conditions.some((c) => c.status === "completed_today")) {
    statusOverlay = "bg-green-400/30";
  } else if (conditions.some((c) => c.status === "treatment_planned")) {
    statusOverlay = "bg-orange-200/40";
  }

  const fills = surfaceFillColors(conditions, toothNumber);
  const center = centerSurfaceCode(toothNumber);
  const emptyCell = "bg-gray-50";

  const titleParts: string[] = [`Tooth ${displayLabel}`];
  if (conditions.length > 0) {
    titleParts.push(conditions.map((c) => CONDITION_LABELS[c.conditionType]).join(", "));
  }
  if (hasTreatmentPlan && planUrgency) {
    titleParts.push(`${treatmentItems.length} treatment-planned (${planUrgency})`);
  }
  const titleText = titleParts.join(" — ");

  return (
    <button
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onMouseEnter}
      onBlur={onMouseLeave}
      data-testid={`tooth-button-${toothNumber}`}
      data-tooth-number={toothNumber}
      aria-label={titleText}
      className={`relative flex flex-col items-center gap-0.5 rounded border transition-all focus:outline-none focus:ring-2 focus:ring-primary
        ${isSelected ? "ring-2 ring-primary" : "hover:opacity-80"}
      `}
    >
      {isUpper && (
        <span className="text-[9px] text-muted-foreground leading-none pt-0.5">
          {displayLabel}
        </span>
      )}

      {/* Tooth body — surface grid inside overflow-hidden; badges as siblings so they don't clip. */}
      <div className="relative">
        <div
          className={`w-9 h-9 rounded-sm border border-gray-400 overflow-hidden ${statusOverlay}`}
        >
          {isMissing ? (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-300 text-gray-700 text-[10px] font-bold">
              ×
            </div>
          ) : (
            <div className="grid h-full w-full grid-cols-3 grid-rows-3">
              <div className={emptyCell} />
              <div
                data-testid={`surface-${toothNumber}-B`}
                className={`${fills.B ?? emptyCell} flex items-center justify-center text-[6px] font-bold leading-none`}
              >
                B
              </div>
              <div className={emptyCell} />
              <div
                data-testid={`surface-${toothNumber}-M`}
                className={`${fills.M ?? emptyCell} flex items-center justify-center text-[6px] font-bold leading-none`}
              >
                M
              </div>
              <div
                data-testid={`surface-${toothNumber}-${center}`}
                className={`${fills[center] ?? emptyCell} flex items-center justify-center text-[6px] font-bold leading-none`}
              >
                {center}
              </div>
              <div
                data-testid={`surface-${toothNumber}-D`}
                className={`${fills.D ?? emptyCell} flex items-center justify-center text-[6px] font-bold leading-none`}
              >
                D
              </div>
              <div className={emptyCell} />
              <div
                data-testid={`surface-${toothNumber}-L`}
                className={`${fills.L ?? emptyCell} flex items-center justify-center text-[6px] font-bold leading-none`}
              >
                L
              </div>
              <div className={emptyCell} />
            </div>
          )}
        </div>

        {hasMultiple && !isMissing && (
          <span className="absolute -top-1 -right-1 flex h-3 w-3 items-center justify-center rounded-full bg-primary text-[7px] text-primary-foreground">
            {conditions.length}
          </span>
        )}

        {hasTreatmentPlan && planUrgency && (
          <span
            data-testid="treatment-plan-badge"
            data-urgency={planUrgency}
            aria-label={`${treatmentItems.length} planned (${planUrgency})`}
            title={`Treatment planned (${planUrgency})`}
            className={`absolute -bottom-1 -left-1 h-2.5 w-2.5 rotate-45 border border-white ${urgencyBadgeColor(planUrgency)}`}
          />
        )}
      </div>

      {!isUpper && (
        <span className="text-[9px] text-muted-foreground leading-none pb-0.5">
          {displayLabel}
        </span>
      )}
    </button>
  );
}

// ── ToothInspector ────────────────────────────────────────────────────────────

// Inline panel under the chart that shows whatever tooth is currently hovered.
// Rendered outside the chart's overflow-x-auto wrapper so it never gets clipped
// (the earlier per-tooth floating popover was unreliable for that reason).
interface ToothInspectorProps {
  toothLabel: string | null;
  conditions: ToothCondition[];
  treatmentItems: TreatmentPlanItem[];
}

function ToothInspector({ toothLabel, conditions, treatmentItems }: ToothInspectorProps) {
  const planUrgency = highestUrgency(treatmentItems);

  return (
    <div
      role="region"
      aria-label="Tooth inspector"
      data-testid="tooth-inspector"
      className="mt-2 min-h-[68px] rounded-md border bg-muted/30 p-2 print:hidden"
    >
      {!toothLabel ? (
        <p className="text-[11px] text-muted-foreground">
          Hover a tooth to see its details.
        </p>
      ) : (
        <>
          <p className="text-xs font-semibold mb-1">Tooth {toothLabel}</p>
          {conditions.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">No conditions recorded.</p>
          ) : (
            <ul className="space-y-1">
              {conditions.map((c) => (
                <li key={c.id} className="flex items-center gap-1.5 text-[11px]">
                  <span
                    className={`inline-block h-2 w-2 rounded-sm ${CONDITION_COLORS[c.conditionType].split(" ")[0]}`}
                  />
                  <span>{formatHoverConditionLine(c)}</span>
                </li>
              ))}
            </ul>
          )}
          {treatmentItems.length > 0 && planUrgency && (
            <div className="mt-1.5 flex items-center gap-1.5 text-[11px]">
              <span
                className={`inline-block h-2 w-2 rotate-45 ${urgencyBadgeColor(planUrgency)}`}
              />
              <span>
                {treatmentItems.length} planned ({planUrgency})
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── ConditionPanel ────────────────────────────────────────────────────────────

interface ConditionPanelProps {
  toothNumber: string;
  conditions: ToothCondition[];
  treatmentItems: TreatmentPlanItem[];
  patientId: string;
  readOnly: boolean;
  onAddClick: () => void;
}

function ConditionPanel({
  toothNumber,
  conditions,
  treatmentItems,
  patientId,
  readOnly,
  onAddClick,
}: ConditionPanelProps) {
  const { mutate: deleteCondition, isPending: isDeleting } =
    useDeleteToothCondition(patientId);

  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-medium">Tooth {toothNumber}</p>
        {!readOnly && (
          <Button size="sm" variant="outline" onClick={onAddClick}>
            + Add condition
          </Button>
        )}
      </div>

      {conditions.length === 0 ? (
        <p className="text-xs text-muted-foreground">No conditions recorded.</p>
      ) : (
        <ul className="space-y-1.5">
          {conditions.map((c) => (
            <li
              key={c.id}
              className="flex items-center justify-between gap-2 text-xs"
            >
              <div className="flex items-center gap-1.5">
                <span
                  className={`inline-flex rounded px-1.5 py-0.5 font-medium ${CONDITION_COLORS[c.conditionType]}`}
                >
                  {CONDITION_LABELS[c.conditionType]}
                </span>
                {c.surfaces.length > 0 && (
                  <span className="text-muted-foreground">
                    surfaces: {c.surfaces.join("")}
                  </span>
                )}
                {c.surfaces.length === 0 && c.surface && (
                  <span className="text-muted-foreground">surfaces: {c.surface}</span>
                )}
                {c.material && <span className="text-muted-foreground">{c.material}</span>}
              </div>
              {!readOnly && (
                <button
                  onClick={() => deleteCondition(c.id)}
                  disabled={isDeleting}
                  className="text-destructive hover:text-destructive/80 disabled:opacity-50"
                  title="Remove condition"
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {treatmentItems.length > 0 && (
        <div className="mt-3 border-t border-border pt-2">
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">
            Treatment Planned
          </p>
          <ul className="space-y-1">
            {treatmentItems.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-2 text-xs"
              >
                <span className="font-medium">{item.procedureName}</span>
                {item.urgency && (
                  <Badge variant="outline" className="capitalize">
                    {item.urgency}
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Legend ────────────────────────────────────────────────────────────────────

function ChartLegend() {
  const entries: [string, string][] = [
    ["bg-blue-200", "Restoration"],
    ["bg-gray-400", "Missing"],
    ["bg-yellow-300", "Implant"],
    ["bg-green-200", "Crown"],
    ["bg-purple-200", "Root canal"],
    ["bg-red-300", "Decay"],
    ["bg-orange-200", "Tx planned"],
    ["bg-green-400", "Done today"],
  ];
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
      {entries.map(([colorClass, label]) => (
        <div key={label} className="flex items-center gap-1">
          <span className={`inline-block w-3 h-3 rounded-sm ${colorClass}`} />
          <span className="text-[10px] text-muted-foreground">{label}</span>
        </div>
      ))}
      <div className="flex items-center gap-1">
        <span className="inline-block w-2.5 h-2.5 rotate-45 bg-red-600" />
        <span className="text-[10px] text-muted-foreground">Urgent</span>
      </div>
      <div className="flex items-center gap-1">
        <span className="inline-block w-2.5 h-2.5 rotate-45 bg-orange-500" />
        <span className="text-[10px] text-muted-foreground">Soon</span>
      </div>
      <div className="flex items-center gap-1">
        <span className="inline-block w-2.5 h-2.5 rotate-45 bg-gray-400" />
        <span className="text-[10px] text-muted-foreground">Elective</span>
      </div>
    </div>
  );
}

// ── ToothChartCard ────────────────────────────────────────────────────────────

interface ToothChartCardProps {
  patientId: string;
  treatmentItemsByTooth?: Map<string, TreatmentPlanItem[]>;
}

export function ToothChartCard({
  patientId,
  treatmentItemsByTooth,
}: ToothChartCardProps) {
  const [notation, setNotation] = useState<NotationSystem>("universal");
  const [isPrimary, setIsPrimary] = useState(false);
  const [asOfDate, setAsOfDate] = useState("");
  const [selectedTooth, setSelectedTooth] = useState<string | null>(null);
  const [hoveredTooth, setHoveredTooth] = useState<string | null>(null);
  const [addFormOpen, setAddFormOpen] = useState(false);

  const { data, isLoading } = useToothChart(patientId, asOfDate || undefined);

  const conditionsByTooth = useMemo(() => {
    const map = new Map<string, ToothCondition[]>();
    for (const c of data?.conditions ?? []) {
      if (!map.has(c.toothNumber)) map.set(c.toothNumber, []);
      map.get(c.toothNumber)!.push(c);
    }
    return map;
  }, [data]);

  const upperTeeth = isPrimary
    ? DECIDUOUS_UPPER
    : UPPER_TEETH.map(String);
  const lowerTeeth = isPrimary
    ? DECIDUOUS_LOWER
    : LOWER_TEETH.map(String);

  const isHistoryMode = Boolean(asOfDate);
  const readOnly = isHistoryMode;

  const selectedConditions = selectedTooth
    ? (conditionsByTooth.get(selectedTooth) ?? [])
    : [];
  const selectedTreatmentItems = selectedTooth
    ? (treatmentItemsByTooth?.get(selectedTooth) ?? [])
    : [];

  return (
    <>
      <Card className="print:shadow-none">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base font-semibold">Tooth Chart</CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => window.print()}
              title="Print tooth chart"
            >
              <Printer className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Controls */}
          <div className="flex flex-wrap items-center gap-3 mb-3 print:hidden">
            <div className="flex gap-1">
              <Button
                size="sm"
                variant={notation === "universal" ? "default" : "outline"}
                className="h-7 text-xs px-2"
                onClick={() => setNotation("universal")}
              >
                Universal
              </Button>
              <Button
                size="sm"
                variant={notation === "fdi" ? "default" : "outline"}
                className="h-7 text-xs px-2"
                onClick={() => setNotation("fdi")}
              >
                FDI
              </Button>
            </div>
            <div className="flex gap-1">
              <Button
                size="sm"
                variant={!isPrimary ? "default" : "outline"}
                className="h-7 text-xs px-2"
                onClick={() => setIsPrimary(false)}
              >
                Adult
              </Button>
              <Button
                size="sm"
                variant={isPrimary ? "default" : "outline"}
                className="h-7 text-xs px-2"
                onClick={() => setIsPrimary(true)}
              >
                Deciduous
              </Button>
            </div>
            <div className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
              <Label className="text-xs text-muted-foreground sr-only">History date</Label>
              <Input
                type="date"
                value={asOfDate}
                onChange={(e) => {
                  setAsOfDate(e.target.value);
                  setSelectedTooth(null);
                  setHoveredTooth(null);
                }}
                className="h-7 text-xs w-36"
                title="View chart as of date"
              />
              {asOfDate && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs px-1"
                  onClick={() => setAsOfDate("")}
                >
                  ×
                </Button>
              )}
            </div>
          </div>

          {isHistoryMode && (
            <div className="mb-2 flex items-center gap-1.5 rounded bg-amber-50 border border-amber-200 px-2 py-1 print:hidden">
              <Clock className="h-3.5 w-3.5 text-amber-600" />
              <p className="text-xs text-amber-700">
                History view as of {asOfDate} — read only
              </p>
            </div>
          )}

          {isLoading ? (
            <div className="flex justify-center py-8">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : (
            <>
              {/* Chart grid */}
              <div className="overflow-x-auto">
                <div className="min-w-[560px]">
                  {/* Upper arch */}
                  <div className="flex justify-center gap-1 pb-1 border-b border-dashed border-border">
                    {upperTeeth.map((t) => (
                      <ToothButton
                        key={t}
                        toothNumber={t}
                        conditions={conditionsByTooth.get(t) ?? []}
                        treatmentItems={treatmentItemsByTooth?.get(t) ?? []}
                        notation={notation}
                        isUpper={true}
                        isSelected={selectedTooth === t}
                        onClick={() =>
                          setSelectedTooth((prev) => (prev === t ? null : t))
                        }
                        onMouseEnter={() => setHoveredTooth(t)}
                        onMouseLeave={() =>
                          setHoveredTooth((prev) => (prev === t ? null : prev))
                        }
                      />
                    ))}
                  </div>

                  {/* Lower arch */}
                  <div className="flex justify-center gap-1 pt-1">
                    {lowerTeeth.map((t) => (
                      <ToothButton
                        key={t}
                        toothNumber={t}
                        conditions={conditionsByTooth.get(t) ?? []}
                        treatmentItems={treatmentItemsByTooth?.get(t) ?? []}
                        notation={notation}
                        isUpper={false}
                        isSelected={selectedTooth === t}
                        onClick={() =>
                          setSelectedTooth((prev) => (prev === t ? null : t))
                        }
                        onMouseEnter={() => setHoveredTooth(t)}
                        onMouseLeave={() =>
                          setHoveredTooth((prev) => (prev === t ? null : prev))
                        }
                      />
                    ))}
                  </div>
                </div>
              </div>

              <ToothInspector
                toothLabel={
                  hoveredTooth && shouldShowHoverCard(hoveredTooth, selectedTooth, hoveredTooth)
                    ? hoveredTooth
                    : null
                }
                conditions={hoveredTooth ? (conditionsByTooth.get(hoveredTooth) ?? []) : []}
                treatmentItems={
                  hoveredTooth ? (treatmentItemsByTooth?.get(hoveredTooth) ?? []) : []
                }
              />

              <ChartLegend />

              {/* Selected tooth detail */}
              {selectedTooth && (
                <div className="mt-3 print:hidden">
                  <ConditionPanel
                    toothNumber={selectedTooth}
                    conditions={selectedConditions}
                    treatmentItems={selectedTreatmentItems}
                    patientId={patientId}
                    readOnly={readOnly}
                    onAddClick={() => setAddFormOpen(true)}
                  />
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {addFormOpen && selectedTooth && (
        <ToothConditionForm
          patientId={patientId}
          toothNumber={selectedTooth}
          open={addFormOpen}
          onClose={() => setAddFormOpen(false)}
        />
      )}
    </>
  );
}
