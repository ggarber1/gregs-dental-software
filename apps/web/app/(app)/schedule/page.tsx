"use client";

import { Suspense, useCallback, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, List, Plus } from "lucide-react";

import FullCalendar from "@fullcalendar/react";
import resourceTimeGridPlugin from "@fullcalendar/resource-timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateClickArg } from "@fullcalendar/interaction";
// Required so FullCalendar's `timeZone` prop resolves named IANA zones
// (e.g. "America/New_York"). Without it, FC silently falls back to UTC.
import luxon3Plugin from "@fullcalendar/luxon3";
import type { DateSelectArg, EventClickArg, EventInput } from "@fullcalendar/core";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { AppointmentModal } from "@/components/scheduling/AppointmentModal";
import { CancelAppointmentModal } from "@/components/scheduling/CancelAppointmentModal";
import { DaySheet } from "@/components/scheduling/DaySheet";
import {
  useAppointments,
  useOperatories,
  type Appointment,
} from "@/lib/api/scheduling";
import { usePracticeTimezone } from "@/lib/api/practice";
import {
  addMonthsLocal,
  dateToTimeInTz,
  formatDateHeaderInTz,
  localInputToUTC,
  toDateStringInTz,
} from "@/lib/timezone";

type ViewMode = "calendar" | "daysheet";

// Hoist stable prop references to module scope — passing new arrays/objects
// on every render can cause FullCalendar to tear down and rebuild, which
// clears the drag-select mirror mid-modal.
const FC_PLUGINS = [resourceTimeGridPlugin, interactionPlugin, luxon3Plugin];
const FC_BUSINESS_HOURS = {
  daysOfWeek: [1, 2, 3, 4, 5],
  startTime: "08:00",
  endTime: "17:00",
};

