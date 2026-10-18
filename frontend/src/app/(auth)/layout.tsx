import Link from "next/link";

import { LivePreview } from "@/components/auth/team-picker";
import { RelayMark } from "@/components/shell/shell";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex flex-col px-6 py-6 sm:px-12">
        <Link href="/" className="inline-flex w-fit items-center gap-2" aria-label="Relay home">
          <RelayMark />
          <span className="text-[17px] font-semibold tracking-[-0.2px]">Relay</span>
        </Link>
        <main className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[440px]">{children}</div>
        </main>
      </div>
      <aside className="hidden border-l bg-secondary/40 lg:block">
        <div className="flex h-full flex-col justify-center px-14">
          <div className="mx-auto w-full max-w-[480px]">
            <p className="text-[13px] font-medium text-muted-foreground">One graph per company</p>
            <p className="mt-2 text-[28px] font-semibold leading-tight tracking-[-0.3px]">
              Customers, people and work in one FalkorDB graph. Agents read it and act.
            </p>
            <LivePreview className="mt-8" />
          </div>
        </div>
      </aside>
    </div>
  );
}
