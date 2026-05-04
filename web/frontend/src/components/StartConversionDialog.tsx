import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (notifyEmail: string | null) => Promise<void>;
  defaultEmail: string | null;
  smtpEnabled: boolean;
  isRerun: boolean;
}

export function StartConversionDialog({
  open,
  onOpenChange,
  onConfirm,
  defaultEmail,
  smtpEnabled,
  isRerun,
}: Props) {
  const [notifyOptIn, setNotifyOptIn] = useState(false);
  const [email, setEmail] = useState(defaultEmail ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setNotifyOptIn(false);
      setEmail(defaultEmail ?? "");
      setError(null);
      setSubmitting(false);
    }
  }, [open, defaultEmail]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    let notify: string | null = null;
    if (notifyOptIn) {
      const trimmed = email.trim();
      if (!EMAIL_RE.test(trimmed)) {
        setError("Please enter a valid email address.");
        return;
      }
      notify = trimmed;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(notify);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start conversion");
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!submitting) onOpenChange(o); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isRerun ? "Re-run conversion" : "Start conversion"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <p className="text-sm">
            Conversion can take several minutes. It's safe to close this tab and
            come back later — your work continues in the background.
          </p>

          {smtpEnabled && (
            <div className="space-y-2">
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={notifyOptIn}
                  onChange={(e) => setNotifyOptIn(e.target.checked)}
                />
                <span>Email me when conversion is done</span>
              </label>

              {notifyOptIn && (
                <div className="space-y-1 pl-6">
                  <Label htmlFor="notify_email">Send to</Label>
                  <Input
                    id="notify_email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoFocus
                  />
                </div>
              )}
            </div>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting
                ? "Starting…"
                : isRerun
                  ? "Re-run conversion"
                  : "Start conversion"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
