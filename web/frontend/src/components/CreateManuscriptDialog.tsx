import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createManuscript,
  importOjsSubmission,
  listOjsSubmissions,
} from "@/api/client";
import type { Manuscript, OjsSubmission } from "@/api/types";

interface Props {
  onCreated: (ms: Manuscript) => void;
}

export function CreateManuscriptDialog({ onCreated }: Props) {
  const [open, setOpen] = useState(false);
  const [submissions, setSubmissions] = useState<OjsSubmission[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState<number | null>(null);

  const [filter, setFilter] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [doiSuffix, setDoiSuffix] = useState("");
  const [submittingManual, setSubmittingManual] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    listOjsSubmissions()
      .then(setSubmissions)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [open]);

  const handleImport = async (submissionId: number) => {
    setImporting(submissionId);
    setError(null);
    try {
      const ms = await importOjsSubmission(submissionId);
      setOpen(false);
      onCreated(ms);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(null);
    }
  };

  const handleManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!doiSuffix.trim()) return;
    setSubmittingManual(true);
    setError(null);
    try {
      const ms = await createManuscript({ doi_suffix: doiSuffix.trim() });
      setOpen(false);
      setDoiSuffix("");
      onCreated(ms);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create manuscript");
    } finally {
      setSubmittingManual(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>
        New Manuscript
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import from OJS Copyediting Queue</DialogTitle>
        </DialogHeader>

        {loading && <p className="text-muted-foreground">Loading OJS submissions…</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && submissions && submissions.length === 0 && (
          <p className="text-muted-foreground py-4 text-sm">
            No submissions currently in copyediting stage in OJS.
          </p>
        )}

        {!loading && submissions && submissions.length > 0 && (
          <div className="min-w-0 space-y-3">
            <Input
              placeholder="Filter by title or DOI suffix…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          <div className="max-h-96 space-y-2 overflow-y-auto overflow-x-hidden">
            {submissions.filter((s) => {
              if (!filter.trim()) return true;
              const q = filter.trim().toLowerCase();
              return (
                s.title.toLowerCase().includes(q) ||
                s.doi_suffix.toLowerCase().includes(q) ||
                s.authors.some((a) => a.name?.toLowerCase().includes(q))
              );
            }).map((s) => (
              <div
                key={s.submission_id}
                className="flex items-center justify-between gap-3 rounded-md border p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{s.title}</div>
                  <div className="text-muted-foreground text-xs">
                    {s.doi_suffix}
                  </div>
                </div>
                <Button
                  size="sm"
                  disabled={s.already_imported || importing !== null}
                  onClick={() => handleImport(s.submission_id)}
                >
                  {s.already_imported
                    ? "Imported"
                    : importing === s.submission_id
                      ? "Importing…"
                      : "Import"}
                </Button>
              </div>
            ))}
          </div>
          </div>
        )}

        <div className="border-t pt-3">
          <button
            type="button"
            onClick={() => setManualOpen((v) => !v)}
            className="text-muted-foreground text-sm hover:underline"
          >
            {manualOpen ? "Hide" : "Advanced:"} enter DOI suffix manually
          </button>
          {manualOpen && (
            <form onSubmit={handleManual} className="mt-3 space-y-2">
              <Label htmlFor="doi_suffix">DOI Suffix</Label>
              <Input
                id="doi_suffix"
                placeholder="CCR2025.1.2.YAO"
                value={doiSuffix}
                onChange={(e) => setDoiSuffix(e.target.value)}
              />
              <Button type="submit" disabled={submittingManual} size="sm">
                {submittingManual ? "Creating…" : "Create"}
              </Button>
            </form>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
