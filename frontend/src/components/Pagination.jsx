import { Field, FieldLabel } from "@/components/ui/field";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PAGE_SIZE_OPTIONS } from "../constants.js";

export default function TablePagination({
  page,
  total,
  pageSize,
  onPageChange,
  onPageSizeChange,
  id = "select-rows-per-page",
}) {
  if (total <= 0) {
    return null;
  }

  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const onFirstPage = page <= 0;
  const onLastPage = page + 1 >= pageCount;

  const changePage = (event, nextPage) => {
    event.preventDefault();
    onPageChange(nextPage);
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <Field orientation="horizontal" className="w-fit">
        <FieldLabel htmlFor={id}>Rows per page</FieldLabel>
        <Select
          value={String(pageSize)}
          onValueChange={(value) => onPageSizeChange(Number(value))}
        >
          <SelectTrigger className="w-20" id={id}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent align="start">
            <SelectGroup>
              {PAGE_SIZE_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </Field>
      <Pagination className="mx-0 w-auto">
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              href="#"
              aria-disabled={onFirstPage}
              className={onFirstPage ? "pointer-events-none opacity-50" : undefined}
              onClick={(event) => {
                if (!onFirstPage) {
                  changePage(event, page - 1);
                } else {
                  event.preventDefault();
                }
              }}
            />
          </PaginationItem>
          <PaginationItem>
            <PaginationNext
              href="#"
              aria-disabled={onLastPage}
              className={onLastPage ? "pointer-events-none opacity-50" : undefined}
              onClick={(event) => {
                if (!onLastPage) {
                  changePage(event, page + 1);
                } else {
                  event.preventDefault();
                }
              }}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  );
}
