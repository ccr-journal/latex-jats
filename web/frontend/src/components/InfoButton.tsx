import { useState, type ReactNode } from "react";
import { HelpCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface InfoButtonProps {
  title: string;
  children: ReactNode;
}

export function InfoButton({ title, children }: InfoButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`More information: ${title}`}
        className="inline-flex h-4 w-4 items-center justify-center text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
      >
        <HelpCircle className="h-4 w-4" />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm text-muted-foreground *:[a]:underline *:[a]:underline-offset-3 *:[a]:hover:text-foreground">
            {children}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