function SchedulePageContent() {
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const [viewMode, setViewMode] = useState<ViewMode>("calendar");
  const [datePickerOpen, setDatePickerOpen] = useState(false);
  const calendarRef = useRef<FullCalendar>(null);
  const timezone = usePracticeTimezone();

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingAppointment, setEditingAppointment] = useState<Appointment | null>(null);
  const [cancellingAppointment, setCancellingAppointment] = useState<Appointment | null>(null);
  const [createDefaults, setCreateDefaults] = useState<{
    date?: string;
    startTime?: string;
    endTime?: string;
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

  // Jump the calendar to a specific wall-clock date ("YYYY-MM-DD") in the
  // practice timezone. Single primitive — every nav button and the date picker
  // funnels through here so there's one place that handles the date→Date
  // conversion and the gotoDate call.
  const jumpToDate = useCallback(
    (dateStr: string) => {
      const iso = localInputToUTC(dateStr, "12:00", timezone);
      setCurrentDate(new Date(iso));
      calendarRef.current?.getApi().gotoDate(dateStr);
    },
    [timezone],
  );

  function goToday() {
    jumpToDate(toDateStringInTz(new Date(), timezone));
  }

  function shiftDays(delta: number) {
    // Wall-clock day math in practice TZ — UTC Date ops here are purely
    // calendrical (no zone conversion), so they don't drift on DST.
    const [y, m, d] = toDateStringInTz(currentDate, timezone).split("-").map(Number);
    const utc = new Date(Date.UTC(y!, m! - 1, d! + delta));
    const newStr = `${utc.getUTCFullYear()}-${String(utc.getUTCMonth() + 1).padStart(2, "0")}-${String(utc.getUTCDate()).padStart(2, "0")}`;
    jumpToDate(newStr);
  }

  function shiftMonths(delta: number) {
    jumpToDate(addMonthsLocal(toDateStringInTz(currentDate, timezone), delta));
  }

  // react-day-picker operates in the browser's local calendar, so we pass
  // Dates whose *local* Y/M/D match the practice-TZ wall-clock Y/M/D.
  const pickerSelected = useMemo(() => {
    const [y, m, d] = toDateStringInTz(currentDate, timezone).split("-").map(Number) as [
      number,
      number,
      number,
    ];
    return new Date(y, m - 1, d);
  }, [currentDate, timezone]);

  function handleDaySelect(date: Date | undefined) {
    if (!date) return;
    const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    jumpToDate(dateStr);
    setDatePickerOpen(false);
  }

  // Calendar interactions
  //
  // `dateClick` fires on a quick single-click on an empty slot; `select` fires
  // on a drag-to-range. We keep both: the modal defaults endTime to start+30min
  // when `defaultEndTime` is omitted, so single-click gets a sensible duration,
  // and drag preserves the dragged duration.
  //
  // `selectMinDistance={5}` below prevents `select` from firing on a zero-pixel
  // click (which would double-open the modal alongside `dateClick`).
  const handleDateClick = useCallback((arg: DateClickArg) => {
    const defaults: typeof createDefaults = {
      date: toDateStringInTz(arg.date, timezone),
      startTime: dateToTimeInTz(arg.date, timezone),
    };
    if (arg.resource?.id) defaults.operatoryId = arg.resource.id;
    setCreateDefaults(defaults);
    setShowCreateModal(true);
  }, [timezone]);

  const handleDateSelect = useCallback((selectInfo: DateSelectArg) => {
    const defaults: typeof createDefaults = {
      date: toDateStringInTz(selectInfo.start, timezone),
      startTime: dateToTimeInTz(selectInfo.start, timezone),
      endTime: dateToTimeInTz(selectInfo.end, timezone),
    };
    if (selectInfo.resource?.id) defaults.operatoryId = selectInfo.resource.id;
    setCreateDefaults(defaults);
    setShowCreateModal(true);
  }, [timezone]);

  // Clear the drag-select mirror on calendar when the create modal closes —
  // otherwise the highlight lingers even after cancel/submit.
  const handleCreateModalOpenChange = useCallback((open: boolean) => {
    setShowCreateModal(open);
    if (!open) calendarRef.current?.getApi().unselect();
  }, []);

  const handleEventClick = useCallback((clickInfo: EventClickArg) => {
    const appt = clickInfo.event.extendedProps.appointment as Appointment;
    setEditingAppointment(appt);
  }, []);

  // Event content renderer — compact to fit 30-min slots.
  //
  // FullCalendar also calls this for the drag-to-select "mirror" placeholder,
  // which has no `appointment` extendedProp. Guard so the mirror renders a
  // minimal time label instead of throwing on `appt.patientName`.
  const renderEventContent = useCallback((eventInfo: { event: EventInput & { extendedProps?: { appointment?: Appointment } }; timeText: string }) => {
    const appt = eventInfo.event.extendedProps?.appointment;
    if (!appt) {
      return (
        <div className="overflow-hidden px-1 py-0.5 text-[11px] leading-snug opacity-80">
          {eventInfo.timeText}
        </div>
      );
    }
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
          <Button variant="ghost" size="sm" onClick={() => shiftDays(-1)} aria-label="Previous day">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => shiftDays(1)} aria-label="Next day">
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => shiftMonths(-3)}>
            −3mo
          </Button>
          <Button variant="outline" size="sm" onClick={() => shiftMonths(3)}>
            +3mo
          </Button>
          <Button variant="outline" size="sm" onClick={() => shiftMonths(6)}>
            +6mo
          </Button>
          <Popover open={datePickerOpen} onOpenChange={setDatePickerOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="rounded px-2 py-1 text-lg font-semibold hover:bg-muted focus:outline-none focus:ring-2 focus:ring-ring"
                aria-label="Pick a date"
              >
                {formatDateHeaderInTz(currentDate, timezone)}
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-auto p-0">
              <Calendar
                mode="single"
                selected={pickerSelected}
                onSelect={handleDaySelect}
                defaultMonth={pickerSelected}
                startMonth={new Date(2000, 0)}
                endMonth={new Date(2050, 11)}
              />
            </PopoverContent>
          </Popover>
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
            plugins={FC_PLUGINS}
            initialView="resourceTimeGridDay"
            initialDate={currentDate}
            timeZone={timezone}
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
            selectMinDistance={5}
            // Disable FC's auto-unselect so the drag-select highlight stays
            // visible the entire time the create modal is open — including
            // when the user clicks into Radix Select/Popover dropdowns, which
            // portal outside the dialog tree. We clear the selection
            // explicitly in `handleCreateModalOpenChange` on modal close.
            unselectAuto={false}
            select={handleDateSelect}
            dateClick={handleDateClick}
            eventClick={handleEventClick}
            eventContent={renderEventContent}
            height="auto"
            expandRows={true}
            resourceLabelContent={(arg) => (
              <span className="text-sm font-semibold">{arg.resource.title}</span>
            )}
            nowIndicator={true}
            businessHours={FC_BUSINESS_HOURS}
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
        onOpenChange={handleCreateModalOpenChange}
        defaultDate={createDefaults.date}
        defaultStartTime={createDefaults.startTime}
        defaultEndTime={createDefaults.endTime}
        defaultOperatoryId={createDefaults.operatoryId}
      />

      <AppointmentModal
        open={editingAppointment !== null}
        onOpenChange={(open) => {
          if (!open) setEditingAppointment(null);
        }}
        appointment={editingAppointment}
        onCancelAppointment={(appt) => {
          // Close the edit modal before opening the confirmation dialog so
          // Radix doesn't stack two dialogs (focus + aria-hidden get tangled).
          setEditingAppointment(null);
          setCancellingAppointment(appt);
        }}
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
