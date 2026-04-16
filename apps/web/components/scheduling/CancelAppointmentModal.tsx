"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useCancelAppointment, type Appointment, type CancelAppointmentBody } from "@/lib/api/scheduling";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  appointment: Appointment | null;
}

export function CancelAppointmentModal({ open, onOpenChange, appointment }: Props) {
  const [reason, setReason] = useState("");
  const cancelMutation = useCancelAppointment();
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleCancel() {
    if (!appointment) return;
    setIsSubmitting(true);
    try {
      const args: { id: string; body?: CancelAppointmentBody } = { id: appointment.id };
      if (reason) args.body = { cancellationReason: reason };
      await cancelMutation.mutateAsync(args);
      setReason("");
      onOpenChange(false);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Cancel Appointment</DialogTitle>
        </DialogHeader>

        <div className="py-4">
          {appointment && (
            <p className="mb-3 text-sm text-muted-foreground">
              Cancel appointment for <span className="font-medium">{appointment.patientName}</span>?
            </p>
          )}
          <Label htmlFor="cancel-reason">Reason (optional)</Label>
          <Textarea
            id="cancel-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Cancellation reason..."
            rows={2}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Keep Appointment
          </Button>
          <Button
            variant="destructive"
            onClick={() => void handleCancel()}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Cancelling..." : "Cancel Appointment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
