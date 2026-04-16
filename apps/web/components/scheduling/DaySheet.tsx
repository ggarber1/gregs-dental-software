"use client";

import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AppointmentStatusActions,
  StatusBadge,
} from "@/components/scheduling/AppointmentStatusActions";
import {
  useAppointments,
  useProviders,
  type Appointment,
} from "@/lib/api/scheduling";
import { usePracticeTimezone } from "@/lib/api/practice";
import { formatTimeInTz, dayBoundsInTz } from "@/lib/timezone";

interface DaySheetProps {
  date: Date;
  onEditAppointment: (appointment: Appointment) => void;
  onCancelAppointment: (appointment: Appointment) => void;
}

export function DaySheet({ date, onEditAppointment, onCancelAppointment }: DaySheetProps) {
  const [providerFilter, setProviderFilter] = useState<string>("all");
  const { data: appointments, isLoading } = useAppointments();
  const { data: providers } = useProviders();
  const timezone = usePracticeTimezone();

  const activeProviders = providers?.filter((p) => p.isActive) ?? [];

  // Filter to selected day in the practice timezone
  const { start: dayStart, end: dayEnd } = dayBoundsInTz(date, timezone);

  const dayAppointments = (appointments ?? [])
    .filter((a) => {
      const start = new Date(a.startTime);
      return start >= dayStart && start < dayEnd;
    })
    .filter((a) => {
      if (providerFilter === "all") return true;
      return a.providerId === providerFilter;
    })
    .filter((a) => a.status !== "cancelled")
    .sort((a, b) => new Date(a.startTime).getTime() - new Date(b.startTime).getTime());

  return (
    <div className="flex flex-col gap-4">
      {/* Provider filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-muted-foreground">Filter by provider:</span>
        <Select value={providerFilter} onValueChange={setProviderFilter}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Providers</SelectItem>
            {activeProviders.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.fullName}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-32">Time</TableHead>
              <TableHead>Patient</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Operatory</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-48">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 7 }).map((__, j) => (
                    <TableCell key={j}>
                      <div className="h-4 w-full animate-pulse rounded bg-muted" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : dayAppointments.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  No appointments scheduled for this day.
                </TableCell>
              </TableRow>
            ) : (
              dayAppointments.map((appt) => (
                <TableRow
                  key={appt.id}
                  className="cursor-pointer"
                  onClick={() => onEditAppointment(appt)}
                >
                  <TableCell className="font-medium whitespace-nowrap">
                    {formatTimeInTz(appt.startTime, timezone)} - {formatTimeInTz(appt.endTime, timezone)}
                  </TableCell>
                  <TableCell className="font-medium">{appt.patientName ?? "—"}</TableCell>
                  <TableCell>
                    {appt.appointmentTypeName ? (
                      <span className="flex items-center gap-1.5">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: appt.appointmentTypeColor ?? "#5B8DEF" }}
                        />
                        {appt.appointmentTypeName}
                      </span>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>{appt.providerName ?? "—"}</TableCell>
                  <TableCell>{appt.operatoryName ?? "—"}</TableCell>
                  <TableCell>
                    <StatusBadge status={appt.status} />
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <AppointmentStatusActions
                      appointment={appt}
                      onCancel={() => onCancelAppointment(appt)}
                      compact
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {!isLoading && dayAppointments.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {dayAppointments.length} appointment{dayAppointments.length !== 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}
