import type { Metadata } from "next";
import { Suspense } from "react";

import { Onboarding } from "./onboarding";

export const metadata: Metadata = { title: "Set up Relay" };

export default function Page() {
  return (
    <Suspense fallback={<div className="min-h-dvh" />}>
      <Onboarding />
    </Suspense>
  );
}
