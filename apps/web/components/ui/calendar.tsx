"use client";

import * as React from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/style.css";

import { cn } from "@/lib/utils";

export type CalendarProps = React.ComponentProps<typeof DayPicker>;

export function Calendar({ className, captionLayout = "dropdown", ...props }: CalendarProps) {
  return (
    <DayPicker
      captionLayout={captionLayout}
      className={cn("rdp-root p-3", className)}
      {...props}
    />
  );
}
Calendar.displayName = "Calendar";
