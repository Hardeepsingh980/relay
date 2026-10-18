"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { AuthForm } from "@/components/auth/auth-form";
import { TeamPicker } from "@/components/auth/team-picker";
import { cn } from "@/lib/utils";

export function SignIn() {
  const params = useSearchParams();
  const [email, setEmail] = useState(Boolean(params.get("invite") || params.get("error")));
  return (
    <div>
      <h1 className="text-[32px] font-semibold leading-[1.1] tracking-[-0.4px]">Sign in to Relay</h1>
      <p className="mt-2 text-[15px] text-muted-foreground">
        Pick someone at Cheerio. You get your own copy of the workspace, so try anything.
      </p>
      <div className="mt-7">
        <TeamPicker next={params.get("next")} />
      </div>
      <p className="mt-3 text-[12px] text-muted-foreground">Cheerio is a sample company. Its people, customers and messages are synthetic.</p>

      <div className="mt-8 border-t pt-5">
        <button
          type="button"
          onClick={() => setEmail((v) => !v)}
          aria-expanded={email}
          className="flex w-full items-center justify-between text-[14px] font-medium"
        >
          Sign in with email
          <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", email && "rotate-180")} />
        </button>
        {email ? (
          <div className="mt-5">
            <AuthForm mode="sign-in" bare />
          </div>
        ) : null}
      </div>
    </div>
  );
}
