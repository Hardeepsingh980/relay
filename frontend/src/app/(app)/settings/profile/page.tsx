import { Suspense } from "react";

import { ProfileSettings } from "./client";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ProfileSettings />
    </Suspense>
  );
}
