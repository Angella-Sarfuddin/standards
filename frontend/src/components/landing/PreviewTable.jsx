import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
      <CardHeader className="gap-x-4 px-4 pt-5 sm:px-6 sm:pt-6">
        <div className="text-xs font-semibold tracking-[0.14em] text-muted-foreground">
          VERIFICATION READY
        </div>
        <CardTitle className="text-xl font-semibold tracking-tight sm:text-2xl">
          {previewRows.length} standards detected
        </CardTitle>
        <CardDescription className="leading-6">
          Review the extracted standards before running the database search.
        </CardDescription>
        <CardAction className="col-span-2 row-start-4 justify-self-stretch pt-2 sm:col-span-1 sm:row-span-2 sm:row-start-1 sm:justify-self-end sm:pt-0">
          <Button
            type="button"
            onClick={onVerify}
            className="h-10 w-full rounded-xl sm:w-auto"
            disabled={isSearchingDocuments}
          >
            {isSearchingDocuments ? <Spinner /> : null}
            {isSearchingDocuments ? "Verifying..." : "Verify & Search"}
            {isSearchingDocuments ? null : <ArrowRight />}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex min-w-0 flex-col gap-4 px-4 pb-5 sm:px-6 sm:pb-6">
        <div className="min-w-0 rounded-xl border border-border/70 bg-background">
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
