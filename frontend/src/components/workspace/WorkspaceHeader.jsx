import { ArrowLeft, Download, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function WorkspaceHeader({
  fileName,
  selectedCount,
  loading,
  onBack,
  onNewSearch,
  onExport,
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <Button type="button" variant="outline" size="icon" onClick={onBack}>
          <ArrowLeft />
        </Button>
        <div>
          <div className="text-xs tracking-[0.16em] text-muted-foreground">
            SEARCH COMPLETE
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {fileName || "Standards Results"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Verified results and quotation intelligence are ready.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={onNewSearch}>
          <Plus />
          New Search
        </Button>
        <Button
          type="button"
          onClick={onExport}
          disabled={selectedCount === 0 || loading}
        >
          <Download />
          {loading ? "Exporting..." : `Export ${selectedCount || ""} Selected`}
        </Button>
      </div>
    </div>
  );
}
