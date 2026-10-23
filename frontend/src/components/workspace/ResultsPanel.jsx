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
  resultsPageStart,
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
  loading,
}) {
  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-xl border bg-card p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs tracking-[0.16em] text-muted-foreground">
            DATABASE VERIFICATION
          </div>
          <h2 className="text-xl font-semibold">Search Results</h2>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold">{searchResults.length}</div>
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

      <ResultsTable
        visibleResults={visibleResults}
        resultsPageStart={resultsPageStart}
        selectedResultIds={selectedResultIds}
        allSelected={allSelected}
        selectableCount={selectableCount}
        onSelectResult={onSelectResult}
        onSelectAll={onSelectAll}
        onManualSearch={onManualSearch}
      />

      <Pagination
        page={resultsPage}
        total={filteredCount}
        onPageChange={onResultsPageChange}
      />

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <div className="text-sm">
          <span className="mr-2 inline-block size-2 rounded-full bg-primary" />
          <strong>{selectedCount}</strong>
          <span className="ml-2 text-muted-foreground">selected for quotation</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={exportMode}
            onValueChange={onExportModeChange}
            disabled={loading}
          >
            <SelectTrigger className="w-72">
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
            onClick={onExport}
            disabled={searchResults.length === 0 || loading}
          >
            <Download />
            {exportMode === "latest-years"
              ? "Export Current Years"
              : "Export Found + Not Found"}
          </Button>
        </div>
      </div>
    </section>
  );
}
