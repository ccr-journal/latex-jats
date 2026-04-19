import { useState } from "react";
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
import { createManuscript, importOjsSubmission } from "@/api/client";
import type { OjsStage } from "@/api/client";
import type { Manuscript, OjsSubmission } from "@/api/types";
import { useOjs, useOjsSubmissions } from "@/ojs/OjsContext";

interface Props {
  onCreated: (ms: Manuscript) => void;
}

export function CreateManuscriptDialog({ onCreated }: Props) {
  const [open, setOpen] = useState(false);
  const [importing, setImporting] = useState<number | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [filter, setFilter] = useState("");
  const [stage, setStage] = useState<OjsStage>("copyediting");
  const [showImported, setShowImported] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [doiSuffix, setDoiSuffix] = useState("");
  const [submittingManual, setSubmittingManual] = useState(false);

  const { refresh } = useOjs();
  const { submissions, loading, error: loadError } = useOjsSubmissions(stage);
  const error = importError ?? loadError;

  const handleImport = async (submissionId: number) => {
    setImporting(submissionId);
    setImportError(null);
    try {
      const ms = await importOjsSubmission(submissionId);
      setOpen(false);
      onCreated(ms);
      void refresh(stage);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(null);
    }
  };

  const handleManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!doiSuffix.trim()) return;
    setSubmittingManual(true);
    setImportError(null);
    try {
      const ms = await createManuscript({ doi_suffix: doiSuffix.trim() });
      setOpen(false);
      setDoiSuffix("");
      onCreated(ms);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Failed to create manuscript");
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
          <DialogTitle>Import from OJS</DialogTitle>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-muted-foreground">Stage:</span>
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value as OjsStage)}
              className="border-input bg-background rounded-md border px-2 py-1 text-sm"
            >
              <option value="copyediting">Copyediting</option>
              <option value="production">Production (backlog)</option>
            </select>
          </label>
          <Button
            size="sm"
            variant="outline"
            disabled={loading}
            onClick={() => void refresh(stage)}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={showImported}
              onChange={(e) => setShowImported(e.target.checked)}
            />
            <span className="text-muted-foreground">
              Show already-imported submissions
            </span>
          </label>
        </div>

        {loading && <p className="text-muted-foreground">Loading OJS submissions…</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && submissions && submissions.length === 0 && (
          <p className="text-muted-foreground py-4 text-sm">
            No submissions currently in {stage} stage in OJS.
          </p>
        )}

        {!loading && submissions && submissions.length > 0 && (() => {
          const q = filter.trim().toLowerCase();
          const matchesFilter = (s: OjsSubmission) =>
            !q ||
            s.title.toLowerCase().includes(q) ||
            s.doi_suffix.toLowerCase().includes(q) ||
            s.authors.some((a) => a.name?.toLowerCase().includes(q));
          const visible = submissions.filter(
            (s) => matchesFilter(s) && (showImported || !s.already_imported),
          );
          const hiddenImported = submissions.filter(
            (s) => matchesFilter(s) && s.already_imported && !showImported,
          ).length;
          return (
            <div className="min-w-0 space-y-3">
              <Input
                placeholder="Filter by title or DOI suffix…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              {visible.length === 0 ? (
                <p className="text-muted-foreground py-4 text-sm">
                  No submissions match the current filter
                  {hiddenImported > 0
                    ? ` (${hiddenImported} already-imported hidden — tick “Show already-imported submissions” to see them).`
                    : "."}
                </p>
              ) : (
                <div className="max-h-96 space-y-2 overflow-y-auto overflow-x-hidden">
                  {visible.map((s) => (
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
              )}
              {visible.length > 0 && hiddenImported > 0 && (
                <p className="text-muted-foreground text-xs">
                  {hiddenImported} already-imported submission
                  {hiddenImported === 1 ? "" : "s"} hidden.
                </p>
              )}
            </div>
          );
        })()}

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
