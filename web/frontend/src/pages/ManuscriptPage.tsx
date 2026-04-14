import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/StatusBadge";
import { LogViewer } from "@/components/LogViewer";
import { PipelineProgress } from "@/components/PipelineProgress";
import { UploadZone } from "@/components/UploadZone";
import { getManuscript, getStatus, uploadFiles, startProcessing, downloadUrl, outputUrl } from "@/api/client";
import type { Manuscript, PipelineStep } from "@/api/types";

const PENDING_STEPS: PipelineStep[] = [
  { name: "prepare",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "compile",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "convert",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "validate", status: "pending", logs: [], started_at: null, completed_at: null },
];

function formatDate(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ManuscriptPage() {
  const { doiSuffix } = useParams<{ doiSuffix: string }>();
  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFullLog, setShowFullLog] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [fix, setFix] = useState(false);

  // Initial fetch
  useEffect(() => {
    if (!doiSuffix) return;
    getManuscript(doiSuffix)
      .then(setManuscript)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [doiSuffix]);

  // Status polling when queued or processing
  useEffect(() => {
    if (!doiSuffix || !manuscript) return;
    if (manuscript.status !== "queued" && manuscript.status !== "processing") return;

    const id = setInterval(async () => {
      try {
        const updated = await getStatus(doiSuffix);
        setManuscript(updated);
        if (updated.status !== "queued" && updated.status !== "processing") {
          clearInterval(id);
        }
      } catch {
        // Ignore transient errors during polling
      }
    }, 3000);

    return () => clearInterval(id);
  }, [doiSuffix, manuscript?.status]);

  if (loading) return <p className="text-muted-foreground">Loading...</p>;
  if (error) return <p className="text-red-600">{error}</p>;
  if (!manuscript || !doiSuffix) return <p className="text-red-600">Manuscript not found</p>;

  const isProcessing = manuscript.status === "queued" || manuscript.status === "processing";
  const isReady = manuscript.status === "ready";
  const hasBeenUploaded = manuscript.uploaded_at !== null;
  const canProcess = hasBeenUploaded && !isProcessing;
  const pipelineSteps = manuscript.pipeline_steps ?? PENDING_STEPS;

  const handleUpload = async (files: File[]) => {
    const updated = await uploadFiles(doiSuffix, files);
    setManuscript(updated);
    setUploadDialogOpen(false);
  };

  const handleStartProcessing = async () => {
    const updated = await startProcessing(doiSuffix, fix);
    setManuscript(updated);
  };

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
          &larr; Manuscripts
        </Link>
      </div>

      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <CardTitle className="text-xl">{manuscript.doi_suffix}</CardTitle>
            <StatusBadge status={manuscript.status} />
          </div>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">Created</dt>
              <dd>{formatDate(manuscript.created_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Updated</dt>
              <dd>{formatDate(manuscript.updated_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Uploaded</dt>
              <dd>{formatDate(manuscript.uploaded_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Uploaded by</dt>
              <dd>{manuscript.uploaded_by ?? "\u2014"}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Source — always visible; upload button opens a dialog */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <CardTitle className="text-base">Source</CardTitle>
            <Button
              variant={hasBeenUploaded ? "outline" : "default"}
              onClick={() => setUploadDialogOpen(true)}
              disabled={isProcessing}
              title={isProcessing ? "Wait for the current conversion to finish" : undefined}
            >
              {hasBeenUploaded ? "Upload new version" : "Upload source"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {hasBeenUploaded ? (
            <p className="text-sm text-muted-foreground">
              Last uploaded {formatDate(manuscript.uploaded_at)}
              {manuscript.uploaded_by ? ` by ${manuscript.uploaded_by}` : ""}.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              No source uploaded yet.
            </p>
          )}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="fix-source"
              checked={fix}
              onChange={(e) => setFix(e.target.checked)}
              disabled={isProcessing}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <Label htmlFor="fix-source" className="text-sm font-normal cursor-pointer">
              Apply source fixes before compiling
            </Label>
          </div>
          {canProcess && (
            <Button onClick={handleStartProcessing}>
              {isReady || manuscript.status === "failed"
                ? "Re-run conversion"
                : "Start conversion"}
            </Button>
          )}
        </CardContent>
      </Card>

      <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {hasBeenUploaded ? "Upload new version" : "Upload source"}
            </DialogTitle>
          </DialogHeader>
          <UploadZone onUpload={handleUpload} />
        </DialogContent>
      </Dialog>

      {/* Pipeline progress — always visible */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isProcessing ? "Pipeline Progress" : "Pipeline"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <PipelineProgress steps={pipelineSteps} />
        </CardContent>
      </Card>

      {/* Output — always visible */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Output</CardTitle>
        </CardHeader>
        <CardContent>
          {isReady ? (
            <div className="flex gap-3">
              <Button asChild>
                <a href={downloadUrl(doiSuffix)} download>
                  Download ZIP
                </a>
              </Button>
              <Button variant="outline" asChild>
                <Link to={`/manuscripts/${doiSuffix}/preview`}>View HTML Proof</Link>
              </Button>
              <Button variant="outline" asChild>
                <a href={outputUrl(doiSuffix, `${doiSuffix}.pdf`)} target="_blank" rel="noopener">
                  View PDF
                </a>
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Output will be available once the conversion completes successfully.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Full log (collapsible) */}
      {!isProcessing && manuscript.job_log && (
        <Card>
          <CardHeader>
            <button
              type="button"
              className="flex items-center gap-2 text-left"
              onClick={() => setShowFullLog(!showFullLog)}
            >
              <CardTitle className="text-base">Full Log</CardTitle>
              <span className="text-xs text-muted-foreground">
                {showFullLog ? "▾ hide" : "▸ show"}
              </span>
            </button>
          </CardHeader>
          {showFullLog && (
            <CardContent>
              <LogViewer log={manuscript.job_log} />
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
}
