"use client";

import { useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import { useApp } from "@/components/app-provider";
import { ConnectionsGrid } from "@/components/workspace/connections";

export function ConnectionsSettings() {
  const params = useSearchParams();
  const { workspace } = useApp();
  useEffect(() => {
    if (params.get("connected") === "google")
      toast.success("Google connected", { description: "After you approve an intro or an email, Relay books the Calendar event or saves the Gmail draft." });
    if (params.get("error")) toast.error(params.get("error")!);
  }, [params]);
  return (
    <div>
      <h2 className="text-[20px] font-semibold">Connections</h2>
      <p className="mt-1 text-muted-foreground">
        Connect your tools with an API key or OAuth, and add MCP servers. Relay checks every credential with a live call before it saves it.
      </p>
      <div className="mt-6">
        <ConnectionsGrid canManage={workspace?.role === "owner" || workspace?.role === "admin"} />
      </div>
    </div>
  );
}
