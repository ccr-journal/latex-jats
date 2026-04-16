import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/StatusBadge";
import { PipelineProgress } from "@/components/PipelineProgress";
import { MetadataCard } from "@/components/MetadataCard";
import { UploadZone } from "@/components/UploadZone";
import { useAuth } from "@/auth/AuthContext";
import { getManuscript, getStatus, uploadFiles, startProcessing, updateManuscript, reimportOjsMetadata, approveManuscript, withdrawApproval, downloadUrl, outputUrl, presign, getAuthorToken, regenerateAuthorToken } from "@/api/client";
import { ApiError } from "@/api/client";
import type { Manuscript, PipelineStep } from "@/api/types";

const PENDING_STEPS: PipelineStep[] = [
  { name: "prepare",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "compile",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "convert",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "check",    status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "validate", status: "pending", logs: [], started_at: null, completed_at: null },
];

function formatAuthors(authors: { name: string | null }[]): string {
  const names = authors.map((a) => a.name ?? "Unknown");
  if (names.length === 0) return "";
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]} & ${names[1]}`;
  return `${names[0]} et al.`;
}

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
  const { user } = useAuth();
  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [abstractExpanded, setAbstractExpanded] = useState(false);
  const [reimporting, setReimporting] = useState(false);
  const [metadataRefreshKey, setMetadataRefreshKey] = useState(0);
  const [approveDialogOpen, setApproveDialogOpen] = useState(false);
  const [approving, setApproving] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawError, setWithdrawError] = useState<string | null>(null);

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
  const isApproved = manuscript.status === "approved";
  const hasOutput = isReady || isApproved;
  const hasBeenUploaded = manuscript.uploaded_at !== null;
  const canProcess = hasBeenUploaded && !isProcessing && !isApproved;
  const pipelineSteps = manuscript.pipeline_steps ?? PENDING_STEPS;
  const checkStep = pipelineSteps.find((s) => s.name === "check");
  const checkStepDone = checkStep != null && ["ok", "warnings", "errors"].includes(checkStep.status);
  const isEditor = user?.role === "editor";
  const isTokenScoped = !!user?.manuscript_token_scope;

  const handleUpload = async (files: File[]) => {
    const updated = await uploadFiles(doiSuffix, files);
    setManuscript(updated);
    setUploadDialogOpen(false);
  };

  const handleFixToggle = async (checked: boolean) => {
    const updated = await updateManuscript(doiSuffix, { fix_source: checked });
    setManuscript(updated);
  };

  const handleReimport = async () => {
    setReimporting(true);
    try {
      const updated = await reimportOjsMetadata(doiSuffix);
      setManuscript(updated);
      setMetadataRefreshKey((k) => k + 1);
    } catch {
      // Ignore — user will see stale data
    } finally {
      setReimporting(false);
    }
  };

  const handleApprove = async () => {
    setApproving(true);
    try {
      const updated = await approveManuscript(doiSuffix);
      setManuscript(updated);
      setApproveDialogOpen(false);
    } finally {
      setApproving(false);
    }
  };

  const handleWithdrawApproval = async () => {
    setWithdrawing(true);
    setWithdrawError(null);
    try {
      const updated = await withdrawApproval(doiSuffix);
      setManuscript(updated);
    } catch (err) {
      setWithdrawError(err instanceof ApiError ? err.message : "Failed to withdraw approval");
    } finally {
      setWithdrawing(false);
    }
  };

  const handleStartProcessing = async () => {
    const updated = await startProcessing(doiSuffix, manuscript.fix_source);
    setManuscript(updated);
  };

  return (
    <div className="space-y-6">
      {!isTokenScoped && (
        <div>
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
            &larr; Manuscripts
          </Link>
        </div>
      )}

      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <CardTitle className="text-xl">{manuscript.doi_suffix}</CardTitle>
            <div className="flex items-center gap-2">
              {isEditor && manuscript.ojs_submission_id && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={reimporting || isProcessing}
                  onClick={handleReimport}
                >
                  {reimporting ? "Importing\u2026" : "Refresh from OJS"}
                </Button>
              )}
              <StatusBadge status={manuscript.status} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {manuscript.title && (
            <div className="text-base font-medium">
              {manuscript.title}
              {manuscript.subtitle && (
                <span className="text-muted-foreground font-normal">: {manuscript.subtitle}</span>
              )}
            </div>
          )}

          {manuscript.authors.length > 0 && (
            <div className="text-muted-foreground text-sm">
              {formatAuthors(manuscript.authors)}
            </div>
          )}

          {(manuscript.volume ||
            manuscript.issue_number ||
            manuscript.year ||
            manuscript.doi) && (
            <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1">
              {manuscript.volume && (
                <span>Vol. {manuscript.volume}</span>
              )}
              {manuscript.issue_number && (
                <span>No. {manuscript.issue_number}</span>
              )}
              {manuscript.year && <span>{manuscript.year}</span>}
              {manuscript.doi && (
                <a
                  href={`https://doi.org/${manuscript.doi}`}
                  target="_blank"
                  rel="noopener"
                  className="hover:underline"
                >
                  {manuscript.doi}
                </a>
              )}
            </div>
          )}

          {manuscript.abstract && (
            <div>
              <div
                className={`prose prose-sm max-w-none [&_p]:my-1 ${
                  abstractExpanded ? "" : "line-clamp-2"
                }`}
                dangerouslySetInnerHTML={{ __html: manuscript.abstract }}
              />
              <button
                type="button"
                onClick={() => setAbstractExpanded(!abstractExpanded)}
                className="text-muted-foreground mt-1 text-xs hover:underline"
              >
                {abstractExpanded ? "Show less" : "Show more"}
              </button>
            </div>
          )}

          {manuscript.keywords && manuscript.keywords.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {manuscript.keywords.map((kw) => (
                <span
                  key={kw}
                  className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-xs"
                >
                  {kw}
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Author link — editor only */}
      {isEditor && <AuthorLinkCard doiSuffix={doiSuffix} />}

      {/* Source — always visible; upload button opens a dialog */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <CardTitle className="text-base">Source</CardTitle>
            <Button
              variant={hasBeenUploaded ? "outline" : "default"}
              onClick={() => setUploadDialogOpen(true)}
              disabled={isProcessing || isApproved}
              title={isApproved ? "Manuscript has been approved — upload is locked" : isProcessing ? "Wait for the current conversion to finish" : undefined}
            >
              {hasBeenUploaded ? "Upload new version" : "Upload source"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {hasBeenUploaded ? (
            <p className="text-sm text-muted-foreground">
              {manuscript.upload_file_count != null
                ? `${manuscript.upload_file_count} file${manuscript.upload_file_count === 1 ? "" : "s"} uploaded`
                : "Uploaded"}{" "}
              {formatDate(manuscript.uploaded_at)}
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
              checked={manuscript.fix_source}
              onChange={(e) => handleFixToggle(e.target.checked)}
              disabled={isProcessing || isApproved}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <Label htmlFor="fix-source" className="text-sm font-normal cursor-pointer">
              Apply source fixes before compiling
            </Label>
          </div>
          {canProcess && (
            <Button onClick={handleStartProcessing}>
              {isReady || isApproved || manuscript.status === "failed"
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

      <Dialog open={approveDialogOpen} onOpenChange={setApproveDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Approve for publication</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            {pipelineSteps.some((s) => s.status === "warnings") && (
              <p className="text-amber-700 bg-amber-50 rounded p-2">
                This manuscript has pipeline warnings. Please review them before approving.
              </p>
            )}
            <p className="text-muted-foreground">
              After publication, the PDF and HTML proof will be locked and can no longer be changed.
              To make further changes, you will need to withdraw approval, upload a new version and re-run the conversion.
            </p>
            <p>Are you sure you want to approve this manuscript for publication?</p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setApproveDialogOpen(false)} disabled={approving}>
              Cancel
            </Button>
            <Button onClick={handleApprove} disabled={approving}>
              {approving ? "Approving\u2026" : "Approve"}
            </Button>
          </div>
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

      {/* Metadata comparison */}
      {manuscript.ojs_submission_id ? (
        checkStepDone ? (
          <MetadataCard
            doiSuffix={doiSuffix}
            isEditor={isEditor}
            readOnly={isApproved}
            refreshKey={metadataRefreshKey}
            onSync={() => {
              getManuscript(doiSuffix).then(setManuscript);
            }}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Metadata Discrepancies</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Metadata comparison will be available after the check step completes.
              </p>
            </CardContent>
          </Card>
        )
      ) : null}

      {/* Output — always visible */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">View proofs</CardTitle>
        </CardHeader>
        <CardContent>
          {hasOutput ? (
            <div className="space-y-3">
              <div className="flex gap-3">
                <Button
                  onClick={async () => {
                    const token = await presign(doiSuffix);
                    const a = document.createElement("a");
                    a.href = downloadUrl(doiSuffix, token);
                    a.download = "";
                    a.click();
                  }}
                >
                  Download ZIP
                </Button>
                <Link
                  to={`/manuscripts/${doiSuffix}/preview`}
                  className={buttonVariants({ variant: "outline" })}
                >
                  View HTML Proof
                </Link>
                <Link
                  to={`/manuscripts/${doiSuffix}/xml`}
                  className={buttonVariants({ variant: "outline" })}
                >
                  View XML
                </Link>
                <Link
                  to={`/manuscripts/${doiSuffix}/pdf`}
                  className={buttonVariants({ variant: "outline" })}
                >
                  View PDF
                </Link>
              </div>
              {isReady && (
                <Button onClick={() => setApproveDialogOpen(true)}>
                  Approve for publication
                </Button>
              )}
              {isApproved && (
                <p className="text-sm text-orange-700 dark:text-orange-300 bg-orange-50 dark:bg-orange-950 rounded p-3">
                  Thanks for checking and approving the proofs. We will now proceed to publish the article. You will be notified when the article is published.
                </p>
              )}
              {isApproved && (
                <div className="flex items-center gap-3">
                  <Button variant="outline" size="sm" onClick={handleWithdrawApproval} disabled={withdrawing}>
                    {withdrawing ? "Withdrawing\u2026" : "Withdraw approval"}
                  </Button>
                  {withdrawError && (
                    <span className="text-sm text-red-600">{withdrawError}</span>
                  )}
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Output will be available once the conversion completes successfully.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


function AuthorLinkCard({ doiSuffix }: { doiSuffix: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const fetchToken = async () => {
    setLoading(true);
    try {
      const data = await getAuthorToken(doiSuffix);
      setUrl(data.url);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const data = await regenerateAuthorToken(doiSuffix);
      setUrl(data.url);
    } finally {
      setRegenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!url) return;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Author link</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {url == null ? (
          <div>
            <p className="text-sm text-muted-foreground mb-2">
              Generate a link that gives authors access to view and upload to this manuscript.
            </p>
            <Button variant="outline" size="sm" onClick={fetchToken} disabled={loading}>
              {loading ? "Generating..." : "Get author link"}
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Share this link with the authors. Anyone with the link can view and upload to this manuscript.
            </p>
            <div className="flex gap-2">
              <Input
                readOnly
                value={url}
                className="font-mono text-xs"
                onClick={(e) => (e.target as HTMLInputElement).select()}
              />
              <Button variant="outline" size="sm" onClick={handleCopy}>
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground"
              onClick={handleRegenerate}
              disabled={regenerating}
            >
              {regenerating ? "Regenerating..." : "Regenerate link (invalidates previous)"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
