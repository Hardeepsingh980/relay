import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/relay/primitives";
import { AccountsClient } from "./accounts-client";

export const metadata: Metadata = { title: "Risk Radar" };

export default function Page() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-[1240px] px-8 py-10"><Skeleton className="h-24" /><Skeleton className="mt-6 h-[480px]" /></div>}>
      <AccountsClient />
    </Suspense>
  );
}
