import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
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
  onPreviewPageChange,
  onVerify,
  loading,
}) {
  if (!previewRows.length) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <div className="text-xs tracking-[0.16em] text-muted-foreground">
          VERIFICATION READY
        </div>
        <CardTitle className="text-xl">
          {previewRows.length} standards detected
        </CardTitle>
        <CardDescription>
          Review the extracted standards before running the database search.
        </CardDescription>
        <CardAction>
          <Button type="button" onClick={onVerify} disabled={loading}>
            {loading ? "Verifying..." : "Verify & Search"}
            <ArrowRight />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">#</TableHead>
                <TableHead>SDO</TableHead>
                <TableHead>Standard</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visiblePreviewRows.map((row, pageIndex) => {
                const index = previewPageStart + pageIndex;

                return (
                  <TableRow key={index}>
                    <TableCell>{String(index + 1).padStart(2, "0")}</TableCell>
                    <TableCell>{displayValue(row.sdo_name)}</TableCell>
                    <TableCell>{displayValue(row.displaystdno)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        <Pagination
          page={previewPage}
          total={previewRows.length}
          onPageChange={onPreviewPageChange}
        />
      </CardContent>
    </Card>
  );
}
