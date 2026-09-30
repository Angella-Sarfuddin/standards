import { useState } from "react";
import axios from "axios";

import {
  searchStandards,
  exportSelectedStandards,
} from "./services/api";

import "./App.css";

const KNOWN_SDOS = [
  "ISO",
  "ISO/IEC",
  "ISO/TR",
  "ISO/TS",
  "JIS",
  "JIS K",
  "UL",
  "ACI",
  "API",
];

const GROUPING_THRESHOLD = 25;
const TABLE_PAGE_SIZE = 100;
const EMPTY = "-";

function App() {
  // =========================================================
  // NORMAL SEARCH
  // =========================================================

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);

  // =========================================================
  // DOCUMENT
  // =========================================================

  const [selectedFile, setSelectedFile] = useState(null);
  const [previewRows, setPreviewRows] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [previewPage, setPreviewPage] = useState(0);
  const [resultsPage, setResultsPage] = useState(0);

  const previewPageStart = previewPage * TABLE_PAGE_SIZE;
  const visiblePreviewRows = previewRows.slice(
    previewPageStart,
    previewPageStart + TABLE_PAGE_SIZE
  );

  const resultsPageStart = resultsPage * TABLE_PAGE_SIZE;

  // =========================================================
  // WORKSPACE
  // =========================================================

  const [workspaceVisible, setWorkspaceVisible] =
    useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // =========================================================
  // SELECTION / EXPORT
  // =========================================================

  const [selectedResults, setSelectedResults] =
    useState([]);

  const [exportedDashboard, setExportedDashboard] =
    useState(null);

  // all | found | not_found | sdo_missing | selected
  const [resultViewFilter, setResultViewFilter] =
    useState("all");

  // =========================================================
  // GROUP INTERACTION
  // =========================================================

  const [openGroupIndex, setOpenGroupIndex] =
    useState(null);

  // =========================================================
  // MANUAL SEARCH
  // =========================================================

  const [manualSearchRow, setManualSearchRow] =
    useState(null);

  const [manualSearchValue, setManualSearchValue] =
    useState("");

  const [manualSearchLoading, setManualSearchLoading] =
    useState(false);

  // =========================================================
  // HELPERS
  // =========================================================

  const displayValue = (value) => {
    if (
      value === null ||
      value === undefined ||
      String(value).trim() === ""
    ) {
      return EMPTY;
    }

    return value;
  };

  const renderPagination = (
    page,
    total,
    onPageChange
  ) => {
    const pageCount = Math.ceil(
      total / TABLE_PAGE_SIZE
    );

    if (pageCount <= 1) {
      return null;
    }

    const firstRow = page * TABLE_PAGE_SIZE + 1;
    const lastRow = Math.min(
      firstRow + TABLE_PAGE_SIZE - 1,
      total
    );

    return (
      <div className="table-pagination">
        <span>
          Showing {firstRow}-{lastRow} of {total}
        </span>

        <div className="table-pagination-controls">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page === 0}
          >
            Previous
          </button>
          <span className="table-page-number">
            Page {page + 1} of {pageCount}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page + 1 >= pageCount}
          >
            Next
          </button>
        </div>
      </div>
    );
  };

  const getStandardId = (result) => {
    return (
      result?.standard?.id ??
      result?.standard?.Standard_id ??
      result?.standard?.standard_id ??
      result?.requested_standard
    );
  };

  const getPrice = (result) => {
    const value =
      result?.standard?.enrichment?.price;

    const price = Number(value);

    return Number.isFinite(price)
      ? price
      : 0;
  };

  const getClassifications = (result) => {
    const classifications =
      result?.standard?.enrichment?.classifications;

    return Array.isArray(classifications)
      ? classifications
      : [];
  };

  const hasSdo = (value) => {
    if (!value) {
      return false;
    }

    const upper = value.toUpperCase();

    return KNOWN_SDOS.some(
      (sdo) =>
        upper === sdo ||
        upper.startsWith(`${sdo} `) ||
        upper.startsWith(`${sdo}/`)
    );
  };

  const getSdoFromStandardNumber = (
    standardNumber
  ) => {
    if (!standardNumber) {
      return null;
    }

    const match =
      standardNumber
        .trim()
        .match(
          /^(ISO(?:\/[A-Z]+(?:\/[A-Z]+)?)?|JIS(?:\s+[A-Z])?|UL|ACI(?:\s+[A-Z]+)?|API(?:\s+[A-Z]+)?)/i
        );

    return match
      ? match[1].trim()
      : null;
  };

  const getManualSearchValue = (
    value,
    currentSdo
  ) => {
    if (
      currentSdo &&
      !hasSdo(value)
    ) {
      return `${currentSdo} ${value}`;
    }

    return value;
  };

  const clearFileInput = () => {
    const input =
      document.getElementById(
        "document-upload"
      );

    if (input) {
      input.value = "";
    }
  };

  // =========================================================
  // RESET
  // =========================================================

  const resetDocumentState = () => {
    setSelectedFile(null);
    setPreviewRows([]);
    setSearchResults([]);
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

  // =========================================================
  // NORMAL SEARCH
  // =========================================================

  const handleSearch = async () => {
    const query =
      searchQuery.trim();

    if (!query) {
      return;
    }

    setLoading(true);
    setError("");
    setSearchResult(null);

    try {
      const response =
        await searchStandards(query);

      setSearchResult(response);
    } catch (err) {
      console.error(err);

      setError(
        err.response?.data?.detail ||
          "Unable to search the standard."
      );
    } finally {
      setLoading(false);
    }
  };

  // =========================================================
  // FILE UPLOAD / EXTRACTION
  // =========================================================

  const handleFileChange = async (
    event
  ) => {
    const file =
      event.target.files?.[0];

    if (!file) {
      return;
    }

    setSelectedFile(file);
    setPreviewRows([]);
    setSearchResults([]);
    setPreviewPage(0);
    setResultsPage(0);
    setSelectedResults([]);
    setExportedDashboard(null);
    setResultViewFilter("all");
    setWorkspaceVisible(false);
    setOpenGroupIndex(null);
    setError("");
    setLoading(true);

    const formData =
      new FormData();

    formData.append(
      "file",
      file
    );

    try {
      const response =
        await axios.post(
          "http://127.0.0.1:8000/documents/extract",
          formData
        );

      const rows =
        response.data.results ||
        [];

      setPreviewRows(rows);
      setPreviewPage(0);

      if (!rows.length) {
        setError(
          "No standards could be extracted from this file."
        );
      }
    } catch (err) {
      console.error(err);

      setSelectedFile(null);
      setPreviewRows([]);

      setError(
        err.response?.data?.detail ||
          "Unable to read the uploaded document."
      );
    } finally {
      setLoading(false);
    }
  };

  // =========================================================
  // SEARCH EXTRACTED DOCUMENT
  // =========================================================

  const handleStartSearch =
    async () => {
      if (!previewRows.length) {
        return;
      }

      setLoading(true);
      setError("");
      setSearchResults([]);
      setResultsPage(0);
      setSelectedResults([]);
      setExportedDashboard(null);
      setResultViewFilter("all");
      setOpenGroupIndex(null);

      try {
        const response =
          await axios.post(
            "http://127.0.0.1:8000/documents/search",
            {
              filename:
                selectedFile?.name ||
                null,
              rows: previewRows,
            }
          );

        const results =
          response.data.results ||
          [];

        setSearchResults(
          results
        );

        /*
         * IMPORTANT:
         *
         * As soon as verification/search
         * completes, move the user into
         * the Results + Dashboard workspace.
         */
        setWorkspaceVisible(true);

        /*
         * Dashboard is generated immediately
         * from verified results.
         */
        setExportedDashboard(
          buildAnalysis(results)
        );

        window.scrollTo({
          top: 0,
          behavior: "smooth",
        });
      } catch (err) {
        console.error(err);

        setError(
          err.response?.data?.detail ||
            "Unable to search the uploaded document."
        );
      } finally {
        setLoading(false);
      }
    };

  // =========================================================
// BUILD DASHBOARD ANALYSIS
// =========================================================

const buildAnalysis = (
  results
) => {
  /*
   * All matched rows.
   *
   * This is the actual verification count shown
   * on the dashboard.
   */
  const matchedResults =
    results.filter(
      (result) =>
        result?.matched &&
        result?.standard
    );

  /*
   * Unique matched standards.
   *
   * Keep this deduplication for grouping, pricing
   * and unique-standard analysis.
   */
  const uniqueResults = [];
  const seenIds = new Set();

  matchedResults.forEach(
    (result) => {
      const id =
        getStandardId(result);

      if (
        seenIds.has(id)
      ) {
        return;
      }

      seenIds.add(id);

      uniqueResults.push(
        result
      );
    }
  );

  /*
   * IMPORTANT:
   *
   * Verified = all matched customer rows.
   * Do NOT use uniqueResults.length here.
   */
  const total =
    matchedResults.length;

  /*
   * Pricing continues to use unique standards
   * so duplicate rows do not double-count price.
   */
  const totalPrice =
    uniqueResults.reduce(
      (sum, result) =>
        sum + getPrice(result),
      0
    );

  /*
   * Grouping is triggered by the actual number
   * of matched customer rows.
   */
  const groupingEnabled =
    total >
    GROUPING_THRESHOLD;

  const groupsMap =
    new Map();

  const sdoMap =
    new Map();

  /*
   * SDO breakdown uses ALL matched rows so that
   * the dashboard breakdown matches Verified.
   */
  matchedResults.forEach(
    (result) => {
      const sdo =
        result.requested_sdo ||
        getSdoFromStandardNumber(
          result.standard
            ?.standardno
        ) ||
        "Unknown";

      sdoMap.set(
        sdo,
        (sdoMap.get(sdo) ||
          0) + 1
      );
    }
  );

  /*
   * Grouping itself continues to work on
   * unique standards.
   */
  uniqueResults.forEach(
    (result) => {
      const sdo =
        result.requested_sdo ||
        getSdoFromStandardNumber(
          result.standard
            ?.standardno
        ) ||
        "Unknown";

      if (!groupingEnabled) {
        return;
      }

      const classifications =
        getClassifications(
          result
        );

      /*
       * No classification:
       * each standard gets its own
       * individual bucket.
       */
      if (
        classifications.length ===
        0
      ) {
        const key =
          `${sdo}||UNCLASSIFIED||${getStandardId(
            result
          )}`;

        groupsMap.set(
          key,
          {
            sdo,
            tc: EMPTY,
            description:
              "No classification",
            standards: [result],
          }
        );

        return;
      }

      /*
       * A standard with multiple
       * classification codes appears
       * in every relevant group.
       */
      classifications.forEach(
        (classification) => {
          const rawCode =
            classification?.code ??
            classification?.classification_code;

          const code =
            rawCode === null ||
            rawCode === undefined ||
            String(
              rawCode
            ).trim() === ""
              ? null
              : String(
                  rawCode
                );

          /*
           * Classification exists but
           * has no usable code.
           */
          if (!code) {
            const key =
              `${sdo}||UNCLASSIFIED||${getStandardId(
                result
              )}`;

            if (
              !groupsMap.has(
                key
              )
            ) {
              groupsMap.set(
                key,
                {
                  sdo,
                  tc: EMPTY,
                  description:
                    "No classification code",
                  standards: [
                    result,
                  ],
                }
              );
            }

            return;
          }

          const key =
            `${sdo}||${code}`;

          if (
            !groupsMap.has(
              key
            )
          ) {
            groupsMap.set(
              key,
              {
                sdo,
                tc: code,
                descriptions: [],
                standards: [],
              }
            );
          }

          const group =
            groupsMap.get(
              key
            );

          const alreadyAdded =
            group.standards.some(
              (item) =>
                getStandardId(
                  item
                ) ===
                getStandardId(
                  result
                )
            );

          if (
            !alreadyAdded
          ) {
            group.standards.push(
              result
            );
          }

          const description =
            classification?.description;

          if (
            description &&
            !group.descriptions.includes(
              description
            )
          ) {
            group.descriptions.push(
              description
            );
          }
        }
      );
    }
  );

  const groups =
    groupingEnabled
      ? Array.from(
          groupsMap.values()
        )
          .map((group) => {
            const description =
              group.description ||
              (
                group.descriptions
                  ?.length === 1
                  ? group
                      .descriptions[0]
                  : group.descriptions
                      ?.length >
                    1
                  ? "Multiple descriptions"
                  : EMPTY
              );

            const type =
              group.standards
                .length >
              1
                ? "GROUP"
                : "INDIVIDUAL";

            const individualTotal =
              group.standards.reduce(
                (
                  sum,
                  item
                ) =>
                  sum +
                  getPrice(
                    item
                  ),
                0
              );

            return {
              ...group,
              description,
              type,
              count:
                group.standards
                  .length,
              individual_total:
                individualTotal,
              group_price:
                null,
              potential_saving:
                null,
            };
          })
          .sort(
            (a, b) =>
              b.count -
              a.count
          )
      : [];

  const relatedGroups =
    groups.filter(
      (group) =>
        group.type ===
        "GROUP"
    );

  const individualBuckets =
    groups.filter(
      (group) =>
        group.type ===
        "INDIVIDUAL"
    );

  /*
   * Unique grouped standards.
   * Important because one standard
   * can belong to multiple groups.
   */
  const groupedIds =
    new Set();

  relatedGroups.forEach(
    (group) => {
      group.standards.forEach(
        (result) => {
          groupedIds.add(
            getStandardId(
              result
            )
          );
        }
      );
    }
  );

  const sdoBreakdown =
    Array.from(
      sdoMap.entries()
    )
      .map(
        ([name, count]) => ({
          name,
          count,
        })
      )
      .sort(
        (a, b) =>
          b.count -
          a.count
      );

  return {
    total,
    totalPrice,
    groupingEnabled,
    groupCount:
      relatedGroups.length,
    individualCount:
      individualBuckets.length,
    groupedStandards:
      groupedIds.size,
    groups,
    sdoBreakdown,
  };
};

  // =========================================================
  // RESULT VIEW FILTER
  // =========================================================

  const matchedCount =
    searchResults.filter(
      (result) => result.matched
    ).length;

  const notFoundCount =
    searchResults.filter(
      (result) =>
        result.status === "NOT FOUND"
    ).length;

  const sdoNotFoundCount =
    searchResults.filter(
      (result) =>
        result.status === "SDO NOT FOUND"
    ).length;

  const selectedResultIdSet = new Set(
    selectedResults.map(getStandardId)
  );

  const filteredSearchResults =
    resultViewFilter === "found"
      ? searchResults.filter(
          (result) => result.matched
        )
      : resultViewFilter === "not_found"
        ? searchResults.filter(
            (result) =>
              result.status === "NOT FOUND"
          )
        : resultViewFilter === "sdo_missing"
          ? searchResults.filter(
              (result) =>
                result.status ===
                "SDO NOT FOUND"
            )
          : resultViewFilter === "selected"
            ? searchResults.filter((result) =>
                selectedResultIdSet.has(
                  getStandardId(result)
                )
              )
            : searchResults;

  const visibleSearchResults =
    filteredSearchResults.slice(
      resultsPageStart,
      resultsPageStart + TABLE_PAGE_SIZE
    );

  const toggleResultViewFilter = (
    nextFilter
  ) => {
    setResultViewFilter((current) =>
      current === nextFilter ? "all" : nextFilter
    );
    setResultsPage(0);
  };

  // =========================================================
  // SELECTION
  // =========================================================

  const selectableResults =
    filteredSearchResults.filter(
      (result) =>
        result.matched &&
        result.standard
    );

  const selectedResultIds = new Set(
    selectedResults.map(getStandardId)
  );

  const allSelected =
    selectableResults.length >
      0 &&
    selectableResults.every((result) =>
      selectedResultIds.has(
        getStandardId(result)
      )
    );

  const handleSelectResult = (
    result
  ) => {
    if (
      !result.matched ||
      !result.standard
    ) {
      return;
    }

    const id =
      getStandardId(result);

    setSelectedResults(
      (previous) => {
        const exists =
          previous.some(
            (item) =>
              getStandardId(
                item
              ) === id
          );

        if (exists) {
          return previous.filter(
            (item) =>
              getStandardId(
                item
              ) !== id
          );
        }

        return [
          ...previous,
          result,
        ];
      }
    );
  };

  const handleSelectAll = () => {
    if (allSelected) {
      const visibleIds = new Set(
        selectableResults.map(getStandardId)
      );

      setSelectedResults((previous) =>
        previous.filter(
          (item) =>
            !visibleIds.has(
              getStandardId(item)
            )
        )
      );
      return;
    }

    setSelectedResults((previous) => {
      const merged = [...previous];
      const existing = new Set(
        previous.map(getStandardId)
      );

      selectableResults.forEach((result) => {
        const id = getStandardId(result);
        if (!existing.has(id)) {
          existing.add(id);
          merged.push(result);
        }
      });

      return merged;
    });
  };

  // =========================================================
  // EXPORT
  // =========================================================

  const handleExportSelected =
    async () => {
      if (
        !selectedResults.length
      ) {
        return;
      }

      setLoading(true);
      setError("");

      try {
        await exportSelectedStandards(
          selectedResults
        );

        /*
         * Dashboard now reflects exactly
         * what was exported.
         */
        setExportedDashboard(
          buildAnalysis(
            selectedResults
          )
        );

        setOpenGroupIndex(
          null
        );
      } catch (err) {
        console.error(err);

        setError(
          err.response?.data?.detail ||
            "Unable to export selected standards."
        );
      } finally {
        setLoading(false);
      }
    };

  // =========================================================
  // MANUAL SEARCH
  // =========================================================

  const handleManualSearch = (
    rowIndex,
    result
  ) => {
    setManualSearchRow(
      rowIndex
    );

    setManualSearchValue(
      result.requested_standard ||
        ""
    );

    setError("");
  };

  const handleManualSearchSubmit =
    async (rowIndex) => {
      const value =
        manualSearchValue.trim();

      if (!value) {
        return;
      }

      const currentRow =
        searchResults[
          rowIndex
        ];

      if (!currentRow) {
        return;
      }

      setManualSearchLoading(
        true
      );

      setError("");

      try {
        const searchValue =
          getManualSearchValue(
            value,
            currentRow.requested_sdo
          );

        const response =
          await searchStandards(
            searchValue
          );

        const results =
          Array.isArray(
            response
          )
            ? response
            : Array.isArray(
                response?.results
              )
            ? response.results
            : [];

        const result =
          results[0] || null;

        setSearchResults(
          (previous) =>
            previous.map(
              (
                row,
                index
              ) => {
                if (
                  index !==
                  rowIndex
                ) {
                  return row;
                }

                if (
                  result?.matched &&
                  result.standard
                ) {
                  const standard =
                    result.standard;

                  return {
                    ...row,
                    requested_standard:
                      value,
                    requested_sdo:
                      getSdoFromStandardNumber(
                        standard.standardno
                      ) ||
                      row.requested_sdo,
                    matched: true,
                    status:
                      result.status ||
                      "AVAILABLE",
                    standard,
                    manual_search:
                      true,
                  };
                }

                return {
                  ...row,
                  requested_standard:
                    value,
                  matched: false,
                  status:
                    "NOT FOUND",
                  standard: null,
                  manual_search:
                    true,
                };
              }
            )
        );

        /*
         * Refresh dashboard because the
         * verified result set changed.
         */
        setExportedDashboard(
          buildAnalysis(
            searchResults.map(
              (row, index) =>
                index ===
                rowIndex
                  ? result
                  : row
            )
          )
        );

        setManualSearchRow(
          null
        );

        setManualSearchValue(
          ""
        );
      } catch (err) {
        console.error(err);

        setError(
          err.response?.data?.detail ||
            "Unable to perform manual search."
        );
      } finally {
        setManualSearchLoading(
          false
        );
      }
    };

  const handleCancelManualSearch =
    () => {
      setManualSearchRow(
        null
      );

      setManualSearchValue(
        ""
      );
    };

  // =========================================================
  // GROUP STANDARD BUBBLES
  // =========================================================

  const renderStandardBubbles = (
    standards
  ) => (
    <div className="standard-bubbles">
      {standards.map(
        (result, index) => (
          <div
            className="standard-bubble"
            key={`${getStandardId(
              result
            )}-${index}`}
            title={
              result.standard
                ?.title || ""
            }
          >
            <span className="bubble-index">
              {String(
                index + 1
              ).padStart(
                2,
                "0"
              )}
            </span>

            <span className="bubble-text">
              {displayValue(
                result.requested_standard ||
                  result.standard
                    ?.display_stdNo ||
                  result.standard
                    ?.standardno
              )}
            </span>
          </div>
        )
      )}
    </div>
  );

  // =========================================================
  // DASHBOARD BAR
  // =========================================================

  const renderSdoBars = () => {
    if (
      !exportedDashboard
        ?.sdoBreakdown?.length
    ) {
      return (
        <div className="empty-dashboard">
          No matched standards yet.
        </div>
      );
    }

    const maximum =
      Math.max(
        ...exportedDashboard.sdoBreakdown.map(
          (item) =>
            item.count
        ),
        1
      );

    return (
      <div className="sdo-chart">
        {exportedDashboard.sdoBreakdown.map(
          (item) => {
            const width =
              (item.count /
                maximum) *
              100;

            return (
              <div
                className="sdo-chart-row"
                key={item.name}
              >
                <div className="sdo-chart-meta">
                  <span>
                    {item.name}
                  </span>

                  <strong>
                    {item.count}
                  </strong>
                </div>

                <div className="sdo-track">
                  <div
                    className="sdo-fill"
                    style={{
                      width: `${width}%`,
                    }}
                  />
                </div>
              </div>
            );
          }
        )}
      </div>
    );
  };

  // =========================================================
  // MAIN UI
  // =========================================================

  return (
    <div className="app">

      {/* =====================================================
          TOP BAR
      ===================================================== */}

      <header className="topbar">

        <div className="brand">

          <div className="brand-mark">
            SI
          </div>

          <div>
            <div className="brand-title">
              Standards Intelligence
            </div>

            <div className="brand-subtitle">
              Standards discovery & quotation workspace
            </div>
          </div>

        </div>

        <div className="topbar-status">
          <span className="status-dot" />
          Database connected
        </div>

      </header>

      {/* =====================================================
          LANDING / UPLOAD SCREEN
      ===================================================== */}

      {!workspaceVisible && (
        <main className="landing">

          <section className="hero">

            <div className="hero-copy">

              <div className="hero-kicker">
                STANDARDS SEARCH PLATFORM
              </div>

              <h1>
                Find the standards
                <br />
                your customer needs.
              </h1>

              <p>
                Upload a customer list,
                verify every standard,
                then move directly into
                the quotation workspace.
              </p>

            </div>

            {/* NORMAL SEARCH */}

            <div className="quick-search-card">

              <div className="card-label">
                QUICK SEARCH
              </div>

              <div className="quick-search">
                <input
                  value={
                    searchQuery
                  }
                  onChange={(event) =>
                    setSearchQuery(
                      event.target.value
                    )
                  }
                  onKeyDown={(event) => {
                    if (
                      event.key ===
                      "Enter"
                    ) {
                      handleSearch();
                    }
                  }}
                  placeholder="e.g. ISO 530"
                />

                <button
                  type="button"
                  className="primary-button"
                  onClick={
                    handleSearch
                  }
                  disabled={loading}
                >
                  {loading
                    ? "Searching..."
                    : "Search"}
                  <span>
                    →
                  </span>
                </button>
              </div>

              {searchResult && (
                <div className="quick-result">

                  <div>
                    <span>
                      Requested
                    </span>

                    <strong>
                      {displayValue(
                        searchResult
                          ?.requested_standard
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>
                      Result
                    </span>

                    <strong>
                      {displayValue(
                        searchResult
                          ?.standard
                          ?.display_stdNo ||
                          searchResult
                            ?.standard
                            ?.standardno
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>
                      Status
                    </span>

                    <strong>
                      {displayValue(
                        searchResult
                          ?.status
                      )}
                    </strong>
                  </div>

                </div>
              )}

            </div>

          </section>

          {/* UPLOAD */}

          <section className="upload-zone">

            <input
              id="document-upload"
              type="file"
              accept=".xlsx,.xls,.csv,.pdf,.docx,.txt"
              onChange={
                handleFileChange
              }
            />

            <label
              htmlFor="document-upload"
              className="upload-card"
            >

              <div className="upload-icon">
                ↑
              </div>

              <div className="upload-main">
                <strong>
                  {selectedFile
                    ? selectedFile.name
                    : "Drop your customer file here"}
                </strong>

                <span>
                  Excel · CSV · PDF · DOCX · TXT
                </span>
              </div>

              <div className="upload-action">
                {selectedFile
                  ? "Change"
                  : "Browse"}
                <span>
                  →
                </span>
              </div>

            </label>

          </section>

          {/* PREVIEW */}

          {previewRows.length > 0 && (
            <section className="verification-card">

              <div className="verification-header">

                <div>
                  <div className="card-label">
                    VERIFICATION READY
                  </div>

                  <h2>
                    {previewRows.length}
                    {" "}
                    standards detected
                  </h2>

                  <p>
                    Review the extracted
                    standards before running
                    the database search.
                  </p>
                </div>

                <button
                  type="button"
                  className="verify-button"
                  onClick={
                    handleStartSearch
                  }
                  disabled={loading}
                >
                  {loading
                    ? "Verifying..."
                    : "Verify & Search"}
                  <span>
                    →
                  </span>
                </button>

              </div>

              <div className="preview-table-shell">
                <table className="standards-table preview-table">
                  <thead>
                    <tr>
                      <th>
                        #
                      </th>
                      <th>
                        SDO
                      </th>
                      <th>
                        Standard
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {visiblePreviewRows.map((row, pageIndex) => {
                      const index = previewPageStart + pageIndex;

                      return (
                          <tr
                            key={
                              index
                            }
                          >
                            <td>
                              {String(
                                index +
                                  1
                              ).padStart(
                                2,
                                "0"
                              )}
                            </td>

                            <td>
                              {displayValue(
                                row.sdo_name
                              )}
                            </td>

                            <td>
                              {displayValue(
                                row.displaystdno
                              )}
                            </td>
                          </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {renderPagination(
                previewPage,
                previewRows.length,
                setPreviewPage
              )}

            </section>
          )}

        </main>
      )}

      {/* =====================================================
          RESULTS + DASHBOARD WORKSPACE
      ===================================================== */}

      {workspaceVisible && (
        <main className="workspace">

          {/* WORKSPACE HEADER */}

          <div className="workspace-header">

            <div>

              <button
                type="button"
                className="back-button"
                onClick={() =>
                  setWorkspaceVisible(
                    false
                  )
                }
              >
                ←
              </button>

              <div className="workspace-heading">

                <div className="workspace-kicker">
                  SEARCH COMPLETE
                </div>

                <h1>
                  {selectedFile?.name ||
                    "Standards Results"}
                </h1>

                <p>
                  Verified results and
                  quotation intelligence
                  are ready.
                </p>

              </div>

            </div>

            <div className="workspace-actions">

              <button
                type="button"
                className="ghost-button"
                onClick={
                  handleNewDocument
                }
              >
                + New Search
              </button>

              <button
                type="button"
                className="primary-button"
                onClick={
                  handleExportSelected
                }
                disabled={
                  selectedResults.length ===
                    0 ||
                  loading
                }
              >
                {loading
                  ? "Exporting..."
                  : `Export ${selectedResults.length || ""} Selected`}
                <span>
                  ↓
                </span>
              </button>

            </div>

          </div>

          {/* PARALLEL WORKSPACE */}

          <div className="workspace-grid">

            {/* =================================================
                RESULTS PANEL
            ================================================= */}

            <section className="results-workspace-panel">

              <div className="panel-top">

                <div>

                  <div className="panel-kicker">
                    DATABASE VERIFICATION
                  </div>

                  <h2>
                    Search Results
                  </h2>

                </div>

                <div className="result-count">
                  <strong>
                    {
                      searchResults.length
                    }
                  </strong>
                  <span>
                    requested
                  </span>
                </div>

              </div>

              {/* RESULT STAT STRIP */}

              <div className="result-stat-strip">

                <button
                  type="button"
                  className={
                    resultViewFilter === "found"
                      ? "result-stat found active"
                      : "result-stat found"
                  }
                  onClick={() =>
                    toggleResultViewFilter("found")
                  }
                  aria-pressed={
                    resultViewFilter === "found"
                  }
                >
                  <span>
                    Found
                  </span>

                  <strong>
                    {matchedCount}
                  </strong>
                </button>

                <button
                  type="button"
                  className={
                    resultViewFilter === "not_found"
                      ? "result-stat warning active"
                      : "result-stat warning"
                  }
                  onClick={() =>
                    toggleResultViewFilter(
                      "not_found"
                    )
                  }
                  aria-pressed={
                    resultViewFilter === "not_found"
                  }
                >
                  <span>
                    Not Found
                  </span>

                  <strong>
                    {notFoundCount}
                  </strong>
                </button>

                <button
                  type="button"
                  className={
                    resultViewFilter ===
                    "sdo_missing"
                      ? "result-stat neutral active"
                      : "result-stat neutral"
                  }
                  onClick={() =>
                    toggleResultViewFilter(
                      "sdo_missing"
                    )
                  }
                  aria-pressed={
                    resultViewFilter ===
                    "sdo_missing"
                  }
                >
                  <span>
                    SDO Missing
                  </span>

                  <strong>
                    {sdoNotFoundCount}
                  </strong>
                </button>

                <button
                  type="button"
                  className={
                    resultViewFilter === "selected"
                      ? "result-stat selected active"
                      : "result-stat selected"
                  }
                  onClick={() =>
                    toggleResultViewFilter(
                      "selected"
                    )
                  }
                  aria-pressed={
                    resultViewFilter === "selected"
                  }
                >
                  <span>
                    Selected
                  </span>

                  <strong>
                    {
                      selectedResults.length
                    }
                  </strong>
                </button>

              </div>

              {/* TABLE */}

              <div className="results-table-shell">

                <table className="standards-table result-table">

                  <thead>
                    <tr>

                      <th className="select-col">
                        <input
                          type="checkbox"
                          checked={
                            allSelected
                          }
                          onChange={
                            handleSelectAll
                          }
                          disabled={
                            selectableResults.length ===
                            0
                          }
                        />
                      </th>

                      <th>
                        SDO
                      </th>

                      <th>
                        Requested
                      </th>

                      <th>
                        Duplicate
                      </th>

                      <th>
                        Matched
                      </th>

                      <th>
                        Title
                      </th>

                      <th>
                        Status
                      </th>

                      <th>
                        Action
                      </th>

                    </tr>
                  </thead>

                  <tbody>

                    {visibleSearchResults.map(
                      (result, pageIndex) => {
                        const index = resultsPageStart + pageIndex;

                        const id =
                          getStandardId(
                            result
                          );

                        const checked = selectedResultIds.has(id);

                        return (
                          <tr
                            key={`${id}-${index}`}
                            className={
                              checked
                                ? "selected-row"
                                : ""
                            }
                          >

                            <td className="select-col">

                              {result.matched &&
                              result.standard ? (
                                <input
                                  type="checkbox"
                                  checked={
                                    checked
                                  }
                                  onChange={() =>
                                    handleSelectResult(
                                      result
                                    )
                                  }
                                />
                              ) : (
                                EMPTY
                              )}

                            </td>

                            <td>
                              <span className="sdo-mini-pill">
                                {displayValue(
                                  result.requested_sdo
                                )}
                              </span>
                            </td>

                            <td>
                              {displayValue(
                                result.requested_standard
                              )}
                            </td>

                            <td>
                              {result.is_duplicate
                                ? `Duplicate of ${result.duplicate_of}`
                                : EMPTY}
                            </td>

                            <td className="matched-number">
                              {displayValue(
                                result
                                  .standard
                                  ?.display_stdNo ||
                                  result
                                    .standard
                                    ?.standardno
                              )}
                            </td>

                            <td
                              className="title-cell"
                              title={
                                result
                                  .standard
                                  ?.title ||
                                ""
                              }
                            >
                              {displayValue(
                                result
                                  .standard
                                  ?.title
                              )}
                            </td>

                            <td>

                              <span
                                className={
                                  result.matched
                                    ? "status-chip available"
                                    : "status-chip unavailable"
                                }
                              >
                                <span />
                                {displayValue(
                                  result.status
                                )}
                              </span>

                            </td>

                            <td>

                              {result.matched ? (
                                <span className="action-dash">
                                  -
                                </span>
                              ) : (
                                <button
                                  type="button"
                                  className="manual-button"
                                  onClick={() =>
                                    handleManualSearch(
                                      index,
                                      result
                                    )
                                  }
                                >
                                  Search manually
                                  <span>
                                    →
                                  </span>
                                </button>
                              )}

                            </td>

                          </tr>
                        );
                      }
                    )}

                  </tbody>

                </table>

              </div>

              {renderPagination(
                resultsPage,
                filteredSearchResults.length,
                setResultsPage
              )}

              {/* RESULTS FOOTER */}

              <div className="results-footer">

                <div>
                  <span className="selection-indicator" />
                  <strong>
                    {
                      selectedResults.length
                    }
                  </strong>
                  <span>
                    selected for quotation
                  </span>
                </div>

                <button
                  type="button"
                  className="footer-export-button"
                  onClick={
                    handleExportSelected
                  }
                  disabled={
                    selectedResults.length ===
                      0 ||
                    loading
                  }
                >
                  Export Selection
                  <span>
                    ↓
                  </span>
                </button>

              </div>

            </section>

            {/* =================================================
                DASHBOARD PANEL
            ================================================= */}

            <aside className="dashboard-workspace-panel">

              <div className="dashboard-scroll">

                {/* DASHBOARD HEADER */}

                <div className="dashboard-top">

                  <div>

                    <div className="panel-kicker">
                      QUOTATION INTELLIGENCE
                    </div>

                    <h2>
                      Dashboard
                    </h2>

                  </div>

                  <div className="live-badge">
                    <span />
                    LIVE
                  </div>

                </div>

                {/* METRICS */}

                <div className="metric-grid">

                  <div className="metric-card metric-main">

                    <span>
                      Verified
                    </span>

                    <strong>
                      {
                        exportedDashboard?.total ||
                        0
                      }
                    </strong>

                    <small>
                      matched standards
                    </small>

                    <div className="metric-accent" />

                  </div>

                  <div className="metric-card">

                    <span>
                      Related Groups
                    </span>

                    <strong>
                      {
                        exportedDashboard
                          ?.groupCount ||
                        0
                      }
                    </strong>

                    <small>
                      classification groups
                    </small>

                  </div>

                  <div className="metric-card">

                    <span>
                      Individual
                    </span>

                    <strong>
                      {
                        exportedDashboard
                          ?.individualCount ||
                        0
                      }
                    </strong>

                    <small>
                      individual buckets
                    </small>

                  </div>

                </div>

                {/* VISUAL OVERVIEW */}

                <div className="dashboard-card">

                  <div className="dashboard-card-heading">

                    <div>
                      <h3>
                        Standards Mix
                      </h3>

                      <p>
                        Distribution across SDOs
                      </p>
                    </div>

                    <span className="card-arrow">
                      ↗
                    </span>

                  </div>

                  <div className="visual-overview">

                    <div
                      className="donut"
                      style={{
                        "--donut-total":
                          exportedDashboard
                            ?.total ||
                          1,
                      }}
                    >
                      <div className="donut-center">
                        <strong>
                          {
                            exportedDashboard
                              ?.total ||
                            0
                          }
                        </strong>

                        <span>
                          standards
                        </span>
                      </div>
                    </div>

                    <div className="donut-legend">

                      {(
                        exportedDashboard
                          ?.sdoBreakdown ||
                        []
                      )
                        .slice(
                          0,
                          5
                        )
                        .map(
                          (
                            item,
                            index
                          ) => {

                            const total =
                              exportedDashboard
                                ?.total ||
                              1;

                            const percentage =
                              Math.round(
                                (item.count /
                                  total) *
                                  100
                              );

                            return (
                              <div
                                className="legend-item"
                                key={
                                  item.name
                                }
                              >

                                <span className={`legend-dot dot-${index}`} />

                                <span>
                                  {
                                    item.name
                                  }
                                </span>

                                <strong>
                                  {
                                    percentage
                                  }%
                                </strong>

                              </div>
                            );
                          }
                        )}

                    </div>

                  </div>

                </div>

                {/* BAR CHART */}

                <div className="dashboard-card">

                  <div className="dashboard-card-heading">

                    <div>
                      <h3>
                        SDO Activity
                      </h3>

                      <p>
                        Verified standards by organization
                      </p>
                    </div>

                    <span className="chart-label">
                      COUNT
                    </span>

                  </div>

                  {renderSdoBars()}

                </div>

                {/* GROUPING */}

                <div className="dashboard-card grouping-dashboard-card">

                  <div className="dashboard-card-heading">

                    <div>
                      <h3>
                        Related Standards
                      </h3>

                      <p>
                        Same classification code
                      </p>
                    </div>

                    <div className="group-count-orb">
                      {
                        exportedDashboard
                          ?.groupCount ||
                        0
                      }
                    </div>

                  </div>

                  {!exportedDashboard
                    ?.groupingEnabled ? (

                    <div className="grouping-lock">

                      <div className="lock-icon">
                        ◌
                      </div>

                      <div>
                        <strong>
                          Grouping not required yet
                        </strong>

                        <span>
                          Grouping activates
                          above{" "}
                          {GROUPING_THRESHOLD}{" "}
                          verified standards.
                        </span>
                      </div>

                    </div>

                  ) : (

                    <div className="group-list">

                      {exportedDashboard.groups.map(
                        (
                          group,
                          index
                        ) => {

                          const open =
                            openGroupIndex ===
                            index;

                          return (
                            <div
                              className={
                                open
                                  ? "group-card open"
                                  : "group-card"
                              }
                              key={
                                `${group.sdo}-${group.description}-${index}`
                              }
                            >

                              <div className="group-card-main">

                                <div className="group-ident">

                                  <span className="group-sdo">
                                    {
                                      displayValue(
                                        group.sdo
                                      )
                                    }
                                  </span>

                                </div>

                                <div className="group-description">
                                  {
                                    displayValue(
                                      group.description
                                    )
                                  }
                                </div>

                                <span
                                  className={
                                    group.type ===
                                    "GROUP"
                                      ? "type-badge related"
                                      : "type-badge individual"
                                  }
                                >
                                  {
                                    group.type
                                  }
                                </span>

                                <button
                                  type="button"
                                  className={
                                    open
                                      ? "view-standards-button active"
                                      : "view-standards-button"
                                  }
                                  onClick={() =>
                                    setOpenGroupIndex(
                                      open
                                        ? null
                                        : index
                                    )
                                  }
                                >

                                  <span className="view-icon">
                                    {open
                                      ? "−"
                                      : "+"}
                                  </span>

                                  <span>
                                    {
                                      group.count
                                    }{" "}
                                    standards
                                  </span>

                                  <span className="view-label">
                                    {open
                                      ? "Hide"
                                      : "View"}
                                  </span>

                                </button>

                              </div>

                              {open && (
                                <div className="group-expanded">

                                  <div className="expanded-header">

                                    <div>
                                      <strong>
                                        Included standards
                                      </strong>

                                      <span>
                                        Click the bubbles
                                        to inspect the
                                        standard title.
                                      </span>
                                    </div>

                                  </div>

                                  {renderStandardBubbles(
                                    group.standards
                                  )}

                                </div>
                              )}

                            </div>
                          );
                        }
                      )}

                    </div>
                  )}

                </div>

                {/* GROUP INSIGHT */}

                {exportedDashboard
                  ?.groupingEnabled && (
                  <div className="insight-card">

                    <div className="insight-icon">
                      ✦
                    </div>

                    <div>

                      <strong>
                        {
                          exportedDashboard
                            .groupedStandards
                        }{" "}
                        unique standards
                      </strong>

                      <span>
                        participate in at least
                        one related classification
                        group.
                      </span>

                    </div>

                  </div>
                )}

                {/* FOOTER */}

                <div className="dashboard-note">
                  <span>
                    i
                  </span>

                  <p>
                    Related groups are built from
                    shared classifications across
                    your verified standards.
                  </p>
                </div>

              </div>

            </aside>

          </div>

        </main>
      )}

      {/* =====================================================
          MANUAL SEARCH MODAL
      ===================================================== */}

      {manualSearchRow !==
        null && (
        <div className="modal-backdrop">

          <div className="manual-modal">

            <div className="modal-top">

              <div>
                <div className="panel-kicker">
                  MANUAL SEARCH
                </div>

                <h2>
                  Find this standard
                </h2>

                <p>
                  The automatic lookup did not
                  resolve this row. Search manually.
                </p>
              </div>

              <button
                type="button"
                className="modal-close"
                onClick={
                  handleCancelManualSearch
                }
              >
                ×
              </button>

            </div>

            <div className="manual-input-wrap">

              <span>
                SEARCH
              </span>

              <input
                value={
                  manualSearchValue
                }
                onChange={(event) =>
                  setManualSearchValue(
                    event.target.value
                  )
                }
                onKeyDown={(event) => {
                  if (
                    event.key ===
                    "Enter"
                  ) {
                    handleManualSearchSubmit(
                      manualSearchRow
                    );
                  }
                }}
                placeholder="Enter standard number..."
                autoFocus
              />

            </div>

            <div className="modal-actions">

              <button
                type="button"
                className="ghost-button"
                onClick={
                  handleCancelManualSearch
                }
              >
                Cancel
              </button>

              <button
                type="button"
                className="primary-button"
                onClick={() =>
                  handleManualSearchSubmit(
                    manualSearchRow
                  )
                }
                disabled={
                  manualSearchLoading ||
                  !manualSearchValue.trim()
                }
              >
                {manualSearchLoading
                  ? "Searching..."
                  : "Search Database"}
                <span>
                  →
                </span>
              </button>

            </div>

          </div>

        </div>
      )}

      {/* =====================================================
          ERROR
      ===================================================== */}

      {error && (
        <div className="toast-error">
          <span>
            !
          </span>

          {error}

          <button
            type="button"
            onClick={() =>
              setError("")
            }
          >
            ×
          </button>
        </div>
      )}

    </div>
  );
}

export default App;