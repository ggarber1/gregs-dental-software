"use client";

import { useState } from "react";
import { CalendarPlus, ChevronDown, ChevronRight, Plus, Printer, Trash2 } from "lucide-react";
import { AppointmentModal } from "@/components/scheduling/AppointmentModal";
import { usePatient } from "@/lib/api/patients";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useTreatmentPlans,
  useTreatmentPlanDetail,
  useCreateTreatmentPlan,
  useUpdateTreatmentPlan,
  useAddTreatmentPlanItem,
  useUpdateTreatmentPlanItem,
  useDeleteTreatmentPlanItem,
  type TreatmentPlan,
  type TreatmentPlanStatus,
  type TreatmentPlanItemUrgency,
  type CreateTreatmentPlanItemBody,
} from "@/lib/api/treatment-plans";
import { cn } from "@/lib/utils";

interface TreatmentPlanTabProps {
  patientId: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

const STATUS_BADGE: Record<
  TreatmentPlanStatus,
  { label: string; variant: "default" | "secondary" | "outline" | "destructive" }
> = {
  proposed: { label: "Proposed", variant: "outline" },
  accepted: { label: "Accepted", variant: "default" },
  in_progress: { label: "In progress", variant: "default" },
  completed: { label: "Completed", variant: "secondary" },
  refused: { label: "Refused", variant: "destructive" },
  superseded: { label: "Superseded", variant: "secondary" },
};

const ACTIVE_STATUSES: TreatmentPlanStatus[] = ["proposed", "accepted", "in_progress"];

const URGENCY_ORDER: Record<TreatmentPlanItemUrgency, number> = {
  urgent: 0,
  soon: 1,
  elective: 2,
};

const URGENCY_OPTIONS: { value: TreatmentPlanItemUrgency; label: string }[] = [
  { value: "urgent", label: "Urgent" },
  { value: "soon", label: "Soon" },
  { value: "elective", label: "Elective" },
];

// Tailwind classes for the urgency badge — red / amber / gray.
const URGENCY_BADGE_CLASS: Record<TreatmentPlanItemUrgency, string> = {
  urgent: "border-transparent bg-red-100 text-red-800 hover:bg-red-200",
  soon: "border-transparent bg-amber-100 text-amber-800 hover:bg-amber-200",
  elective: "border-transparent bg-gray-100 text-gray-700 hover:bg-gray-200",
};

const URGENCY_LABEL: Record<TreatmentPlanItemUrgency, string> = {
  urgent: "Urgent",
  soon: "Soon",
  elective: "Elective",
};

// Tailwind classes for the active/inactive states of the urgency toggle buttons.
const URGENCY_TOGGLE_ACTIVE: Record<TreatmentPlanItemUrgency, string> = {
  urgent: "bg-red-600 text-white border-red-600 hover:bg-red-600",
  soon: "bg-amber-500 text-white border-amber-500 hover:bg-amber-500",
  elective: "bg-gray-500 text-white border-gray-500 hover:bg-gray-500",
};

function UrgencyBadge({ urgency }: { urgency: TreatmentPlanItemUrgency }) {
  return (
    <Badge
      data-testid={`urgency-badge-${urgency}`}
      className={cn("text-xs", URGENCY_BADGE_CLASS[urgency])}
    >
      {URGENCY_LABEL[urgency]}
    </Badge>
  );
}

function UrgencyToggle({
  value,
  onChange,
  disabled,
}: {
  value: TreatmentPlanItemUrgency;
  onChange: (next: TreatmentPlanItemUrgency) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-md border border-border" role="group">
      {URGENCY_OPTIONS.map((opt, idx) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            disabled={disabled}
            aria-pressed={active}
            className={cn(
              "h-8 px-3 text-xs font-medium transition-colors border-r border-border last:border-r-0",
              idx === 0 && "rounded-l-md",
              idx === URGENCY_OPTIONS.length - 1 && "rounded-r-md",
              active
                ? URGENCY_TOGGLE_ACTIVE[opt.value]
                : "bg-background text-muted-foreground hover:bg-muted",
              disabled && "opacity-50 cursor-not-allowed",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Plan detail expand panel ───────────────────────────────────────────────────

const ITEM_NEXT_ACTION: Partial<Record<string, { label: string; next: string }>> = {
  accepted: { label: "Mark scheduled", next: "scheduled" },
  scheduled: { label: "Mark complete", next: "completed" },
};

function PlanDetail({ patientId, planId }: { patientId: string; planId: string }) {
  const { data, isLoading } = useTreatmentPlanDetail(patientId, planId);
  const { data: patient } = usePatient(patientId);
  const updateItem = useUpdateTreatmentPlanItem(patientId, planId);
  const deleteItem = useDeleteTreatmentPlanItem(patientId, planId);

  const [addingItem, setAddingItem] = useState(false);
  const [newItem, setNewItem] = useState<Partial<CreateTreatmentPlanItemBody>>({});
  const addItem = useAddTreatmentPlanItem(patientId, planId);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [schedulingOpen, setSchedulingOpen] = useState(false);

  function toggleItem(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  }

  function handlePrint() {
    window.print();
  }

  async function handleAddItem() {
    if (!newItem.procedureCode || !newItem.procedureName || newItem.feeCents === undefined) return;
    await addItem.mutateAsync(newItem as CreateTreatmentPlanItemBody);
    setNewItem({});
    setAddingItem(false);
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!data) return null;

  // Sort items by urgency (urgent → soon → elective). Re-sorted client-side
  // so that local mutations (e.g., changing an item's urgency) reflect
  // immediately before the server-side re-fetch.
  const sortedItems = [...data.items].sort(
    (a, b) => URGENCY_ORDER[a.urgency] - URGENCY_ORDER[b.urgency],
  );

  return (
    <div className="mt-3 space-y-3 print:mt-0">
      {/* Items table */}
      <div className="overflow-x-auto rounded-md border border-border print:border-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground print:bg-transparent">
              <th className="w-8 px-3 py-2 print:hidden" />
              <th className="px-3 py-2">Tooth</th>
              <th className="px-3 py-2">Code</th>
              <th className="px-3 py-2">Procedure</th>
              <th className="px-3 py-2">Surface</th>
              <th className="px-3 py-2 text-right">Fee</th>
              <th className="px-3 py-2 text-right">Ins. Est.</th>
              <th className="px-3 py-2 text-right">Pt. Est.</th>
              <th className="px-3 py-2">Urgency</th>
              <th className="px-3 py-2 print:hidden">Status</th>
              <th className="px-3 py-2 print:hidden" />
            </tr>
          </thead>
          <tbody>
            {sortedItems.length === 0 && (
              <tr>
                <td colSpan={11} className="px-3 py-4 text-center text-muted-foreground">
                  No items yet.
                </td>
              </tr>
            )}
            {sortedItems.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-0">
                <td className="px-3 py-2 print:hidden">
                  {item.status === "accepted" && (
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => toggleItem(item.id)}
                      className="h-4 w-4 cursor-pointer rounded border-border"
                      aria-label={`Select ${item.procedureName}`}
                    />
                  )}
                </td>
                <td className="px-3 py-2 text-muted-foreground">{item.toothNumber ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{item.procedureCode}</td>
                <td className="px-3 py-2">{item.procedureName}</td>
                <td className="px-3 py-2 text-muted-foreground">{item.surface ?? "—"}</td>
                <td className="px-3 py-2 text-right">{formatCents(item.feeCents)}</td>
                <td className="px-3 py-2 text-right text-muted-foreground">
                  {item.insuranceEstCents != null ? formatCents(item.insuranceEstCents) : "—"}
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">
                  {item.patientEstCents != null ? formatCents(item.patientEstCents) : "—"}
                </td>
                <td className="px-3 py-2">
                  <div className="hidden print:block">
                    <UrgencyBadge urgency={item.urgency} />
                  </div>
                  <div className="relative inline-block print:hidden">
                    {/* Display: a colored Badge. Wraps a transparent native
                        <select> so the user can change urgency in place. */}
                    <UrgencyBadge urgency={item.urgency} />
                    <select
                      aria-label={`Urgency for ${item.procedureName}`}
                      value={item.urgency}
                      onChange={(e) =>
                        updateItem.mutate({
                          itemId: item.id,
                          body: {
                            urgency: e.target.value as TreatmentPlanItemUrgency,
                          },
                        })
                      }
                      disabled={updateItem.isPending}
                      className="absolute inset-0 cursor-pointer opacity-0"
                    >
                      {URGENCY_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </td>
                <td className="px-3 py-2 print:hidden">
                  <Badge variant="outline" className="text-xs">
                    {item.status}
                  </Badge>
                </td>
                <td className="px-3 py-2 print:hidden">
                  <div className="flex items-center gap-1">
                    {ITEM_NEXT_ACTION[item.status] && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() =>
                          updateItem.mutate({
                            itemId: item.id,
                            body: { status: ITEM_NEXT_ACTION[item.status]!.next as "scheduled" | "completed" },
                          })
                        }
                        disabled={updateItem.isPending}
                      >
                        {ITEM_NEXT_ACTION[item.status]!.label}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive"
                      onClick={() => deleteItem.mutate(item.id)}
                      disabled={deleteItem.isPending}
                      aria-label="Remove item"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
          {sortedItems.length > 0 && (
            <tfoot>
              <tr className="border-t border-border bg-muted/20 text-sm font-medium">
                <td colSpan={4} className="px-3 py-2 text-right">Total</td>
                <td className="px-3 py-2 text-right">
                  {formatCents(sortedItems.reduce((s, i) => s + i.feeCents, 0))}
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">
                  {formatCents(
                    sortedItems.reduce((s, i) => s + (i.insuranceEstCents ?? 0), 0),
                  )}
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground">
                  {formatCents(
                    sortedItems.reduce((s, i) => s + (i.patientEstCents ?? 0), 0),
                  )}
                </td>
                <td />
                <td colSpan={2} className="print:hidden" />
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* Add item form */}
      {addingItem && (
        <div className="rounded-md border border-border p-3 print:hidden">
          <p className="mb-2 text-sm font-medium">Add procedure</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className="space-y-1">
              <Label className="text-xs">Tooth #</Label>
              <Input
                className="h-8 text-sm"
                placeholder="14"
                value={newItem.toothNumber ?? ""}
                onChange={(e) => setNewItem((p) => ({ ...p, toothNumber: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">CDT Code *</Label>
              <Input
                className="h-8 text-sm"
                placeholder="D2391"
                value={newItem.procedureCode ?? ""}
                onChange={(e) =>
                  setNewItem((p) => ({ ...p, procedureCode: e.target.value }))
                }
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs">Procedure Name *</Label>
              <Input
                className="h-8 text-sm"
                placeholder="Resin composite, 1 surface"
                value={newItem.procedureName ?? ""}
                onChange={(e) =>
                  setNewItem((p) => ({ ...p, procedureName: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Surface</Label>
              <Input
                className="h-8 text-sm"
                placeholder="MOD"
                value={newItem.surface ?? ""}
                onChange={(e) => setNewItem((p) => ({ ...p, surface: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Fee ($) *</Label>
              <Input
                className="h-8 text-sm"
                type="number"
                min="0"
                step="0.01"
                placeholder="250.00"
                value={newItem.feeCents !== undefined ? newItem.feeCents / 100 : ""}
                onChange={(e) =>
                  setNewItem((p) => ({
                    ...p,
                    feeCents: Math.round(parseFloat(e.target.value) * 100),
                  }))
                }
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Ins. Est. ($)</Label>
              <Input
                className="h-8 text-sm"
                type="number"
                min="0"
                step="0.01"
                placeholder="150.00"
                value={
                  newItem.insuranceEstCents !== undefined
                    ? newItem.insuranceEstCents / 100
                    : ""
                }
                onChange={(e) =>
                  setNewItem((p) => ({
                    ...p,
                    insuranceEstCents: Math.round(parseFloat(e.target.value) * 100),
                  }))
                }
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Pt. Est. ($)</Label>
              <Input
                className="h-8 text-sm"
                type="number"
                min="0"
                step="0.01"
                placeholder="100.00"
                value={
                  newItem.patientEstCents !== undefined ? newItem.patientEstCents / 100 : ""
                }
                onChange={(e) =>
                  setNewItem((p) => ({
                    ...p,
                    patientEstCents: Math.round(parseFloat(e.target.value) * 100),
                  }))
                }
              />
            </div>
            <div className="col-span-2 space-y-1 sm:col-span-4">
              <Label className="text-xs">Urgency</Label>
              <UrgencyToggle
                value={newItem.urgency ?? "soon"}
                onChange={(u) => setNewItem((p) => ({ ...p, urgency: u }))}
              />
            </div>
          </div>
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              onClick={() => void handleAddItem()}
              disabled={
                addItem.isPending ||
                !newItem.procedureCode ||
                !newItem.procedureName ||
                newItem.feeCents === undefined
              }
            >
              Add
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setAddingItem(false);
                setNewItem({});
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2 print:hidden">
        {!addingItem && (
          <Button size="sm" variant="outline" onClick={() => setAddingItem(true)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Add procedure
          </Button>
        )}
        {selectedIds.size > 0 && (
          <Button size="sm" onClick={() => setSchedulingOpen(true)}>
            <CalendarPlus className="mr-1.5 h-3.5 w-3.5" />
            Schedule {selectedIds.size} item{selectedIds.size > 1 ? "s" : ""}
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={handlePrint}>
          <Printer className="mr-1.5 h-3.5 w-3.5" />
          Print
        </Button>
      </div>

      <AppointmentModal
        open={schedulingOpen}
        onOpenChange={setSchedulingOpen}
        defaultPatientId={patientId}
        defaultPatientName={
          patient ? `${patient.firstName} ${patient.lastName}` : undefined
        }
        onCreated={(appt) => {
          [...selectedIds].forEach((itemId) => {
            updateItem.mutate({
              itemId,
              body: { status: "scheduled", appointmentId: appt.id },
            });
          });
          setSelectedIds(new Set());
        }}
      />
    </div>
  );
}

// ── Plan row ──────────────────────────────────────────────────────────────────

function PlanRow({ plan, patientId }: { plan: TreatmentPlan; patientId: string }) {
  const [expanded, setExpanded] = useState(false);
  const updatePlan = useUpdateTreatmentPlan(patientId, plan.id);
  const badge = STATUS_BADGE[plan.status];

  return (
    <div className="rounded-md border border-border">
      <div
        className="flex cursor-pointer items-center gap-3 px-4 py-3"
        onClick={() => setExpanded((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && setExpanded((v) => !v)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className="flex-1 font-medium">{plan.name}</span>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {plan.status === "proposed" && (
            <>
              <Button
                size="sm"
                variant="default"
                onClick={() => updatePlan.mutate({ status: "accepted" })}
                disabled={updatePlan.isPending}
              >
                Accept
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => updatePlan.mutate({ status: "refused" })}
                disabled={updatePlan.isPending}
              >
                Refuse
              </Button>
            </>
          )}
          <Badge variant={badge.variant} className="text-xs">
            {badge.label}
          </Badge>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border px-4 pb-4">
          <PlanDetail patientId={patientId} planId={plan.id} />
        </div>
      )}
    </div>
  );
}

// ── New plan form ─────────────────────────────────────────────────────────────

interface DraftItem {
  key: number;
  toothNumber: string;
  procedureCode: string;
  procedureName: string;
  feeCents: string;
  urgency: TreatmentPlanItemUrgency;
}

const EMPTY_DRAFT_ITEM: Omit<DraftItem, "key"> = {
  toothNumber: "",
  procedureCode: "",
  procedureName: "",
  feeCents: "",
  urgency: "soon",
};

function NewPlanForm({ patientId, onDone }: { patientId: string; onDone: () => void }) {
  const [name, setName] = useState("Treatment Plan");
  const [items, setItems] = useState<DraftItem[]>([{ key: 0, ...EMPTY_DRAFT_ITEM }]);
  const [nextKey, setNextKey] = useState(1);
  const create = useCreateTreatmentPlan(patientId);

  function addItem() {
    setItems((prev) => [...prev, { key: nextKey, ...EMPTY_DRAFT_ITEM }]);
    setNextKey((k) => k + 1);
  }

  function removeItem(key: number) {
    setItems((prev) => prev.filter((i) => i.key !== key));
  }

  function setItemField<K extends keyof Omit<DraftItem, "key">>(
    key: number,
    field: K,
    value: DraftItem[K],
  ) {
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, [field]: value } : i)));
  }

  async function handleSubmit() {
    const validItems = items.filter(
      (i) => i.procedureCode.trim() && i.procedureName.trim() && i.feeCents.trim(),
    );
    await create.mutateAsync({
      name: name.trim() || "Treatment Plan",
      items: validItems.map((i, idx) => ({
        ...(i.toothNumber.trim() ? { toothNumber: i.toothNumber.trim() } : {}),
        procedureCode: i.procedureCode.trim(),
        procedureName: i.procedureName.trim(),
        feeCents: Math.round(parseFloat(i.feeCents) * 100),
        urgency: i.urgency,
        priority: idx + 1,
      })),
    });
    onDone();
  }

  return (
    <div className="rounded-md border border-border p-4">
      <p className="mb-4 text-sm font-medium">New treatment plan</p>

      <div className="mb-4 space-y-1">
        <Label className="text-xs">Plan name</Label>
        <Input
          className="h-9"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Treatment Plan"
        />
      </div>

      <div className="mb-2 text-xs font-medium text-muted-foreground">Procedures</div>
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.key}
            className="grid grid-cols-[3rem_6rem_1fr_5rem_auto_1.5rem] gap-2 items-center"
          >
            <Input
              className="h-8 text-sm"
              placeholder="Tooth"
              value={item.toothNumber}
              onChange={(e) => setItemField(item.key, "toothNumber", e.target.value)}
            />
            <Input
              className="h-8 text-sm"
              placeholder="Code *"
              value={item.procedureCode}
              onChange={(e) => setItemField(item.key, "procedureCode", e.target.value)}
            />
            <Input
              className="h-8 text-sm"
              placeholder="Procedure name *"
              value={item.procedureName}
              onChange={(e) => setItemField(item.key, "procedureName", e.target.value)}
            />
            <Input
              className="h-8 text-sm"
              type="number"
              min="0"
              step="0.01"
              placeholder="Fee *"
              value={item.feeCents}
              onChange={(e) => setItemField(item.key, "feeCents", e.target.value)}
            />
            <UrgencyToggle
              value={item.urgency}
              onChange={(u) => setItemField(item.key, "urgency", u)}
            />
            <button
              type="button"
              onClick={() => removeItem(item.key)}
              disabled={items.length === 1}
              className="text-muted-foreground hover:text-destructive disabled:opacity-30"
              aria-label="Remove row"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      <Button size="sm" variant="ghost" className="mt-2 h-7 px-2 text-xs" onClick={addItem}>
        <Plus className="mr-1 h-3 w-3" />
        Add row
      </Button>

      <div className="mt-4 flex gap-2">
        <Button size="sm" onClick={() => void handleSubmit()} disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create plan"}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ── Main tab component ─────────────────────────────────────────────────────────

export function TreatmentPlanTab({ patientId }: TreatmentPlanTabProps) {
  const { data, isLoading } = useTreatmentPlans(patientId);
  const [creating, setCreating] = useState(false);

  const plans = data?.items ?? [];
  const active = plans.filter((p) => ACTIVE_STATUSES.includes(p.status));
  const historical = plans.filter(
    (p) => !ACTIVE_STATUSES.includes(p.status),
  );

  return (
    <div className="space-y-6 rounded-lg border border-border bg-card p-4 print:border-0 print:p-0">
      <div className="flex items-center justify-between print:hidden">
        <h2 className="text-base font-semibold">Treatment Plans</h2>
        {!creating && (
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            New plan
          </Button>
        )}
      </div>

      {creating && (
        <NewPlanForm patientId={patientId} onDone={() => setCreating(false)} />
      )}

      {isLoading && (
        <div className="flex justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {!isLoading && plans.length === 0 && !creating && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No treatment plans yet. Create one to get started.
        </p>
      )}

      {active.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Active
          </h3>
          {active.map((plan) => (
            <PlanRow key={plan.id} plan={plan} patientId={patientId} />
          ))}
        </section>
      )}

      {historical.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            History
          </h3>
          {historical.map((plan) => (
            <PlanRow key={plan.id} plan={plan} patientId={patientId} />
          ))}
        </section>
      )}
    </div>
  );
}
