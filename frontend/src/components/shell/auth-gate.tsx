"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useApp } from "@/components/app-provider";
import { RelayMark } from "./shell";

/** Client-side guard. The API enforces sessions; this just routes signed-out visitors to sign-in. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, workspace, authLoading } = useApp();
  const router = useRouter();
  const pathname = usePathname();
  const needsSetup = !!user && (!workspace || !user.onboardedAt);

  useEffect(() => {
    if (authLoading) return;
    if (!user) router.replace(`/sign-in?next=${encodeURIComponent(pathname)}`);
    else if (needsSetup) router.replace("/welcome");
  }, [authLoading, user, needsSetup, router, pathname]);

  if (!user || needsSetup) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-busy="true">
        <RelayMark className="size-8 animate-pulse" />
      </div>
    );
  }
  return <>{children}</>;
}
