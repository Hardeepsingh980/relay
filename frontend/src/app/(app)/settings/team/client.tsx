"use client";

import { useSWRConfig } from "swr";

import { useApp } from "@/components/app-provider";
import { InviteBox, TeamList } from "@/components/workspace/team";

export function TeamSettings() {
  const { workspace } = useApp();
  const { mutate } = useSWRConfig();
  const admin = workspace?.role === "owner" || workspace?.role === "admin";
  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-[20px] font-semibold">Teammates</h2>
        <p className="mt-1 text-muted-foreground">Admins can invite people and connect tools.</p>
      </div>
      {admin ? (
        <div className="rounded-2xl border bg-card p-5">
          <p className="mb-3 font-medium">Invite people</p>
          <InviteBox onSent={() => mutate("/api/workspace/members")} />
        </div>
      ) : null}
      <TeamList />
    </div>
  );
}
