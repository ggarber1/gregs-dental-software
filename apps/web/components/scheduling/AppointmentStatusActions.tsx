"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  useUpdateAppointment,
  type Appointment,
  type AppointmentStatus,
} from "@/lib/api/scheduling";

const STATUS_LABELS: Record<AppointmentStatus, string> = {
  scheduled: "Scheduled",
  confirmed: "Confirmed",
  checked_in: "Checked In",
  in_chair: "In Chair",
  completed: "Completed",
  cancelled: "Cancelled",
  no_show: "No Show",
};

const STATUS_COLORS: Record<AppointmentStatus, string> = {
  scheduled: "bg-slate-100 text-slate-700",
  confirmed: "bg-blue-100 text-blue-700",
  checked_in: "bg-amber-100 text-amber-700",
  in_chair: "bg-purple-100 text-purple-700",
  completed: "bg-green-100 text-green-700",
  cancelled: "bg-red-100 text-red-700",
  no_show: "bg-gray-100 text-gray-500",
};

interface Transition {
  label: string;
  status: AppointmentStatus;
  variant: "default" | "outline" | "destructive" | "secondary" | "ghost";
}

const TRANSITIONS: Record<string, Transition[]> = {
  scheduled: [
    { label: "Confirm", status: "confirmed", variant: "default" },
    { label: "No-Show", status: "no_show", variant: "outline" },
  ],
  confirmed: [
    { label: "Check In", status: "checked_in", variant: "default" },
    { label: "No-Show", status: "no_show", variant: "outline" },
  ],
  checked_in: [
    { label: "Seat", status: "in_chair", variant: "default" },
    { label: "No-Show", status: "no_show", variant: "outline" },
  ],
  in_chair: [
    { label: "Complete", status: "completed", variant: "default" },
  ],
};

interface StatusBadgeProps {
  status: AppointmentStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

interface StatusActionsProps {
  appointment: Appointment;
  onCancel?: () => void;
  compact?: boolean;
}

export function AppointmentStatusActions({ appointment, onCancel, compact }: StatusActionsProps) {
  const updateMutation = useUpdateAppointment();
  const [pending, setPending] = useState<string | null>(null);

  const transitions = TRANSITIONS[appointment.status] ?? [];
  const isTerminal = ["completed", "cancelled"].includes(appointment.status);
  const canRevert = !isTerminal && appointment.status !== "scheduled";

  async function handleTransition(status: AppointmentStatus) {
    setPending(status);
    try {
      await updateMutation.mutateAsync({
        id: appointment.id,
        body: { status },
      });
    } finally {
      setPending(null);
    }
  }

  if (isTerminal) {
    return <StatusBadge status={appointment.status} />;
  }

  return (
    <div className="flex items-center gap-2">
      <StatusBadge status={appointment.status} />
      {canRevert && (
        <Button
          variant="ghost"
          size={compact ? "sm" : "default"}
          disabled={pending !== null}
          onClick={() => void handleTransition("scheduled")}
        >
          {pending === "scheduled" ? "..." : "Undo"}
        </Button>
      )}
      {transitions.map((t) => (
        <Button
          key={t.status}
          variant={t.variant}
          size={compact ? "sm" : "default"}
          disabled={pending !== null}
          onClick={() => void handleTransition(t.status)}
        >
          {pending === t.status ? "..." : t.label}
        </Button>
      ))}
      {onCancel && (
        <Button
          variant="ghost"
          size={compact ? "sm" : "default"}
          className="text-destructive hover:text-destructive"
          onClick={onCancel}
          disabled={pending !== null}
        >
          Cancel
        </Button>
      )}
    </div>
  );
}
