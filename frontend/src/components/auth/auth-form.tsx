"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";

import { GoogleButton } from "@/components/auth/google-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi, safeNext } from "@/lib/api";

type Mode = "sign-in" | "sign-up";

export function AuthForm({ mode, invite, lockedEmail, compact, bare }: { mode: Mode; invite?: string; lockedEmail?: string; compact?: boolean; bare?: boolean }) {
  const router = useRouter();
  const params = useSearchParams();
  const rawNext = params.get("next");
  const next = safeNext(rawNext);
  const inviteToken = invite ?? params.get("invite");
  const [name, setName] = useState("");
  const [email, setEmail] = useState(lockedEmail ?? "");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(params.get("error"));

  // Already signed in? Skip the form (unless we're accepting an invite, handled by the join page).
  useEffect(() => {
    if (inviteToken) return;
    authApi
      .me()
      .then((r) => router.replace(r.workspace && r.user.onboardedAt ? next : "/welcome"))
      .catch(() => null);
  }, [router, next, inviteToken]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "sign-up") {
        await authApi.signUp(name, email, password, inviteToken);
        router.replace("/welcome");
        return;
      }
      await authApi.signIn(email, password, inviteToken);
      const me = await authApi.me();
      router.replace(!inviteToken && me.workspace && me.user.onboardedAt ? next : "/welcome");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong. Try again.";
      setError(msg === "Failed to fetch" ? "Relay cannot connect to its server. Make sure that the Relay API is running." : msg);
      setBusy(false);
    }
  };

  const signUp = mode === "sign-up";
  const qs = new URLSearchParams();
  if (rawNext) qs.set("next", next);
  if (inviteToken && !invite) qs.set("invite", inviteToken);
  const switchHref = `${signUp ? "/sign-in" : "/sign-up"}${qs.toString() ? `?${qs}` : ""}`;

  return (
    <div>
      {bare ? null : !compact ? (
        <>
          <h1 className="text-[36px] font-semibold leading-[1.1] tracking-[-0.4px]">{signUp ? "Create your account" : "Welcome back"}</h1>
          <p className="mt-2 text-subheading text-muted-foreground">
            {signUp ? "Set up a workspace and run your first handover in minutes." : "Sign in to continue your work."}
          </p>
        </>
      ) : (
        <p className="mb-5 text-center text-[15px] font-medium">Create your account to join</p>
      )}

      <GoogleButton next={signUp ? "/welcome" : next} invite={inviteToken} className={compact || bare ? "mb-6" : "mt-8 -mb-2"} />

      <form onSubmit={submit} className={compact || bare ? "space-y-4" : "mt-8 space-y-4"} noValidate>
        {signUp ? (
          <Field label="Full name" htmlFor="name">
            <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required className="h-11" />
          </Field>
        ) : null}
        <Field label="Work email" htmlFor="email">
          <Input
            id="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            value={email}
            readOnly={!!lockedEmail}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="h-11 read-only:bg-secondary read-only:text-muted-foreground"
          />
        </Field>
        <Field label="Password" htmlFor="password" hint={signUp ? "At least 8 characters" : undefined}>
          <div className="relative">
            <Input
              id="password"
              type={show ? "text" : "password"}
              autoComplete={signUp ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={signUp ? 8 : undefined}
              className="h-11 pr-11"
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              aria-label={show ? "Hide password" : "Show password"}
              className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted-foreground hover:text-foreground"
            >
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </Field>

        {error ? (
          <p role="alert" className="rounded-2xl bg-risk-soft px-4 py-2.5 text-sm text-risk">
            {error}
          </p>
        ) : null}

        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : null}
          {signUp ? (busy ? "Creating account…" : "Create account") : busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-center text-[14px] text-muted-foreground">
        {signUp ? "Already have an account? " : "New to Relay? "}
        <Link href={invite ? `/sign-in?invite=${invite}&next=${encodeURIComponent(`/join/${invite}`)}` : switchHref} className="font-medium text-foreground underline-offset-4 hover:text-primary hover:underline">
          {signUp ? "Sign in" : "Create an account"}
        </Link>
      </p>
    </div>
  );
}

function Field({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <label htmlFor={htmlFor} className="text-sm font-medium">
          {label}
        </label>
        {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}
