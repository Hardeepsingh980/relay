"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/settings/connections", label: "Connections" },
  { href: "/settings/team", label: "Teammates" },
  { href: "/settings/workspace", label: "Workspace" },
  { href: "/settings/profile", label: "Profile" },
];

export function SettingsNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Settings" className="flex gap-1 overflow-x-auto md:flex-col">
      {ITEMS.map((i) => (
        <Link
          key={i.href}
          href={i.href}
          aria-current={pathname === i.href ? "page" : undefined}
          className={cn(
            "whitespace-nowrap rounded-xl px-3 py-2 text-[14px] font-medium transition-colors",
            pathname === i.href ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
          )}
        >
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
