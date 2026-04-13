"use client";

import { useState } from "react";
import { Building2, Pencil, Plus, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  usePatientInsurance,
  useCreateInsurance,
  useUpdateInsurance,
  useDeleteInsurance,
  type Insurance,
  type CreateInsuranceBody,
  type UpdateInsuranceBody,
  type RelationshipToInsured,
  type InsurancePriority,
} from "@/lib/api/insurance";

// ── Preset carrier list ───────────────────────────────────────────────────────

const PRESET_CARRIERS = [
  "Delta Dental",
  "MassHealth / DentaQuest",
  "Cigna",
  "Aetna",
  "MetLife",
  "Guardian",
  "United Concordia",
  "Humana",
  "Anthem Blue Cross",
  "BlueCross BlueShield",
  "Ameritas",
  "Principal",
  "Other",
];

// ── Insurance form state ──────────────────────────────────────────────────────

interface InsuranceFormState {
  priority: InsurancePriority;
  carrier: string;
  carrierOther: string;
  memberId: string;
  groupNumber: string;
  relationshipToInsured: RelationshipToInsured;
  insuredFirstName: string;
  insuredLastName: string;
  insuredDateOfBirth: string;
}

const EMPTY_FORM: InsuranceFormState = {
  priority: "primary",
  carrier: "",
  carrierOther: "",
  memberId: "",
  groupNumber: "",
  relationshipToInsured: "self",
  insuredFirstName: "",
  insuredLastName: "",
  insuredDateOfBirth: "",
};

function rowToForm(row: Insurance): InsuranceFormState {
  const isPreset = PRESET_CARRIERS.includes(row.carrier);
  return {
    priority: row.priority,
    carrier: isPreset ? row.carrier : "Other",
    carrierOther: isPreset ? "" : row.carrier,
    memberId: row.memberId ?? "",
    groupNumber: row.groupNumber ?? "",
    relationshipToInsured: row.relationshipToInsured,
    insuredFirstName: row.insuredFirstName ?? "",
    insuredLastName: row.insuredLastName ?? "",
    insuredDateOfBirth: row.insuredDateOfBirth ?? "",
  };
}

