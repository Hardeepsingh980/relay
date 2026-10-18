import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/relay/primitives";
import { ProfileClient } from "./profile-client";

export const metadata: Metadata = { title: "Person" };

export default function Page({ params }: PageProps<"/people/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-[960px] px-8 py-10"><Skeleton className="h-40" /></div>}>
      <ProfileClient params={params} />
    </Suspense>
  );
}
