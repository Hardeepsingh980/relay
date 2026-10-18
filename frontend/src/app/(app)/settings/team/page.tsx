import { Suspense } from "react";

import { TeamSettings } from "./client";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <TeamSettings />
    </Suspense>
  );
}
