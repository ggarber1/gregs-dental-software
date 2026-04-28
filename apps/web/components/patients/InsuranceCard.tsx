"use client";

import { useState } from "react";
import { AlertTriangle, Building2, Pencil, Plus, Trash2, X } from "lucide-react";

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
import { useInsurancePlans, type InsurancePlan } from "@/lib/api/insurance-plans";

// ── Insurance form state ──────────────────────────────────────────────────────

interface InsuranceFormState {
  priority: InsurancePriority;
  insurancePlanId: string | null;
  carrier: string; // only used when insurancePlanId is null ("Other")
  memberId: string;
  groupNumber: string;
  relationshipToInsured: RelationshipToInsured;
  insuredFirstName: string;
  insuredLastName: string;
  insuredDateOfBirth: string;
}

const EMPTY_FORM: InsuranceFormState = {
  priority: "primary",
  insurancePlanId: null,
  carrier: "",
  memberId: "",
  groupNumber: "",
  relationshipToInsured: "self",
  insuredFirstName: "",
  insuredLastName: "",
  insuredDateOfBirth: "",
};

const OTHER_PLAN_SENTINEL = "__other__";

function rowToForm(row: Insurance, plans: InsurancePlan[]): InsuranceFormState {
  const matchedPlan = row.insurancePlanId
    ? plans.find((p) => p.id === row.insurancePlanId)
    : plans.find((p) => p.carrierName === row.carrier);
  return {
    priority: row.priority,
    insurancePlanId: matchedPlan?.id ?? null,
    carrier: matchedPlan ? "" : row.carrier,
    memberId: row.memberId ?? "",
    groupNumber: row.groupNumber ?? "",
    relationshipToInsured: row.relationshipToInsured,
    insuredFirstName: row.insuredFirstName ?? "",
    insuredLastName: row.insuredLastName ?? "",
    insuredDateOfBirth: row.insuredDateOfBirth ?? "",
  };
}

function formToBody(form: InsuranceFormState): CreateInsuranceBody {
  const body: CreateInsuranceBody = {
    priority: form.priority,
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
  if (form.insurancePlanId !== null) {
    body.insurancePlanId = form.insurancePlanId;
  } else {
    body.carrier = form.carrier.trim();
  }
  return body;
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface InsuranceFormProps {
  form: InsuranceFormState;
  plans: InsurancePlan[];
  onChange: (next: InsuranceFormState) => void;
  onSave: () => void;
  onCancel: () => void;
  isSaving: boolean;
  error?: string | undefined;
}

function InsuranceForm({
  form,
  plans,
  onChange,
  onSave,
  onCancel,
  isSaving,
  error,
}: InsuranceFormProps) {
  function set<K extends keyof InsuranceFormState>(key: K, value: InsuranceFormState[K]) {
    onChange({ ...form, [key]: value });
  }

  const showInsuredFields = form.relationshipToInsured !== "self";
  const selectedPlanValue = form.insurancePlanId ?? OTHER_PLAN_SENTINEL;

  function handlePlanChange(value: string) {
    if (value === OTHER_PLAN_SENTINEL) {
      onChange({ ...form, insurancePlanId: null });
    } else {
      onChange({ ...form, insurancePlanId: value, carrier: "" });
    }
  }

  const isFormValid =
    form.insurancePlanId !== null || form.carrier.trim().length > 0;

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

      {/* Carrier — from plans catalog */}
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Carrier *</Label>
        <Select value={selectedPlanValue} onValueChange={handlePlanChange}>
          <SelectTrigger className="h-8 text-sm">
            <SelectValue placeholder="Select carrier…" />
          </SelectTrigger>
          <SelectContent>
            {plans.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.carrierName}
                {!p.isInNetwork && (
                  <span className="ml-1 text-xs text-muted-foreground">(out-of-network)</span>
                )}
              </SelectItem>
            ))}
            <SelectItem value={OTHER_PLAN_SENTINEL}>Other (not in catalog)</SelectItem>
          </SelectContent>
        </Select>
        {form.insurancePlanId === null && (
          <Input
            className="mt-1 h-8 text-sm"
            placeholder="Enter carrier name"
            value={form.carrier}
            onChange={(e) => set("carrier", e.target.value)}
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
        <Button size="sm" onClick={onSave} disabled={isSaving || !isFormValid}>
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
  plans: InsurancePlan[];
}

function InsuranceRow({ row, patientId, plans }: InsuranceRowProps) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<InsuranceFormState>(EMPTY_FORM);
  const [saveError, setSaveError] = useState<string | undefined>();

  const updateMutation = useUpdateInsurance(patientId, row.id);
  const deleteMutation = useDeleteInsurance(patientId);

  function startEdit() {
    setForm(rowToForm(row, plans));
    setSaveError(undefined);
    setEditing(true);
  }

  function handleSave() {
    const isOther = form.insurancePlanId === null;
    if (isOther && !form.carrier.trim()) {
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
        plans={plans}
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
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm">{row.carrier}</span>
          <Badge variant={row.priority === "primary" ? "default" : "secondary"} className="text-xs">
            {row.priority}
          </Badge>
          {row.priority === "secondary" && (
            <Badge variant="outline" className="text-xs gap-1 text-amber-600 border-amber-300">
              <AlertTriangle className="h-3 w-3" />
              Manual co-pay review
            </Badge>
          )}
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

  const { data: insuranceList, isLoading: isLoadingInsurance } = usePatientInsurance(patientId);
  const { data: plans = [], isLoading: isLoadingPlans } = useInsurancePlans();
  const createMutation = useCreateInsurance(patientId);

  const isLoading = isLoadingInsurance || isLoadingPlans;

  function handleAdd() {
    const isOther = addForm.insurancePlanId === null;
    if (isOther && !addForm.carrier.trim()) {
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
          <InsuranceRow key={row.id} row={row} patientId={patientId} plans={plans} />
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
              plans={plans}
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
