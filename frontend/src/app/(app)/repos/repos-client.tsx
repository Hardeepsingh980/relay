"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ArrowRight, Code2, ExternalLink, Loader2, TriangleAlert, UserMinus, X } from "lucide-react";

import { Card, CardTitle, EmptyState, PageHeader, Skeleton } from "@/components/relay/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, enc } from "@/lib/api";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ types */

type Stage = "queued" | "cloning" | "parsing" | "scoring" | "done" | "failed";

interface Knower {
  id: string;
  name: string;
  score: number;
  commits?: number;
  lastSeen?: string | null;
}

interface ModuleRow {
  id: string;
  path: string;
  commits: number;
  lastCommit: string | null;
  people: number;
  busFactor: number;
  strong: number;
  knowers: Knower[];
}

interface OnlyOneRow {
  id: string;
  path: string;
  commits: number;
  lastCommit: string | null;
  personId: string;
  person: string;
  score: number;
  personCommits: number;
  nextBest: Knower | null;
}

interface PersonRow {
  id: string;
  name: string;
  commits: number;
  lastSeen: string | null;
  modulesKnown: number;
  strongIn: number;
  onlyThey: number;
  centrality: number | null;
  topModules: { path: string; score: number }[];
}

interface CentralRow {
  id: string;
  name: string;
  centrality: number;
  modulesKnown: number | null;
  commits: number | null;
}

interface QueryRun {
  name: string;
  title: string;
  cypher: string;
  params: Record<string, unknown>;
  ms: number;
  rows: number;
}

interface Summary {
  repo: string;
  url: string;
  graph: string;
  asOf: string;
  historyWindow: string;
  commits: number;
  people: number;
  modules: number;
  firstCommit: string | null;
  lastCommit: string | null;
  onlyOneCount: number;
  modulesTable: ModuleRow[];
  onlyOne: OnlyOneRow[];
  peopleTable: PersonRow[];
  central: CentralRow[];
  skipped: Record<string, number>;
  graphSize: { ms: number; nodes: number; edges: number };
  thresholds: { strong: number; credible: number; halfLifeDays: number; saturation: number };
  queries: QueryRun[];
  timings: Record<string, number>;
}

interface Job {
  id: string;
  repo: string;
  url: string;
  status: Stage;
  message: string;
  progress: Record<string, number>;
  createdAt: number;
  startedAt: number | null;
  finishedAt: number | null;
  summary: Summary | null;
}

interface RecentRow {
  id: string;
  repo: string;
  status: Stage;
  message: string;
  finishedAt: number | null;
  commits: number | null;
  people: number | null;
  onlyOneCount: number | null;
}

interface Departure {
  person: { id: string; name: string; commits: number; lastCommit: string | null; centrality: number | null };
  orphaned: { id: string; path: string; commits: number; lastCommit: string | null; score: number; personCommits: number; nextBest: Knower | null }[];
  covered: { id: string; path: string; commits: number; score: number; busFactorAfter: number; coveredBy: Knower[] }[];
  queries: QueryRun[];
}

interface AskResult {
  answer: string;
  facts: { id: string; kind: string; text: string }[];
  factsConsidered: number;
  model: string;
  ms: number;
  queries: QueryRun[];
}

/* ---------------------------------------------------------------- helpers */

const RUNNING = new Set<Stage>(["queued", "cloning", "parsing", "scoring"]);
const STEPS: { id: Stage; label: string }[] = [
  { id: "cloning", label: "Clone" },
  { id: "parsing", label: "Read history" },
  { id: "scoring", label: "Score in the graph" },
];
const EXAMPLES = ["https://github.com/FalkorDB/falkordb-py", "https://github.com/pallets/click", "https://github.com/tiangolo/typer"];

const num = (n: number | null | undefined) => (n ?? 0).toLocaleString("en-US");
const score = (s: number | null | undefined) => (s == null ? "—" : s.toFixed(2));

