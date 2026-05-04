"use client";

import Link from "next/link";
import { CalendarPlus } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useOpenTreatmentPlanQueue } from "@/lib/api/treatment-plans";

export default function OpenTreatmentPlansPage() {
  const { data, isLoading } = useOpenTreatmentPlanQueue();

  const items = data ?? [];

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader
        title="Open Treatment Plans"
        description="Patients with accepted plans who have not yet scheduled all procedures."
      />

      {isLoading && (
        <div className="flex justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="rounded-lg border border-border py-16 text-center">
          <p className="text-sm text-muted-foreground">
            No patients with unscheduled accepted treatment plans.
          </p>
        </div>
      )}

      {!isLoading && items.length > 0 && (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Patient</TableHead>
                <TableHead>Plan</TableHead>
                <TableHead className="text-right">Pending items</TableHead>
                <TableHead className="text-right">Days waiting</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.planId}>
                  <TableCell>
                    <Link
                      href={`/patients/${item.patientId}?tab=treatment-plan`}
                      className="font-medium hover:underline"
                    >
                      {item.patientName}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{item.planName}</TableCell>
                  <TableCell className="text-right">
                    <Badge variant="outline">{item.pendingItemCount}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <span
                      className={
                        item.daysSinceAcceptance > 30
                          ? "font-medium text-destructive"
                          : "text-muted-foreground"
                      }
                    >
                      {item.daysSinceAcceptance}d
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/schedule?patientId=${item.patientId}`}>
                        <CalendarPlus className="mr-1.5 h-3.5 w-3.5" />
                        Schedule
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
