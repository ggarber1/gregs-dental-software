"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  CalendarDays,
  CreditCard,
  LayoutDashboard,
  LogOut,
  Settings,
  Users,
} from "lucide-react";
import { signOut } from "aws-amplify/auth";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/schedule", label: "Schedule", icon: CalendarDays },
  { href: "/patients", label: "Patients", icon: Users },
  { href: "/billing", label: "Billing", icon: CreditCard },
] as const;

const settingsItem = { href: "/settings", label: "Settings", icon: Settings };

interface NavItemProps {
  href: string;
  label: string;
  icon: React.ElementType;
  isActive: boolean;
}

function NavItem({ href, label, icon: Icon, isActive }: NavItemProps) {
  return (
    <>
      <TooltipTrigger asChild>
        <Link
          href={href}
          className={cn(
            "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
            "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            isActive
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "text-sidebar-foreground/70",
            "md:w-full",
            "max-md:justify-center max-md:px-2",
          )}
        >
          <Icon className="h-5 w-5 shrink-0" />
          <span className="hidden md:inline">{label}</span>
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right" className="md:hidden">
        {label}
      </TooltipContent>
    </>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  async function handleSignOut() {
    try {
      await signOut();
    } catch {
      // Non-fatal — proceed to clear cookies regardless.
    }
    await fetch("/_session", { method: "DELETE" });
    router.push("/login");
  }

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          "flex h-screen flex-col bg-sidebar text-sidebar-foreground",
          "w-14 md:w-56",
          "border-r border-sidebar-border",
        )}
      >
        <div className="flex h-14 items-center border-b border-sidebar-border px-3 md:px-4">
          <span className="hidden text-sm font-semibold md:block">Dental PMS</span>
          <span className="text-lg font-bold md:hidden">D</span>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-2">
          {navItems.map((item) => (
            <Tooltip key={item.href}>
              <NavItem
                href={item.href}
                label={item.label}
                icon={item.icon}
                isActive={pathname === item.href || pathname.startsWith(item.href + "/")}
              />
            </Tooltip>
          ))}
        </nav>

        <Separator className="bg-sidebar-border" />

        <div className="flex flex-col gap-1 p-2">
          <Tooltip>
            <NavItem
              href={settingsItem.href}
              label={settingsItem.label}
              icon={settingsItem.icon}
              isActive={pathname === settingsItem.href}
            />
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                  "w-full justify-start text-sidebar-foreground/70",
                  "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  "max-md:justify-center max-md:px-2",
                )}
                onClick={() => void handleSignOut()}
              >
                <LogOut className="h-5 w-5 shrink-0" />
                <span className="hidden md:inline">Sign out</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right" className="md:hidden">
              Sign out
            </TooltipContent>
          </Tooltip>
        </div>
      </aside>
    </TooltipProvider>
  );
}
