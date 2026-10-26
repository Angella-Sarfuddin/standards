import PreviewTable from "./PreviewTable.jsx";
import QuickSearch from "./QuickSearch.jsx";
import UploadZone from "./UploadZone.jsx";

export default function Landing({
  searchQuery,
  onSearchQueryChange,
  onSearch,
  searchResult,
  selectedFile,
  onFileChange,
  previewRows,
  visiblePreviewRows,
  previewPageStart,
  previewPage,
  onPreviewPageChange,
  onVerify,
  isQuickSearching,
  isExtracting,
  isSearchingDocuments,
}) {
  return (
    <main className="mx-auto flex w-full max-w-[1440px] min-w-0 flex-col gap-7 px-4 py-7 sm:gap-8 sm:px-6 sm:py-10 lg:px-8">
      <section className="grid min-w-0 items-center gap-6 lg:grid-cols-[minmax(0,1.08fr)_minmax(380px,0.92fr)] lg:gap-10 xl:gap-14">
        <div className="flex min-w-0 flex-col gap-4 py-2 sm:gap-5">
          <div className="text-xs font-semibold tracking-[0.16em] text-primary">
            STANDARDS SEARCH PLATFORM
          </div>
          <h1 className="max-w-3xl text-[clamp(2.15rem,4.4vw,3.75rem)] leading-[1.04] font-semibold tracking-[-0.045em] text-balance">
            Find the standards
            <br className="hidden sm:block" />{" "}
            your customer needs.
          </h1>
          <p className="max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
            Upload a customer list, verify every standard, then move directly
            into the quotation workspace.
          </p>
        </div>
        <QuickSearch
          searchQuery={searchQuery}
          onSearchQueryChange={onSearchQueryChange}
          onSearch={onSearch}
          searchResult={searchResult}
          isQuickSearching={isQuickSearching}
        />
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
        onPreviewPageChange={onPreviewPageChange}
        onVerify={onVerify}
        isSearchingDocuments={isSearchingDocuments}
      />
    </main>
  );
}
