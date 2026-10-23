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
    <div className="flex flex-wrap items-center justify-between gap-3 px-1 text-sm text-muted-foreground">
      <span>
        Showing {firstRow}-{lastRow} of {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page === 0}
        >
          Previous
        </Button>
        <span className="min-w-24 text-center text-foreground">
          Page {page + 1} of {pageCount}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page + 1 >= pageCount}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
