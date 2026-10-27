import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import Pagination from "../Pagination.jsx";
import { displayValue } from "../../utils/standards.js";

export default function PreviewTable({
  previewRows,
  visiblePreviewRows,
  previewPageStart,
  previewPage,
  pageSize,
  onPreviewPageChange,
  onPageSizeChange,
  onVerify,
  isSearchingDocuments,
}) {
  if (!previewRows.length) {
    return null;
  }

  return (
    <Card className="border border-border/70 shadow-sm ring-0">
      <CardContent className="flex min-w-0 flex-col gap-4 px-4 py-5 sm:px-6 sm:py-6">
        <div className="min-w-0 overflow-hidden rounded-xl border border-border/70 bg-background">
          <div className="flex items-center justify-between gap-3 border-b bg-muted px-4 py-2.5">
            <div className="flex min-w-0 items-center gap-3">
              <span className="shrink-0 text-[11px] font-semibold tracking-[0.14em] text-muted-foreground">
                VERIFICATION READY
              </span>
              <span className="truncate text-sm font-semibold tracking-tight">
                {previewRows.length} standards detected
              </span>
            </div>
            <Button
              type="button"
              onClick={onVerify}
              className="h-8 shrink-0 rounded-lg"
              disabled={isSearchingDocuments}
            >
              {isSearchingDocuments ? <Spinner /> : null}
              {isSearchingDocuments ? "Verifying..." : "Verify & Search"}
              {isSearchingDocuments ? null : <ArrowRight />}
            </Button>
          </div>
          <Table
            containerClassName="max-h-[min(28rem,58vh)]"
            className="min-w-[620px] table-fixed"
          >
            <TableHeader className="[&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-muted [&_th]:text-[11px] [&_th]:font-semibold [&_th]:text-muted-foreground">
              <TableRow>
                <TableHead className="w-16">#</TableHead>
                <TableHead className="w-44">SDO</TableHead>
                <TableHead>Standard</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visiblePreviewRows.map((row, pageIndex) => {
                const index = previewPageStart + pageIndex;

                return (
                  <TableRow key={index}>
                    <TableCell>{String(index + 1).padStart(2, "0")}</TableCell>
                    <TableCell className="whitespace-normal break-words align-top">{displayValue(row.sdo_name)}</TableCell>
                    <TableCell className="whitespace-normal break-words align-top font-medium">{displayValue(row.displaystdno)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        <Pagination
          id="preview-rows-per-page"
          page={previewPage}
          total={previewRows.length}
          pageSize={pageSize}
          onPageChange={onPreviewPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      </CardContent>
    </Card>
  );
}
