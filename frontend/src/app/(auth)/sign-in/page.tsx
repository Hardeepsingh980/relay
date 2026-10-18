import type { Metadata } from "next";
import { Suspense } from "react";

import { SignIn } from "./sign-in-client";

export const metadata: Metadata = { title: "Sign in" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <SignIn />
    </Suspense>
  );
}
