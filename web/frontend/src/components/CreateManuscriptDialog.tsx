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
import { createManuscript } from "@/api/client";
import type { Manuscript } from "@/api/types";

interface Props {
  onCreated: (ms: Manuscript) => void;
}

export function CreateManuscriptDialog({ onCreated }: Props) {
  const [open, setOpen] = useState(false);
  const [doiSuffix, setDoiSuffix] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!doiSuffix.trim() || !title.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const ms = await createManuscript({ doi_suffix: doiSuffix.trim(), title: title.trim() });
      setOpen(false);
      setDoiSuffix("");
      setTitle("");
      onCreated(ms);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create manuscript");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New Manuscript</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Manuscript</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="doi_suffix">DOI Suffix</Label>
            <Input
              id="doi_suffix"
              placeholder="CCR2025.1.2.YAO"
              value={doiSuffix}
              onChange={(e) => setDoiSuffix(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="title">Title</Label>
            <Input
              id="title"
              placeholder="Article title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Creating..." : "Create"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
