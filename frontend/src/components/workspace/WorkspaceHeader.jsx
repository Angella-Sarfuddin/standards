import { ArrowLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function WorkspaceHeader({
  fileName,
  onBack,
  onNewSearch,
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-start justify-between gap-4 rounded-2xl border border-border/70 bg-card px-4 py-4 shadow-sm sm:px-5">
      <div className="flex min-w-0 items-start gap-3">
        <Button type="button" variant="outline" size="icon" className="mt-1 shrink-0 rounded-xl bg-card" onClick={onBack} aria-label="Back to search" title="Back to search">
          <ArrowLeft />
        </Button>
        <div className="min-w-0">
          <div className="text-[11px] font-semibold tracking-[0.14em] text-primary">
            SEARCH COMPLETE
          </div>
          <h1 className="mt-1 break-words text-xl font-semibold tracking-tight sm:text-2xl">
            {fileName || "Standards Results"}
          </h1>
          <p className="mt-1 text-sm leading-5 text-muted-foreground">
            Verified results and quotation intelligence are ready.
          </p>
        </div>
      </div>
      <div className="ml-auto flex flex-wrap gap-2">
        <Button type="button" variant="outline" className="rounded-xl bg-card" onClick={onNewSearch}>
          <Plus />
          New Search
        </Button>
      </div>
    </div>
  );
}
