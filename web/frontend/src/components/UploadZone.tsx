import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

interface UploadZoneProps {
  onUpload: (files: File[]) => Promise<void>;
}

// Extend HTMLInputElement attributes to allow webkitdirectory (not in TS DOM types)
declare module "react" {
  interface InputHTMLAttributes<T> {
    webkitdirectory?: string;
    directory?: string;
  }
}

export function UploadZone({ onUpload }: UploadZoneProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listExpanded, setListExpanded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

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

  const openPicker = (ref: React.RefObject<HTMLInputElement | null>) => {
    // Reset before opening so picking the same files again still fires onChange
    if (ref.current) {
      ref.current.value = "";
      ref.current.click();
    }
  };

  const handleSubmit = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      await onUpload(files);
      setFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const paths = files.map(
    (f) => (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name,
  );
  const topDirs = new Set(
    paths.filter((p) => p.includes("/")).map((p) => p.split("/", 1)[0]),
  );
  const rootFiles = paths.filter((p) => !p.includes("/"));
  const folderName =
    topDirs.size === 1 && rootFiles.length === 0 ? [...topDirs][0] : null;
  const isSingleZip =
    files.length === 1 && files[0].name.toLowerCase().endsWith(".zip");
  const summary = isSingleZip
    ? `zip archive: ${files[0].name}`
    : folderName
    ? `${files.length} file${files.length > 1 ? "s" : ""} from folder "${folderName}"`
    : `${files.length} file${files.length > 1 ? "s" : ""} selected`;

  return (
    <div className="space-y-3">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files) addFiles(e.target.files);
        }}
      />
      <input
        ref={folderInputRef}
        type="file"
        webkitdirectory=""
        directory=""
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files) addFiles(e.target.files);
        }}
      />

      <div
        className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
          dragging ? "border-primary bg-primary/5" : "border-muted-foreground/25"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <p className="text-sm text-muted-foreground mb-3">
          Drag files or a folder here
        </p>
        <div className="flex justify-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => openPicker(fileInputRef)}
          >
            Choose files
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => openPicker(folderInputRef)}
          >
            Choose folder
          </Button>
        </div>
        <p className="text-xs text-muted-foreground/60 mt-3">
          Upload a .zip archive, a folder, or individual files (.tex, .bib, images, etc.)
        </p>
      </div>

      {files.length > 0 && (
        <div className="space-y-3">
          <div className="rounded-md border bg-muted/50 overflow-hidden">
            <div className="flex items-center justify-between gap-2 px-3 py-2">
              <button
                type="button"
                className="flex items-center gap-1 text-sm font-medium hover:text-foreground min-w-0 flex-1 text-left"
                onClick={() => setListExpanded((v) => !v)}
              >
                <span className="text-xs text-muted-foreground shrink-0">
                  {listExpanded ? "▾" : "▸"}
                </span>
                <span className="truncate">{summary}</span>
              </button>
              <button
                type="button"
                className="text-xs text-red-500 hover:text-red-700 shrink-0"
                onClick={() => setFiles([])}
              >
                Clear
              </button>
            </div>
            {listExpanded && (
              <ul className="max-h-40 overflow-auto border-t px-3 py-2 text-xs space-y-1">
                {files.map((f, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between gap-2 text-muted-foreground"
                  >
                    <span className="truncate min-w-0 flex-1">{paths[i]}</span>
                    <button
                      type="button"
                      className="text-xs text-red-500 hover:text-red-700 shrink-0"
                      onClick={() =>
                        setFiles((prev) => prev.filter((_, j) => j !== i))
                      }
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <Button onClick={handleSubmit} disabled={uploading}>
            {uploading
              ? "Uploading..."
              : `Upload ${files.length} file${files.length > 1 ? "s" : ""}`}
          </Button>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
