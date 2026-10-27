import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { displayValue } from "../../utils/standards.js";

export default function QuickSearch({
  searchQuery,
  onSearchQueryChange,
  onSearch,
  searchResult,
  isQuickSearching,
}) {
  return (
    <Card className="border border-border/70 bg-card shadow-sm ring-0">
      <CardHeader className="px-5 pt-5 sm:px-6 sm:pt-6">
        <CardTitle className="text-xs font-semibold tracking-[0.14em] text-muted-foreground">
          QUICK SEARCH
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-5 pb-5 sm:px-6 sm:pb-6">
        <div className="flex min-w-0 gap-2">
          <Input
            className="h-11 min-w-0 rounded-xl bg-background px-3 text-sm shadow-none"
            value={searchQuery}
            onChange={(event) => onSearchQueryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onSearch();
              }
            }}
            placeholder="e.g. ISO 530"
          />
          <Button
            type="button"
            onClick={onSearch}
            className="h-11 rounded-xl px-4 shadow-sm"
            disabled={isQuickSearching || !searchQuery.trim()}
          >
            {isQuickSearching ? <Spinner /> : <Search />}
            {isQuickSearching ? "Searching..." : "Search"}
          </Button>
        </div>

        {searchResult && (
          <div className="flex flex-col gap-2">
            {searchResult.length ? (
              searchResult.map((result, index) => (
                <div
                  className="rounded-lg border bg-muted/40 p-3 text-sm"
                  key={
                    result?.standard?.id ||
                    result?.standard?.Standard_id ||
                    `${result?.requested_standard || "standard"}-${index}`
                  }
                >
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div>
                      <div className="text-xs text-muted-foreground">Requested</div>
                      <div className="font-medium">
                        {displayValue(result?.requested_standard)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Result</div>
                      <div className="font-medium">
                        {displayValue(
                          result?.standard?.display_stdNo ||
                            result?.standard?.standardno ||
                            result?.replacement_standard
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">Status</div>
                      <div className="font-medium">
                        {displayValue(result?.status)}
                      </div>
                    </div>
                  </div>
                  {result?.standard?.title && (
                    <p className="mt-2 text-sm">{result.standard.title}</p>
                  )}
                  {result?.status_detail && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {result.status_detail}
                    </p>
                  )}
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                No matching standard was returned for this search.
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
