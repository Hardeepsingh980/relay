import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/relay/primitives";
import { AccountClient } from "./account-client";

export const metadata: Metadata = { title: "Account" };

export default function Page({ params }: PageProps<"/accounts/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-[1240px] px-8 py-10"><Skeleton className="h-24" /><Skeleton className="mt-6 h-[480px]" /></div>}>
      <AccountClient params={params} />
    </Suspense>
  );
}
