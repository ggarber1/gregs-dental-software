"use client";

import { Suspense, useCallback, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, List, Plus } from "lucide-react";

import FullCalendar from "@fullcalendar/react";
import resourceTimeGridPlugin from "@fullcalendar/resource-timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateSelectArg, EventClickArg, EventInput } from "@fullcalendar/core";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { AppointmentModal } from "@/components/scheduling/AppointmentModal";
import { CancelAppointmentModal } from "@/components/scheduling/CancelAppointmentModal";
import { DaySheet } from "@/components/scheduling/DaySheet";
import {
  useAppointments,
  useOperatories,
  type Appointment,
} from "@/lib/api/scheduling";

type ViewMode = "calendar" | "daysheet";

function formatDateHeader(date: Date): string {
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function toDateString(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function SchedulePageContent() {
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [viewMode, setViewMode] = useState<ViewMode>("calendar");
  const calendarRef = useRef<FullCalendar>(null);

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingAppointment, setEditingAppointment] = useState<Appointment | null>(null);
  const [cancellingAppointment, setCancellingAppointment] = useState<Appointment | null>(null);
  const [createDefaults, setCreateDefaults] = useState<{
    date?: string;
    startTime?: string;
    operatoryId?: string;
  }>({});

  // Data
  const { data: appointments } = useAppointments();
  const { data: operatories } = useOperatories();

  const activeOperatories = useMemo(
    () =>
      (operatories ?? [])
        .filter((o) => o.isActive)
        .sort((a, b) => a.displayOrder - b.displayOrder),
    [operatories],
  );

  // FullCalendar resources = operatories
  const resources = useMemo(
    () =>
      activeOperatories.map((o) => ({
        id: o.id,
        title: o.name,
        eventColor: o.color,
      })),
    [activeOperatories],
  );

  // FullCalendar events = appointments
  const events: EventInput[] = useMemo(
    () =>
      (appointments ?? [])
        .filter((a) => a.status !== "cancelled" && a.status !== "no_show")
        .map((a) => {
          const ev: EventInput = {
            id: a.id,
            title: a.patientName ?? "No patient",
            start: a.startTime,
            end: a.endTime,
            backgroundColor: a.appointmentTypeColor ?? "#5B8DEF",
            borderColor: a.appointmentTypeColor ?? "#5B8DEF",
            extendedProps: {
              appointment: a,
            },
          };
          if (a.operatoryId) ev.resourceId = a.operatoryId;
          return ev;
        }),
    [appointments],
  );

  // Date navigation
  function goToday() {
    const today = new Date();
    setCurrentDate(today);
    calendarRef.current?.getApi().gotoDate(today);
  }

  function goPrev() {
    const prev = new Date(currentDate);
    prev.setDate(prev.getDate() - 1);
    setCurrentDate(prev);
    calendarRef.current?.getApi().gotoDate(prev);
  }

  function goNext() {
    const next = new Date(currentDate);
    next.setDate(next.getDate() + 1);
    setCurrentDate(next);
    calendarRef.current?.getApi().gotoDate(next);
  }

  // Calendar interactions
  const handleDateSelect = useCallback((selectInfo: DateSelectArg) => {
    const start = selectInfo.start;
    const h = String(start.getHours()).padStart(2, "0");
    const m = String(start.getMinutes()).padStart(2, "0");

    const defaults: typeof createDefaults = {
      date: toDateString(start),
      startTime: `${h}:${m}`,
    };
    if (selectInfo.resource?.id) defaults.operatoryId = selectInfo.resource.id;
    setCreateDefaults(defaults);
    setShowCreateModal(true);
  }, []);

  const handleEventClick = useCallback((clickInfo: EventClickArg) => {
    const appt = clickInfo.event.extendedProps.appointment as Appointment;
    setEditingAppointment(appt);
  }, []);

  // Event content renderer — compact to fit 30-min slots
  const renderEventContent = useCallback((eventInfo: { event: EventInput & { extendedProps: { appointment: Appointment } }; timeText: string }) => {
    const appt = eventInfo.event.extendedProps.appointment;
    const name = appt.patientName ?? "No patient";
    // Combine type + provider on one line to save vertical space
    const details = [appt.appointmentTypeName, appt.providerName].filter(Boolean).join(" · ");
    return (
      <div className="overflow-hidden px-1 py-0.5 text-[11px] leading-snug">
        <div className="font-semibold truncate">{name}</div>
        {details && <div className="truncate opacity-75">{details}</div>}
      </div>
    );
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Schedule"
        description="Daily appointment schedule and operatory view"
        actions={
          <Button onClick={() => {
            setCreateDefaults({});
            setShowCreateModal(true);
          }}>
            <Plus className="h-4 w-4" />
            New Appointment
          </Button>
        }
      />

      {/* Toolbar: date nav + view toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={goToday}>
            Today
          </Button>
          <Button variant="ghost" size="sm" onClick={goPrev}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={goNext}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <h2 className="text-lg font-semibold">{formatDateHeader(currentDate)}</h2>
        </div>

        <div className="flex items-center gap-1 rounded-md border p-0.5">
          <Button
            variant={viewMode === "calendar" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setViewMode("calendar")}
          >
            <CalendarDays className="mr-1 h-4 w-4" />
            Calendar
          </Button>
          <Button
            variant={viewMode === "daysheet" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setViewMode("daysheet")}
          >
            <List className="mr-1 h-4 w-4" />
            Day Sheet
          </Button>
        </div>
      </div>

      {/* Calendar view */}
      {viewMode === "calendar" && (
        <div className="rounded-md border bg-white p-2">
          <FullCalendar
            ref={calendarRef}
            plugins={[resourceTimeGridPlugin, interactionPlugin]}
            initialView="resourceTimeGridDay"
            initialDate={currentDate}
            resources={resources}
            events={events}
            headerToolbar={false}
            allDaySlot={false}
            slotMinTime="07:00:00"
            slotMaxTime="19:00:00"
            slotDuration="00:15:00"
            slotLabelInterval="01:00:00"
            selectable={true}
            selectMirror={true}
            select={handleDateSelect}
            eventClick={handleEventClick}
            eventContent={renderEventContent}
            height="auto"
            expandRows={true}
            resourceLabelContent={(arg) => (
              <span className="text-sm font-semibold">{arg.resource.title}</span>
            )}
            nowIndicator={true}
            businessHours={{
              daysOfWeek: [1, 2, 3, 4, 5],
              startTime: "08:00",
              endTime: "17:00",
            }}
          />
        </div>
      )}

      {/* Day sheet view */}
      {viewMode === "daysheet" && (
        <DaySheet
          date={currentDate}
          onEditAppointment={setEditingAppointment}
          onCancelAppointment={setCancellingAppointment}
        />
      )}

      {/* Modals */}
      <AppointmentModal
        open={showCreateModal}
        onOpenChange={setShowCreateModal}
        defaultDate={createDefaults.date}
        defaultStartTime={createDefaults.startTime}
        defaultOperatoryId={createDefaults.operatoryId}
      />

      <AppointmentModal
        open={editingAppointment !== null}
        onOpenChange={(open) => {
          if (!open) setEditingAppointment(null);
        }}
        appointment={editingAppointment}
      />

      <CancelAppointmentModal
        open={cancellingAppointment !== null}
        onOpenChange={(open) => {
          if (!open) setCancellingAppointment(null);
        }}
        appointment={cancellingAppointment}
      />
    </div>
  );
}

export default function SchedulePage() {
  return (
    <Suspense>
      <SchedulePageContent />
    </Suspense>
  );
}
