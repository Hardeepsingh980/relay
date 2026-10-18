import { Suspense } from "react";

import { ConnectionsSettings } from "./client";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ConnectionsSettings />
    </Suspense>
  );
}
