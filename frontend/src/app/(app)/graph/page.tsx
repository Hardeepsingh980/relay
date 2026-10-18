import type { Metadata } from "next";
import { Suspense } from "react";

import { GraphClient } from "./graph-client";

export const metadata: Metadata = { title: "Knowledge graph" };

export default function Page() {
  return (
    <Suspense fallback={<div className="fixed inset-x-0 bottom-0 top-16 bg-[#070b14] md:left-[232px]" />}>
      <GraphClient />
    </Suspense>
  );
}
