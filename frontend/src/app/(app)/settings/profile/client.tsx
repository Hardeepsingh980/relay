"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useApp } from "@/components/app-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Labeled } from "@/components/workspace/connections";
import { api } from "@/lib/api";

export function ProfileSettings() {
  const { user, refreshMe, signOut } = useApp();
  const [name, setName] = useState(user?.name ?? "");
  if (!user) return null;
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-[20px] font-semibold">Profile</h2>
        <p className="mt-1 text-muted-foreground">{user.email}{user.google ? " · signs in with Google" : ""}</p>
      </div>
      <form
        className="rounded-2xl border bg-card p-5"
        onSubmit={async (e) => {
          e.preventDefault();
          await api.patch("/api/me", { name });
          refreshMe();
          toast.success("Saved");
        }}
      >
        <Labeled label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
        </Labeled>
        <Button type="submit" className="mt-4" disabled={name.trim().length < 2 || name === user.name}>
          Save
        </Button>
      </form>
      <div className="flex items-center justify-between rounded-2xl border bg-card p-5">
        <div>
          <p className="font-medium">Sign out</p>
          <p className="text-[14px] text-muted-foreground">On this browser only.</p>
        </div>
        <Button variant="quiet" onClick={() => signOut()}>
          Sign out
        </Button>
      </div>
    </div>
  );
}
