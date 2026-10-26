import { ArrowRight, Upload } from "lucide-react";
import { useState } from "react";
import { Card } from "@/components/ui/card";

const formatFileSize = (size) => {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
};

export default function UploadZone({
  selectedFile,
  onFileChange,
  isExtracting,
  disabled,
}) {
  const [isDragOver, setIsDragOver] = useState(false);

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragOver(false);
    if (!disabled && event.dataTransfer.files?.[0]) {
      onFileChange(event.dataTransfer.files[0]);
    }
  };

  return (
    <section
      className="min-w-0"
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setIsDragOver(true);
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setIsDragOver(false);
        }
      }}
      onDrop={handleDrop}
      aria-label="Upload a standards file"
    >
      <input
        id="document-upload"
        className="sr-only"
        type="file"
        accept=".xlsx,.xls,.csv,.pdf,.doc,.docx,.txt"
        onChange={onFileChange}
        disabled={disabled}
      />
      <label
        htmlFor="document-upload"
        aria-disabled={disabled}
        className={`block rounded-2xl focus-within:outline-none focus-within:ring-2 focus-within:ring-ring/60 ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
      >
        <Card
          className={`min-h-28 flex-row flex-wrap items-center gap-3 border border-dashed px-4 py-4 shadow-none ring-0 transition-colors sm:flex-nowrap sm:gap-4 sm:px-5 sm:py-5 ${isDragOver ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/50 hover:bg-primary/[0.02]"}`}
        >
          <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary sm:size-12">
            <Upload />
          </div>
          <div className="min-w-0 flex-1 basis-[calc(100%_-_4rem)] sm:basis-0">
            <div className="break-all text-sm font-semibold leading-5 sm:break-words" title={selectedFile?.name || ""}>
              {selectedFile?.name || "Drop your customer file here"}
            </div>
            {selectedFile && (
              <div className="mt-1 text-xs tabular-nums text-muted-foreground">
                {formatFileSize(selectedFile.size)}
              </div>
            )}
            {isExtracting && (
              <div className="text-xs text-primary" role="status">
                Reading your customer file...
              </div>
            )}
            <div className="mt-1 text-xs leading-5 text-muted-foreground sm:text-sm">
              XLSX · XLS · CSV · PDF · DOC · DOCX · TXT · up to 10 MB
            </div>
          </div>
          <div className="ml-auto flex h-9 shrink-0 items-center gap-2 rounded-lg border border-primary/15 bg-primary/[0.04] px-3 text-sm font-medium text-primary sm:ml-0">
            {isExtracting ? "Reading..." : selectedFile ? "Replace" : "Browse"}
            <ArrowRight className="size-4" />
          </div>
        </Card>
      </label>
    </section>
  );
}
