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
  useAppointmentTypes,
  useCreateAppointmentType,
  useUpdateAppointmentType,
  useDeleteAppointmentType,
  type AppointmentType,
} from "@/lib/api/scheduling";

interface FormValues {
  name: string;
  durationMinutes: string;
  color: string;
  isActive: boolean;
}

const EMPTY: FormValues = {
  name: "",
  durationMinutes: "30",
  color: "#5B8DEF",
  isActive: true,
};

export function AppointmentTypesSettings() {
  const { data: types, isLoading } = useAppointmentTypes();
  const createMutation = useCreateAppointmentType();
  const updateMutation = useUpdateAppointmentType();
  const deleteMutation = useDeleteAppointmentType();

  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<AppointmentType | null>(null);
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof FormValues, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!showModal) return;
    if (editing) {
      setValues({
        name: editing.name,
        durationMinutes: String(editing.durationMinutes),
        color: editing.color,
        isActive: editing.isActive,
      });
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
    const dur = Number(values.durationMinutes);
    if (!values.durationMinutes || isNaN(dur) || dur < 5 || dur > 480) {
      errs.durationMinutes = "5–480 minutes";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSubmit() {
    if (!validate()) return;
    setIsSubmitting(true);
    try {
      const body = {
        name: values.name.trim(),
        durationMinutes: Number(values.durationMinutes),
        color: values.color,
        isActive: values.isActive,
      };
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

  function openEdit(t: AppointmentType) {
    setEditing(t);
    setShowModal(true);
  }

  const sorted = [...(types ?? [])].sort((a, b) => a.displayOrder - b.displayOrder);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Appointment Types</h3>
        <Button size="sm" onClick={openCreate}>
          <Plus className="mr-1 h-4 w-4" />
          Add Type
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Color</TableHead>
              <TableHead>Active</TableHead>
              <TableHead className="w-24">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            ) : sorted.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  No appointment types yet. Add one to get started.
                </TableCell>
              </TableRow>
            ) : (
              sorted.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">
                    <span className="flex items-center gap-2">
                      <span
                        className="inline-block h-3 w-3 rounded-full"
                        style={{ backgroundColor: t.color }}
                      />
                      {t.name}
                    </span>
                  </TableCell>
                  <TableCell>{t.durationMinutes} min</TableCell>
                  <TableCell>
                    <span
                      className="inline-block h-5 w-5 rounded border"
                      style={{ backgroundColor: t.color }}
                    />
                  </TableCell>
                  <TableCell>{t.isActive ? "Yes" : "No"}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(t)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => void handleDelete(t.id)}
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
            <DialogTitle>{editing ? "Edit Appointment Type" : "Add Appointment Type"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div>
              <Label htmlFor="type-name">Name</Label>
              <Input
                id="type-name"
                value={values.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="e.g. Cleaning, Crown Prep"
              />
              {errors.name && <p className="mt-1 text-xs text-destructive">{errors.name}</p>}
            </div>
            <div>
              <Label htmlFor="type-duration">Duration (minutes)</Label>
              <Input
                id="type-duration"
                type="number"
                min={5}
                max={480}
                value={values.durationMinutes}
                onChange={(e) => set("durationMinutes", e.target.value)}
              />
              {errors.durationMinutes && (
                <p className="mt-1 text-xs text-destructive">{errors.durationMinutes}</p>
              )}
            </div>
            <div>
              <Label htmlFor="type-color">Calendar Color</Label>
              <div className="flex items-center gap-2">
                <input
                  id="type-color"
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
              {isSubmitting ? "Saving..." : editing ? "Update" : "Add Type"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
