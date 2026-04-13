import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

interface UploadZoneProps {
  onUpload: (files: File[], fix: boolean) => Promise<void>;
}

export function UploadZone({ onUpload }: UploadZoneProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [fix, setFix] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((newFiles: FileList | File[]) => {
    setFiles((prev) => [...prev, ...Array.from(newFiles)]);
    setError(null);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles],
  );

  const handleSubmit = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      await onUpload(files, fix);
      setFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div
        className={`rounded-lg border-2 border-dashed p-8 text-center transition-colors cursor-pointer ${
          dragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <p className="text-sm text-muted-foreground">
          Drag files here or click to browse
        </p>
        <p className="text-xs text-muted-foreground/60 mt-1">
          Upload a .zip archive or individual files (.tex, .bib, images, etc.)
        </p>
      </div>

      {files.length > 0 && (
        <div className="space-y-3">
          <ul className="text-sm space-y-1">
            {files.map((f, i) => (
              <li key={i} className="flex items-center justify-between text-muted-foreground">
                <span>{f.name}</span>
                <button
                  className="text-xs text-red-500 hover:text-red-700"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFiles((prev) => prev.filter((_, j) => j !== i));
                  }}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="fix-source"
              checked={fix}
              onChange={(e) => setFix(e.target.checked)}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <Label htmlFor="fix-source" className="text-sm font-normal cursor-pointer">
              Apply source fixes before compiling
            </Label>
          </div>
          <Button onClick={handleSubmit} disabled={uploading}>
            {uploading ? "Uploading..." : `Upload ${files.length} file${files.length > 1 ? "s" : ""}`}
          </Button>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
