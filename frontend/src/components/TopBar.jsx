import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function TopBar({ isDark, onToggleTheme }) {
  return (
    <header className="sticky top-0 z-30 border-b border-border/80 bg-background/90 px-4 py-3 backdrop-blur-xl sm:px-6">
      <div className="mx-auto flex w-full max-w-[1600px] items-center justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-sm font-semibold tracking-tight text-primary-foreground shadow-sm">
            SI
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold tracking-tight">
              Standards Intelligence
            </div>
            <div className="hidden text-xs text-muted-foreground sm:block">
              Standards discovery &amp; quotation workspace
            </div>
          </div>
        </div>
        <Button type="button" variant="outline" size="sm" className="h-9 rounded-xl" onClick={onToggleTheme} aria-label={`Switch to ${isDark ? "light" : "dark"} mode`} title={`Switch to ${isDark ? "light" : "dark"} mode`}>
          {isDark ? <Sun /> : <Moon />}
          <span className="hidden sm:inline">{isDark ? "Light mode" : "Dark mode"}</span>
        </Button>
      </div>
    </header>
  );
}
