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
import { ApiError, linkUpstream } from "@/api/client";
import type { Manuscript } from "@/api/types";

interface Props {
  doiSuffix: string;
  current: Manuscript;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onLinked: (ms: Manuscript) => void;
}

type Provider = "overleaf" | "github" | "gitlab" | "generic";

// Overleaf's "Clone with git" panel and GitHub's clone box copy with the
// `git clone ` prefix included; strip it so a paste lands as a plain URL.
function stripGitClonePrefix(raw: string): string {
  return raw.replace(/^\s*git\s+clone\s+/i, "").trimStart();
}

function detectProvider(url: string): Provider {
  const lower = url.toLowerCase();
  if (lower.includes("overleaf.com")) return "overleaf";
  if (lower.includes("github.com")) return "github";
  if (lower.includes("gitlab.com")) return "gitlab";
  return "generic";
}

function OverleafInstructions() {
  return (
    <ol className="list-decimal space-y-1 pl-5">
      <li>
        In Overleaf, open the project and click{" "}
        <span className="font-medium">Menu → Sync → Git</span>. Copy the URL —
        it looks like{" "}
        <code>https://git@git.overleaf.com/&lt;PROJECT_ID&gt;</code>.
      </li>
      <li>
        Create an access token in{" "}
        <a
          href="https://www.overleaf.com/user/settings"
          target="_blank"
          rel="noopener"
          className="underline"
        >
          Account Settings → Project and Personal Access Tokens
        </a>
        . Tokens are limited to 10 per account and expire after one year.
      </li>
      <li>Paste the URL and token above.</li>
    </ol>
  );
}

function GitHubInstructions() {
  return (
    <ol className="list-decimal space-y-1 pl-5">
      <li>
        Copy the repository URL from GitHub's{" "}
        <span className="font-medium">Code → HTTPS</span> button — e.g.{" "}
        <code>https://github.com/owner/repo.git</code>.
      </li>
      <li>
        Public repos don't need a token. For private repos, create a{" "}
        <a
          href="https://github.com/settings/personal-access-tokens"
          target="_blank"
          rel="noopener"
          className="underline"
        >
          fine-grained personal access token
        </a>{" "}
        scoped to the single repository, with{" "}
        <span className="font-medium">Contents: Read</span> permission.
      </li>
      <li>Paste the URL (and, if private, the token) above.</li>
    </ol>
  );
}

function ProviderInstructions({ provider }: { provider: Provider }) {
  if (provider === "overleaf") return <OverleafInstructions />;
  if (provider === "github") return <GitHubInstructions />;
  // generic / gitlab / unknown — show both common cases.
  return (
    <div className="space-y-3">
      <div>
        <p className="font-medium">Overleaf</p>
        <OverleafInstructions />
      </div>
      <div>
        <p className="font-medium">GitHub</p>
        <GitHubInstructions />
      </div>
    </div>
  );
}

function isExternalUpstream(ms: Manuscript): boolean {
  return !!ms.upstream_url && !ms.upstream_url.startsWith("file://");
}

