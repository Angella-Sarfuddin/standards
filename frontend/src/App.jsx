import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  searchStandards,
  searchDocumentRequest,
  extractDocument,
  exportFoundAndNotFoundBundle,
  exportLatestYearStandards,
} from "./api/index.js";
import { TABLE_PAGE_SIZE } from "./constants.js";
import { buildAnalysis } from "./utils/analysis.js";
import {
  expandSeriesResultsForExport,
  getManualSearchValue,
  getResultKey,
  getSdoFromStandardNumber,
} from "./utils/standards.js";
import Landing from "./components/landing/Landing.jsx";
import ManualSearchDialog from "./components/ManualSearchDialog.jsx";
import TopBar from "./components/TopBar.jsx";
import Workspace from "./components/workspace/Workspace.jsx";
import { Toaster } from "@/components/ui/sonner";

const getApiErrorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  if (Array.isArray(detail)) {
    const messages = [
      ...new Set(
        detail
          .map((item) =>
            typeof item?.msg === "string" ? item.msg.trim() : ""
          )
          .filter(Boolean)
      ),
    ];

    if (messages.length) {
      return messages.join("; ");
    }
  }

  return fallback;
};

const isNotFoundResult = (result) =>
  result.status === "NOT FOUND" ||
  result.status === "SDO NOT FOUND" ||
  !result.matched;
const isSdoMissingResult = (result) => result.status === "SDO NOT FOUND";
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const SUPPORTED_UPLOAD_EXTENSIONS = new Set([
  ".xlsx",
  ".xls",
  ".csv",
  ".pdf",
  ".doc",
  ".docx",
  ".txt",
]);

