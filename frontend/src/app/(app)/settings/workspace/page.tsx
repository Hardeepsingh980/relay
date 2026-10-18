import { Suspense } from "react";

import { WorkspaceSettings } from "./client";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <WorkspaceSettings />
    </Suspense>
  );
}
