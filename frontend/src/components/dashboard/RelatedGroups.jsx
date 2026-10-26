import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronUp } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { GROUPING_THRESHOLD } from "../../constants.js";
import { displayValue, getStandardId } from "../../utils/standards.js";

function StandardBubbles({ standards }) {
  return (
    <div className="flex flex-wrap gap-2">
      {standards.map((result, index) => (
        <div
          key={`${getStandardId(result)}-${index}`}
          title={result.standard?.title || ""}
          className="flex items-center gap-2 rounded-full border bg-muted/50 px-2 py-1 text-xs"
        >
          <span className="font-semibold text-muted-foreground">
            {String(index + 1).padStart(2, "0")}
          </span>
          <span>
            {displayValue(
              result.requested_standard ||
                result.standard?.display_stdNo ||
                result.standard?.standardno
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function RelatedGroups({
  dashboard,
  openGroupIndex,
  onToggleGroup,
}) {
  return (
    <div className="flex flex-col gap-3">
      {!dashboard?.groupingEnabled ? (
        <div className="rounded-lg border border-dashed p-4 text-sm">
          <strong className="block">Grouping not required yet</strong>
          <span className="text-muted-foreground">
            Grouping activates above {GROUPING_THRESHOLD} verified standards.
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {dashboard.groups.map((group, index) => {
            const open = openGroupIndex === index;

            return (
              <Collapsible
                key={`${group.sdo}-${group.description}-${index}`}
                open={open}
                onOpenChange={(next) => onToggleGroup(next ? index : null)}
                className="rounded-xl border border-border/70 bg-background/70 p-3 transition-colors data-[state=open]:border-primary/25"
              >
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">{displayValue(group.sdo)}</Badge>
                    <Badge
                      variant={group.type === "GROUP" ? "default" : "outline"}
                    >
                      {group.type}
                    </Badge>
                  </div>
                  <div className="text-sm leading-5 text-foreground">{displayValue(group.description)}</div>
                  <CollapsibleTrigger asChild>
                    <Button
                      type="button"
                      variant={open ? "secondary" : "outline"}
                      size="sm"
                      className="h-9 w-fit rounded-lg"
                      aria-label={`${open ? "Hide" : "Show"} ${group.count} standards for ${displayValue(group.sdo)}`}
                      title={`${open ? "Hide" : "View"} related standards`}
                    >
                      {open ? <ChevronUp /> : <ChevronDown />}
                      {group.count} standards · {open ? "Hide" : "View"}
                    </Button>
                  </CollapsibleTrigger>
                </div>
                <CollapsibleContent
                  id={`related-group-content-${index}`}
                  className="mt-3 border-t pt-3"
                >
                  <div className="mb-2 text-sm">
                    <strong>Included standards</strong>
                    <div className="text-xs text-muted-foreground">
                      Hover a bubble to inspect the standard title.
                    </div>
                  </div>
                  <StandardBubbles standards={group.standards} />
                </CollapsibleContent>
              </Collapsible>
            );
          })}
        </div>
      )}

      {dashboard?.groupingEnabled && (
        <div className="rounded-lg bg-primary/5 p-3 text-sm">
          <strong>{dashboard.groupedStandards} unique standards</strong>
          <div className="text-muted-foreground">
            participate in at least one related classification group.
          </div>
        </div>
      )}
    </div>
  );
}
