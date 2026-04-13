import { useEffect, useRef } from "react";

export function LogViewer({ log }: { log: string }) {
  const ref = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [log]);

  if (!log) return null;

  return (
    <pre
      ref={ref}
      className="max-h-80 overflow-auto rounded-md border bg-muted p-4 text-sm font-mono whitespace-pre-wrap"
    >
      {log.split("\n").map((line, i) => {
        let color = "";
        if (line.startsWith("WARNING:")) color = "text-amber-600";
        else if (line.startsWith("ERROR:")) color = "text-red-600";
        return (
          <span key={i} className={color}>
            {line}
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}
