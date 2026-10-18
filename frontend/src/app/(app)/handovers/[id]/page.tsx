import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/relay/primitives";
import { HandoverClient } from "./handover-client";

export const metadata: Metadata = { title: "Handover" };

export default function Page({ params }: PageProps<"/handovers/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-[1180px] px-8 py-10"><Skeleton className="h-24" /><Skeleton className="mt-6 h-[480px]" /></div>}>
      <HandoverClient params={params} />
    </Suspense>
  );
}