function App() {
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem("standards-intelligence-theme");
    return saved === "dark";
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
    document.documentElement.style.colorScheme = isDark ? "dark" : "light";
    localStorage.setItem("standards-intelligence-theme", isDark ? "dark" : "light");
  }, [isDark]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);

  const [selectedFile, setSelectedFile] = useState(null);
  const [previewRows, setPreviewRows] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [searchRequestCount, setSearchRequestCount] = useState(0);
  const [previewPage, setPreviewPage] = useState(0);
  const [resultsPage, setResultsPage] = useState(0);

  const previewPageStart = previewPage * TABLE_PAGE_SIZE;
  const visiblePreviewRows = previewRows.slice(
    previewPageStart,
    previewPageStart + TABLE_PAGE_SIZE
  );
  const resultsPageStart = resultsPage * TABLE_PAGE_SIZE;

  const [workspaceVisible, setWorkspaceVisible] = useState(false);
  const [isQuickSearching, setIsQuickSearching] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isSearchingDocuments, setIsSearchingDocuments] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState("");

  const [selectedResults, setSelectedResults] = useState([]);
  const [exportedDashboard, setExportedDashboard] = useState(null);
  const [exportMode, setExportMode] = useState("found-and-not-found");
  const [resultViewFilter, setResultViewFilter] = useState("all");
  const [openGroupIndex, setOpenGroupIndex] = useState(null);

  const [manualSearchRow, setManualSearchRow] = useState(null);
  const [manualSearchValue, setManualSearchValue] = useState("");
  const [manualSearchLoading, setManualSearchLoading] = useState(false);

  const clearFileInput = () => {
    const input = document.getElementById("document-upload");
    if (input) {
      input.value = "";
    }
  };

  const resetDocumentState = () => {
    setSelectedFile(null);
    setPreviewRows([]);
    setSearchResults([]);
    setSearchRequestCount(0);
    setPreviewPage(0);
    setResultsPage(0);
    setSelectedResults([]);
    setExportedDashboard(null);
    setResultViewFilter("all");
    setWorkspaceVisible(false);
    setOpenGroupIndex(null);
    setManualSearchRow(null);
    setManualSearchValue("");
    setError("");
    setSearchResult(null);
  };

  const handleNewDocument = () => {
    resetDocumentState();
    setSearchQuery("");
    clearFileInput();
  };

  const handleSearch = async () => {
    const query = searchQuery.trim();

    if (!query) {
      return;
    }

    setIsQuickSearching(true);
    setError("");
    setSearchResult(null);

    try {
      const response = await searchStandards(query);
      setSearchResult(Array.isArray(response) ? response : []);
    } catch (err) {
      console.error(err);
      setError(getApiErrorMessage(err, "Unable to search the standard."));
    } finally {
      setIsQuickSearching(false);
    }
  };

  const handleFileChange = async (eventOrFile) => {
    const file = eventOrFile?.target?.files
      ? eventOrFile.target.files[0]
      : eventOrFile;

    if (eventOrFile?.currentTarget) {
      eventOrFile.currentTarget.value = "";
    }

    if (!file) {
      return;
    }

    const extension = file.name?.match(/\.[^.]+$/)?.[0]?.toLowerCase();
    if (!SUPPORTED_UPLOAD_EXTENSIONS.has(extension)) {
      setError(
        "Unsupported file type. Choose XLSX, XLS, CSV, PDF, DOC, DOCX, or TXT."
      );
      return;
    }

    if (file.size > MAX_UPLOAD_BYTES) {
      setError("The file is too large. Choose a file no larger than 10 MB.");
      return;
    }

    setSelectedFile(file);
    setPreviewRows([]);
    setSearchResults([]);
    setSearchRequestCount(0);
    setPreviewPage(0);
    setResultsPage(0);
    setSelectedResults([]);
    setExportedDashboard(null);
    setResultViewFilter("all");
    setWorkspaceVisible(false);
    setOpenGroupIndex(null);
    setError("");
    setIsExtracting(true);

    try {
      const response = await extractDocument(file);
      const rows = response.results || [];

      setPreviewRows(rows);
      setPreviewPage(0);

      if (!rows.length) {
        setError("No standards could be extracted from this file.");
      }
    } catch (err) {
      console.error(err);
      setSelectedFile(null);
      setPreviewRows([]);
      setError(
        getApiErrorMessage(err, "Unable to read the uploaded document.")
      );
    } finally {
      setIsExtracting(false);
    }
  };

  const handleStartSearch = async () => {
    if (!previewRows.length) {
      return;
    }

    setSearchRequestCount(previewRows.length);
    setIsSearchingDocuments(true);
    setError("");
    setSearchResults([]);
    setResultsPage(0);
    setSelectedResults([]);
    setExportedDashboard(null);
    setResultViewFilter("all");
    setOpenGroupIndex(null);

    try {
      const response = await searchDocumentRequest(
        previewRows,
        selectedFile?.name || null
      );

      const results = response.results || [];
      setSearchRequestCount(
        response.input_requests ?? previewRows.length
      );

      const displayResults = await expandSeriesResultsForExport(results);

      setSearchResults(
        displayResults.map((result, index) => ({
          ...result,
          _resultKey: index,
        }))
      );
      setWorkspaceVisible(true);
      setExportedDashboard(buildAnalysis(displayResults));

      window.scrollTo({
        top: 0,
        behavior: "smooth",
      });
    } catch (err) {
      console.error(err);
      setError(
        getApiErrorMessage(
          err,
          "Unable to search the uploaded document."
        )
      );
    } finally {
      setIsSearchingDocuments(false);
    }
  };

  useEffect(() => {
    if (!searchResults.length) {
      return undefined;
    }

    let cancelled = false;
    const normalizeSeriesRows = async () => {
      try {
        const expanded = await expandSeriesResultsForExport(searchResults);
        const changed =
          expanded.length !== searchResults.length ||
          expanded.some((result, index) => result !== searchResults[index]);

        if (!cancelled && changed) {
          const normalized = expanded.map((result, index) => ({
            ...result,
            _resultKey: index,
          }));
          setSearchResults(normalized);
          setResultsPage(0);
          setExportedDashboard(buildAnalysis(normalized));
        }
      } catch (normalizationError) {
        console.error("Unable to expand series results:", normalizationError);
      }
    };

    normalizeSeriesRows();
    return () => {
      cancelled = true;
    };
  }, [searchResults]);

  useEffect(() => {
    if (!error) {
      toast.dismiss("app-error");
      return;
    }

    toast.error(error, {
      id: "app-error",
      onDismiss: () => setError(""),
    });
  }, [error]);

  const matchedCount = searchResults.filter((result) => result.matched).length;

  const notFoundResults = searchResults.filter(isNotFoundResult).length;

  const sdoNotFoundCount = searchResults.filter(isSdoMissingResult).length;

  const selectedResultIdSet = new Set(selectedResults.map(getResultKey));

  const filteredSearchResults =
    resultViewFilter === "found"
      ? searchResults.filter((result) => result.matched)
      : resultViewFilter === "not_found"
        ? searchResults.filter(isNotFoundResult)
        : resultViewFilter === "sdo_missing"
          ? searchResults.filter(isSdoMissingResult)
          : resultViewFilter === "selected"
            ? searchResults.filter((result) =>
                selectedResultIdSet.has(getResultKey(result))
              )
            : searchResults;

  const visibleSearchResults = filteredSearchResults.slice(
    resultsPageStart,
    resultsPageStart + TABLE_PAGE_SIZE
  );

  const toggleResultViewFilter = (nextFilter) => {
    setResultViewFilter((current) =>
      current === nextFilter ? "all" : nextFilter
    );
    setResultsPage(0);
  };

  const selectableResults = visibleSearchResults.filter(
    (result) => result.matched && result.standard
  );

  const selectedResultIds = new Set(selectedResults.map(getResultKey));

  const allSelected =
    selectableResults.length > 0 &&
    selectableResults.every((result) =>
      selectedResultIds.has(getResultKey(result))
    );

  const handleSelectResult = (result) => {
    if (!result.matched || !result.standard) {
      return;
    }

    const resultKey = getResultKey(result);

    setSelectedResults((previous) => {
      const exists = previous.some((item) => getResultKey(item) === resultKey);

      if (exists) {
        return previous.filter((item) => getResultKey(item) !== resultKey);
      }

      return [...previous, result];
    });
  };

  const handleSelectAll = () => {
    if (allSelected) {
      const visibleIds = new Set(selectableResults.map(getResultKey));

      setSelectedResults((previous) =>
        previous.filter((item) => !visibleIds.has(getResultKey(item)))
      );
      return;
    }

    setSelectedResults((previous) => {
      const merged = [...previous];
      const existing = new Set(previous.map(getResultKey));

      selectableResults.forEach((result) => {
        const resultKey = getResultKey(result);
        if (!existing.has(resultKey)) {
          existing.add(resultKey);
          merged.push(result);
        }
      });

      return merged;
    });
  };

  const handleExportSelected = async () => {
    if (!selectedResults.length) {
      return;
    }

    setIsExporting(true);
    setError("");

    try {
      const quotationResults = await expandSeriesResultsForExport(
        selectedResults
      );

      if (exportMode === "latest-years") {
        await exportLatestYearStandards(quotationResults);
      } else {
        const refreshedResults =
          await expandSeriesResultsForExport(searchResults);
        await exportFoundAndNotFoundBundle(quotationResults, refreshedResults);
        setExportedDashboard(buildAnalysis(quotationResults));
        setOpenGroupIndex(null);
      }
    } catch (err) {
      console.error(err);
      setError(
        getApiErrorMessage(err, "Unable to export selected standards.")
      );
    } finally {
      setIsExporting(false);
    }
  };

  const handleManualSearch = (result) => {
    setManualSearchRow(getResultKey(result));
    setManualSearchValue(result.requested_standard || "");
    setError("");
  };

  const handleManualSearchSubmit = async (resultKey) => {
    const value = manualSearchValue.trim();

    if (!value) {
      return;
    }

    const currentRow = searchResults.find(
      (row) => getResultKey(row) === resultKey
    );

    if (!currentRow) {
      return;
    }

    setManualSearchLoading(true);
    setError("");

    try {
      const searchValue = getManualSearchValue(value, currentRow.requested_sdo);
      const response = await searchStandards(searchValue);
      const results = Array.isArray(response)
        ? response
        : Array.isArray(response?.results)
          ? response.results
          : [];
      const result = results[0] || null;

      const updatedSearchResults = searchResults.map((row) => {
        if (getResultKey(row) !== resultKey) {
          return row;
        }

        if (result?.matched && result.standard) {
          const standard = result.standard;

          return {
            ...row,
            requested_standard: value,
            requested_sdo:
              getSdoFromStandardNumber(standard.standardno) ||
              row.requested_sdo,
            matched: true,
            status: result.status || "AVAILABLE",
            standard,
            manual_search: true,
          };
        }

        return {
          ...row,
          requested_standard: value,
          matched: false,
          status: "NOT FOUND",
          standard: null,
          manual_search: true,
        };
      });

      setSearchResults(updatedSearchResults);
      setExportedDashboard(buildAnalysis(updatedSearchResults));

      setManualSearchRow(null);
      setManualSearchValue("");
    } catch (err) {
      console.error(err);
      setError(
        getApiErrorMessage(err, "Unable to perform manual search.")
      );
    } finally {
      setManualSearchLoading(false);
    }
  };

  const handleCancelManualSearch = () => {
    setManualSearchRow(null);
    setManualSearchValue("");
  };

  return (
    <div className="app-shell relative min-h-svh bg-background text-foreground">
      <Toaster />
      <TopBar isDark={isDark} onToggleTheme={() => setIsDark((current) => !current)} />

      {!workspaceVisible ? (
        <Landing
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          onSearch={handleSearch}
          searchResult={searchResult}
          selectedFile={selectedFile}
          onFileChange={handleFileChange}
          isExtracting={isExtracting}
          previewRows={previewRows}
          visiblePreviewRows={visiblePreviewRows}
          previewPageStart={previewPageStart}
          previewPage={previewPage}
          onPreviewPageChange={setPreviewPage}
          onVerify={handleStartSearch}
          isQuickSearching={isQuickSearching}
          isSearchingDocuments={isSearchingDocuments}
        />
      ) : (
        <Workspace
          fileName={selectedFile?.name}
          isExporting={isExporting}
          onBack={() => setWorkspaceVisible(false)}
          onNewSearch={handleNewDocument}
          onExport={handleExportSelected}
          searchResults={searchResults}
          searchRequestCount={searchRequestCount}
          filteredCount={filteredSearchResults.length}
          visibleResults={visibleSearchResults}
          resultsPage={resultsPage}
          onResultsPageChange={setResultsPage}
          resultViewFilter={resultViewFilter}
          matchedCount={matchedCount}
          notFoundCount={notFoundResults}
          sdoNotFoundCount={sdoNotFoundCount}
          selectedCount={selectedResults.length}
          onToggleFilter={toggleResultViewFilter}
          selectedResultIds={selectedResultIds}
          allSelected={allSelected}
          selectableCount={selectableResults.length}
          onSelectResult={handleSelectResult}
          onSelectAll={handleSelectAll}
          onManualSearch={handleManualSearch}
          exportMode={exportMode}
          onExportModeChange={setExportMode}
          dashboard={exportedDashboard}
          openGroupIndex={openGroupIndex}
          onToggleGroup={setOpenGroupIndex}
        />
      )}

      <ManualSearchDialog
        open={manualSearchRow !== null}
        value={manualSearchValue}
        loading={manualSearchLoading}
        onChange={setManualSearchValue}
        onSubmit={() => handleManualSearchSubmit(manualSearchRow)}
        onCancel={handleCancelManualSearch}
      />
    </div>
  );
}

export default App;

