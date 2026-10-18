"use client";

import { useEffect, useState } from "react";

import { authApi } from "@/lib/api";

function GoogleG() {
  return (
    <svg viewBox="0 0 48 48" className="size-[18px]" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.6-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.6-.4-3.5z" />
    </svg>
  );
}

/** "Continue with Google", shown only when the server has a Google OAuth client (with an "or" divider below). */
export function GoogleButton({ next, invite, label = "Continue with Google", className }: {
  next?: string | null; invite?: string | null; label?: string; className?: string;
}) {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    authApi.providers().then((p) => setEnabled(p.google)).catch(() => setEnabled(false));
  }, []);
  if (!enabled) return null;
  return (
    <div className={className}>
      <a
        href={authApi.googleUrl(next, invite)}
        className="flex h-11 w-full items-center justify-center gap-2.5 rounded-full border bg-card text-[15px] font-medium transition-colors hover:bg-secondary"
      >
        <GoogleG />
        {label}
      </a>
      <div className="mt-6 flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" />
        or with email
        <span className="h-px flex-1 bg-border" />
      </div>
    </div>
  );
}
