import {
  siConfluence,
  siGithub,
  siGoogle,
  siHubspot,
  siIntercom,
  siJira,
  siLinear,
  siModelcontextprotocol,
  siNotion,
  siZendesk,
} from "simple-icons";

import { cn } from "@/lib/utils";

// Official marks from simple-icons; Slack's own mark is drawn below, and Freshdesk, Fireflies and Gong
// use their site icons.
const LOGOS: Record<string, { path: string; title: string }> = {
  hubspot: siHubspot,
  zendesk: siZendesk,
  intercom: siIntercom,
  jira: siJira,
  linear: siLinear,
  confluence: siConfluence,
  notion: siNotion,
  github: siGithub,
  google: siGoogle,
  mcp: siModelcontextprotocol,
};

// Slack's own four-colour mark (simple-icons no longer carries it).
export function SlackMark({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 127 127" className={className} role="img">
      <path fill="#E01E5A" d="M27.2 80c0 7.3-5.9 13.2-13.2 13.2C6.7 93.2.8 87.3.8 80c0-7.3 5.9-13.2 13.2-13.2h13.2V80zm6.6 0c0-7.3 5.9-13.2 13.2-13.2 7.3 0 13.2 5.9 13.2 13.2v33c0 7.3-5.9 13.2-13.2 13.2-7.3 0-13.2-5.9-13.2-13.2V80z" />
      <path fill="#36C5F0" d="M47 27c-7.3 0-13.2-5.9-13.2-13.2C33.8 6.5 39.7.6 47 .6c7.3 0 13.2 5.9 13.2 13.2V27H47zm0 6.7c7.3 0 13.2 5.9 13.2 13.2 0 7.3-5.9 13.2-13.2 13.2H13.9C6.6 60.1.7 54.2.7 46.9c0-7.3 5.9-13.2 13.2-13.2H47z" />
      <path fill="#2EB67D" d="M99.9 46.9c0-7.3 5.9-13.2 13.2-13.2 7.3 0 13.2 5.9 13.2 13.2 0 7.3-5.9 13.2-13.2 13.2H99.9V46.9zm-6.6 0c0 7.3-5.9 13.2-13.2 13.2-7.3 0-13.2-5.9-13.2-13.2V13.8C66.9 6.5 72.8.6 80.1.6c7.3 0 13.2 5.9 13.2 13.2v33.1z" />
      <path fill="#ECB22E" d="M80.1 99.8c7.3 0 13.2 5.9 13.2 13.2 0 7.3-5.9 13.2-13.2 13.2-7.3 0-13.2-5.9-13.2-13.2V99.8h13.2zm0-6.6c-7.3 0-13.2-5.9-13.2-13.2 0-7.3 5.9-13.2 13.2-13.2h33.1c7.3 0 13.2 5.9 13.2 13.2 0 7.3-5.9 13.2-13.2 13.2H80.1z" />
    </svg>
  );
}

// The brand's own site icon, for brands simple-icons does not carry.
const SITE_ICON: Record<string, string> = { freshdesk: "freshdesk.com", fireflies: "fireflies.ai", gong: "gong.io" };

export function BrandLogo({ id, name, color, size = "md" }: { id: string; name: string; color: string; size?: "md" | "sm" }) {
  const icon = LOGOS[id];
  const box = size === "sm" ? "size-8 rounded-lg" : "size-10 rounded-xl";
  const glyph = size === "sm" ? "size-4" : "size-5";
  if (id === "slack") {
    return (
      <span className={cn("flex shrink-0 items-center justify-center border border-black/5 bg-white", box)} aria-hidden>
        <SlackMark className={glyph} />
      </span>
    );
  }
  if (!icon && SITE_ICON[id]) {
    return (
      <span className={cn("flex shrink-0 items-center justify-center border border-black/5 bg-white", box)} aria-hidden>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`https://www.google.com/s2/favicons?domain=${SITE_ICON[id]}&sz=64`} alt="" className={glyph} />
      </span>
    );
  }
  if (!icon) {
    return (
      <span
        className={cn("flex shrink-0 items-center justify-center text-[15px] font-semibold text-white", box)}
        style={{ backgroundColor: color }}
        aria-hidden
      >
        {name.charAt(0)}
      </span>
    );
  }
  return (
    <span className={cn("flex shrink-0 items-center justify-center border border-black/5 bg-white", box)} aria-hidden>
      <svg viewBox="0 0 24 24" className={size === "sm" ? "size-4" : "size-5"} role="img">
        <path d={icon.path} fill={color} />
      </svg>
    </span>
  );
}
