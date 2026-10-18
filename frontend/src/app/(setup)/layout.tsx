import { AppProvider } from "@/components/app-provider";

// Signed-in screens wait for the session (client-side gate), so navigations into them may block.
export const instant = false;

export default function SetupLayout({ children }: LayoutProps<"/">) {
  return <AppProvider>{children}</AppProvider>;
}
