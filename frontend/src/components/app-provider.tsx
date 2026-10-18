"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import useSWR, { SWRConfig, useSWRConfig } from "swr";

import { ApiError, authApi, currentPersona, fetcher, storePersona, type Me, type User, type WorkspaceInfo } from "@/lib/api";
import type { Persona, Session, SourceRef } from "@/lib/types";

interface AppCtx {
  user: User | null;
  workspace: WorkspaceInfo | null;
  workspaces: WorkspaceInfo[];
  refreshMe: () => void;
  authLoading: boolean;
  signOut: () => Promise<void>;
  persona: string;
  personaInfo: Persona | undefined;
  setPersona: (id: string) => void;
  session: Session | undefined;
  source: SourceRef | null;
  openSource: (s: SourceRef) => void;
  closeSource: () => void;
  askOpen: boolean;
  askSeed: string;
  openAsk: (q?: string) => void;
  closeAsk: () => void;
}

const Ctx = createContext<AppCtx | null>(null);

/** The sample company this workspace runs on (Cheerio, Lumen, ...). */
export function useCompany() {
  const { session } = useApp();
  return session?.demo.company ?? "the company";
}

export function useApp() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useApp outside AppProvider");
  return c;
}

function Inner({ children }: { children: React.ReactNode }) {
  const [persona, setPersonaState] = useState("");
  const [source, setSource] = useState<SourceRef | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  const [askSeed, setAskSeed] = useState("");
  const { mutate } = useSWRConfig();
  const router = useRouter();
  const { data: me, error: meError, isLoading: authLoading, mutate: mutateMe } = useSWR<Me>("/api/me", fetcher, {
    shouldRetryOnError: (e) => !(e instanceof ApiError && e.status === 401),
    revalidateOnFocus: true,
  });
  const user = meError ? null : me?.user ?? null;
  const workspace = meError ? null : me?.workspace ?? null;
  const { data: session } = useSWR<Session>(workspace ? "/api/session" : null, fetcher, { refreshInterval: 60_000 });

  const signOut = useCallback(async () => {
    await authApi.signOut().catch(() => null);
    await mutateMe(undefined, { revalidate: false });
    await mutate(() => true, undefined, { revalidate: false });
    router.replace("/");
  }, [mutate, mutateMe, router]);

  useEffect(() => {
    // localStorage is only readable after mount (prerendering runs without it).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPersonaState(currentPersona());
  }, []);

  // First visit on this browser: start from the persona chosen during onboarding.
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("relay.persona");
    } catch {
      /* storage unavailable */
    }
    if (!stored && me?.user.defaultPersona) {
      storePersona(me.user.defaultPersona);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPersonaState(me.user.defaultPersona);
    }
  }, [me?.user.defaultPersona]);

  const setPersona = useCallback(
    (id: string) => {
      storePersona(id);
      setPersonaState(id);
      mutate(() => true, undefined, { revalidate: true });
    },
    [mutate],
  );

  const openAsk = useCallback((q?: string) => {
    setAskSeed(q ?? "");
    setAskOpen(true);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAskSeed("");
        setAskOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo<AppCtx>(() => {
    const personaInfo = session?.personas.find((p) => p.id === persona) ?? session?.personas[0];
    // Signed in from the team picker: you are that teammate, so greetings and menus use their name.
    const shown = user?.sandbox && personaInfo ? { ...user, name: personaInfo.name } : user;
    return {
      user: shown,
      workspace,
      workspaces: me?.workspaces ?? [],
      refreshMe: () => mutateMe(),
      authLoading,
      signOut,
      persona: session?.personas.some((p) => p.id === persona) ? persona : session?.personas[0]?.id ?? persona,
      personaInfo,
      setPersona,
      session,
      source,
      openSource: setSource,
      closeSource: () => setSource(null),
      askOpen,
      askSeed,
      openAsk,
      closeAsk: () => setAskOpen(false),
    };
  }, [user, workspace, me?.workspaces, mutateMe, authLoading, signOut, persona, session, setPersona, source, askOpen, askSeed, openAsk],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ fetcher, revalidateOnFocus: false, keepPreviousData: true }}>
      <Inner>{children}</Inner>
    </SWRConfig>
  );
}
