import { Search } from "lucide-react";
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
  selectedResultIds,
  allSelected,
  selectableCount,
  onSelectResult,
  onSelectAll,
  onManualSearch,
}) {
  return (
    <div className="min-w-0 rounded-xl border border-border/70 bg-card">
      <Table
        containerClassName="max-h-[min(36rem,64vh)]"
        className="min-w-[990px] table-fixed"
      >
        <TableHeader className="[&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:h-11 [&_th]:border-b [&_th]:border-border [&_th]:bg-muted [&_th]:text-[11px] [&_th]:font-semibold [&_th]:tracking-wide [&_th]:text-muted-foreground">
          <TableRow>
            <TableHead className="w-11 text-center">
              <Checkbox
                checked={allSelected}
                onCheckedChange={onSelectAll}
                disabled={selectableCount === 0}
                aria-label="Select all selectable results on this page"
              />
            </TableHead>
            <TableHead className="w-24">SDO</TableHead>
            <TableHead className="w-40">Requested</TableHead>
            <TableHead className="w-[170px]">Matched</TableHead>
            <TableHead className="w-[230px]">Title</TableHead>
            <TableHead className="w-[140px]">Status</TableHead>
            <TableHead className="w-[150px]">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visibleResults.map((result) => {
            const checked = selectedResultIds.has(getResultKey(result));
            const canSelect = Boolean(result.matched && result.standard);

            return (
              <TableRow
                key={`result-${getResultKey(result)}`}
                className="transition-colors hover:bg-primary/[0.025]"
                data-state={checked ? "selected" : undefined}
              >
                <TableCell className="text-center align-top tabular-nums">
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
                <TableCell className="whitespace-normal break-words align-top">
                  <Badge variant="secondary">
                    {displayValue(result.requested_sdo)}
                  </Badge>
                </TableCell>
                <TableCell className="whitespace-normal break-words align-top font-medium leading-5">
                  {displayValue(result.requested_standard)}
                </TableCell>
                <TableCell className="whitespace-normal break-words align-top font-medium leading-5 text-foreground">
                  {displayValue(
                    result.standard?.display_stdNo || result.standard?.standardno
                  )}
                </TableCell>
                <TableCell
                  className="max-w-[230px] whitespace-normal break-words align-top leading-5 text-muted-foreground"
                  title={result.standard?.title || ""}
                >
                  {displayValue(result.standard?.title)}
                </TableCell>
                <TableCell>
                  <Badge className={`h-6 rounded-full px-2.5 text-[11px] font-semibold ${statusClass(result.status)}`}>
                    {displayValue(result.status)}
                  </Badge>
                  {result.status_detail && (
                    <div className="mt-1 max-w-56 whitespace-normal break-words text-xs leading-5 text-muted-foreground">
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
                      className="h-9 w-fit rounded-lg whitespace-normal px-3"
                      onClick={() => onManualSearch(result)}
                    >
                      Search manually
                      <Search />
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
