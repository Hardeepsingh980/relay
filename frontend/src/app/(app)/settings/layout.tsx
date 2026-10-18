import { SettingsNav } from "./settings-nav";

export default function SettingsLayout({ children }: LayoutProps<"/settings">) {
  return (
    <div className="mx-auto max-w-[1100px] px-4 py-10 md:px-8">
      <p className="text-[13px] font-medium text-muted-foreground">Settings</p>
      <h1 className="mt-1 text-[30px] font-semibold leading-tight tracking-[-0.3px] md:text-[34px] md:tracking-[-0.4px]">Workspace & account</h1>
      <div className="mt-8 grid grid-cols-1 gap-8 md:grid-cols-[200px_minmax(0,1fr)]">
        <SettingsNav />
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
