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
  loading,
}) {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-10">
      <section className="grid items-start gap-8 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="flex flex-col gap-4 pt-2">
          <div className="text-xs font-medium tracking-[0.18em] text-primary">
            STANDARDS SEARCH PLATFORM
          </div>
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Find the standards
            <br />
            your customer needs.
          </h1>
          <p className="max-w-md text-muted-foreground">
            Upload a customer list, verify every standard, then move directly
            into the quotation workspace.
          </p>
        </div>
        <QuickSearch
          searchQuery={searchQuery}
          onSearchQueryChange={onSearchQueryChange}
          onSearch={onSearch}
          searchResult={searchResult}
          loading={loading}
        />
      </section>

      <UploadZone selectedFile={selectedFile} onFileChange={onFileChange} />

      <PreviewTable
        previewRows={previewRows}
        visiblePreviewRows={visiblePreviewRows}
        previewPageStart={previewPageStart}
        previewPage={previewPage}
        onPreviewPageChange={onPreviewPageChange}
        onVerify={onVerify}
        loading={loading}
      />
    </main>
  );
}
