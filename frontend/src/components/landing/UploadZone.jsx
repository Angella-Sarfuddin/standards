import { ArrowRight, Upload } from "lucide-react";
import { Card } from "@/components/ui/card";

export default function UploadZone({ selectedFile, onFileChange }) {
  return (
    <section>
      <input
        id="document-upload"
        className="sr-only"
        type="file"
        accept=".xlsx,.xls,.csv,.pdf,.doc,.docx,.txt"
        onChange={onFileChange}
      />
      <label htmlFor="document-upload" className="block cursor-pointer">
        <Card className="flex flex-row items-center gap-4 border-dashed px-5 py-5 transition-colors hover:border-primary hover:bg-primary/5">
          <div className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Upload />
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium">
              {selectedFile ? selectedFile.name : "Drop your customer file here"}
            </div>
            <div className="text-sm text-muted-foreground">
              Excel · CSV · PDF · DOCX · TXT
            </div>
          </div>
          <div className="flex items-center gap-1 text-sm font-medium text-primary">
            {selectedFile ? "Change" : "Browse"}
            <ArrowRight className="size-4" />
          </div>
        </Card>
      </label>
    </section>
  );
}
