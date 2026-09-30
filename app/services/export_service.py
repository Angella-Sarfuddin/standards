
import pandas as pd
from io import BytesIO


class ExportService:

    @staticmethod
    def export_results(response):

        results = response.get("results", [])
        grouping = response.get("grouping", {})

        quotation_rows = []

        for result in results:

            if not result.get("matched"):
                continue

            standard = result.get("standard")

            if not standard:
                continue

            enrichment = standard.get(
                "enrichment",
                {}
            )

            classifications = enrichment.get(
                "classifications",
                []
            )

            price = enrichment.get("price")
            standard_year = standard.get("standardyear")
            if standard_year is None:
                standard_year = enrichment.get("year")

            currency = (
                standard.get("currency")
                or enrichment.get("currency")
            )

            quotation_row = {
                "SDO": result.get("requested_sdo"),
                "Standard": result.get("requested_standard"),
                "Matched Standard": (
                    standard.get("display_stdNo")
                    or standard.get("standardno")
                ),
                "Title": standard.get("title"),
                "Standard Year": standard_year,
                "Currency": currency,
            }

            if classifications:

                for classification in classifications:

                    quotation_rows.append(
                        {
                            **quotation_row,
                            "TC": classification.get("code"),
                            "TC Description": classification.get(
                                "description"
                            ),
                            "Price": price,
                            "Status": result.get("status"),
                        }
                    )

            else:

                quotation_rows.append(
                    {
                        **quotation_row,
                        "TC": None,
                        "TC Description": None,
                        "Price": price,
                        "Status": result.get("status"),
                    }
                )

        quotation_df = pd.DataFrame(quotation_rows)

        grouping_rows = []

        if grouping.get("enabled"):

            for group in grouping.get("groups", []):

                grouping_rows.append({
                    "SDO": group.get("sdo"),
                    "TC": group.get("tc"),
                    "TC Description": group.get(
                        "description"
                    ),
                    "Type": group.get(
                        "type"
                    ),
                    "Standards Count": group.get(
                        "count"
                    ),
                    "Individual Total": group.get(
                        "individual_total"
                    ),
                    "Group Price": group.get(
                        "group_price"
                    ),
                    "Potential Saving": group.get(
                        "potential_saving"
                    )
                })

        grouping_df = pd.DataFrame(grouping_rows)

        output = BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            quotation_df.to_excel(
                writer,
                index=False,
                sheet_name="Quotation"
            )

            grouping_df.to_excel(
                writer,
                index=False,
                sheet_name="Grouping Summary"
            )

        output.seek(0)

        return output

