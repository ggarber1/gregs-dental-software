"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateMedicalHistoryVersion,
  type MedicalHistoryVersion,
  type AllergyEntry,
  type MedicationEntry,
  type ConditionEntry,
} from "@/lib/api/medical-history";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  patientId: string;
  open: boolean;
  onClose: () => void;
  currentVersion?: MedicalHistoryVersion;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function blankAllergy(): AllergyEntry {
  return { name: "" };
}

function blankMedication(): MedicationEntry {
  return { name: "" };
}

function blankCondition(): ConditionEntry {
  return { name: "" };
}

// ── Row components ────────────────────────────────────────────────────────────

function AllergyRow({
  entry,
  onChange,
  onRemove,
}: {
  entry: AllergyEntry;
  onChange: (e: AllergyEntry) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-start gap-2">
      <div className="grid flex-1 grid-cols-3 gap-2">
        <Input
          placeholder="Name *"
          value={entry.name}
          onChange={(e) => onChange({ ...entry, name: e.target.value })}
        />
        <Input
          placeholder="Severity"
          value={entry.severity ?? ""}
          onChange={(e) => onChange({ ...entry, severity: e.target.value || undefined })}
        />
        <Input
          placeholder="Reaction"
          value={entry.reaction ?? ""}
          onChange={(e) => onChange({ ...entry, reaction: e.target.value || undefined })}
        />
      </div>
      <Button type="button" variant="ghost" size="sm" onClick={onRemove}>
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

function MedicationRow({
  entry,
  onChange,
  onRemove,
}: {
  entry: MedicationEntry;
  onChange: (e: MedicationEntry) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-start gap-2">
      <div className="grid flex-1 grid-cols-3 gap-2">
        <Input
          placeholder="Name *"
          value={entry.name}
          onChange={(e) => onChange({ ...entry, name: e.target.value })}
        />
        <Input
          placeholder="Dose"
          value={entry.dose ?? ""}
          onChange={(e) => onChange({ ...entry, dose: e.target.value || undefined })}
        />
        <Input
          placeholder="Frequency"
          value={entry.frequency ?? ""}
          onChange={(e) => onChange({ ...entry, frequency: e.target.value || undefined })}
        />
      </div>
      <Button type="button" variant="ghost" size="sm" onClick={onRemove}>
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

function ConditionRow({
  entry,
  onChange,
  onRemove,
}: {
  entry: ConditionEntry;
  onChange: (e: ConditionEntry) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-start gap-2">
      <div className="grid flex-1 grid-cols-3 gap-2">
        <Input
          placeholder="Name *"
          value={entry.name}
          onChange={(e) => onChange({ ...entry, name: e.target.value })}
        />
        <Input
          placeholder="ICD-10 hint"
          value={entry.icd10Hint ?? ""}
          onChange={(e) => onChange({ ...entry, icd10Hint: e.target.value || undefined })}
        />
        <Input
          placeholder="Notes"
          value={entry.notes ?? ""}
          onChange={(e) => onChange({ ...entry, notes: e.target.value || undefined })}
        />
      </div>
      <Button type="button" variant="ghost" size="sm" onClick={onRemove}>
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{children}</p>;
}

function ColumnHeaders({ cols }: { cols: string[] }) {
  return (
    <div className={`grid grid-cols-${cols.length} gap-2 pr-10`}>
      {cols.map((c) => (
        <span key={c} className="text-xs text-muted-foreground">
          {c}
        </span>
      ))}
    </div>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────────

export function MedicalHistoryModal({ patientId, open, onClose, currentVersion }: Props) {
  const [allergies, setAllergies] = useState<AllergyEntry[]>(
    () => currentVersion?.allergies ?? [],
  );
  const [medications, setMedications] = useState<MedicationEntry[]>(
    () => currentVersion?.medications ?? [],
  );
  const [conditions, setConditions] = useState<ConditionEntry[]>(
    () => currentVersion?.conditions ?? [],
  );
  const [flagBloodThinners, setFlagBloodThinners] = useState(
    () => currentVersion?.flags.flagBloodThinners ?? false,
  );
  const [flagBisphosphonates, setFlagBisphosphonates] = useState(
    () => currentVersion?.flags.flagBisphosphonates ?? false,
  );
  const [flagHeartCondition, setFlagHeartCondition] = useState(
    () => currentVersion?.flags.flagHeartCondition ?? false,
  );
  const [flagDiabetes, setFlagDiabetes] = useState(
    () => currentVersion?.flags.flagDiabetes ?? false,
  );
  const [flagPacemaker, setFlagPacemaker] = useState(
    () => currentVersion?.flags.flagPacemaker ?? false,
  );
  const [flagLatexAllergy, setFlagLatexAllergy] = useState(
    () => currentVersion?.flags.flagLatexAllergy ?? false,
  );
  const [additionalNotes, setAdditionalNotes] = useState(
    () => currentVersion?.additionalNotes ?? "",
  );
  const [error, setError] = useState<string | null>(null);

  const { mutate, isPending } = useCreateMedicalHistoryVersion(patientId);

  function handleSubmit() {
    const validAllergies = allergies.filter((a) => a.name.trim());
    const validMedications = medications.filter((m) => m.name.trim());
    const validConditions = conditions.filter((c) => c.name.trim());

    mutate(
      {
        allergies: validAllergies,
        medications: validMedications,
        conditions: validConditions,
        flags: {
          flagBloodThinners,
          flagBisphosphonates,
          flagHeartCondition,
          flagDiabetes,
          flagPacemaker,
          flagLatexAllergy,
        },
        ...(additionalNotes.trim() ? { additionalNotes: additionalNotes.trim() } : {}),
      },
      {
        onSuccess: () => {
          setError(null);
          onClose();
        },
        onError: () => setError("Failed to save. Please try again."),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {currentVersion ? "Update Medical History" : "Record Medical History"}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-6">
          {/* Allergies */}
          <div className="flex flex-col gap-2">
            <SectionLabel>Allergies</SectionLabel>
            <ColumnHeaders cols={["Name", "Severity", "Reaction"]} />
            {allergies.map((a, i) => (
              <AllergyRow
                key={i}
                entry={a}
                onChange={(e) => setAllergies((prev) => prev.map((x, j) => (j === i ? e : x)))}
                onRemove={() => setAllergies((prev) => prev.filter((_, j) => j !== i))}
              />
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-fit"
              onClick={() => setAllergies((prev) => [...prev, blankAllergy()])}
            >
              <Plus className="h-3 w-3" />
              Add allergy
            </Button>
          </div>

          {/* Medications */}
          <div className="flex flex-col gap-2">
            <SectionLabel>Medications</SectionLabel>
            <ColumnHeaders cols={["Name", "Dose", "Frequency"]} />
            {medications.map((m, i) => (
              <MedicationRow
                key={i}
                entry={m}
                onChange={(e) => setMedications((prev) => prev.map((x, j) => (j === i ? e : x)))}
                onRemove={() => setMedications((prev) => prev.filter((_, j) => j !== i))}
              />
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-fit"
              onClick={() => setMedications((prev) => [...prev, blankMedication()])}
            >
              <Plus className="h-3 w-3" />
              Add medication
            </Button>
          </div>

          {/* Conditions */}
          <div className="flex flex-col gap-2">
            <SectionLabel>Conditions</SectionLabel>
            <ColumnHeaders cols={["Name", "ICD-10 Hint", "Notes"]} />
            {conditions.map((c, i) => (
              <ConditionRow
                key={i}
                entry={c}
                onChange={(e) => setConditions((prev) => prev.map((x, j) => (j === i ? e : x)))}
                onRemove={() => setConditions((prev) => prev.filter((_, j) => j !== i))}
              />
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-fit"
              onClick={() => setConditions((prev) => [...prev, blankCondition()])}
            >
              <Plus className="h-3 w-3" />
              Add condition
            </Button>
          </div>

          {/* Clinical flags */}
          <div className="flex flex-col gap-2">
            <SectionLabel>Clinical flags</SectionLabel>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[
                { id: "bt", label: "Blood thinner risk", checked: flagBloodThinners, set: setFlagBloodThinners },
                { id: "bp", label: "Bisphosphonate therapy", checked: flagBisphosphonates, set: setFlagBisphosphonates },
                { id: "hc", label: "Heart condition", checked: flagHeartCondition, set: setFlagHeartCondition },
                { id: "db", label: "Diabetes", checked: flagDiabetes, set: setFlagDiabetes },
                { id: "pm", label: "Pacemaker / ICD", checked: flagPacemaker, set: setFlagPacemaker },
                { id: "la", label: "Latex allergy", checked: flagLatexAllergy, set: setFlagLatexAllergy },
              ].map(({ id, label, checked, set }) => (
                <div key={id} className="flex items-center gap-2">
                  <input
                    id={`flag-${id}`}
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => set(e.target.checked)}
                    className="h-4 w-4 rounded border-input"
                  />
                  <Label htmlFor={`flag-${id}`} className="cursor-pointer text-sm">
                    {label}
                  </Label>
                </div>
              ))}
            </div>
          </div>

          {/* Additional notes */}
          <div className="flex flex-col gap-2">
            <SectionLabel>Additional notes</SectionLabel>
            <Textarea
              value={additionalNotes}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setAdditionalNotes(e.target.value)}
              placeholder="Clinical notes relevant to this visit or update…"
              rows={3}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={isPending}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={isPending}>
              {isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
