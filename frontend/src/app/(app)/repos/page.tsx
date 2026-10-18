import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/relay/primitives";
import { ReposClient } from "./repos-client";

export const metadata: Metadata = { title: "Repo knowledge" };

export default function Page() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-[1240px] px-8 py-10"><Skeleton className="h-24" /><Skeleton className="mt-6 h-[320px]" /></div>}>
      <ReposClient />
    </Suspense>
  );
}
