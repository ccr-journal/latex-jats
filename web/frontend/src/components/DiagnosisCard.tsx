import {
  getDiagnosis,
  postDiagnosisMessage,
  resetDiagnosis,
} from "@/api/client";
import type { DiagnosisChat, Manuscript } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface DiagnosisCardProps {
  manuscript: Manuscript;
}

export function DiagnosisCard({ manuscript }: DiagnosisCardProps) {
  const { user } = useAuth();
  const enabled = user?.claude_api_enabled ?? false;

  const [chat, setChat] = useState<DiagnosisChat | null>(null);
  const [draft, setDraft] = useState("");
  const [includeSource, setIncludeSource] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clearDialogOpen, setClearDialogOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Load existing chat on mount / when the manuscript changes.
  useEffect(() => {
    let cancelled = false;
    getDiagnosis(manuscript.doi_suffix)
      .then((c) => {
        if (!cancelled) setChat(c);
      })
      .catch(() => {
        // Non-fatal — leave chat null and let the user start a new one.
      });
    return () => {
      cancelled = true;
    };
  }, [manuscript.doi_suffix]);

  // Scroll to the latest message after each update.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat?.messages.length]);

  const send = async (content: string) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await postDiagnosisMessage(
        manuscript.doi_suffix,
        content,
        includeSource,
      );
      setChat(updated);
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const confirmClear = async () => {
    setBusy(true);
    setError(null);
    try {
      await resetDiagnosis(manuscript.doi_suffix);
      setChat(null);
      setIncludeSource(true);
      setClearDialogOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const messages = chat?.messages ?? [];
  const hasMessages = messages.length > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-4 text-muted-foreground" />
          Ask Claude
        </CardTitle>
        <CardDescription>
          You can use this pane to ask Claude to dianose the log files and, if you allow, the source files.
          It knows about the CCR class file and author's guide, so should be able to give appropriate suggestions.
          It can give a general diagnosis of any warnings or errors, and you can also ask specific questions.
          <br />
          Please do be careful: these are Claude's guesses based on the source and the logs, verify before changing your source and always check the resulting proofs.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!enabled && (
          <p className="text-sm text-muted-foreground">
            Claude diagnosis is not enabled on this server (no
            <code className="mx-1">ANTHROPIC_API_KEY</code>set).
          </p>
        )}

        {enabled && hasMessages && (
          <div className="flex max-h-[480px] flex-col gap-3 overflow-y-auto rounded-md border bg-muted/30 p-3">
            {messages.map((m, i) => (
              <div
                key={i}
                className={
                  m.role === "user"
                    ? "self-end max-w-[85%] rounded-lg bg-primary px-3 py-2 text-primary-foreground whitespace-pre-wrap text-sm"
                    : "self-start max-w-[85%] rounded-lg bg-card ring-1 ring-foreground/10 px-3 py-2 whitespace-pre-wrap text-sm"
                }
              >
                {/* Hide the failure-context blob from the first user message —
                    it's just the logs the author already sees in the pipeline
                    card. Show a placeholder instead. */}
                {m.role === "user" && i === 0 && m.content.startsWith("Manuscript:")
                  ? <em className="text-primary-foreground/80">Diagnose this conversion</em>
                  : m.content}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}

        {enabled && (
          <div className="flex flex-col gap-2">
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={
                hasMessages
                  ? "Ask a follow-up…"
                  : "Ask Claude something specific, or leave blank for a general diagnosis…"
              }
              rows={3}
              disabled={busy}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  if (!hasMessages || draft.trim()) {
                    e.preventDefault();
                    send(draft.trim());
                  }
                }
              }}
            />
            {!hasMessages && (
              <div className="flex items-center gap-2">
                <Checkbox
                  id="diagnosis-include-source"
                  checked={includeSource}
                  onCheckedChange={(v) => setIncludeSource(v === true)}
                  disabled={busy}
                />
                <Label
                  htmlFor="diagnosis-include-source"
                  className="text-xs text-muted-foreground font-normal cursor-pointer"
                >
                  Include source files (recommended — lets Claude see the actual
                  LaTeX/Quarto, not just the logs)
                </Label>
              </div>
            )}
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                Up to 5 messages per day. ⌘/Ctrl+Enter to send.
              </p>
              <div className="flex gap-2">
                {hasMessages && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setClearDialogOpen(true)}
                    disabled={busy}
                  >
                    Clear conversation
                  </Button>
                )}
                <Button
                  type="button"
                  size={hasMessages ? "sm" : "default"}
                  onClick={() => send(draft.trim())}
                  disabled={busy || (hasMessages && !draft.trim())}
                >
                  {busy
                    ? hasMessages ? "Sending…" : "Diagnosing…"
                    : hasMessages
                      ? "Send"
                      : draft.trim()
                        ? "Ask Claude"
                        : "Diagnose this conversion"}
                </Button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}
      </CardContent>

      <Dialog
        open={clearDialogOpen}
        onOpenChange={(open) => { if (!busy) setClearDialogOpen(open); }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Clear conversation</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p>
              This deletes the entire diagnosis chat for this manuscript. The
              next time you click <em>Diagnose this conversion</em> a fresh
              chat will start.
            </p>
            <p>This cannot be undone. Are you sure?</p>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="outline"
              onClick={() => setClearDialogOpen(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmClear}
              disabled={busy}
            >
              {busy ? "Clearing…" : "Clear"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
