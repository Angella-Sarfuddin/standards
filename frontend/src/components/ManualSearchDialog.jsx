import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export default function ManualSearchDialog({
  open,
  value,
  loading,
  onChange,
  onSubmit,
  onCancel,
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onCancel();
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="text-xs tracking-[0.16em] text-muted-foreground">
            MANUAL SEARCH
          </div>
          <DialogTitle>Find this standard</DialogTitle>
          <DialogDescription>
            The automatic lookup did not resolve this row. Search manually.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium tracking-wide text-muted-foreground">
            SEARCH
          </span>
          <Input
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                onSubmit();
              }
            }}
            placeholder="Enter standard number..."
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={onSubmit}
            disabled={loading || !value.trim()}
          >
            {loading ? "Searching..." : "Search Database"}
            <ArrowRight />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