export function LinkUpstreamDialog({
  doiSuffix,
  current,
  open,
  onOpenChange,
  onLinked,
}: Props) {
  const existing = isExternalUpstream(current);
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [ref, setRef] = useState("");
  const [subpath, setSubpath] = useState("");
  const [mainFile, setMainFile] = useState("");
  const [replaceToken, setReplaceToken] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Prefill from the current manuscript whenever the dialog opens.
  useEffect(() => {
    if (!open) return;
    setUrl(existing ? current.upstream_url ?? "" : "");
    setToken("");
    setRef(current.upstream_ref ?? "");
    setSubpath(current.upstream_subpath ?? "");
    setMainFile(current.main_file ?? "");
    setReplaceToken(false);
    setError(null);
  }, [open, existing, current]);

  const provider = detectProvider(url);
  const hasStoredToken = existing && current.upstream_has_token;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      const linked = await linkUpstream(doiSuffix, {
        url: url.trim(),
        token: token.trim() || undefined,
        // Only clear the stored token when the user explicitly asked to replace
        // it but left the field blank.
        clear_token: replaceToken && !token.trim() ? true : undefined,
        ref: ref.trim() || undefined,
        subpath: subpath.trim() || undefined,
        main_file: mainFile.trim() || undefined,
      });
      // Hand the linked manuscript to the parent and close — the parent kicks
      // off the sync so the page-level "Syncing…" indicator does the talking.
      onLinked(linked);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to link source");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {existing ? "Update git / Overleaf link" : "Link git / Overleaf source"}
          </DialogTitle>
        </DialogHeader>
        {/*
          autoComplete="off" on the form plus one-off, non-standard names on
          the URL and token inputs together persuade Chrome/Firefox not to
          treat them as username/password and offer to autofill the editor's
          login. The token is rendered as type="text" since the user already
          pasted it somewhere to get here — masking adds nothing.
        */}
        <form onSubmit={handleSubmit} className="space-y-3" autoComplete="off">
          <div className="space-y-1">
            <Label htmlFor="upstream-url">Repository URL</Label>
            <Input
              id="upstream-url"
              name="ccr-upstream-url"
              placeholder="https://github.com/user/repo or https://git.overleaf.com/<PROJECT_ID>"
              value={url}
              onChange={(e) => setUrl(stripGitClonePrefix(e.target.value))}
              required
              autoFocus
              autoComplete="off"
            />
            {url && (
              <p className="text-muted-foreground text-xs">
                Detected: <span className="font-medium">{provider}</span>
              </p>
            )}
          </div>

          <div className="space-y-1">
            <Label htmlFor="upstream-token">
              Access token{" "}
              <span className="text-muted-foreground font-normal">
                (optional for public repos)
              </span>
            </Label>
            {hasStoredToken && !replaceToken ? (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-sm italic">
                  Token stored
                </span>
                <button
                  type="button"
                  onClick={() => setReplaceToken(true)}
                  className="text-xs hover:underline"
                >
                  Replace
                </button>
              </div>
            ) : (
              <>
                <Input
                  id="upstream-token"
                  name="ccr-upstream-token"
                  type="text"
                  placeholder={provider === "overleaf" ? "Overleaf personal access token" : "Personal access token"}
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  autoComplete="off"
                  data-1p-ignore
                  data-lpignore="true"
                />
                {hasStoredToken && (
                  <p className="text-muted-foreground text-xs">
                    Leave blank and save to clear the stored token.{" "}
                    <button
                      type="button"
                      onClick={() => setReplaceToken(false)}
                      className="hover:underline"
                    >
                      Cancel replace
                    </button>
                  </p>
                )}
              </>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="upstream-ref">
                Branch/tag{" "}
                <span className="text-muted-foreground font-normal">(optional)</span>
              </Label>
              <Input
                id="upstream-ref"
                placeholder="main"
                value={ref}
                onChange={(e) => setRef(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="upstream-subpath">
                Subdirectory{" "}
                <span className="text-muted-foreground font-normal">(optional)</span>
              </Label>
              <Input
                id="upstream-subpath"
                value={subpath}
                onChange={(e) => setSubpath(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="upstream-main-file">
              Main file{" "}
              <span className="text-muted-foreground font-normal">
                (defaults to main.tex / first .qmd)
              </span>
            </Label>
            <Input
              id="upstream-main-file"
              placeholder="main.tex"
              value={mainFile}
              onChange={(e) => setMainFile(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <details className="rounded border bg-muted/30 px-3 py-2 text-xs">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              Help &amp; instructions
            </summary>
            <div className="mt-2 space-y-2 text-foreground">
              <ProviderInstructions provider={provider} />
            </div>
          </details>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !url.trim()}>
              {submitting
                ? "Saving…"
                : existing
                  ? "Update & sync"
                  : "Link & sync"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
