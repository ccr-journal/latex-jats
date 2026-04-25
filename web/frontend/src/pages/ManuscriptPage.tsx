import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
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
import { LinkUpstreamDialog } from "@/components/LinkUpstreamDialog";
import { useAuth } from "@/auth/AuthContext";
import { getManuscript, getStatus, getVersion, uploadFiles, startProcessing, updateManuscript, reimportOjsMetadata, approveManuscript, withdrawApproval, deleteManuscript, archiveManuscript, unarchiveManuscript, downloadUrl, outputUrl, presign, getAuthorToken, regenerateAuthorToken, getInviteTemplate, inviteAuthors, syncUpstream, unlinkUpstream, type Recipient } from "@/api/client";
import { ApiError } from "@/api/client";
import type { Manuscript, PipelineStep } from "@/api/types";

const PENDING_STEPS: PipelineStep[] = [
  { name: "prepare",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "compile",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "convert",  status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "check",    status: "pending", logs: [], started_at: null, completed_at: null },
  { name: "validate", status: "pending", logs: [], started_at: null, completed_at: null },
];

function isExternalUpstream(ms: Manuscript): boolean {
  return !!ms.upstream_url && !ms.upstream_url.startsWith("file://");
}

function formatUpstreamHost(url: string | null): string {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`;
  } catch {
    return url;
  }
}

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
  const navigate = useNavigate();
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
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [archiving, setArchiving] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [ccrClsVersion, setCcrClsVersion] = useState<string | null>(null);
  const [linkUpstreamOpen, setLinkUpstreamOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [upstreamError, setUpstreamError] = useState<string | null>(null);

  // Initial fetch
  useEffect(() => {
    if (!doiSuffix) return;
    getManuscript(doiSuffix)
      .then(setManuscript)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [doiSuffix]);

  useEffect(() => {
    getVersion().then((v) => setCcrClsVersion(v.ccr_cls_version)).catch(() => {});
  }, []);

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
  const isArchived = manuscript.status === "archived";
  const hasOutput = isReady || isApproved;
  const hasBeenUploaded = manuscript.uploaded_at !== null;
  // Disable convert during a sync so the editor can't kick off a pipeline run
  // against a half-fetched source_dir.
  const canProcess = hasBeenUploaded && !isProcessing && !isApproved && !syncing;
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

  const handleUseCanonicalToggle = async (checked: boolean) => {
    const updated = await updateManuscript(doiSuffix, { use_canonical_ccr_cls: checked });
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
    const updated = await startProcessing(
      doiSuffix,
      manuscript.fix_source,
      manuscript.use_canonical_ccr_cls,
    );
    setManuscript(updated);
  };

  const handleArchive = async () => {
    setArchiving(true);
    setArchiveError(null);
    try {
      const updated = await archiveManuscript(doiSuffix);
      setManuscript(updated);
    } catch (err) {
      setArchiveError(err instanceof ApiError ? err.message : "Failed to archive");
    } finally {
      setArchiving(false);
    }
  };

  const handleUnarchive = async () => {
    setArchiving(true);
    setArchiveError(null);
    try {
      const updated = await unarchiveManuscript(doiSuffix);
      setManuscript(updated);
    } catch (err) {
      setArchiveError(err instanceof ApiError ? err.message : "Failed to unarchive");
    } finally {
      setArchiving(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setUpstreamError(null);
    try {
      const updated = await syncUpstream(doiSuffix);
      setManuscript(updated);
    } catch (err) {
      setUpstreamError(err instanceof ApiError ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const handleUnlink = async () => {
    if (!window.confirm("Unlink the git / Overleaf source? The currently synced files will be deleted — you'll need to re-link or upload again before running the conversion.")) return;
    setUpstreamError(null);
    try {
      const updated = await unlinkUpstream(doiSuffix);
      setManuscript(updated);
    } catch (err) {
      setUpstreamError(err instanceof ApiError ? err.message : "Failed to unlink");
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteManuscript(doiSuffix);
      navigate("/dashboard");
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Failed to delete manuscript");
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {!isTokenScoped && (
        <div>
          <Link to="/dashboard" className="text-sm text-muted-foreground hover:text-foreground">
            &larr; Manuscripts
          </Link>
        </div>
      )}

      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <CardTitle className="text-xl">{manuscript.doi_suffix}</CardTitle>
              <StatusBadge status={manuscript.status} />
            </div>
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
              {isEditor && (isArchived ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={archiving}
                  onClick={handleUnarchive}
                >
                  {archiving ? "Unarchiving\u2026" : "Unarchive"}
                </Button>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={archiving || isProcessing}
                  title={isProcessing ? "Wait for the current conversion to finish" : undefined}
                  onClick={handleArchive}
                >
                  {archiving ? "Archiving\u2026" : "Archive"}
                </Button>
              ))}
              {isEditor && (
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={isApproved || isProcessing}
                  title={
                    isApproved
                      ? "Withdraw approval before deleting"
                      : isProcessing
                        ? "Wait for the current conversion to finish"
                        : undefined
                  }
                  onClick={() => {
                    setDeleteError(null);
                    setDeleteDialogOpen(true);
                  }}
                >
                  Delete
                </Button>
              )}
            </div>
          </div>
          {archiveError && (
            <p className="text-sm text-red-600 mt-2">{archiveError}</p>
          )}
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
              {(() => {
                const primary = manuscript.authors.find((a) => a.primary_contact);
                return primary ? (
                  <span className="ml-2 text-xs">
                    (primary contact: {primary.name ?? "unknown"})
                  </span>
                ) : null;
              })()}
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

          {(manuscript.date_received ||
            manuscript.date_accepted ||
            manuscript.date_published) && (
            <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {manuscript.date_received && (
                <span>Received {manuscript.date_received}</span>
              )}
              {manuscript.date_accepted && (
                <span>Accepted {manuscript.date_accepted}</span>
              )}
              {manuscript.date_published && (
                <span>Published {manuscript.date_published}</span>
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

          {isEditor && <AuthorLink doiSuffix={doiSuffix} authors={manuscript.authors} />}
        </CardContent>
      </Card>

      {/* Source — always visible; upload button opens a dialog */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <CardTitle className="text-base">Source</CardTitle>
            <div className="flex items-center gap-2">
              {isExternalUpstream(manuscript) ? (
                <>
                  <Button
                    onClick={handleSync}
                    disabled={isProcessing || isApproved || syncing}
                    title={isApproved ? "Manuscript has been approved — sync is locked" : undefined}
                  >
                    {syncing ? "Syncing…" : "Sync now"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setLinkUpstreamOpen(true)}
                    disabled={isProcessing || isApproved}
                  >
                    Edit link
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleUnlink}
                    disabled={isProcessing || isApproved}
                  >
                    Unlink
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant={hasBeenUploaded ? "outline" : "default"}
                    onClick={() => setUploadDialogOpen(true)}
                    disabled={isProcessing || isApproved}
                    title={isApproved ? "Manuscript has been approved — upload is locked" : isProcessing ? "Wait for the current conversion to finish" : undefined}
                  >
                    {hasBeenUploaded ? "Upload new version" : "Upload source"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setLinkUpstreamOpen(true)}
                    disabled={isProcessing || isApproved}
                  >
                    Link git / overleaf
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {upstreamError && (
            <p className="text-sm text-red-600">{upstreamError}</p>
          )}
          {isExternalUpstream(manuscript) ? (
            <div className="text-sm space-y-1">
              <p>
                <span className="text-muted-foreground">Linked to</span>{" "}
                <a
                  href={manuscript.upstream_url ?? "#"}
                  target="_blank"
                  rel="noopener"
                  className="font-medium hover:underline"
                >
                  {formatUpstreamHost(manuscript.upstream_url)}
                </a>
                {manuscript.upstream_ref && (
                  <span className="text-muted-foreground"> · {manuscript.upstream_ref}</span>
                )}
                {manuscript.upstream_subpath && (
                  <span className="text-muted-foreground"> · {manuscript.upstream_subpath}</span>
                )}
              </p>
              {manuscript.last_synced_at ? (
                <p className="text-muted-foreground">
                  Last synced {formatDate(manuscript.last_synced_at)}
                  {manuscript.last_synced_sha
                    ? ` at ${manuscript.last_synced_sha.slice(0, 7)}`
                    : ""}
                  .
                </p>
              ) : (
                <p className="text-muted-foreground">Not synced yet — click Sync now to fetch.</p>
              )}
            </div>
          ) : hasBeenUploaded ? (
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
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="use-canonical-ccr-cls"
              checked={manuscript.use_canonical_ccr_cls}
              onChange={(e) => handleUseCanonicalToggle(e.target.checked)}
              disabled={isProcessing || isApproved}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <Label htmlFor="use-canonical-ccr-cls" className="text-sm font-normal cursor-pointer">
              Use most recent ccr.cls file{ccrClsVersion ? ` (v${ccrClsVersion})` : ""}
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

      <LinkUpstreamDialog
        doiSuffix={doiSuffix}
        current={manuscript}
        open={linkUpstreamOpen}
        onOpenChange={setLinkUpstreamOpen}
        onLinked={(linked) => {
          setManuscript(linked);
          // The link wipes source_dir; auto-sync so the user lands in a
          // usable state. Errors surface via upstreamError on the Source card.
          void handleSync();
        }}
      />

      <Dialog open={deleteDialogOpen} onOpenChange={(open) => { if (!deleting) setDeleteDialogOpen(open); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete manuscript</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p>
              This will permanently and irreversibly remove <strong>{doiSuffix}</strong>,
              including all uploaded source files, conversion output, author records,
              and access tokens.
            </p>
            <p>This cannot be undone. Are you sure?</p>
            {deleteError && <p className="text-red-600">{deleteError}</p>}
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Deleting\u2026" : "Delete"}
            </Button>
          </div>
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


function AuthorLink({ doiSuffix, authors }: { doiSuffix: string; authors: { name: string | null; email: string | null }[] }) {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [inviteMessage, setInviteMessage] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [newRecipient, setNewRecipient] = useState("");
  const [loadingTemplate, setLoadingTemplate] = useState(false);

  const authorsWithEmail = authors.filter((a) => a.email);

  useEffect(() => {
    getAuthorToken(doiSuffix)
      .then((data) => setUrl(data.url))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [doiSuffix]);

  const handleCopy = async () => {
    if (!url) return;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRegenerate = async () => {
    if (!window.confirm("Regenerate the author link? The previous link will stop working.")) return;
    setRegenerating(true);
    try {
      const data = await regenerateAuthorToken(doiSuffix);
      setUrl(data.url);
    } finally {
      setRegenerating(false);
    }
  };

  const handleOpenInvite = async () => {
    setInviteMessage(null);
    setNewRecipient("");
    setInviteDialogOpen(true);
    setLoadingTemplate(true);
    try {
      const tpl = await getInviteTemplate(doiSuffix);
      setSubject(tpl.subject);
      setBody(tpl.body);
      setRecipients(tpl.recipients);
    } catch {
      setSubject("");
      setBody("");
      setRecipients([]);
    } finally {
      setLoadingTemplate(false);
    }
  };

  const handleInvite = async () => {
    setInviting(true);
    setInviteMessage(null);
    try {
      const result = await inviteAuthors(doiSuffix, { subject, body, recipients });
      setInviteMessage(`Sent to ${result.sent.join(", ")}`);
      setInviteDialogOpen(false);
    } catch (err) {
      setInviteMessage(err instanceof Error ? err.message : "Failed to send invitations");
    } finally {
      setInviting(false);
    }
  };

  const handleAddRecipient = () => {
    const input = newRecipient.trim();
    if (!input) return;
    // Parse "Name <email>" or just "email"
    const match = input.match(/^(.+?)\s*<([^>]+)>$/);
    const recipient: Recipient = match
      ? { name: match[1].trim(), email: match[2].trim() }
      : { name: input.split("@")[0], email: input };
    if (!recipient.email.includes("@")) return;
    if (recipients.some((r) => r.email === recipient.email)) return;
    setRecipients([...recipients, recipient]);
    setNewRecipient("");
  };

  const handleRemoveRecipient = (email: string) => {
    setRecipients(recipients.filter((r) => r.email !== email));
  };

  if (loading) return null;

  return (
    <>
      <div className="text-muted-foreground flex items-center gap-2 text-sm">
        {url ? (
          <>
            <button type="button" onClick={handleCopy} className="hover:underline">
              {copied ? "Copied!" : "Copy author link"}
            </button>
            <button
              type="button"
              onClick={handleRegenerate}
              disabled={regenerating}
              className="text-xs hover:underline"
            >
              {regenerating ? "(regenerating...)" : "(regenerate)"}
            </button>
            <span className="text-muted-foreground/50">|</span>
            <button
              type="button"
              onClick={handleOpenInvite}
              disabled={authorsWithEmail.length === 0}
              className="hover:underline disabled:opacity-50 disabled:no-underline"
              title={authorsWithEmail.length === 0 ? "No authors have email addresses" : undefined}
            >
              Invite authors
            </button>
          </>
        ) : (
          <span>Author link unavailable</span>
        )}
        {inviteMessage && (
          <span className={inviteMessage.includes("Failed") ? "text-red-600" : "text-green-700"}>
            {inviteMessage}
          </span>
        )}
      </div>

      <Dialog open={inviteDialogOpen} onOpenChange={setInviteDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Invite authors</DialogTitle>
          </DialogHeader>
          {loadingTemplate ? (
            <p className="text-sm text-muted-foreground">Loading template...</p>
          ) : (
            <div className="space-y-3">
              <div className="space-y-1">
                <Label className="text-sm font-medium">To</Label>
                <div className="flex flex-wrap gap-1.5">
                  {recipients.map((r) => (
                    <span
                      key={r.email}
                      className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs"
                    >
                      {r.name} &lt;{r.email}&gt;
                      <button
                        type="button"
                        onClick={() => handleRemoveRecipient(r.email)}
                        className="ml-0.5 text-muted-foreground hover:text-foreground"
                        aria-label={`Remove ${r.name}`}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newRecipient}
                    onChange={(e) => setNewRecipient(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAddRecipient(); } }}
                    placeholder="Add recipient: Name <email> or email"
                    className="flex-1 rounded border border-input bg-background px-3 py-1.5 text-sm"
                  />
                  <Button type="button" variant="outline" size="sm" onClick={handleAddRecipient} disabled={!newRecipient.trim()}>
                    Add
                  </Button>
                </div>
                {authorsWithEmail.length > recipients.length && (
                  <button
                    type="button"
                    onClick={() => setRecipients(authorsWithEmail.map((a) => ({ name: a.name ?? "Author", email: a.email! })))}
                    className="text-xs text-muted-foreground hover:underline"
                  >
                    Add all authors with email
                  </button>
                )}
              </div>
              <div className="space-y-1">
                <Label htmlFor="invite-subject" className="text-sm font-medium">Subject</Label>
                <input
                  id="invite-subject"
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="invite-body" className="text-sm font-medium">
                  Message <span className="font-normal text-muted-foreground">(markdown)</span>
                </Label>
                <textarea
                  id="invite-body"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={16}
                  className="w-full rounded border border-input bg-background px-3 py-2 text-sm font-mono"
                />
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setInviteDialogOpen(false)} disabled={inviting}>
              Cancel
            </Button>
            <Button onClick={handleInvite} disabled={inviting || loadingTemplate || recipients.length === 0}>
              {inviting ? "Sending\u2026" : "Send invitations"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
