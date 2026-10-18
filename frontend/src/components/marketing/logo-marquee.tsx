import { BrandLogo } from "@/components/brand-logo";

// The connectors Relay ships with (backend/src/relay/connectors.py), plus MCP.
const TOOLS = [
  ["hubspot", "HubSpot", "#FF7A59"],
  ["slack", "Slack", "#4A154B"],
  ["jira", "Jira", "#0052CC"],
  ["zendesk", "Zendesk", "#03363D"],
  ["github", "GitHub", "#181717"],
  ["notion", "Notion", "#000000"],
  ["intercom", "Intercom", "#1F1F1F"],
  ["linear", "Linear", "#5E6AD2"],
  ["google", "Google Workspace", "#4285F4"],
  ["confluence", "Confluence", "#172B4D"],
  ["freshdesk", "Freshdesk", "#25C16F"],
  ["gong", "Gong", "#8039DF"],
  ["fireflies", "Fireflies", "#E8336D"],
  ["mcp", "MCP servers", "#000000"],
];

function Row({ items, reverse }: { items: string[][]; reverse?: boolean }) {
  return (
    <div className="flex w-max gap-3 animate-[relay-marquee_48s_linear_infinite] hover:[animation-play-state:paused]" style={{ animationDirection: reverse ? "reverse" : "normal" }}>
      {[...items, ...items].map(([id, name, color], i) => (
        <span key={`${id}-${i}`} className="flex items-center gap-2.5 rounded-full border bg-card py-1.5 pl-1.5 pr-4 text-[14px] font-medium shadow-panel" aria-hidden={i >= items.length}>
          <BrandLogo id={id} name={name} color={color} size="sm" />
          {name}
        </span>
      ))}
    </div>
  );
}

export function LogoMarquee() {
  return (
    <div className="relative mt-8 flex flex-col gap-3 overflow-hidden py-2 [mask-image:linear-gradient(90deg,transparent,black_12%,black_88%,transparent)]">
      <Row items={TOOLS.slice(0, 7)} />
      <Row items={TOOLS.slice(7)} reverse />
    </div>
  );
}
