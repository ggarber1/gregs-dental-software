"use client";

import Link from "next/link";
import { LogOut } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { usePortalProfile } from "@/lib/api/portal";

const portalSections = [
  {
    title: "Appointments",
    description: "Upcoming appointments and visit details will appear here.",
  },
  {
    title: "Treatment Plans",
    description: "Active treatment plans and progress will appear here.",
  },
  {
    title: "Visit Summaries",
    description: "Past visit summaries and care notes will appear here.",
  },
  {
    title: "Medical & Insurance Updates",
    description: "Pre-visit medical history and insurance updates will appear here.",
  },
];

export default function PortalHomePage() {
  const { data: profile, isLoading, error } = usePortalProfile();

  async function handleSignOut() {
    await fetch("/portal/auth/session", { method: "DELETE" });
    window.location.href = "/portal/login";
  }

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading your portal...</p>;
  }

  if (error || !profile) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Unable to load portal</CardTitle>
          <CardDescription>Please sign in again to continue.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/portal/login">Go to login</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">{profile.practiceName}</p>
          <h2 className="text-2xl font-semibold">
            Welcome, {profile.firstName} {profile.lastName}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary">Phase 5.2A</Badge>
          <Button variant="outline" size="sm" onClick={() => void handleSignOut()}>
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {portalSections.map((section) => (
          <Card key={section.title}>
            <CardHeader>
              <CardTitle className="text-lg">{section.title}</CardTitle>
              <CardDescription>{section.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Coming in Phase 5.2B.</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
