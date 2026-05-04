"use client";

import { useMemo, useState } from "react";
import { Printer, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useToothChart,
  useDeleteToothCondition,
  type ToothCondition,
  type ConditionType,
  type NotationSystem,
} from "@/lib/api/tooth-chart";
import { ToothConditionForm } from "./ToothConditionForm";

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

function getToothColorClass(conditions: ToothCondition[]): string {
  if (conditions.length === 0) return "bg-gray-50 text-gray-400";
  // Status overrides take priority (status is per condition, check any)
  if (conditions.some((c) => c.status === "completed_today")) {
    return "bg-green-400 text-green-900";
  }
  if (conditions.some((c) => c.status === "treatment_planned")) {
    return "bg-orange-200 text-orange-800";
  }
  // Fall back to condition type priority
  for (const type of CONDITION_PRIORITY) {
    if (conditions.some((c) => c.conditionType === type)) {
      return CONDITION_COLORS[type];
    }
  }
  return CONDITION_COLORS[conditions[0]?.conditionType ?? "other"];
}

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

// ── ToothButton ───────────────────────────────────────────────────────────────

interface ToothButtonProps {
  toothNumber: string;
  conditions: ToothCondition[];
  notation: NotationSystem;
  isUpper: boolean;
  isSelected: boolean;
  onClick: () => void;
}

function ToothButton({
  toothNumber,
  conditions,
  notation,
  isUpper,
  isSelected,
  onClick,
}: ToothButtonProps) {
  const numericTooth = parseInt(toothNumber, 10);
  const displayLabel = isNaN(numericTooth)
    ? toothNumber
    : toothLabel(numericTooth, notation);

  const colorClass = getToothColorClass(conditions);
  const primaryType = primaryConditionType(conditions);
  const hasMultiple = conditions.length > 1;

  return (
    <button
      onClick={onClick}
      title={`Tooth ${displayLabel}${conditions.length > 0 ? `: ${conditions.map((c) => CONDITION_LABELS[c.conditionType]).join(", ")}` : ""}`}
      className={`relative flex flex-col items-center gap-0.5 rounded border transition-all focus:outline-none focus:ring-2 focus:ring-primary
        ${isSelected ? "ring-2 ring-primary" : "hover:opacity-80"}
      `}
    >
      {/* Tooth number — above for upper, below for lower */}
      {isUpper && (
        <span className="text-[9px] text-muted-foreground leading-none pt-0.5">
          {displayLabel}
        </span>
      )}

      {/* Tooth body */}
      <div
        className={`w-7 h-8 rounded-sm flex items-center justify-center text-[8px] font-bold ${colorClass} border border-gray-300`}
      >
        {primaryType === "missing" && "×"}
        {hasMultiple && primaryType !== "missing" && (
          <span className="absolute -top-1 -right-1 flex h-3 w-3 items-center justify-center rounded-full bg-primary text-[7px] text-primary-foreground">
            {conditions.length}
          </span>
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

// ── ConditionPanel ────────────────────────────────────────────────────────────

interface ConditionPanelProps {
  toothNumber: string;
  conditions: ToothCondition[];
  patientId: string;
  readOnly: boolean;
  onAddClick: () => void;
}

function ConditionPanel({
  toothNumber,
  conditions,
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
                {c.surface && <span className="text-muted-foreground">surfaces: {c.surface}</span>}
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
    </div>
  );
}

// ── ToothChartCard ────────────────────────────────────────────────────────────

interface ToothChartCardProps {
  patientId: string;
}

export function ToothChartCard({ patientId }: ToothChartCardProps) {
  const [notation, setNotation] = useState<NotationSystem>("universal");
  const [isPrimary, setIsPrimary] = useState(false);
  const [asOfDate, setAsOfDate] = useState("");
  const [selectedTooth, setSelectedTooth] = useState<string | null>(null);
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
                        notation={notation}
                        isUpper={true}
                        isSelected={selectedTooth === t}
                        onClick={() =>
                          setSelectedTooth((prev) => (prev === t ? null : t))
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
                        notation={notation}
                        isUpper={false}
                        isSelected={selectedTooth === t}
                        onClick={() =>
                          setSelectedTooth((prev) => (prev === t ? null : t))
                        }
                      />
                    ))}
                  </div>
                </div>
              </div>

              <ChartLegend />

              {/* Selected tooth detail */}
              {selectedTooth && (
                <div className="mt-3 print:hidden">
                  <ConditionPanel
                    toothNumber={selectedTooth}
                    conditions={selectedConditions}
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
