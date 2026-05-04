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
} from "@/lib/api/tooth-chart";

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

export function ToothConditionForm({
  patientId,
  toothNumber,
  open,
  onClose,
}: ToothConditionFormProps) {
  const [conditionType, setConditionType] = useState<ConditionType>("existing_restoration");
  const [surface, setSurface] = useState("");
  const [material, setMaterial] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<ToothConditionStatus>("existing");
  const [providerId, setProviderId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: providers } = useProviders();
  const { mutate, isPending } = useAddToothCondition(patientId);

  const showMaterial = MATERIAL_CONDITION_TYPES.includes(conditionType);

  function handleSubmit() {
    if (!providerId.trim()) {
      setError("Provider ID is required.");
      return;
    }
    setError(null);
    mutate(
      {
        toothNumber,
        conditionType,
        status,
        recordedAt: new Date().toISOString().slice(0, 10),
        recordedBy: providerId.trim(),
        ...(surface.trim() && { surface: surface.trim() }),
        ...(showMaterial && material.trim() && { material: material.trim() }),
        ...(notes.trim() && { notes: notes.trim() }),
      },
      {
        onSuccess: () => {
          setSurface("");
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

          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">
              Surfaces (e.g. MOD, B, L)
            </Label>
            <Input
              value={surface}
              onChange={(e) => setSurface(e.target.value.toUpperCase())}
              placeholder="Leave blank for whole-tooth"
              maxLength={10}
            />
          </div>

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