function day(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

function errorText(e: unknown, fallback: string) {
  return e instanceof Error && e.message ? e.message : fallback;
}

function BusFactor({ n }: { n: number }) {
  return (
    <span
      className={cn(
        "inline-flex min-w-7 justify-center rounded-full px-2 py-0.5 text-[12.5px] font-semibold tabular",
        n === 0 ? "bg-risk-soft text-risk" : n === 1 ? "bg-warn-soft text-warn" : "bg-secondary text-foreground/80",
      )}
    >
      {n}
    </span>
  );
}

function Cypher({ queries }: { queries: QueryRun[] }) {
  return (
    <ol className="space-y-3">
      {queries.map((q, i) => (
        <li key={`${q.name}-${i}`} className="rounded-2xl border bg-background">
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-b px-4 py-2">
            <span className="text-[13px] font-medium">{q.title}</span>
            <span className="text-[12px] text-muted-foreground tabular">
              {q.ms.toFixed(1)} ms · {num(q.rows)} {q.rows === 1 ? "row" : "rows"}
            </span>
          </div>
          <pre className="overflow-x-auto px-4 py-3 font-mono text-[12px] leading-relaxed text-foreground/85">{q.cypher}</pre>
          {Object.keys(q.params ?? {}).length ? (
            <p className="border-t px-4 py-2 font-mono text-[11.5px] text-muted-foreground">params {JSON.stringify(q.params)}</p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/* ------------------------------------------------------------------ page */

export function ReposClient() {
  const params = useSearchParams();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const jobId = params.get("a");
  const [url, setUrl] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { data: job, error: jobError } = useSWR<Job>(jobId ? `/api/repos/${enc(jobId)}` : null, {
    refreshInterval: (d) => (!d || RUNNING.has(d.status) ? 1000 : 0),
    keepPreviousData: false,
  });
  const { data: recent } = useSWR<{ analyses: RecentRow[] }>("/api/repos");
  const finished = job && !RUNNING.has(job.status);
  useEffect(() => {
    if (finished) mutate("/api/repos");
  }, [finished, mutate]);

  const analyze = async (target: string) => {
    const value = target.trim();
    if (!value) return;
    setUrl(value);
    setStartError(null);
    setStarting(true);
    try {
      const r = await api.post<{ id: string; status: Stage }>("/api/repos", { url: value });
      router.replace(`/repos?a=${enc(r.id)}`, { scroll: false });
      mutate("/api/repos");
    } catch (e) {
      setStartError(errorText(e, "Could not start the analysis"));
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1240px] px-4 py-10 md:px-8">
      <PageHeader
        eyebrow="Knowledge · real data"
        title="Repo knowledge"
        subtitle="Analyze any public GitHub repo: who knows what, and what leaves when someone does."
      />

      <Card className="mt-8 p-5">
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            analyze(url);
          }}
        >
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            aria-label="GitHub repository URL"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            className="sm:flex-1"
          />
          <Button type="submit" disabled={starting || !url.trim()}>
            {starting ? <Loader2 className="size-4 animate-spin" /> : null}
            Analyze
          </Button>
        </form>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-muted-foreground">Try</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              disabled={starting}
              onClick={() => analyze(ex)}
              className="rounded-full border bg-card px-2.5 py-0.5 font-mono text-[12px] text-foreground/80 transition-colors hover:border-foreground/25 hover:text-foreground"
            >
              {ex.replace("https://github.com/", "")}
            </button>
          ))}
        </div>
        {startError ? (
          <p role="alert" className="mt-3 flex items-center gap-1.5 text-[13.5px] text-risk">
            <TriangleAlert className="size-4" aria-hidden /> {startError}
          </p>
        ) : null}
        <p className="mt-3 text-[12.5px] text-muted-foreground">
          Relay clones the default branch without file contents, reads up to 3,000 commits from the last two years, skips bots,
          lockfiles and generated folders, and builds a graph of people, modules and commits in FalkorDB.
        </p>
      </Card>

      {jobId && jobError ? (
        <div className="mt-6">
          <EmptyState title="Analysis not found" body={errorText(jobError, "This analysis is not available any more.")} />
        </div>
      ) : jobId && !job ? (
        <Skeleton className="mt-6 h-40" />
      ) : job && RUNNING.has(job.status) ? (
        <Progress job={job} />
      ) : job && job.status === "failed" ? (
        <Card className="mt-6 p-5">
          <CardTitle icon={TriangleAlert}>Could not analyze {job.repo}</CardTitle>
          <p className="mt-1 text-[14px] text-muted-foreground">{job.message}</p>
          <Button variant="quiet" size="sm" className="mt-4" onClick={() => analyze(job.url)}>
            Try again
          </Button>
        </Card>
      ) : job?.summary ? (
        <Results key={job.id} jobId={job.id} summary={job.summary} />
      ) : null}

      {!jobId && recent?.analyses.length ? (
        <Card className="mt-6">
          <div className="px-5 pt-4">
            <CardTitle>Recent analyses</CardTitle>
          </div>
          <ul className="mt-2 divide-y">
            {recent.analyses.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => router.replace(`/repos?a=${enc(a.id)}`, { scroll: false })}
                  className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-5 py-3 text-left transition-colors last:rounded-b-2xl hover:bg-background"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-[13px]">{a.repo}</span>
                    <span className="block truncate text-[12.5px] text-muted-foreground">
                      {a.status === "done"
                        ? `${num(a.commits)} commits · ${num(a.people)} people · ${num(a.onlyOneCount)} modules only one person knows`
                        : a.message}
                    </span>
                  </span>
                  <ArrowRight className="size-4 text-muted-foreground" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- progress */

function Progress({ job }: { job: Job }) {
  const at = STEPS.findIndex((s) => s.id === job.status);
  const p = job.progress ?? {};
  const counts =
    job.status === "cloning"
      ? `${(p.mb ?? 0).toFixed(1)} MB · ${num(p.seconds)} s`
      : job.status === "parsing" && p.commits != null
        ? `${num(p.commits)} commits · ${num(p.people)} people · ${num(p.modules)} modules`
        : job.status === "scoring" && p.commits != null
          ? `${num(p.written ?? 0)} of ${num(p.commits)} commits written · ${num(p.people)} people · ${num(p.modules)} modules`
          : null;
  return (
    <Card className="mt-6 p-5" aria-live="polite">
      <div className="flex items-center gap-2">
        <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />
        <h2 className="text-[16px] font-semibold">
          Analyzing <span className="font-mono text-[15px]">{job.repo}</span>
        </h2>
      </div>
      <ol className="mt-4 grid gap-2 sm:grid-cols-3">
        {STEPS.map((s, i) => (
          <li
            key={s.id}
            className={cn(
              "rounded-2xl border px-3 py-2 text-[13px]",
              i < at ? "bg-covered-soft text-covered" : i === at ? "border-foreground/20 bg-background font-medium" : "text-muted-foreground",
            )}
          >
            <span className="tabular">{i + 1}.</span> {s.label}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-[14px]">{job.message}</p>
      {counts ? <p className="mt-0.5 text-[13px] text-muted-foreground tabular">{counts}</p> : null}
    </Card>
  );
}

/* ---------------------------------------------------------------- results */

function Results({ jobId, summary: s }: { jobId: string; summary: Summary }) {
  const [showCypher, setShowCypher] = useState(false);
  const [allModules, setAllModules] = useState(false);
  const [allPeople, setAllPeople] = useState(false);
  const [dep, setDep] = useState<{ personId: string; name: string; data?: Departure; error?: string } | null>(null);
  const depRef = useRef<HTMLDivElement>(null);

  const orphaned = useMemo(() => new Set(dep?.data?.orphaned.map((m) => m.path) ?? []), [dep]);
  const modules = allModules ? s.modulesTable : s.modulesTable.slice(0, 20);
  const people = allPeople ? s.peopleTable : s.peopleTable.slice(0, 15);

  const preview = async (p: { id: string; name: string }) => {
    setDep({ personId: p.id, name: p.name });
    requestAnimationFrame(() => depRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    try {
      const data = await api.get<Departure>(`/api/repos/${enc(jobId)}/departure?person=${enc(p.id)}`);
      setDep((d) => (d?.personId === p.id ? { ...d, data } : d));
    } catch (e) {
      setDep((d) => (d?.personId === p.id ? { ...d, error: errorText(e, "Could not run the departure preview") } : d));
    }
  };

  const tiles = [
    { label: "Commits analyzed", value: s.commits, hint: `${day(s.firstCommit)} to ${day(s.lastCommit)}` },
    { label: "People", value: s.people, hint: s.skipped.bots ? `${num(s.skipped.bots)} bot commits skipped` : "after merging identities" },
    { label: "Modules", value: s.modules, hint: "top folders, lockfiles and builds skipped" },
    { label: "Only one person knows", value: s.onlyOneCount, hint: `strong above ${s.thresholds.strong}, nobody else above ${s.thresholds.credible}`, risk: s.onlyOneCount > 0 },
  ];

  return (
    <div className="mt-8 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 font-mono text-[18px] font-semibold hover:underline">
            {s.repo} <ExternalLink className="size-4 text-muted-foreground" aria-hidden />
          </a>
          <p className="text-[13px] text-muted-foreground">
            {s.historyWindow} · analyzed {day(s.asOf)} · graph <span className="font-mono">{s.graph}</span> with {num(s.graphSize.nodes)} nodes and{" "}
            {num(s.graphSize.edges)} edges
          </p>
        </div>
        <Button variant="quiet" size="sm" onClick={() => setShowCypher((v) => !v)} aria-expanded={showCypher}>
          <Code2 className="size-3.5" /> {showCypher ? "Hide Cypher" : "Show Cypher"}
        </Button>
      </div>

      {showCypher ? (
        <Card className="p-5">
          <CardTitle icon={Code2}>Queries behind this page</CardTitle>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            Each commit adds 0.5^(age in days / {s.thresholds.halfLifeDays}) to a person&apos;s weight on a module; score = 1 − exp(−weight /{" "}
            {s.thresholds.saturation}). Clone {num(s.timings.cloneMs)} ms, parse {num(s.timings.parseMs)} ms, graph write {num(s.timings.writeMs)} ms, scoring{" "}
            {num(s.timings.scoreMs)} ms.
          </p>
          <div className="mt-4">
            <Cypher queries={s.queries} />
          </div>
        </Card>
      ) : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((t) => (
          <Card key={t.label} className="p-4">
            <p className="text-[12.5px] font-medium text-muted-foreground">{t.label}</p>
            <p className={cn("mt-1 text-[28px] font-semibold leading-none tabular", t.risk && "text-risk")}>{num(t.value)}</p>
            <p className="mt-2 text-[12px] leading-snug text-muted-foreground">{t.hint}</p>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="p-5">
          <CardTitle>Only one person knows</CardTitle>
          <p className="mt-1 text-[12.5px] text-muted-foreground">Modules with one strong person and no credible second.</p>
          {s.onlyOne.length ? (
            <ul className="mt-3 divide-y">
              {s.onlyOne.map((o) => (
                <li key={o.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-[13px]">{o.path}</span>
                    <span className="block text-[12.5px] text-muted-foreground">
                      {o.nextBest ? `Next best: ${o.nextBest.name} (${score(o.nextBest.score)})` : "Nobody else has touched it"} · {num(o.commits)} commits
                    </span>
                  </span>
                  <span className="text-right text-[13px]">
                    <span className="font-medium">{o.person}</span> <span className="text-muted-foreground tabular">{score(o.score)}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 rounded-2xl bg-background px-4 py-6 text-center text-[13.5px] text-muted-foreground">
              Every module someone knows strongly has a credible second person.
            </p>
          )}
        </Card>

        <Card className="p-5">
          <CardTitle>Most central people</CardTitle>
          <p className="mt-1 text-[12.5px] text-muted-foreground">PageRank over who works on the same modules, pointing at the people who know them.</p>
          <ol className="mt-3 space-y-2">
            {s.central.slice(0, 8).map((c, i) => (
              <li key={c.id} className="flex items-baseline justify-between gap-3 text-[13.5px]">
                <span className="min-w-0 truncate">
                  <span className="mr-2 text-muted-foreground tabular">{i + 1}</span>
                  {c.name}
                </span>
                <span className="text-muted-foreground tabular">{c.centrality.toFixed(3)}</span>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <AskBox jobId={jobId} summary={s} showCypher={showCypher} />

      <Card className="overflow-hidden">
        <div className="px-5 pt-4">
          <CardTitle>People</CardTitle>
          <p className="mt-1 text-[12.5px] text-muted-foreground">Modules known means a score above {s.thresholds.credible}.</p>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-[13.5px]">
            <thead>
              <tr className="border-y text-[11.5px] font-medium uppercase tracking-wide text-muted-foreground">
                <th className="px-5 py-2 text-left font-medium">Name</th>
                <th className="px-3 py-2 text-right font-medium">Commits</th>
                <th className="px-3 py-2 text-right font-medium">Modules known</th>
                <th className="px-3 py-2 text-right font-medium">Only they know</th>
                <th className="px-3 py-2 text-right font-medium">Centrality</th>
                <th className="px-5 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {people.map((p) => (
                <tr key={p.id} className={cn(dep?.personId === p.id && "bg-background")}>
                  <td className="px-5 py-2.5">
                    <span className="block font-medium leading-tight">{p.name}</span>
                    <span className="block truncate text-[12px] text-muted-foreground">
                      {p.topModules.length ? p.topModules.map((m) => `${m.path} ${score(m.score)}`).join(" · ") : `last commit ${day(p.lastSeen)}`}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular">{num(p.commits)}</td>
                  <td className="px-3 py-2.5 text-right tabular">{num(p.modulesKnown)}</td>
                  <td className={cn("px-3 py-2.5 text-right tabular", p.onlyThey > 0 && "font-semibold text-risk")}>{num(p.onlyThey)}</td>
                  <td className="px-3 py-2.5 text-right text-muted-foreground tabular">{p.centrality == null ? "—" : p.centrality.toFixed(3)}</td>
                  <td className="px-5 py-2.5 text-right">
                    <Button variant="quiet" size="xs" onClick={() => preview(p)}>
                      <UserMinus /> Preview departure
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {s.peopleTable.length > 15 ? (
          <button type="button" onClick={() => setAllPeople((v) => !v)} className="w-full border-t px-5 py-2.5 text-[13px] text-muted-foreground hover:text-foreground">
            {allPeople ? "Show fewer" : `Show all ${num(s.peopleTable.length)}`}
          </button>
        ) : null}
      </Card>

      <div ref={depRef} className="scroll-mt-6">
        {dep ? <DepartureCard dep={dep} credible={s.thresholds.credible} showCypher={showCypher} onClose={() => setDep(null)} /> : null}
      </div>

      <Card className="overflow-hidden">
        <div className="px-5 pt-4">
          <CardTitle>Modules</CardTitle>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            Bus factor is the number of people above {s.thresholds.credible}.
            {orphaned.size ? ` Highlighted: modules nobody credibly knows if ${dep?.name} leaves.` : ""}
          </p>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[720px] text-[13.5px]">
            <thead>
              <tr className="border-y text-[11.5px] font-medium uppercase tracking-wide text-muted-foreground">
                <th className="px-5 py-2 text-left font-medium">Module</th>
                <th className="px-3 py-2 text-right font-medium">Bus factor</th>
                <th className="px-3 py-2 text-left font-medium">Top knowers</th>
                <th className="px-3 py-2 text-right font-medium">Commits</th>
                <th className="px-5 py-2 text-right font-medium">Last commit</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {modules.map((m) => {
                const gone = orphaned.has(m.path);
                return (
                  <tr key={m.id} className={cn(gone && "bg-risk-soft")}>
                    <td className="px-5 py-2.5">
                      <span className="font-mono text-[13px]">{m.path}</span>
                      {gone ? <span className="ml-2 rounded-full bg-risk px-1.5 py-0.5 text-[10.5px] font-medium text-white">Orphaned</span> : null}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <BusFactor n={m.busFactor} />
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="flex flex-wrap gap-x-3 gap-y-0.5">
                        {m.knowers.slice(0, 3).map((k) => (
                          <span key={k.id} className={cn("whitespace-nowrap", k.score <= s.thresholds.credible && "text-muted-foreground")}>
                            {k.name} <span className="text-muted-foreground tabular">{score(k.score)}</span>
                          </span>
                        ))}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right tabular">{num(m.commits)}</td>
                    <td className="px-5 py-2.5 text-right text-muted-foreground tabular">{day(m.lastCommit)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {s.modulesTable.length > 20 ? (
          <button type="button" onClick={() => setAllModules((v) => !v)} className="w-full border-t px-5 py-2.5 text-[13px] text-muted-foreground hover:text-foreground">
            {allModules ? "Show fewer" : `Show all ${num(s.modulesTable.length)}`}
          </button>
        ) : null}
      </Card>
    </div>
  );
}

/* -------------------------------------------------------------- departure */

function DepartureCard({
  dep,
  credible,
  showCypher,
  onClose,
}: {
  dep: { personId: string; name: string; data?: Departure; error?: string };
  credible: number;
  showCypher: boolean;
  onClose: () => void;
}) {
  const d = dep.data;
  return (
    <Card className="border-risk/30 p-5" aria-live="polite">
      <CardTitle
        icon={UserMinus}
        action={
          <Button variant="ghost" size="icon-xs" onClick={onClose} aria-label="Close departure preview">
            <X />
          </Button>
        }
      >
        If {dep.name} leaves
      </CardTitle>
      {dep.error ? (
        <p className="mt-2 text-[13.5px] text-risk">{dep.error}</p>
      ) : !d ? (
        <p className="mt-2 flex items-center gap-2 text-[13.5px] text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden /> Removing {dep.name} from the graph…
        </p>
      ) : (
        <>
          <p className="mt-1 text-[13.5px] text-muted-foreground">
            {d.orphaned.length
              ? `${d.orphaned.length} ${d.orphaned.length === 1 ? "module is" : "modules are"} left with nobody above ${credible}.`
              : `Every module ${d.person.name} knows strongly still has someone above ${credible}.`}{" "}
            {num(d.person.commits)} commits, last on {day(d.person.lastCommit)}.
          </p>
          {d.orphaned.length ? (
            <ul className="mt-3 divide-y rounded-2xl border">
              {d.orphaned.map((m) => (
                <li key={m.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-2.5">
                  <span className="min-w-0">
                    <span className="font-mono text-[13px]">{m.path}</span>
                    <span className="ml-2 text-[12.5px] text-muted-foreground tabular">
                      {score(m.score)} · {num(m.personCommits)} of {num(m.commits)} commits
                    </span>
                  </span>
                  <span className="text-[13px]">
                    {m.nextBest ? (
                      <>
                        Next best <span className="font-medium">{m.nextBest.name}</span>{" "}
                        <span className="text-muted-foreground tabular">{score(m.nextBest.score)}</span>
                      </>
                    ) : (
                      <span className="text-risk">Nobody else has touched it</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
          {d.covered.length ? (
            <div className="mt-4">
              <p className="text-[12.5px] font-medium text-muted-foreground">Still covered</p>
              <ul className="mt-1 space-y-1 text-[13px]">
                {d.covered.slice(0, 8).map((m) => (
                  <li key={m.id} className="flex flex-wrap items-baseline justify-between gap-x-4">
                    <span className="font-mono text-[12.5px]">{m.path}</span>
                    <span className="text-muted-foreground">
                      bus factor <span className="tabular">{m.busFactorAfter}</span> after · {m.coveredBy.map((c) => c.name).join(", ")}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {showCypher ? (
            <div className="mt-4">
              <Cypher queries={d.queries} />
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}

/* -------------------------------------------------------------------- ask */

function AskBox({ jobId, summary: s, showCypher }: { jobId: string; summary: Summary; showCypher: boolean }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const suggestions = [
    s.modulesTable[0] ? `Who should I ask about ${s.modulesTable[0].path}?` : null,
    s.central[0] ? `What happens if ${s.central[0].name} leaves?` : null,
    "Which modules depend on a single person?",
  ].filter((x): x is string => !!x);

  const ask = async (question: string) => {
    const value = question.trim();
    if (value.length < 3) return;
    setQ(value);
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.post<AskResult>(`/api/repos/${enc(jobId)}/ask`, { question: value }));
    } catch (e) {
      setError(errorText(e, "Could not get an answer"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5">
      <CardTitle>Ask about this repo</CardTitle>
      <p className="mt-1 text-[12.5px] text-muted-foreground">Gemini answers from facts Relay pulls out of this graph, and shows which ones it used.</p>
      <form
        className="mt-3 flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
      >
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Who knows the CLI parser best?" aria-label="Question about this repository" className="sm:flex-1" />
        <Button type="submit" disabled={busy || q.trim().length < 3}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          Ask
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap gap-2">
        {suggestions.map((x) => (
          <button
            key={x}
            type="button"
            disabled={busy}
            onClick={() => ask(x)}
            className="rounded-full border bg-card px-2.5 py-0.5 text-[12.5px] text-foreground/80 transition-colors hover:border-foreground/25 hover:text-foreground"
          >
            {x}
          </button>
        ))}
      </div>
      {error ? (
        <p role="alert" className="mt-3 flex items-start gap-1.5 text-[13.5px] text-risk">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> {error}
        </p>
      ) : null}
      {busy ? (
        <p className="mt-4 flex items-center gap-2 text-[13.5px] text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden /> Querying the graph and asking Gemini…
        </p>
      ) : null}
      {result ? (
        <div className="mt-4 rounded-2xl bg-background p-4">
          <p className="whitespace-pre-line text-[14.5px] leading-relaxed">{result.answer}</p>
          {result.facts.length ? (
            <div className="mt-3">
              <p className="text-[12px] font-medium text-muted-foreground">
                Facts used ({result.facts.length} of {result.factsConsidered})
              </p>
              <ul className="mt-1 space-y-1">
                {result.facts.map((f) => (
                  <li key={f.id} className="text-[12.5px] text-foreground/80">
                    <span className="mr-1.5 font-mono text-muted-foreground">{f.id}</span>
                    {f.text}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <p className="mt-3 text-[11.5px] text-muted-foreground tabular">
            {result.model} · {num(result.ms)} ms
          </p>
          {showCypher ? (
            <div className="mt-3">
              <Cypher queries={result.queries} />
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
