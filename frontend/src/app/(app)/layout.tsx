import { Suspense } from "react";

import { AppProvider } from "@/components/app-provider";
import { AskBar } from "@/components/relay/ask-bar";
import { SourceDrawer } from "@/components/relay/source-drawer";
import { AuthGate } from "@/components/shell/auth-gate";
import { Shell } from "@/components/shell/shell";

// Signed-in screens wait for the session (client-side gate), so navigations into them may block.
export const instant = false;

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AppProvider>
      <Suspense fallback={<div className="min-h-dvh" />}>
        <AuthGate>
          <Shell>{children}</Shell>
          <SourceDrawer />
          <AskBar />
        </AuthGate>
      </Suspense>
    </AppProvider>
  );
}
