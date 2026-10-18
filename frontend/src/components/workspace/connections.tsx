"use client";

import { useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Check, Copy, ExternalLink, Loader2, Plus, Trash2 } from "lucide-react";

import { BrandLogo as Logo } from "@/components/brand-logo";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { API_BASE, api, enc } from "@/lib/api";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ types (GET /api/connectors)

interface CredentialField {
  key: string;
  label: string;
  secret: boolean;
  placeholder: string;
  help: string;
  optional: boolean;
}

interface Provider {
  id: string;
  name: string;
  category: string;
  color: string;
  auth: "api_key" | "oauth";
  description: string;
  fields: CredentialField[];
  docs: string;
  docsLabel: string;
  uses: string;
  sample: string | null;
  connected: boolean;
  account: string | null;
  verifiedAt: string | null;
  values: Record<string, string>;
  // Google only
  redirectUri?: string;
  serverClient?: boolean;
  clientSaved?: boolean;
  clientAccount?: string | null;
  clientVerifiedAt?: string | null;
}

interface McpServer {
  id: string;
  name: string;
  url: string;
  transport: string | null;
  tools: { name: string; description: string }[];
  server: string | null;
  token: string | null;
  verifiedAt: string | null;
}

interface Catalog {
  company: string;
  canManage: boolean;
  sample: { id: string; name: string; size?: string | null }[];
  categories: { name: string; providers: Provider[] }[];
  mcp: McpServer[];
  mcpUses: string;
}

const KEY = "/api/connectors";

// ------------------------------------------------------------------ helpers

function when(iso: string | null | undefined) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function errorText(err: unknown) {
  return err instanceof Error ? err.message : "Something went wrong";
}

function Chip({ tone, children }: { tone: "on" | "sample" | "off" | "warn"; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full shrink-0 items-center gap-1.5 truncate whitespace-nowrap rounded-full px-2 py-0.5 text-[11.5px] font-medium",
        tone === "on" && "bg-covered-soft text-covered",
        tone === "sample" && "bg-secondary text-foreground/75",
        tone === "warn" && "bg-warn-soft text-warn",
        tone === "off" && "text-muted-foreground",
      )}
    >
      {tone === "on" ? <span className="size-1.5 shrink-0 rounded-full bg-covered" aria-hidden /> : null}
      <span className="truncate">{children}</span>
    </span>
  );
}

function status(p: Provider): { tone: "on" | "sample" | "off" | "warn"; label: string } {
  if (p.connected) return { tone: "on", label: "Connected" };
  if (p.id === "google" && p.clientSaved) return { tone: "warn", label: "Client saved · not authorized" };
  if (p.sample) return { tone: "sample", label: "Sample data imported" };
  return { tone: "off", label: "Not connected" };
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      type="button"
      size="xs"
      variant="quiet"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          toast.error("Couldn't copy. Select the text and copy it.");
        }
      }}
    >
      {done ? <Check /> : <Copy />} {done ? "Copied" : "Copy"}
    </Button>
  );
}

// ------------------------------------------------------------------ grid

