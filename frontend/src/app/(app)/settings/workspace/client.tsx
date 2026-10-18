"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useApp } from "@/components/app-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Labeled } from "@/components/workspace/connections";
import { api } from "@/lib/api";

export function WorkspaceSettings() {
  const { workspace, refreshMe, session } = useApp();
  const [name, setName] = useState(workspace?.name ?? "");
  const admin = workspace?.role === "owner" || workspace?.role === "admin";
  if (!workspace) return null;
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-[20px] font-semibold">Workspace</h2>
        <p className="mt-1 text-muted-foreground">You are {workspace.role === "owner" ? "the owner" : `a${workspace.role === "admin" ? "n admin" : " member"}`} of this workspace.</p>
      </div>
      <form
        className="rounded-2xl border bg-card p-5"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.patch("/api/workspace", { name });
            refreshMe();
            toast.success("Workspace renamed");
          } catch (err) {
            toast.error(err instanceof Error ? err.message : "Could not rename");
          }
        }}
      >
        <Labeled label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} disabled={!admin} />
        </Labeled>
        {admin ? (
          <Button type="submit" className="mt-4" disabled={name.trim().length < 2 || name === workspace.name}>
            Save
          </Button>
        ) : null}
      </form>
      <div className="rounded-2xl border bg-card p-5">
        <p className="font-medium">Data</p>
        <p className="mt-1 text-[14px] text-muted-foreground">
          {session?.demo.company ?? workspace.name} data, in this workspace&apos;s own FalkorDB graph.
        </p>
      </div>
    </div>
  );
}
