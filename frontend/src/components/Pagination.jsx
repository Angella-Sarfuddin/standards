import { TABLE_PAGE_SIZE } from "../constants.js";
import { Button } from "@/components/ui/button";

export default function Pagination({ page, total, onPageChange }) {
  const pageCount = Math.ceil(total / TABLE_PAGE_SIZE);

  if (pageCount <= 1) {
    return null;
  }

  const firstRow = page * TABLE_PAGE_SIZE + 1;
  const lastRow = Math.min(firstRow + TABLE_PAGE_SIZE - 1, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-1 text-xs text-muted-foreground sm:text-sm">
      <span className="tabular-nums">
        Showing {firstRow}-{lastRow} of {total}
      </span>
      <div className="flex items-center gap-1.5 sm:gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 rounded-lg"
          onClick={() => onPageChange(page - 1)}
          disabled={page === 0}
        >
          Previous
        </Button>
        <span className="min-w-24 text-center text-xs font-medium tabular-nums text-foreground">
          Page {page + 1} of {pageCount}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 rounded-lg"
          onClick={() => onPageChange(page + 1)}
          disabled={page + 1 >= pageCount}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
