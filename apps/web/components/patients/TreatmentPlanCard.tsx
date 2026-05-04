"use client";

import { ClipboardList } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useTreatmentPlans, type TreatmentPlanStatus } from "@/lib/api/treatment-plans";

interface TreatmentPlanCardProps {
  patientId: string;
  onViewAll: () => void;
}

const STATUS_BADGE: Record<TreatmentPlanStatus, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  proposed: { label: "Proposed", variant: "outline" },
  accepted: { label: "Accepted", variant: "default" },
  in_progress: { label: "In progress", variant: "default" },
  completed: { label: "Completed", variant: "secondary" },
  refused: { label: "Refused", variant: "destructive" },
  superseded: { label: "Superseded", variant: "secondary" },
};

const ACTIVE_STATUSES: TreatmentPlanStatus[] = ["proposed", "accepted", "in_progress"];

export function TreatmentPlanCard({ patientId, onViewAll }: TreatmentPlanCardProps) {
  const { data, isLoading } = useTreatmentPlans(patientId);

  const activePlans = (data?.items ?? []).filter((p) =>
    ACTIVE_STATUSES.includes(p.status),
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-base font-semibold">Treatment Plans</CardTitle>
        <Button variant="ghost" size="sm" onClick={onViewAll}>
          View all
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex justify-center py-4">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        )}

        {!isLoading && activePlans.length === 0 && (
          <p className="text-sm text-muted-foreground">No active treatment plans.</p>
        )}

        {!isLoading && activePlans.length > 0 && (
          <div className="space-y-2">
            {activePlans.slice(0, 3).map((plan) => {
              const badge = STATUS_BADGE[plan.status];
              return (
                <div key={plan.id} className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <ClipboardList className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="truncate text-sm">{plan.name}</span>
                  </div>
                  <Badge variant={badge.variant} className="shrink-0 text-xs">
                    {badge.label}
                  </Badge>
                </div>
              );
            })}
            {activePlans.length > 3 && (
              <p className="text-xs text-muted-foreground">
                +{activePlans.length - 3} more
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
