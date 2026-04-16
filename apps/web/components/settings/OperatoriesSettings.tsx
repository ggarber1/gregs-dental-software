"use client";

import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";

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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useOperatories,
  useCreateOperatory,
  useUpdateOperatory,
  useDeleteOperatory,
  type Operatory,
} from "@/lib/api/scheduling";

interface FormValues {
  name: string;
  color: string;
  isActive: boolean;
}

const EMPTY: FormValues = {
  name: "",
  color: "#7BC67E",
  isActive: true,
};

export function OperatoriesSettings() {
  const { data: operatories, isLoading } = useOperatories();
  const createMutation = useCreateOperatory();
  const updateMutation = useUpdateOperatory();
  const deleteMutation = useDeleteOperatory();

  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Operatory | null>(null);
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof FormValues, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!showModal) return;
    if (editing) {
      setValues({ name: editing.name, color: editing.color, isActive: editing.isActive });
    } else {
      setValues(EMPTY);
    }
    setErrors({});
  }, [showModal, editing]);

  function set<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function validate(): boolean {
    const errs: Partial<Record<keyof FormValues, string>> = {};
    if (!values.name.trim()) errs.name = "Required";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSubmit() {
    if (!validate()) return;
    setIsSubmitting(true);
    try {
      const body = { name: values.name.trim(), color: values.color, isActive: values.isActive };
      if (editing) {
        await updateMutation.mutateAsync({ id: editing.id, body });
      } else {
        await createMutation.mutateAsync(body);
      }
      setShowModal(false);
      setEditing(null);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(id: string) {
    await deleteMutation.mutateAsync(id);
  }

  function openCreate() {
    setEditing(null);
    setShowModal(true);
  }

  function openEdit(op: Operatory) {
    setEditing(op);
    setShowModal(true);
  }

  const sorted = [...(operatories ?? [])].sort((a, b) => a.displayOrder - b.displayOrder);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Operatories</h3>
        <Button size="sm" onClick={openCreate}>
          <Plus className="mr-1 h-4 w-4" />
          Add Operatory
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Color</TableHead>
              <TableHead>Active</TableHead>
              <TableHead className="w-24">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            ) : sorted.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  No operatories yet. Add one to get started.
                </TableCell>
              </TableRow>
            ) : (
              sorted.map((o) => (
                <TableRow key={o.id}>
                  <TableCell className="font-medium">{o.name}</TableCell>
                  <TableCell>
                    <span
                      className="inline-block h-5 w-5 rounded border"
                      style={{ backgroundColor: o.color }}
                    />
                  </TableCell>
                  <TableCell>{o.isActive ? "Yes" : "No"}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(o)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => void handleDelete(o.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={showModal} onOpenChange={(open) => { setShowModal(open); if (!open) setEditing(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Operatory" : "Add Operatory"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div>
              <Label htmlFor="op-name">Name</Label>
              <Input
                id="op-name"
                value={values.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="e.g. Operatory 1"
              />
              {errors.name && <p className="mt-1 text-xs text-destructive">{errors.name}</p>}
            </div>
            <div>
              <Label htmlFor="op-color">Calendar Color</Label>
              <div className="flex items-center gap-2">
                <input
                  id="op-color"
                  type="color"
                  value={values.color}
                  onChange={(e) => set("color", e.target.value)}
                  className="h-9 w-12 cursor-pointer rounded border"
                />
                <span className="text-sm text-muted-foreground">{values.color}</span>
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={values.isActive}
                onChange={(e) => set("isActive", e.target.checked)}
                className="h-4 w-4 rounded border"
              />
              <span className="text-sm font-medium">Active</span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowModal(false)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button onClick={() => void handleSubmit()} disabled={isSubmitting}>
              {isSubmitting ? "Saving..." : editing ? "Update" : "Add Operatory"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
