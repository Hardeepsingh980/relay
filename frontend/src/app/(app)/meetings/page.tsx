import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/relay/primitives";
import { MeetingsClient } from "./meetings-client";

export const metadata: Metadata = { title: "Meetings" };

export default function Page() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-[1100px] px-8 py-10"><Skeleton className="h-24" /><Skeleton className="mt-6 h-[420px]" /></div>}>
      <MeetingsClient />
    </Suspense>
  );
}
