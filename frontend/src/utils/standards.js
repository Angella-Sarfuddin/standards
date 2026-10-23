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
  const expanded = [];

  for (const result of results || []) {
    if (result?._seriesExpanded) {
      expanded.push(result);
      continue;
    }

    const matchedDesignation =
      result?.standard?.display_stdNo || result?.standard?.standardno || "";
    if (
      result?.matched &&
      result?.standard &&
      !/\bSER(?:IES)?\b/i.test(String(matchedDesignation))
    ) {
      expanded.push({ ...result, _seriesExpanded: true });
      continue;
    }

    const designation = getSeriesDesignation(result);

    if (!designation) {
      expanded.push(result);
      continue;
    }

    const refreshed = await searchDocumentStandards([
      {
        sdo_name: result?.requested_sdo || "",
        displaystdno: designation,
      },
    ]);
    const refreshedMatches = refreshed.filter(
      (item) => item?.matched && item?.standard
    );
    if (refreshedMatches.length) {
      expanded.push(
        ...refreshedMatches.map((item) => ({
          ...item,
          _seriesExpanded: true,
          source_row_identity:
            result?.source_row_identity || item?.source_row_identity,
        }))
      );
    } else {
      expanded.push({ ...result, _seriesExpanded: true });
    }
  }

  return deduplicateResultRows(expanded);
};
