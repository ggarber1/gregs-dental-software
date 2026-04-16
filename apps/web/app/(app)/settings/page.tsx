"use client";

import { Suspense, useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { ProvidersSettings } from "@/components/settings/ProvidersSettings";
import { OperatoriesSettings } from "@/components/settings/OperatoriesSettings";
import { AppointmentTypesSettings } from "@/components/settings/AppointmentTypesSettings";

const TABS = [
  { key: "providers", label: "Providers" },
  { key: "operatories", label: "Operatories" },
  { key: "appointment-types", label: "Appointment Types" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function SettingsContent() {
  const [activeTab, setActiveTab] = useState<TabKey>("providers");

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Manage providers, operatories, and appointment types"
      />

      <div className="flex items-center gap-1 rounded-md border p-0.5 w-fit">
        {TABS.map((tab) => (
          <Button
            key={tab.key}
            variant={activeTab === tab.key ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {activeTab === "providers" && <ProvidersSettings />}
      {activeTab === "operatories" && <OperatoriesSettings />}
      {activeTab === "appointment-types" && <AppointmentTypesSettings />}
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense>
      <SettingsContent />
    </Suspense>
  );
}
