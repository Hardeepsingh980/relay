import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const mono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Relay: keep your customers, and keep what your people know", template: "%s · Relay" },
  description:
    "Relay puts your customer records, support tickets, product usage, Slack, docs, Jira and calls in one graph. It finds customers at risk of leaving, saves what employees know before they leave, and helps your sales team on live calls.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${mono.variable} h-full`}>
      <body className="min-h-full">
        <TooltipProvider delayDuration={250}>
          {children}
          <Toaster position="bottom-right" />
        </TooltipProvider>
      </body>
    </html>
  );
}
