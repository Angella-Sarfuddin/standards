import { ArrowRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
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
  loading,
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xs tracking-[0.16em] text-muted-foreground">
          QUICK SEARCH
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex gap-2">
          <Input
            value={searchQuery}
            onChange={(event) => onSearchQueryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onSearch();
              }
            }}
            placeholder="e.g. ISO 530"
          />
          <Button type="button" onClick={onSearch} disabled={loading}>
            <Search />
            {loading ? "Searching..." : "Search"}
            <ArrowRight />
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
