import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/relay/primitives";
import { MeetingClient } from "./meeting-client";

export const metadata: Metadata = { title: "Meeting" };

export default function Page({ params }: PageProps<"/meetings/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-[1240px] px-8 py-10"><Skeleton className="h-24" /><Skeleton className="mt-6 h-[480px]" /></div>}>
      <MeetingClient params={params} />
    </Suspense>
  );
}
