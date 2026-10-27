import { searchDocumentStandards } from "../api/index.js";
import { EMPTY, KNOWN_SDOS } from "../constants.js";

export const displayValue = (value) => {
  if (value === null || value === undefined || String(value).trim() === "") {
    return EMPTY;
  }

  return value;
};

export const getStandardId = (result) => {
  return (
    result?.standard?.id ??
    result?.standard?.Standard_id ??
    result?.standard?.standard_id ??
    result?.requested_standard
  );
};

export const getResultKey = (result) =>
  result?._resultKey ?? getStandardId(result);

export const getPrice = (result) => {
  const price = Number(result?.standard?.enrichment?.price);
  return Number.isFinite(price) ? price : 0;
};

export const getClassifications = (result) => {
  const classifications = result?.standard?.enrichment?.classifications;
  return Array.isArray(classifications) ? classifications : [];
};

const tcCodeLabel = (code) => {
  const text = String(code || "").trim();
  if (!text) {
    return "";
  }
  const simple = text.match(/^(?:TC\s*[- ]?\s*)?(\d+[A-Z]?)$/i);
  if (simple) {
    return `TC ${simple[1].toUpperCase()}`;
  }
  const hierarchy = text.replace(/\s+/g, "").match(/^(\d+)(?:\/\d+)+$/);
  if (hierarchy) {
    return `TC ${hierarchy[1]}`;
  }
  if (/\bTC\s*[- ]?\s*\d/i.test(text)) {
    return text.replace(/\s+/g, " ").replace(/\.+$/, "");
  }
  return "";
};

const textHasCommitteeCode = (text) =>
  /\b(?:ISO\s*\/\s*)?TC\s*[- ]?\s*\d|\b(?:SC|WG|JWG|PGD|GMB|GBM|MHD|ETD|CED)\s*[- ]?\s*\d/i.test(
    String(text || "")
  );

const tcCellText = (code, description) => {
  const name = String(description || "").trim();
  const rawCode = String(code || "").trim();
  const label = tcCodeLabel(rawCode);
  if (name && label) {
    if (textHasCommitteeCode(name)) {
      return name;
    }
    return `${name} (${label})`;
  }
  return name || label || rawCode;
};

export const formatTechnicalCommittee = (result) => {
  const labels = [];
  getClassifications(result).forEach((item) => {
    const label = tcCellText(item?.code, item?.description);
    if (label && !labels.includes(label)) {
      labels.push(label);
    }
  });
  return labels.join(", ");
};

export const hasSdo = (value) => {
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

export const getSdoFromStandardNumber = (standardNumber) => {
  if (!standardNumber) {
    return null;
  }

  const match = standardNumber
    .trim()
    .match(
      /^(ISO(?:\/[A-Z]+(?:\/[A-Z]+)?)?|JIS(?:\s+[A-Z])?|UL|ACI(?:\s+[A-Z]+)?|API(?:\s+[A-Z]+)?)/i
    );

  return match ? match[1].trim() : null;
};

export const getManualSearchValue = (value, currentSdo) => {
  if (currentSdo && !hasSdo(value)) {
    return `${currentSdo} ${value}`;
  }

  return value;
};

export const getSeriesDesignation = (result) => {
  const standard = result?.standard || {};
  const candidates = [
    result?.requested_standard,
    standard.display_stdNo,
    standard.standardno,
    result?.displaystdno,
    result?.raw_standard_expression,
    result?.standard_expression?.raw,
    result?.source_data?.displaystdno,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  return candidates.find((value) => /\bSER(?:IES)?\b/i.test(value));
};

export const deduplicateResultRows = (results) => {
  const seen = new Set();
  return (results || []).filter((result) => {
    const sdo = String(
      result?.requested_sdo || result?.sdo_name || result?.sdo || ""
    )
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
    const request = String(result?.requested_standard || "")
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
    const standard = result?.standard || {};
    const resolved =
      standard.Standard_id ||
      standard.id ||
      standard.display_stdNo ||
      standard.standardno ||
      "";
    const sourceIdentity = result?.source_row_identity;
    const sourceSuffix = sourceIdentity
      ? `:source:${JSON.stringify(sourceIdentity)}`
      : "";
    const key =
      result?.matched && result?.standard
        ? `found:${sdo}:${request}:${String(resolved).toUpperCase()}${sourceSuffix}`
        : `unmatched:${sdo}:${request}:${String(result?.status || "").toUpperCase()}:${String(result?.status_detail || "").toUpperCase()}${sourceSuffix}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

export const expandSeriesResultsForExport = async (results) => {
  const sourceResults = results || [];
  const expandedByIndex = Array(sourceResults.length);
  const pendingSeries = [];

  for (const [index, result] of sourceResults.entries()) {
    if (result?._seriesExpanded) {
      expandedByIndex[index] = [result];
      continue;
    }

    const matchedDesignation =
      result?.standard?.display_stdNo || result?.standard?.standardno || "";
    if (
      result?.matched &&
      result?.standard &&
      !/\bSER(?:IES)?\b/i.test(String(matchedDesignation))
    ) {
      expandedByIndex[index] = [{ ...result, _seriesExpanded: true }];
      continue;
    }

    const designation = getSeriesDesignation(result);

    if (!designation) {
      expandedByIndex[index] = [result];
      continue;
    }

    pendingSeries.push({
      index,
      result,
      designation,
      sourceRow: pendingSeries.length + 1,
    });
  }

  if (pendingSeries.length) {
    const sourceFile = "__series_expansion_batch__";
    const refreshed = await searchDocumentStandards(
      pendingSeries.map(({ result, designation, sourceRow }) => ({
        sdo_name: result?.requested_sdo || "",
        displaystdno: designation,
        source_file: sourceFile,
        source_row: sourceRow,
      }))
    );
    const refreshedBySourceRow = new Map();
    for (const item of refreshed) {
      const sourceIdentity = item?.source_row_identity;
      if (
        !Array.isArray(sourceIdentity) ||
        sourceIdentity[0] !== sourceFile
      ) {
        continue;
      }
      const sourceRow = Number(sourceIdentity[1]);
      if (!Number.isInteger(sourceRow)) continue;
      const group = refreshedBySourceRow.get(sourceRow) || [];
      group.push(item);
      refreshedBySourceRow.set(sourceRow, group);
    }

    for (const { index, result, sourceRow } of pendingSeries) {
      const refreshedMatches = (refreshedBySourceRow.get(sourceRow) || []).filter(
        (item) => item?.matched && item?.standard
      );
      if (refreshedMatches.length) {
        expandedByIndex[index] = refreshedMatches.map((item) => {
          const expandedItem = { ...item };
          delete expandedItem.source_row_identity;
          return {
            ...expandedItem,
            _seriesExpanded: true,
            ...(result?.source_row_identity
              ? { source_row_identity: result.source_row_identity }
              : {}),
          };
        });
      } else {
        expandedByIndex[index] = [{ ...result, _seriesExpanded: true }];
      }
    }
  }

  return deduplicateResultRows(expandedByIndex.flat());
};
