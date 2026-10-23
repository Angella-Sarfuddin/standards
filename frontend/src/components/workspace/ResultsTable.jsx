import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EMPTY } from "../../constants.js";
import { displayValue, getResultKey } from "../../utils/standards.js";

function statusClass(status) {
  if (status === "AVAILABLE") {
    return "bg-emerald-100 text-emerald-800";
  }
  if (status === "SDO NOT FOUND") {
    return "bg-slate-100 text-slate-700";
  }
  return "bg-amber-100 text-amber-800";
}

export default function ResultsTable({
  visibleResults,
  resultsPageStart,
  selectedResultIds,
  allSelected,
  selectableCount,
  onSelectResult,
  onSelectAll,
  onManualSearch,
}) {
  return (
    <div className="overflow-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                checked={allSelected}
                onCheckedChange={onSelectAll}
                disabled={selectableCount === 0}
                aria-label="Select all visible results"
              />
            </TableHead>
            <TableHead>SDO</TableHead>
            <TableHead>Requested</TableHead>
            <TableHead>Matched</TableHead>
            <TableHead>Title</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visibleResults.map((result, pageIndex) => {
            const index = resultsPageStart + pageIndex;
            const checked = selectedResultIds.has(getResultKey(result));
            const canSelect = Boolean(result.matched && result.standard);

            return (
              <TableRow
                key={`result-${getResultKey(result)}`}
                data-state={checked ? "selected" : undefined}
              >
                <TableCell>
                  {canSelect ? (
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => onSelectResult(result)}
                      aria-label="Select result"
                    />
                  ) : (
                    EMPTY
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">
                    {displayValue(result.requested_sdo)}
                  </Badge>
                </TableCell>
                <TableCell>{displayValue(result.requested_standard)}</TableCell>
                <TableCell className="font-medium">
                  {displayValue(
                    result.standard?.display_stdNo || result.standard?.standardno
                  )}
                </TableCell>
                <TableCell className="max-w-64 truncate" title={result.standard?.title || ""}>
                  {displayValue(result.standard?.title)}
                </TableCell>
                <TableCell>
                  <Badge className={statusClass(result.status)}>
                    {displayValue(result.status)}
                  </Badge>
                  {result.status_detail && (
                    <div className="mt-1 max-w-56 text-xs text-muted-foreground">
                      {result.status_detail}
                    </div>
                  )}
                </TableCell>
                <TableCell>
                  {result.matched ? (
                    EMPTY
                  ) : (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => onManualSearch(index, result)}
                    >
                      Search manually
                      <ArrowRight />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