export function ConnectionsGrid({ compact = false, canManage }: { compact?: boolean; canManage?: boolean }) {
  const { data, error, mutate } = useSWR<Catalog>(KEY);
  const [open, setOpen] = useState<string | null>(null);
  const [addMcp, setAddMcp] = useState(false);

  if (error && !data) {
    return <p className="rounded-2xl border bg-card p-4 text-sm text-muted-foreground">Couldn&apos;t load connections: {errorText(error)}</p>;
  }
  if (!data) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-36 animate-pulse rounded-2xl bg-secondary" />
        ))}
      </div>
    );
  }
  const manage = canManage ?? data.canManage;
  const providers = data.categories.flatMap((c) => c.providers);
  const selected = providers.find((p) => p.id === open) ?? null;
  const cols = compact ? "sm:grid-cols-2" : "sm:grid-cols-2 xl:grid-cols-3";

  return (
    <div className="space-y-8">
      <div className="rounded-2xl border bg-card p-4">
        <p className="text-[14px] leading-snug">
          This workspace runs on imported sample data from {data.company}&apos;s tools. Add credentials to connect your own.
        </p>
        {data.sample.length ? (
          <>
            <p className="mt-3 text-xs text-muted-foreground">The sample covers:</p>
            <ul className="mt-1.5 flex flex-wrap gap-1.5">
              {data.sample.map((s) => (
                <li key={s.id} className="rounded-full bg-secondary px-2.5 py-1 text-[12px]">
                  {s.name}
                  {s.size ? <span className="text-muted-foreground tabular"> · {s.size}</span> : null}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {!manage ? <p className="mt-3 text-xs text-muted-foreground">Only workspace owners and admins can add or remove connections.</p> : null}
      </div>

      {data.categories.map((cat) => (
        <section key={cat.name}>
          <h3 className="mb-3 text-[15px] font-semibold">{cat.name}</h3>
          <div className={cn("grid gap-3", cols)}>
            {cat.providers.map((p) => (
              <ProviderCard key={p.id} p={p} manage={manage} onOpen={() => setOpen(p.id)} onChange={() => mutate()} />
            ))}
          </div>
        </section>
      ))}

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-[15px] font-semibold">MCP servers</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{data.mcpUses}</p>
          </div>
          <Button size="sm" variant="quiet" onClick={() => setAddMcp(true)} disabled={!manage}>
            <Plus /> Add MCP server
          </Button>
        </div>
        {data.mcp.length ? (
          <div className="space-y-3">
            {data.mcp.map((m) => (
              <McpCard key={m.id} m={m} manage={manage} onChange={() => mutate()} />
            ))}
          </div>
        ) : (
          <p className="rounded-2xl border border-dashed bg-card p-4 text-sm text-muted-foreground">
            No MCP servers yet. Add a server&apos;s URL (streamable HTTP or SSE) and Relay lists its tools.
          </p>
        )}
      </section>

      {selected ? (
        <ConnectDialog key={selected.id} p={selected} manage={manage} onClose={() => setOpen(null)} onSaved={() => mutate()} />
      ) : null}
      <McpDialog open={addMcp} onOpenChange={setAddMcp} onSaved={() => mutate()} />
    </div>
  );
}

function ProviderCard({ p, manage, onOpen, onChange }: { p: Provider; manage: boolean; onOpen: () => void; onChange: () => void }) {
  const s = status(p);
  const [busy, setBusy] = useState(false);
  const disconnect = async () => {
    setBusy(true);
    try {
      await api.request(`${KEY}/${enc(p.id)}`, { method: "DELETE" });
      toast(`${p.name} disconnected`, { description: "Relay deleted the stored credentials." });
      onChange();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  const verified = when(p.verifiedAt);
  return (
    <div className="flex flex-col rounded-2xl border bg-card p-4">
      <div className="flex items-start gap-3">
        <Logo id={p.id} name={p.name} color={p.color} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
            <p className="truncate font-medium">{p.name}</p>
            <Chip tone={s.tone}>{s.label}</Chip>
          </div>
          <p className="mt-0.5 text-[13px] leading-snug text-muted-foreground">{p.description}</p>
        </div>
      </div>

      {p.connected ? (
        <div className="mt-3 space-y-1.5 text-[12.5px]">
          <p className="truncate font-medium" title={p.account ?? undefined}>
            {p.account}
          </p>
          {verified ? <p className="text-muted-foreground">Verified {verified}</p> : null}
          <p className="leading-snug text-muted-foreground">{p.uses}</p>
        </div>
      ) : p.sample ? (
        <p className="mt-3 text-[12.5px] text-muted-foreground tabular">Sample: {p.sample}</p>
      ) : null}

      <div className="mt-auto flex flex-wrap items-center gap-2 pt-3">
        {p.connected ? (
          <>
            <Button size="sm" variant="quiet" onClick={onOpen} disabled={!manage}>
              Update
            </Button>
            <Button size="sm" variant="ghost" onClick={disconnect} disabled={!manage || busy}>
              {busy ? <Loader2 className="animate-spin" /> : null} Disconnect
            </Button>
          </>
        ) : p.id === "google" && p.clientSaved ? (
          <>
            {manage ? (
              <Button asChild size="sm">
                <a href={`${API_BASE}/api/workspace/connections/google/start`}>Authorize with Google</a>
              </Button>
            ) : (
              <Button size="sm" disabled>
                Authorize with Google
              </Button>
            )}
            {!p.serverClient ? (
              <Button size="sm" variant="ghost" onClick={onOpen} disabled={!manage}>
                Edit client
              </Button>
            ) : null}
          </>
        ) : (
          <Button size="sm" variant="outline" onClick={onOpen} disabled={!manage}>
            Connect
          </Button>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ connect dialog

function ConnectDialog({ p, manage, onClose, onSaved }: { p: Provider; manage: boolean; onClose: () => void; onSaved: () => void }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(p.fields.map((f) => [f.key, f.secret ? "" : (p.values[f.key] ?? "")])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const isGoogle = p.id === "google";
  const showFields = !(isGoogle && p.serverClient);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const res = await api.post<Provider>(`${KEY}/${enc(p.id)}`, { fields: values });
      onSaved();
      if (isGoogle) {
        setSaved(`Google accepted this client (${res.clientAccount ?? "OAuth client"}). Now authorize a Google account.`);
        setValues((v) => ({ ...v, client_secret: "" }));
      } else {
        toast.success(`${p.name} connected`, { description: res.account ?? undefined });
        onClose();
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent className="max-h-[90vh] max-w-md overflow-y-auto [&>*]:min-w-0">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <Logo id={p.id} name={p.name} color={p.color} size="sm" />
            <DialogTitle>{p.connected ? `Update ${p.name}` : `Connect ${p.name}`}</DialogTitle>
          </div>
          <DialogDescription>
            {isGoogle
              ? "Google uses OAuth. Save your OAuth client, then authorize a Google account."
              : "Relay checks these credentials with one live call to " + p.name + ", then stores them encrypted. They are never shown again."}
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-xl bg-secondary px-3 py-2.5 text-[12.5px] leading-snug">
          <p className="font-medium">What Relay does with this</p>
          <p className="mt-0.5 text-muted-foreground">{p.uses}</p>
        </div>

        {isGoogle && p.redirectUri ? (
          <div className="min-w-0 space-y-1.5">
            <p className="text-sm font-medium">Redirect URI</p>
            <p className="text-xs text-muted-foreground">Add this as an authorized redirect URI on your OAuth client (Web application).</p>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-lg border bg-card px-2.5 py-1.5 text-[12px]" title={p.redirectUri}>
                {p.redirectUri}
              </code>
              <CopyButton text={p.redirectUri} />
            </div>
          </div>
        ) : null}

        {isGoogle && p.serverClient ? (
          <p className="text-[13px] text-muted-foreground">This server already has a Google OAuth client, so you only need to authorize an account.</p>
        ) : null}

        {showFields ? (
          <form className="space-y-3" onSubmit={submit} id={`connect-${p.id}`}>
            {p.fields.map((f) => (
              <Labeled key={f.key} label={f.optional ? `${f.label} (optional)` : f.label}>
                <Input
                  type={f.secret ? "password" : "text"}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={f.secret && p.values[f.key] ? `Saved ${p.values[f.key]}. Enter it again to update.` : f.placeholder}
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                  required={!f.optional}
                />
                {f.help ? <span className="block text-xs text-muted-foreground">{f.help}</span> : null}
              </Labeled>
            ))}
            <a href={p.docs} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[13px] text-primary hover:underline">
              {p.docsLabel} <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </form>
        ) : null}

        {error ? (
          <p role="alert" className="rounded-xl bg-risk-soft px-3 py-2 text-sm text-risk">
            {error}
          </p>
        ) : null}
        {saved ? (
          <p role="status" className="rounded-xl bg-covered-soft px-3 py-2 text-sm text-covered">
            {saved}
          </p>
        ) : null}

        <DialogFooter className="gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {saved ? "Close" : "Cancel"}
          </Button>
          {isGoogle && (p.clientSaved || saved) ? (
            <Button asChild variant={showFields ? "outline" : "default"}>
              <a href={`${API_BASE}/api/workspace/connections/google/start`}>Authorize with Google</a>
            </Button>
          ) : null}
          {showFields ? (
            <Button type="submit" form={`connect-${p.id}`} disabled={busy || !manage}>
              {busy ? <Loader2 className="animate-spin" /> : null} {busy ? "Testing…" : "Test & save"}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ MCP

function McpCard({ m, manage, onChange }: { m: McpServer; manage: boolean; onChange: () => void }) {
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const shown = all ? m.tools : m.tools.slice(0, 12);
  const verified = when(m.verifiedAt);
  return (
    <div className="rounded-2xl border bg-card p-4">
      <div className="flex items-start gap-3">
        <Logo id="mcp" name="MCP" color="#000000" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
            <p className="truncate font-medium">{m.name}</p>
            <Chip tone="on">
              Connected · {m.tools.length} tool{m.tools.length === 1 ? "" : "s"}
            </Chip>
          </div>
          <p className="mt-0.5 truncate font-mono text-[12px] text-muted-foreground" title={m.url}>
            {m.url}
          </p>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {[m.transport === "sse" ? "SSE" : "Streamable HTTP", m.server ? `server “${m.server}”` : null, m.token ? `token ${m.token}` : "no token", verified ? `verified ${verified}` : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          disabled={!manage || busy}
          onClick={async () => {
            setBusy(true);
            try {
              await api.request(`${KEY}/mcp/${enc(m.id)}`, { method: "DELETE" });
              toast(`${m.name} removed`);
              onChange();
            } catch (err) {
              toast.error(errorText(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <Loader2 className="animate-spin" /> : <Trash2 />} Remove
        </Button>
      </div>
      {m.tools.length ? (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {shown.map((t) => (
            <li key={t.name} title={t.description || undefined} className="rounded-md border bg-secondary/60 px-2 py-0.5 font-mono text-[11.5px]">
              {t.name}
            </li>
          ))}
          {m.tools.length > 12 ? (
            <li>
              <button type="button" className="px-1 text-[12px] text-primary hover:underline" onClick={() => setAll(!all)}>
                {all ? "Show fewer" : `Show all ${m.tools.length}`}
              </button>
            </li>
          ) : null}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">The server answered but lists no tools.</p>
      )}
    </div>
  );
}

function McpDialog({ open, onOpenChange, onSaved }: { open: boolean; onOpenChange: (o: boolean) => void; onSaved: () => void }) {
  const [f, setF] = useState({ name: "", url: "", token: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setError(null);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <Logo id="mcp" name="MCP" color="#000000" size="sm" />
            <DialogTitle>Add MCP server</DialogTitle>
          </div>
          <DialogDescription>
            Relay connects to the server, lists its tools and stores it. A bearer token, if you add one, is stored encrypted.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              const m = await api.post<McpServer>(`${KEY}/mcp`, { name: f.name, url: f.url, token: f.token || null });
              toast.success(`${m.name} connected`, { description: `${m.tools.length} tools listed` });
              onSaved();
              setF({ name: "", url: "", token: "" });
              onOpenChange(false);
            } catch (err) {
              setError(errorText(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <Labeled label="Name">
            <Input placeholder="Relay tools" value={f.name} onChange={set("name")} required maxLength={60} />
          </Labeled>
          <Labeled label="Server URL">
            <Input placeholder="https://example.com/mcp" value={f.url} onChange={set("url")} required spellCheck={false} />
            <span className="block text-xs text-muted-foreground">Streamable HTTP endpoint (usually /mcp), or an SSE endpoint ending in /sse.</span>
          </Labeled>
          <Labeled label="Bearer token (optional)">
            <Input type="password" value={f.token} onChange={set("token")} autoComplete="off" />
          </Labeled>
          {error ? (
            <p role="alert" className="rounded-xl bg-risk-soft px-3 py-2 text-sm text-risk">
              {error}
            </p>
          ) : null}
          <DialogFooter className="gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? <Loader2 className="animate-spin" /> : null} {busy ? "Connecting…" : "Connect & list tools"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function Labeled({ label, hint, children }: { label: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="flex items-baseline justify-between text-sm font-medium">
        {label}
        {hint ? <span className="text-xs font-normal text-muted-foreground">{hint}</span> : null}
      </span>
      {children}
    </label>
  );
}
