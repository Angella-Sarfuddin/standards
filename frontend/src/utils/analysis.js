import { EMPTY, GROUPING_THRESHOLD } from "../constants.js";
import {
  getClassifications,
  getPrice,
  getSdoFromStandardNumber,
  getStandardId,
} from "./standards.js";

export const buildAnalysis = (results) => {
  const matchedResults = results.filter(
    (result) => result?.matched && result?.standard
  );

  const uniqueResults = [];
  const seenIds = new Set();

  matchedResults.forEach((result) => {
    const id = getStandardId(result);

    if (seenIds.has(id)) {
      return;
    }

    seenIds.add(id);
    uniqueResults.push(result);
  });

  const total = matchedResults.length;

  const updatedEditionResults = matchedResults.filter((result) => {
    if (!result.status_detail) return false;
    if (result.status === "EDITION MISMATCH") return true;
    return String(result.status_detail).startsWith(
      "Current available version:"
    );
  });

  const totalPrice = uniqueResults.reduce(
    (sum, result) => sum + getPrice(result),
    0
  );

  const groupingEnabled = total > GROUPING_THRESHOLD;

  const groupsMap = new Map();
  const sdoMap = new Map();

  matchedResults.forEach((result) => {
    const sdo =
      result.requested_sdo ||
      getSdoFromStandardNumber(result.standard?.standardno) ||
      "Unknown";

    sdoMap.set(sdo, (sdoMap.get(sdo) || 0) + 1);
  });

  uniqueResults.forEach((result) => {
    const sdo =
      result.requested_sdo ||
      getSdoFromStandardNumber(result.standard?.standardno) ||
      "Unknown";

    if (!groupingEnabled) {
      return;
    }

    const classifications = getClassifications(result);

    if (classifications.length === 0) {
      const key = `${sdo}||UNCLASSIFIED||${getStandardId(result)}`;

      groupsMap.set(key, {
        sdo,
        tc: EMPTY,
        description: "No classification",
        standards: [result],
      });

      return;
    }

    classifications.forEach((classification) => {
      const rawCode =
        classification?.code ?? classification?.classification_code;

      const code =
        rawCode === null ||
        rawCode === undefined ||
        String(rawCode).trim() === ""
          ? null
          : String(rawCode);

      if (!code) {
        const key = `${sdo}||UNCLASSIFIED||${getStandardId(result)}`;

        if (!groupsMap.has(key)) {
          groupsMap.set(key, {
            sdo,
            tc: EMPTY,
            description: "No classification code",
            standards: [result],
          });
        }

        return;
      }

      const key = `${sdo}||${code}`;

      if (!groupsMap.has(key)) {
        groupsMap.set(key, {
          sdo,
          tc: code,
          descriptions: [],
          standards: [],
        });
      }

      const group = groupsMap.get(key);

      const alreadyAdded = group.standards.some(
        (item) => getStandardId(item) === getStandardId(result)
      );

      if (!alreadyAdded) {
        group.standards.push(result);
      }

      const description = classification?.description;

      if (description && !group.descriptions.includes(description)) {
        group.descriptions.push(description);
      }
    });
  });

  const groups = groupingEnabled
    ? Array.from(groupsMap.values())
        .map((group) => {
          const description =
            group.description ||
            (group.descriptions?.length === 1
              ? group.descriptions[0]
              : group.descriptions?.length > 1
                ? "Multiple descriptions"
                : EMPTY);

          const type = group.standards.length > 1 ? "GROUP" : "INDIVIDUAL";

          const individualTotal = group.standards.reduce(
            (sum, item) => sum + getPrice(item),
            0
          );

          return {
            ...group,
            description,
            type,
            count: group.standards.length,
            individual_total: individualTotal,
            group_price: null,
            potential_saving: null,
          };
        })
        .sort((a, b) => b.count - a.count)
    : [];

  const relatedGroups = groups.filter((group) => group.type === "GROUP");
  const individualBuckets = groups.filter(
    (group) => group.type === "INDIVIDUAL"
  );

  const groupedIds = new Set();

  relatedGroups.forEach((group) => {
    group.standards.forEach((result) => {
      groupedIds.add(getStandardId(result));
    });
  });

  const sdoBreakdown = Array.from(sdoMap.entries())
    .map(([name, count]) => ({
      name,
      count,
    }))
    .sort((a, b) => b.count - a.count);

  return {
    total,
    updatedEditionCount: updatedEditionResults.length,
    updatedEditionResults,
    totalPrice,
    groupingEnabled,
    groupCount: relatedGroups.length,
    individualCount: individualBuckets.length,
    groupedStandards: groupedIds.size,
    groups,
    sdoBreakdown,
  };
};
