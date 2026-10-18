"use client";

import { useState } from "react";
import { Search } from "lucide-react";

import { useApp, useCompany } from "@/components/app-provider";
import { AskResult, useAsk } from "@/components/relay/ask-bar";
import { Card, PageHeader } from "@/components/relay/primitives";

export function AskClient() {
  const company = useCompany();
  const { session } = useApp();
  const [q, setQ] = useState("");
  const a = useAsk();
  return (
    <div className="mx-auto max-w-[760px] px-4 py-10 md:px-8">
      <PageHeader eyebrow="Knowledge" title="Ask" subtitle={`Answers from ${company}'s graph, with sources.`} />
      <Card className="mt-8 overflow-hidden">
        <form
          className="flex items-center gap-3 border-b px-4"
          onSubmit={(e) => {
            e.preventDefault();
            a.ask(q);
          }}
        >
          <Search className="size-4 text-muted-foreground" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={session?.suggestions?.[0] ?? "Ask a question"}
            aria-label="Ask a question"
            className="h-14 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
          />
        </form>
        <AskResult a={a} onAsk={(x) => { setQ(x); a.ask(x); }} />
      </Card>
    </div>
  );
}
