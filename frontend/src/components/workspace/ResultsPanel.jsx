import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import Pagination from "../Pagination.jsx";
import ResultStatStrip from "./ResultStatStrip.jsx";
import ResultsTable from "./ResultsTable.jsx";

export default function ResultsPanel({
  searchResults,
  searchRequestCount,
  filteredCount,
  visibleResults,
  resultsPage,
  onResultsPageChange,
  resultViewFilter,
  matchedCount,
  notFoundCount,
  sdoNotFoundCount,
  selectedCount,
  onToggleFilter,
  selectedResultIds,
  allSelected,
  selectableCount,
  onSelectResult,
  onSelectAll,
  onManualSearch,
  exportMode,
  onExportModeChange,
  onExport,
  isExporting,
}) {
  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-2xl border border-border/70 bg-card p-4 shadow-sm sm:p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold tracking-[0.14em] text-primary">
            DATABASE VERIFICATION
          </div>
          <h2 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">Search Results</h2>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-2xl font-semibold tabular-nums tracking-tight">{searchResults.length}</div>
          <div className="text-xs text-muted-foreground">results</div>
          <div className="text-xs text-muted-foreground">
            from {searchRequestCount} extracted requests
          </div>
        </div>
      </div>

      <ResultStatStrip
        resultViewFilter={resultViewFilter}
        matchedCount={matchedCount}
        notFoundCount={notFoundCount}
        sdoNotFoundCount={sdoNotFoundCount}
        selectedCount={selectedCount}
        onToggleFilter={onToggleFilter}
      />

      <p className="-mt-2 text-xs text-muted-foreground">
        Select all applies to selectable rows on this page.
      </p>

      {filteredCount === 0 ? (
        <div
          className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground"
          role="status"
        >
          No rows in this view.
        </div>
      ) : (
        <ResultsTable
          visibleResults={visibleResults}
          selectedResultIds={selectedResultIds}
          allSelected={allSelected}
          selectableCount={selectableCount}
          onSelectResult={onSelectResult}
          onSelectAll={onSelectAll}
          onManualSearch={onManualSearch}
        />
      )}

      <Pagination
        page={resultsPage}
        total={filteredCount}
        onPageChange={onResultsPageChange}
      />

      <div className="flex flex-col items-stretch justify-between gap-3 border-t border-border/70 pt-4 sm:flex-row sm:items-center">
        <div className="text-sm">
          <span className="mr-2 inline-block size-2 rounded-full bg-primary align-middle" />
          <strong>{selectedCount}</strong>
          <span className="ml-2 text-muted-foreground">selected for quotation</span>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          <Select
            value={exportMode}
            onValueChange={onExportModeChange}
            disabled={isExporting}
          >
            <SelectTrigger className="h-10 w-full rounded-xl bg-background sm:w-72">
              <SelectValue placeholder="Export file" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="found-and-not-found">
                Quotation + not found files
              </SelectItem>
              <SelectItem value="latest-years">
                Matching standards with current year
              </SelectItem>
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="outline"
            className="h-10 w-full rounded-xl sm:w-auto"
            onClick={onExport}
            disabled={selectedCount === 0 || isExporting}
          >
            <Download />
            {isExporting
              ? "Exporting..."
              : `Export ${selectedCount} Selected`}
          </Button>
        </div>
      </div>
    </section>
  );
}
