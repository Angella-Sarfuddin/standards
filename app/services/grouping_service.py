
from collections import defaultdict


class GroupingService:

    GROUPING_THRESHOLD = 25

    @staticmethod
    def group_results(results):

        # ONLY ACTUAL DB MATCHES ARE ELIGIBLE
        matched_results = [
            result
            for result in results
            if result.get("matched")
            and result.get("standard")
        ]

        matched_total = len(matched_results)

        # GROUPING ONLY STARTS WHEN MORE THAN 25
        # ACTUAL STANDARDS ARE MATCHED
        if matched_total <= GroupingService.GROUPING_THRESHOLD:
            return {
                "enabled": False,
                "total": matched_total,
                "groups": []
            }

        groups = defaultdict(list)

        # Keep standards without classifications separate.
        unclassified = []

        for result in matched_results:

            standard = result.get("standard")

            enrichment = standard.get(
                "enrichment",
                {}
            )

            classifications = enrichment.get(
                "classifications",
                []
            )

            sdo_name = result.get(
                "requested_sdo"
            ) or "Unknown"

            # No classification:
            # do NOT combine these into one Unclassified group.
            if not classifications:
                unclassified.append(result)
                continue

            # A standard with multiple classification codes
            # intentionally appears in EVERY matching group.
            added_codes = set()

            for classification in classifications:

                classification_code = classification.get(
                    "code"
                )

                if classification_code is None:
                    continue

                classification_code = str(
                    classification_code
                )

                # Prevent the same standard from being added
                # twice to the same code if duplicate classification
                # records exist.
                if classification_code in added_codes:
                    continue

                added_codes.add(classification_code)

                groups[
                    (
                        sdo_name,
                        classification_code
                    )
                ].append(result)

        formatted_groups = []

        # --------------------------------------------------
        # CLASSIFICATION GROUPS
        # --------------------------------------------------

        for (
            sdo_name,
            classification_code
        ), standards in groups.items():

            descriptions = []

            for result in standards:

                classifications = (
                    result
                    .get("standard", {})
                    .get("enrichment", {})
                    .get("classifications", [])
                )

                for classification in classifications:

                    code = classification.get(
                        "code"
                    )

                    if (
                        code is not None
                        and str(code) == classification_code
                    ):

                        description = classification.get(
                            "description"
                        )

                        if (
                            description
                            and description not in descriptions
                        ):
                            descriptions.append(
                                description
                            )

            # Use the actual description when there is one.
            # If the same code has multiple descriptions,
            # keep that fact explicit instead of hiding it.
            if not descriptions:
                description = None
            elif len(descriptions) == 1:
                description = descriptions[0]
            else:
                description = "Multiple descriptions"

            individual_total = sum(
                (
                    result
                    .get("standard", {})
                    .get("enrichment", {})
                    .get("price")
                    or 0
                )
                for result in standards
            )

            group_type = (
                "GROUP"
                if len(standards) > 1
                else "INDIVIDUAL"
            )

            formatted_groups.append({
                "sdo": sdo_name,
                "tc": classification_code,
                "description": description,
                "type": group_type,
                "count": len(standards),
                "individual_total": individual_total,
                "group_price": None,
                "potential_saving": None,
                "standards": [
                    result["requested_standard"]
                    for result in standards
                ]
            })

        # --------------------------------------------------
        # STANDARDS WITHOUT CLASSIFICATIONS
        # --------------------------------------------------

        # These are INDIVIDUAL because there is no
        # classification_code connecting them to another standard.
        for result in unclassified:

            standard = result.get(
                "standard",
                {}
            )

            price = (
                standard
                .get("enrichment", {})
                .get("price")
                or 0
            )

            formatted_groups.append({
                "sdo": result.get(
                    "requested_sdo"
                ) or "Unknown",
                "tc": "Unclassified",
                "description": None,
                "type": "INDIVIDUAL",
                "count": 1,
                "individual_total": price,
                "group_price": None,
                "potential_saving": None,
                "standards": [
                    result["requested_standard"]
                ]
            })

        return {
            "enabled": True,
            "total": matched_total,
            "groups": formatted_groups
        }