function formToBody(form: InsuranceFormState): CreateInsuranceBody {
  const carrier = form.carrier === "Other" ? form.carrierOther.trim() : form.carrier;
  return {
    priority: form.priority,
    carrier,
    memberId: form.memberId || null,
    groupNumber: form.groupNumber || null,
    relationshipToInsured: form.relationshipToInsured,
    insuredFirstName:
      form.relationshipToInsured !== "self" ? form.insuredFirstName || null : null,
    insuredLastName:
      form.relationshipToInsured !== "self" ? form.insuredLastName || null : null,
    insuredDateOfBirth:
      form.relationshipToInsured !== "self" ? form.insuredDateOfBirth || null : null,
  };
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface InsuranceFormProps {
  form: InsuranceFormState;
  onChange: (next: InsuranceFormState) => void;
  onSave: () => void;
  onCancel: () => void;
  isSaving: boolean;
  error?: string;
}

function InsuranceForm({ form, onChange, onSave, onCancel, isSaving, error }: InsuranceFormProps) {
  function set<K extends keyof InsuranceFormState>(key: K, value: InsuranceFormState[K]) {
    onChange({ ...form, [key]: value });
  }

  const showInsuredFields = form.relationshipToInsured !== "self";

  return (
    <div className="space-y-3 pt-2">
      {/* Priority */}
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Priority</Label>
        <Select
          value={form.priority}
          onValueChange={(v) => set("priority", v as InsurancePriority)}
        >
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="primary">Primary</SelectItem>
            <SelectItem value="secondary">Secondary</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Carrier */}
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Carrier *</Label>
        <Select value={form.carrier} onValueChange={(v) => set("carrier", v)}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue placeholder="Select carrier…" />
          </SelectTrigger>
          <SelectContent>
            {PRESET_CARRIERS.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {form.carrier === "Other" && (
          <Input
            className="mt-1 h-8 text-sm"
            placeholder="Enter carrier name"
            value={form.carrierOther}
            onChange={(e) => set("carrierOther", e.target.value)}
          />
        )}
      </div>

      {/* Member ID + Group */}
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Member ID</Label>
          <Input
            className="h-8 text-sm"
            value={form.memberId}
            onChange={(e) => set("memberId", e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Group number</Label>
          <Input
            className="h-8 text-sm"
            value={form.groupNumber}
            onChange={(e) => set("groupNumber", e.target.value)}
          />
        </div>
      </div>

      {/* Relationship */}
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Relationship to insured</Label>
        <Select
          value={form.relationshipToInsured}
          onValueChange={(v) => set("relationshipToInsured", v as RelationshipToInsured)}
        >
          <SelectTrigger className="h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="self">Self</SelectItem>
            <SelectItem value="spouse">Spouse</SelectItem>
            <SelectItem value="child">Child</SelectItem>
            <SelectItem value="other">Other</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Insured details — only when not self */}
      {showInsuredFields && (
        <div className="space-y-3 rounded-md border p-3">
          <p className="text-xs font-medium text-muted-foreground">Insured party details</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">First name</Label>
              <Input
                className="h-8 text-sm"
                value={form.insuredFirstName}
                onChange={(e) => set("insuredFirstName", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Last name</Label>
              <Input
                className="h-8 text-sm"
                value={form.insuredLastName}
                onChange={(e) => set("insuredLastName", e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Date of birth</Label>
            <Input
              type="date"
              className="h-8 text-sm"
              value={form.insuredDateOfBirth}
              onChange={(e) => set("insuredDateOfBirth", e.target.value)}
            />
          </div>
        </div>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex gap-2">
        <Button size="sm" onClick={onSave} disabled={isSaving || !form.carrier}>
          {isSaving ? "Saving…" : "Save"}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={isSaving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ── Row view ──────────────────────────────────────────────────────────────────

interface InsuranceRowProps {
  row: Insurance;
  patientId: string;
}

function InsuranceRow({ row, patientId }: InsuranceRowProps) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<InsuranceFormState>(EMPTY_FORM);
  const [saveError, setSaveError] = useState<string | undefined>();

  const updateMutation = useUpdateInsurance(patientId, row.id);
  const deleteMutation = useDeleteInsurance(patientId);

  function startEdit() {
    setForm(rowToForm(row));
    setSaveError(undefined);
    setEditing(true);
  }

  function handleSave() {
    const effectiveCarrier =
      form.carrier === "Other" ? form.carrierOther.trim() : form.carrier;
    if (!effectiveCarrier) {
      setSaveError("Carrier is required");
      return;
    }
    const body: UpdateInsuranceBody = formToBody(form);
    updateMutation.mutate(body, {
      onSuccess: () => setEditing(false),
      onError: (err) => setSaveError(err.message),
    });
  }

  if (editing) {
    return (
      <InsuranceForm
        form={form}
        onChange={setForm}
        onSave={handleSave}
        onCancel={() => setEditing(false)}
        isSaving={updateMutation.isPending}
        error={saveError}
      />
    );
  }

  const holderName =
    row.relationshipToInsured !== "self" && (row.insuredFirstName || row.insuredLastName)
      ? `${row.insuredFirstName ?? ""} ${row.insuredLastName ?? ""}`.trim()
      : null;

  return (
    <div className="flex items-start justify-between gap-2 rounded-md border p-3">
      <div className="flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">{row.carrier}</span>
          <Badge variant={row.priority === "primary" ? "default" : "secondary"} className="text-xs">
            {row.priority}
          </Badge>
        </div>
        {row.memberId && (
          <p className="text-xs text-muted-foreground">Member ID: {row.memberId}</p>
        )}
        {row.groupNumber && (
          <p className="text-xs text-muted-foreground">Group: {row.groupNumber}</p>
        )}
        {row.relationshipToInsured !== "self" && (
          <p className="text-xs text-muted-foreground capitalize">
            Insured: {holderName ?? row.relationshipToInsured}
          </p>
        )}
      </div>
      <div className="flex gap-1 shrink-0">
        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={startEdit}>
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7 text-destructive hover:text-destructive"
          onClick={() => deleteMutation.mutate(row.id)}
          disabled={deleteMutation.isPending}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

// ── Main card ─────────────────────────────────────────────────────────────────

interface Props {
  patientId: string;
}

export function InsuranceCard({ patientId }: Props) {
  const [adding, setAdding] = useState(false);
  const [addForm, setAddForm] = useState<InsuranceFormState>(EMPTY_FORM);
  const [addError, setAddError] = useState<string | undefined>();

  const { data: insuranceList, isLoading } = usePatientInsurance(patientId);
  const createMutation = useCreateInsurance(patientId);

  function handleAdd() {
    const effectiveCarrier =
      addForm.carrier === "Other" ? addForm.carrierOther.trim() : addForm.carrier;
    if (!effectiveCarrier) {
      setAddError("Carrier is required");
      return;
    }
    const body = formToBody(addForm);
    createMutation.mutate(body, {
      onSuccess: () => {
        setAdding(false);
        setAddForm(EMPTY_FORM);
        setAddError(undefined);
      },
      onError: (err) => setAddError(err.message),
    });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Building2 className="h-4 w-4" />
          Insurance
        </CardTitle>
        {!adding && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 text-xs"
            onClick={() => {
              setAddForm(EMPTY_FORM);
              setAddError(undefined);
              setAdding(true);
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            Add
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

        {!isLoading && insuranceList?.length === 0 && !adding && (
          <p className="text-sm text-muted-foreground">No insurance on file.</p>
        )}

        {insuranceList?.map((row) => (
          <InsuranceRow key={row.id} row={row} patientId={patientId} />
        ))}

        {adding && (
          <div className="rounded-md border p-3">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-medium">New insurance</p>
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6"
                onClick={() => setAdding(false)}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
            <InsuranceForm
              form={addForm}
              onChange={setAddForm}
              onSave={handleAdd}
              onCancel={() => setAdding(false)}
              isSaving={createMutation.isPending}
              error={addError}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
