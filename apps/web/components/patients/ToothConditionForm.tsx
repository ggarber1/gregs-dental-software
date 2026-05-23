"use client";

import { useState } from "react";
import { useProviders } from "@/lib/api/scheduling";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  useAddToothCondition,
  type ConditionType,
  type ToothConditionStatus,
  type ToothSurface,
} from "@/lib/api/tooth-chart";
import { centerSurfaceCode, isAnteriorTooth } from "./ToothChartCard";

const CONDITION_TYPE_LABELS: Record<ConditionType, string> = {
  existing_restoration: "Existing restoration",
  missing: "Missing / extracted",
  implant: "Implant",
  crown: "Crown",
  bridge_pontic: "Bridge pontic",
  bridge_abutment: "Bridge abutment",
  root_canal: "Root canal",
  decay: "Decay",
  fracture: "Fracture",
  watch: "Watch",
  other: "Other",
};

const STATUS_LABELS: Record<ToothConditionStatus, string> = {
  existing: "Existing",
  treatment_planned: "Treatment planned",
  completed_today: "Completed today",
};

// Condition types that have meaningful material choices
const MATERIAL_CONDITION_TYPES: ConditionType[] = [
  "existing_restoration",
  "crown",
  "bridge_pontic",
  "bridge_abutment",
  "implant",
];

interface ToothConditionFormProps {
  patientId: string;
  toothNumber: string;
  open: boolean;
  onClose: () => void;
}

// Surfaces that don't apply to whole-tooth conditions like crowns or extractions.
const WHOLE_TOOTH_CONDITION_TYPES: ConditionType[] = [
  "missing",
  "implant",
  "crown",
  "bridge_pontic",
  "bridge_abutment",
];

const SURFACE_LABEL_LONG: Record<ToothSurface, string> = {
  B: "Buccal",
  M: "Mesial",
  O: "Occlusal",
  D: "Distal",
  L: "Lingual",
  I: "Incisal",
};

// Clickable 5-cell cross showing B/M/{O|I}/D/L. The center cell label is
// "I" for anterior teeth (6-11, 22-27), otherwise "O".
function SurfaceSelector({
  toothNumber,
  selected,
  onToggle,
}: {
  toothNumber: string;
  selected: ToothSurface[];
  onToggle: (s: ToothSurface) => void;
}) {
  const center = centerSurfaceCode(toothNumber);
  const cellBase =
    "flex items-center justify-center text-xs font-semibold border border-gray-300 select-none";
  const cellSize = "w-10 h-10";

  function cellClass(s: ToothSurface) {
    const isOn = selected.includes(s);
    return `${cellBase} ${cellSize} ${
      isOn
        ? "bg-primary text-primary-foreground"
        : "bg-background text-foreground hover:bg-muted"
    }`;
  }

  return (
    <div className="grid w-fit grid-cols-3 grid-rows-3 gap-0.5">
      <div className={`${cellSize}`} />
      <button
        type="button"
        data-testid="surface-selector-B"
        aria-pressed={selected.includes("B")}
        onClick={() => onToggle("B")}
        className={cellClass("B")}
      >
        B
      </button>
      <div className={`${cellSize}`} />

      <button
        type="button"
        data-testid="surface-selector-M"
        aria-pressed={selected.includes("M")}
        onClick={() => onToggle("M")}
        className={cellClass("M")}
      >
        M
      </button>
      <button
        type="button"
        data-testid={`surface-selector-${center}`}
        aria-pressed={selected.includes(center)}
        onClick={() => onToggle(center)}
        className={cellClass(center)}
      >
        {center}
      </button>
      <button
        type="button"
        data-testid="surface-selector-D"
        aria-pressed={selected.includes("D")}
        onClick={() => onToggle("D")}
        className={cellClass("D")}
      >
        D
      </button>

      <div className={`${cellSize}`} />
      <button
        type="button"
        data-testid="surface-selector-L"
        aria-pressed={selected.includes("L")}
        onClick={() => onToggle("L")}
        className={cellClass("L")}
      >
        L
      </button>
      <div className={`${cellSize}`} />
    </div>
  );
}

export function ToothConditionForm({
  patientId,
  toothNumber,
  open,
  onClose,
}: ToothConditionFormProps) {
  const [conditionType, setConditionType] = useState<ConditionType>("existing_restoration");
  const [surfaces, setSurfaces] = useState<ToothSurface[]>([]);
  const [material, setMaterial] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<ToothConditionStatus>("existing");
  const [providerId, setProviderId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: providers } = useProviders();
  const { mutate, isPending } = useAddToothCondition(patientId);

  const showMaterial = MATERIAL_CONDITION_TYPES.includes(conditionType);
  const isWholeTooth = WHOLE_TOOTH_CONDITION_TYPES.includes(conditionType);
  const anterior = isAnteriorTooth(toothNumber);

  function toggleSurface(s: ToothSurface) {
    setSurfaces((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    );
  }

  function handleSubmit() {
    if (!providerId.trim()) {
      setError("Provider ID is required.");
      return;
    }
    setError(null);
    const effectiveSurfaces = isWholeTooth ? [] : surfaces;
    mutate(
      {
        toothNumber,
        conditionType,
        status,
        recordedAt: new Date().toISOString().slice(0, 10),
        recordedBy: providerId.trim(),
        ...(effectiveSurfaces.length > 0 && { surfaces: effectiveSurfaces }),
        ...(showMaterial && material.trim() && { material: material.trim() }),
        ...(notes.trim() && { notes: notes.trim() }),
      },
      {
        onSuccess: () => {
          setSurfaces([]);
          setMaterial("");
          setNotes("");
          setConditionType("existing_restoration");
          setStatus("existing");
          setProviderId("");
          onClose();
        },
        onError: () => setError("Failed to save condition. Please try again."),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add condition — Tooth {toothNumber}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Condition type</Label>
            <Select
              value={conditionType}
              onValueChange={(v) => setConditionType(v as ConditionType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(CONDITION_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Status</Label>
            <Select
              value={status}
              onValueChange={(v) => setStatus(v as ToothConditionStatus)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {!isWholeTooth && (
            <div className="flex flex-col gap-2">
              <Label className="text-xs text-muted-foreground">
                Surfaces {anterior ? "(B / M / I / D / L)" : "(B / M / O / D / L)"}
              </Label>
              <SurfaceSelector
                toothNumber={toothNumber}
                selected={surfaces}
                onToggle={toggleSurface}
              />
              {surfaces.length > 0 && (
                <p className="text-[10px] text-muted-foreground">
                  Selected: {surfaces.map((s) => SURFACE_LABEL_LONG[s]).join(", ")}
                </p>
              )}
            </div>
          )}

          {showMaterial && (
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Material</Label>
              <Input
                value={material}
                onChange={(e) => setMaterial(e.target.value)}
                placeholder="composite, amalgam, PFM, zirconia…"
              />
            </div>
          )}

          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Notes</Label>
            <Input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optional"
            />
          </div>

          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Provider *</Label>
            <Select value={providerId} onValueChange={setProviderId}>
              <SelectTrigger>
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                {(providers ?? []).map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.fullName}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? "Saving…" : "Add condition"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
