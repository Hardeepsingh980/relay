"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { useApp } from "@/components/app-provider";
import { AuthForm } from "@/components/auth/auth-form";
import { RelayMark } from "@/components/shell/shell";
import { Button } from "@/components/ui/button";
import { api, fetcher } from "@/lib/api";

interface InviteInfo {
  email: string;
  role: string;
  status: string;
  workspace: string;
  invitedBy: string | null;
  valid: boolean;
}

export function JoinClient({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const { data, error } = useSWR<InviteInfo>(`/api/invites/${token}`, fetcher, { shouldRetryOnError: false });
  const { user, authLoading, refreshMe } = useApp();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const accept = async () => {
    setBusy(true);
    try {
      await api.post(`/api/invites/${token}/accept`);
      await refreshMe();
      router.replace("/welcome");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Join failed. Try again.");
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-dvh flex-col items-center px-5 py-10">
      <Link href="/" className="flex items-center gap-2" aria-label="Relay home">
        <RelayMark />
        <span className="text-[17px] font-semibold tracking-[-0.2px]">Relay</span>
      </Link>
      <div className="mt-12 w-full max-w-[440px]">
        {error ? (
          <div className="rounded-3xl border bg-card p-8 text-center">
            <p className="text-heading">This invite link is not valid</p>
            <p className="mt-2 text-muted-foreground">Ask the person who invited you for a new link.</p>
            <Button asChild className="mt-6">
              <Link href="/">Go to Relay</Link>
            </Button>
          </div>
        ) : !data || authLoading ? (
          <div className="h-64 animate-pulse rounded-3xl bg-secondary" />
        ) : (
          <>
            <div className="rounded-3xl bg-lavender p-8 text-center">
              <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-card text-[22px] font-semibold">
                {data.workspace[0]?.toUpperCase()}
              </span>
              <p className="mt-4 text-[13px] text-foreground/70">{data.invitedBy ? `${data.invitedBy} invited you to` : "You are invited to"}</p>
              <h1 className="mt-1 text-heading">{data.workspace}</h1>
              <p className="mt-2 text-[14px] text-foreground/70">
                as {data.role === "admin" ? "an admin" : "a member"} · {data.email}
              </p>
            </div>
            <div className="mt-6 rounded-3xl border bg-card p-8">
              {!data.valid ? (
                <div className="text-center">
                  <p className="font-medium">Someone already used this invite</p>
                  <Button asChild className="mt-4">
                    <Link href="/sign-in">Sign in</Link>
                  </Button>
                </div>
              ) : user ? (
                user.email === data.email ? (
                  <div className="text-center">
                    <p className="text-muted-foreground">Signed in as {user.email}</p>
                    <Button size="lg" className="mt-4 w-full" onClick={accept} disabled={busy}>
                      {busy ? <Loader2 className="animate-spin" /> : null} Join {data.workspace}
                    </Button>
                  </div>
                ) : (
                  <p className="text-center text-muted-foreground">
                    This invite is for {data.email}, but you are signed in as {user.email}. To accept it, sign out and sign in as {data.email}.
                  </p>
                )
              ) : (
                <AuthForm mode="sign-up" invite={token} lockedEmail={data.email} compact />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
