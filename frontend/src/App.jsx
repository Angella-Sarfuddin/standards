import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

import {
  searchStandards,
  exportFoundAndNotFoundBundle,
  exportLatestYearStandards,
  API_BASE_URL,
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

function App() {
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
  const [loading, setLoading] = useState(false);
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

    setLoading(true);
    setError("");
    setSearchResult(null);

    try {
      const response = await searchStandards(query);
      setSearchResult(Array.isArray(response) ? response : []);
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || "Unable to search the standard.");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = async (event) => {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    event.currentTarget.value = "";

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
    setLoading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post(
        `${API_BASE_URL}/documents/extract`,
        formData
      );
      const rows = response.data.results || [];

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
        err.response?.data?.detail || "Unable to read the uploaded document."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleStartSearch = async () => {
    if (!previewRows.length) {
      return;
    }

    setSearchRequestCount(previewRows.length);
    setLoading(true);
    setError("");
    setSearchResults([]);
    setResultsPage(0);
    setSelectedResults([]);
    setExportedDashboard(null);
    setResultViewFilter("all");
    setOpenGroupIndex(null);

    try {
      const response = await axios.post(`${API_BASE_URL}/documents/search`, {
        filename: selectedFile?.name || null,
        rows: previewRows,
      });

      const results = response.data.results || [];
      setSearchRequestCount(
        response.data.input_requests ?? previewRows.length
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
        err.response?.data?.detail || "Unable to search the uploaded document."
      );
    } finally {
      setLoading(false);
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
        const expandedSelections =
          await expandSeriesResultsForExport(selectedResults);
        const changed =
          expanded.length !== searchResults.length ||
          expanded.some((result, index) => result !== searchResults[index]);
        const selectionChanged =
          expandedSelections.length !== selectedResults.length ||
          expandedSelections.some(
            (result, index) => result !== selectedResults[index]
          );

        if (!cancelled && selectionChanged) {
          setSelectedResults(expandedSelections);
        }

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
  }, [searchResults, selectedResults]);

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

  const notFoundResults = searchResults.filter(
    (result) =>
      result.status === "NOT FOUND" ||
      result.status === "SDO NOT FOUND" ||
      !result.matched
  ).length;

  const sdoNotFoundCount = searchResults.filter(
    (result) => result.status === "SDO NOT FOUND"
  ).length;

  const selectedResultIdSet = new Set(selectedResults.map(getResultKey));

  const filteredSearchResults =
    resultViewFilter === "found"
      ? searchResults.filter((result) => result.matched)
      : resultViewFilter === "not_found"
        ? searchResults.filter((result) => !result.matched)
        : resultViewFilter === "sdo_missing"
          ? searchResults.filter((result) => result.status === "SDO NOT FOUND")
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

  const selectableResults = filteredSearchResults.filter(
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
    if (!searchResults.length) {
      return;
    }

    setLoading(true);
    setError("");

    try {
      if (exportMode === "latest-years") {
        await exportLatestYearStandards(searchResults);
      } else {
        const refreshedResults =
          await expandSeriesResultsForExport(searchResults);
        const quotationResults = selectedResults.length
          ? await expandSeriesResultsForExport(selectedResults)
          : refreshedResults.filter((result) => result.matched);
        await exportFoundAndNotFoundBundle(quotationResults, refreshedResults);
        setExportedDashboard(buildAnalysis(quotationResults));
        setOpenGroupIndex(null);
      }
    } catch (err) {
      console.error(err);
      setError(
        err.response?.data?.detail || "Unable to export selected standards."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleManualSearch = (rowIndex, result) => {
    setManualSearchRow(rowIndex);
    setManualSearchValue(result.requested_standard || "");
    setError("");
  };

  const handleManualSearchSubmit = async (rowIndex) => {
    const value = manualSearchValue.trim();

    if (!value) {
      return;
    }

    const currentRow = searchResults[rowIndex];

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

      setSearchResults((previous) =>
        previous.map((row, index) => {
          if (index !== rowIndex) {
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
        })
      );

      setExportedDashboard(
        buildAnalysis(
          searchResults.map((row, index) =>
            index === rowIndex ? result : row
          )
        )
      );

      setManualSearchRow(null);
      setManualSearchValue("");
    } catch (err) {
      console.error(err);
      setError(
        err.response?.data?.detail || "Unable to perform manual search."
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
    <div className="min-h-svh bg-background text-foreground">
      <Toaster />
      <TopBar />

      {!workspaceVisible ? (
        <Landing
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          onSearch={handleSearch}
          searchResult={searchResult}
          selectedFile={selectedFile}
          onFileChange={handleFileChange}
          previewRows={previewRows}
          visiblePreviewRows={visiblePreviewRows}
          previewPageStart={previewPageStart}
          previewPage={previewPage}
          onPreviewPageChange={setPreviewPage}
          onVerify={handleStartSearch}
          loading={loading}
        />
      ) : (
        <Workspace
          fileName={selectedFile?.name}
          loading={loading}
          onBack={() => setWorkspaceVisible(false)}
          onNewSearch={handleNewDocument}
          onExport={handleExportSelected}
          searchResults={searchResults}
          searchRequestCount={searchRequestCount}
          filteredCount={filteredSearchResults.length}
          visibleResults={visibleSearchResults}
          resultsPage={resultsPage}
          resultsPageStart={resultsPageStart}
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
