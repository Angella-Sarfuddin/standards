import { useState } from "react";
import { Moon, Search, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { displayValue } from "../utils/standards.js";

function BrandMark() {
  return (
    <div className="relative h-11 w-44 shrink-0" aria-label="BSB Edge">
      <img
        src="/logo.png"
        alt="BSB Edge"
        className="absolute top-1/2 left-1/2 h-44 w-auto max-w-none -translate-x-1/2 -translate-y-1/2 rotate-90 dark:hidden"
      />
      <img
        src="/logo-1.png"
        alt=""
        className="absolute top-1/2 left-1/2 hidden h-44 w-auto max-w-none -translate-x-1/2 -translate-y-1/2 rotate-90 dark:block"
      />
    </div>
  );
}

export default function TopBar({
  isDark,
  onToggleTheme,
  searchQuery,
  onSearchQueryChange,
  onSearch,
  searchResult,
  isQuickSearching,
}) {
  const [resultsOpen, setResultsOpen] = useState(false);

  const submitSearch = (event) => {
    event.preventDefault();
    const text = searchQuery.trim();
    if (!text || isQuickSearching) {
      return;
    }
    setResultsOpen(true);
    onSearch(text);
  };

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background">
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-3 px-4 py-3 sm:px-6 md:flex-row md:items-center md:gap-8 md:py-4">
        <div className="flex min-w-0 items-center gap-4">
          <BrandMark />
          <div className="hidden h-10 w-px bg-border md:block" />
          <div className="hidden min-w-0 text-[13px] leading-5 text-muted-foreground md:block">
            <div>Standards Manage Your Business</div>
            <div>We Manage Your Standards</div>
          </div>
        </div>

        <div className="relative min-w-0 md:ml-auto md:w-[32rem] md:max-w-[48%]">
          <form
            className="flex items-center gap-2"
            onSubmit={submitSearch}
          >
            <div className="flex h-12 min-w-0 flex-1 items-center rounded-full border border-[#e10600]/70 bg-background pr-1 pl-4 shadow-sm">
              <input
                className="h-full min-w-0 flex-1 bg-transparent pr-2 text-sm outline-none placeholder:text-muted-foreground"
                value={searchQuery}
                onChange={(event) => onSearchQueryChange(event.target.value)}
                onFocus={() => {
                  if (searchResult) {
                    setResultsOpen(true);
                  }
                }}
                placeholder="Textual search..."
                aria-label="Textual search"
              />
              <button
                type="submit"
                className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[#d0121a] text-white transition-colors hover:bg-[#b40f16] disabled:opacity-60"
                disabled={isQuickSearching || !searchQuery.trim()}
                aria-label={isQuickSearching ? "Searching" : "Search"}
              >
                {isQuickSearching ? (
                  <Spinner className="size-4 text-white" />
                ) : (
                  <Search className="size-4" />
                )}
              </button>
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="size-10 shrink-0 rounded-full"
              onClick={onToggleTheme}
              aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
              title={`Switch to ${isDark ? "light" : "dark"} mode`}
            >
              {isDark ? <Sun /> : <Moon />}
            </Button>
          </form>

          {resultsOpen && searchResult && (
            <div className="absolute top-[calc(100%+0.5rem)] right-12 left-0 z-50 max-h-80 overflow-auto rounded-2xl border bg-popover p-2 text-popover-foreground shadow-lg">
              {searchResult.length ? (
                searchResult.map((result, index) => (
                  <div
                    className="rounded-xl px-3 py-2.5 text-sm hover:bg-muted/60"
                    key={
                      result?.standard?.id ||
                      result?.standard?.Standard_id ||
                      `${result?.requested_standard || "standard"}-${index}`
                    }
                  >
                    <div className="font-medium">
                      {displayValue(
                        result?.standard?.display_stdNo ||
                          result?.standard?.standardno ||
                          result?.requested_standard
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {displayValue(result?.status)}
                      {result?.standard?.title ? ` · ${result.standard.title}` : ""}
                    </div>
                  </div>
                ))
              ) : (
                <div className="px-3 py-4 text-sm text-muted-foreground">
                  No matching standard was returned for this search.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
