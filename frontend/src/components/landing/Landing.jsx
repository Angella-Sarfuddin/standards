import PreviewTable from "./PreviewTable.jsx";
import UploadZone from "./UploadZone.jsx";

export default function Landing({
  selectedFile,
  onFileChange,
  previewRows,
  visiblePreviewRows,
  previewPageStart,
  previewPage,
  pageSize,
  onPreviewPageChange,
  onPageSizeChange,
  onVerify,
  isExtracting,
  isSearchingDocuments,
}) {
  return (
    <main className="mx-auto flex w-full max-w-[1440px] min-w-0 flex-col gap-8 px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <section className="max-w-3xl">
        <h1 className="text-[clamp(2rem,4vw,3.25rem)] leading-[1.08] font-semibold tracking-[-0.04em] text-balance">
          Find the standards your customer needs.
        </h1>
        <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">
          Search from the header, or upload a customer list and move straight
          into the quotation workspace.
        </p>
      </section>

      <UploadZone
        selectedFile={selectedFile}
        onFileChange={onFileChange}
        isExtracting={isExtracting}
        disabled={isExtracting || isSearchingDocuments}
      />

      <PreviewTable
        previewRows={previewRows}
        visiblePreviewRows={visiblePreviewRows}
        previewPageStart={previewPageStart}
        previewPage={previewPage}
        pageSize={pageSize}
        onPreviewPageChange={onPreviewPageChange}
        onPageSizeChange={onPageSizeChange}
        onVerify={onVerify}
        isSearchingDocuments={isSearchingDocuments}
      />
    </main>
  );
}
