"use client";

import { useEffect, useMemo, useState } from "react";
import { Lock, Pencil, Plus, Trash2 } from "lucide-react";

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
  useProviders,
  useCreateProvider,
  useUpdateProvider,
  useDeleteProvider,
  type Provider,
  type CreateProviderBody,
} from "@/lib/api/scheduling";
import {
  CUSTOM_NPI_SENTINEL,
  activeDentists,
  matchDentistByNpi,
} from "@/components/settings/supervisingDentist";

const PROVIDER_TYPES = [
  { value: "dentist", label: "Dentist" },
  { value: "hygienist", label: "Hygienist" },
  { value: "specialist", label: "Specialist" },
  { value: "other", label: "Other" },
] as const;

interface FormValues {
  fullName: string;
  npi: string;
  providerType: CreateProviderBody["providerType"];
  licenseNumber: string;
  specialty: string;
  color: string;
  isActive: boolean;
}

const EMPTY: FormValues = {
  fullName: "",
  npi: "",
  providerType: "dentist",
  licenseNumber: "",
  specialty: "",
  color: "#4F86C6",
  isActive: true,
};

export function ProvidersSettings() {
  const { data: providers, isLoading } = useProviders();
  const createMutation = useCreateProvider();
  const updateMutation = useUpdateProvider();
  const deleteMutation = useDeleteProvider();

  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Provider | null>(null);
  const [values, setValues] = useState<FormValues>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<keyof FormValues, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Supervising-dentist dropdown selection (hygienist rows only). Stored as a
  // provider id, CUSTOM_NPI_SENTINEL, or "" for unselected.
  const [supervisorSelection, setSupervisorSelection] = useState<string>("");

  const dentistOptions = useMemo(
    () => activeDentists(providers, editing?.id),
    [providers, editing?.id],
  );

  useEffect(() => {
    if (!showModal) return;
    if (editing) {
      setValues({
        fullName: editing.fullName,
        npi: editing.npi,
        providerType: editing.providerType,
        licenseNumber: editing.licenseNumber ?? "",
        specialty: editing.specialty ?? "",
        color: editing.color,
        isActive: editing.isActive,
      });
      if (editing.providerType === "hygienist") {
        const match = matchDentistByNpi(editing.npi, dentistOptions);
        setSupervisorSelection(
          match.kind === "dentist"
            ? match.providerId
            : match.kind === "custom"
              ? CUSTOM_NPI_SENTINEL
              : "",
        );
      } else {
        setSupervisorSelection("");
      }
    } else {
      setValues(EMPTY);
      setSupervisorSelection("");
    }
    setErrors({});
  }, [showModal, editing, dentistOptions]);

  function set<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function handleProviderTypeChange(next: FormValues["providerType"]) {
    set("providerType", next);
    if (next !== "hygienist") {
      setSupervisorSelection("");
    }
  }

  function handleSupervisorChange(next: string) {
    setSupervisorSelection(next);
    if (next === CUSTOM_NPI_SENTINEL) {
      set("npi", "");
      return;
    }
    const dentist = dentistOptions.find((d) => d.id === next);
    if (dentist) set("npi", dentist.npi);
  }

  const isHygienist = values.providerType === "hygienist";
  const npiLocked =
    isHygienist &&
    supervisorSelection !== "" &&
    supervisorSelection !== CUSTOM_NPI_SENTINEL;

  function validate(): boolean {
    const errs: Partial<Record<keyof FormValues, string>> = {};
    if (!values.fullName.trim()) errs.fullName = "Required";
    if (!/^\d{10}$/.test(values.npi)) errs.npi = "Must be 10 digits";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSubmit() {
    if (!validate()) return;
    setIsSubmitting(true);
    try {
      const body: CreateProviderBody = {
        fullName: values.fullName.trim(),
        npi: values.npi,
        providerType: values.providerType,
        color: values.color,
        isActive: values.isActive,
      };
      if (values.licenseNumber.trim()) body.licenseNumber = values.licenseNumber.trim();
      if (values.specialty.trim()) body.specialty = values.specialty.trim();

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

  function openEdit(provider: Provider) {
    setEditing(provider);
    setShowModal(true);
  }

  const sorted = [...(providers ?? [])].sort((a, b) => a.displayOrder - b.displayOrder);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Providers</h3>
        <Button size="sm" onClick={openCreate}>
          <Plus className="mr-1 h-4 w-4" />
          Add Provider
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>NPI</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Specialty</TableHead>
              <TableHead>Color</TableHead>
              <TableHead>Active</TableHead>
              <TableHead className="w-24">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            ) : sorted.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  No providers yet. Add one to get started.
                </TableCell>
              </TableRow>
            ) : (
              sorted.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.fullName}</TableCell>
                  <TableCell className="font-mono text-sm">{p.npi}</TableCell>
                  <TableCell className="capitalize">{p.providerType}</TableCell>
                  <TableCell>{p.specialty ?? "—"}</TableCell>
                  <TableCell>
                    <span
                      className="inline-block h-5 w-5 rounded border"
                      style={{ backgroundColor: p.color }}
                    />
                  </TableCell>
                  <TableCell>{p.isActive ? "Yes" : "No"}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openEdit(p)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => void handleDelete(p.id)}
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
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Provider" : "Add Provider"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div>
              <Label htmlFor="provider-name">Full Name</Label>
              <Input
                id="provider-name"
                value={values.fullName}
                onChange={(e) => set("fullName", e.target.value)}
              />
              {errors.fullName && <p className="mt-1 text-xs text-destructive">{errors.fullName}</p>}
            </div>
            <div>
              <Label htmlFor="provider-type">Type</Label>
              <Select
                value={values.providerType}
                onValueChange={(v) =>
                  handleProviderTypeChange(v as FormValues["providerType"])
                }
              >
                <SelectTrigger id="provider-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDER_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {isHygienist && (
              <div>
                <Label htmlFor="provider-supervisor">Supervising dentist</Label>
                <Select
                  value={supervisorSelection}
                  onValueChange={handleSupervisorChange}
                >
                  <SelectTrigger id="provider-supervisor">
                    <SelectValue
                      placeholder={
                        dentistOptions.length === 0
                          ? "No dentists yet — use Custom NPI"
                          : "Select supervising dentist…"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {dentistOptions.map((d) => (
                      <SelectItem key={d.id} value={d.id}>
                        {d.fullName} · {d.npi}
                      </SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_NPI_SENTINEL}>
                      Custom NPI (exception)
                    </SelectItem>
                  </SelectContent>
                </Select>
                <p className="mt-1 text-xs text-muted-foreground">
                  Hygienists bill under the supervising dentist&apos;s NPI.
                </p>
              </div>
            )}
            <div>
              <Label htmlFor="provider-npi">NPI (10 digits)</Label>
              <div className="relative">
                <Input
                  id="provider-npi"
                  value={values.npi}
                  onChange={(e) => set("npi", e.target.value)}
                  maxLength={10}
                  placeholder="1234567890"
                  readOnly={npiLocked}
                  aria-readonly={npiLocked}
                  className={npiLocked ? "bg-muted pr-8" : undefined}
                />
                {npiLocked && (
                  <Lock
                    className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden="true"
                  />
                )}
              </div>
              {errors.npi && <p className="mt-1 text-xs text-destructive">{errors.npi}</p>}
            </div>
            <div>
              <Label htmlFor="provider-license">License Number (optional)</Label>
              <Input
                id="provider-license"
                value={values.licenseNumber}
                onChange={(e) => set("licenseNumber", e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="provider-specialty">Specialty (optional)</Label>
              <Input
                id="provider-specialty"
                value={values.specialty}
                onChange={(e) => set("specialty", e.target.value)}
                placeholder="e.g. general, orthodontics"
              />
            </div>
            <div>
              <Label htmlFor="provider-color">Calendar Color</Label>
              <div className="flex items-center gap-2">
                <input
                  id="provider-color"
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
              {isSubmitting ? "Saving..." : editing ? "Update" : "Add Provider"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
