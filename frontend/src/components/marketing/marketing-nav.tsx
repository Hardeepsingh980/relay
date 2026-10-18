"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";

import { RelayMark } from "@/components/shell/shell";
import { Button } from "@/components/ui/button";
import { authApi } from "@/lib/api";
import { cn } from "@/lib/utils";

export function useSignedIn() {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  useEffect(() => {
    authApi.me().then(() => setSignedIn(true)).catch(() => setSignedIn(false));
  }, []);
  return signedIn;
}

const LINKS = [
  ["Product", "#product"],
  ["How agents think", "#trace"],
  ["Your own repo", "#repos"],
  ["How it works", "#how"],
];

/** True once the page has scrolled a little, so the bar gets its surface. */
function useScrolled() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 8);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);
  return scrolled;
}

export function MarketingNav() {
  const signedIn = useSignedIn();
  const scrolled = useScrolled();
  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-40 border-b transition-[background-color,border-color,box-shadow] duration-300",
        scrolled ? "border-border bg-background/85 shadow-[0_1px_12px_rgba(15,23,42,0.05)] backdrop-blur-md" : "border-transparent bg-transparent",
      )}
    >
      <nav aria-label="Main" className="mx-auto flex h-16 max-w-[1240px] items-center px-5 md:px-8">
        <Link href="/" className="flex items-center gap-2" aria-label="Relay home">
          <RelayMark />
          <span className="text-[17px] font-semibold tracking-[-0.2px]">Relay</span>
        </Link>
        <div className="ml-10 hidden items-center gap-7 text-[14.5px] text-muted-foreground md:flex">
          {LINKS.map(([label, href]) => (
            <a key={href} href={href} className="hover:text-foreground">
              {label}
            </a>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {signedIn ? (
            <Button asChild>
              <Link href="/home">
                Open Relay <ArrowRight />
              </Link>
            </Button>
          ) : (
            <>
              <Link href="/sign-in" className="rounded-full px-3 py-1.5 text-[14.5px] font-medium text-muted-foreground hover:text-foreground">
                Sign in
              </Link>
              <Button asChild>
                <Link href="/sign-in">Try Relay</Link>
              </Button>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
