"use client";

import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useInsurancePlans,
  useCreateInsurancePlan,
  useUpdateInsurancePlan,
  useDeleteInsurancePlan,
  type InsurancePlan,
  type CreateInsurancePlanBody,
} from "@/lib/api/insurance-plans";

interface FormValues {
  carrierName: string;
  payerId: string;
  groupNumber: string;
  isInNetwork: boolean;
}

const EMPTY: FormValues = {
  carrierName: "",
  payerId: "",
  groupNumber: "",
  isInNetwork: true,
};

function planToForm(plan: InsurancePlan): FormValues {
  return {
    carrierName: plan.carrierName,
    payerId: plan.payerId,
    groupNumber: plan.groupNumber ?? "",
    isInNetwork: plan.isInNetwork,
  };
}

export function InsurancePlansSettings() {
  const { data: plans = [], isLoading } = useInsurancePlans();
  const createMutation = useCreateInsurancePlan();
  const deleteMutation = useDeleteInsurancePlan();

  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<InsurancePlan | null>(null);
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [saveError, setSaveError] = useState<string | undefined>();

  const updateMutation = useUpdateInsurancePlan(editing?.id ?? "");

  function openCreate() {
    setEditing(null);
    setValues(EMPTY);
    setSaveError(undefined);
    setShowModal(true);
  }

  function openEdit(plan: InsurancePlan) {
    setEditing(plan);
    setValues(planToForm(plan));
    setSaveError(undefined);
    setShowModal(true);
  }

  function set<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSave() {
    if (!values.carrierName.trim()) {
      setSaveError("Carrier name is required");
      return;
    }
    if (!values.payerId.trim()) {
      setSaveError("Payer ID is required");
      return;
    }

    const body: CreateInsurancePlanBody = {
      carrierName: values.carrierName.trim(),
      payerId: values.payerId.trim(),
      groupNumber: values.groupNumber.trim() || null,
      isInNetwork: values.isInNetwork,
    };

    if (editing) {
      updateMutation.mutate(body, {
        onSuccess: () => setShowModal(false),
        onError: (err) => setSaveError(err.message),
      });
    } else {
      createMutation.mutate(body, {
        onSuccess: () => setShowModal(false),
        onError: (err) => setSaveError(err.message),
      });
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Manage the insurance carriers accepted by this practice. These appear in the carrier
          picker on patient charts.
        </p>
        <Button size="sm" className="gap-1" onClick={openCreate}>
          <Plus className="h-3.5 w-3.5" />
          Add carrier
        </Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!isLoading && plans.length === 0 && (
        <p className="text-sm text-muted-foreground">No insurance plans configured.</p>
      )}

      {plans.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Carrier</TableHead>
              <TableHead>Payer ID</TableHead>
              <TableHead>Group</TableHead>
              <TableHead>Network</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {plans.map((plan) => (
              <TableRow key={plan.id}>
                <TableCell className="font-medium">{plan.carrierName}</TableCell>
                <TableCell className="font-mono text-xs">{plan.payerId}</TableCell>
                <TableCell>{plan.groupNumber ?? <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell>
                  <Badge
                    variant={plan.isInNetwork ? "default" : "secondary"}
                    className="text-xs"
                  >
                    {plan.isInNetwork ? "In-network" : "Out-of-network"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1 justify-end">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      onClick={() => openEdit(plan)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-destructive hover:text-destructive"
                      onClick={() => deleteMutation.mutate(plan.id)}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={showModal} onOpenChange={setShowModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit carrier" : "Add carrier"}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex flex-col gap-1.5">
              <Label>Carrier name *</Label>
              <Input
                value={values.carrierName}
                onChange={(e) => set("carrierName", e.target.value)}
                placeholder="e.g. Delta Dental"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Payer ID *</Label>
              <Input
                value={values.payerId}
                onChange={(e) => set("payerId", e.target.value)}
                placeholder="e.g. DLTADNTL"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Clearinghouse payer ID used for eligibility and claims routing.
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Group number</Label>
              <Input
                value={values.groupNumber}
                onChange={(e) => set("groupNumber", e.target.value)}
                placeholder="Optional"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Network status</Label>
              <Select
                value={values.isInNetwork ? "in" : "out"}
                onValueChange={(v) => set("isInNetwork", v === "in")}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="in">In-network</SelectItem>
                  <SelectItem value="out">Out-of-network</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {saveError && <p className="text-sm text-destructive">{saveError}</p>}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModal(false)} disabled={isSaving}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
