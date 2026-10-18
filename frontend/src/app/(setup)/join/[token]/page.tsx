import type { Metadata } from "next";
import { Suspense } from "react";

import { JoinClient } from "./join-client";

export const metadata: Metadata = { title: "Join a workspace" };

export default function Page({ params }: PageProps<"/join/[token]">) {
  return (
    <Suspense fallback={<div className="min-h-dvh" />}>
      <JoinClient params={params} />
    </Suspense>
  );
}
