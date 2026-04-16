import { useState } from "react";
import type { PipelineStep, StepStatus } from "@/api/types";
import { LogViewer } from "@/components/LogViewer";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const STEP_LABELS: Record<string, string> = {
  prepare: "Prepare",
  compile: "Compile",
  convert: "Convert",
  check: "Check",
  validate: "Validate",
};

const STATUS_STYLES: Record<StepStatus, { dot: string; text: string; label: string }> = {
  pending:  { dot: "bg-muted-foreground/40", text: "text-muted-foreground", label: "Pending" },
  running:  { dot: "bg-blue-500 animate-pulse", text: "text-blue-600", label: "Running" },
  ok:       { dot: "bg-green-500", text: "text-green-700", label: "OK" },
  warnings: { dot: "bg-amber-500", text: "text-amber-700", label: "Warnings" },
  errors:   { dot: "bg-orange-600", text: "text-orange-700", label: "Errors" },
  failed:   { dot: "bg-red-600", text: "text-red-700", label: "Failed" },
  skipped:  { dot: "bg-muted-foreground/30", text: "text-muted-foreground/60", label: "Skipped" },
};

function hasLog(step: PipelineStep): boolean {
  return step.logs.length > 0;
}

export function PipelineProgress({ steps }: { steps: PipelineStep[] }) {
  const [selectedStep, setSelectedStep] = useState<PipelineStep | null>(null);
  const [activeTab, setActiveTab] = useState(0);

  const openStep = (step: PipelineStep) => {
    setSelectedStep(step);
    setActiveTab(0);
  };

  return (
    <>
      <div className="flex items-center gap-1">
        {steps.map((step, i) => {
          const style = STATUS_STYLES[step.status];
          const clickable = hasLog(step);
          return (
            <div key={step.name} className="contents">
              {i > 0 && <div className="h-px flex-1 bg-border" />}
              <button
                type="button"
                onClick={() => clickable && openStep(step)}
                disabled={!clickable}
                className={`flex flex-col items-center gap-1.5 rounded-lg px-3 py-2 text-xs transition-colors ${
                  clickable
                    ? "cursor-pointer hover:bg-muted"
                    : "cursor-default"
                }`}
              >
                <div className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
                <span className="font-medium">
                  {STEP_LABELS[step.name] ?? step.name}
                </span>
                <span className={`text-[10px] ${style.text}`}>
                  {style.label}
                </span>
              </button>
            </div>
          );
        })}
      </div>

      <Dialog
        open={!!selectedStep}
        onOpenChange={(open) => { if (!open) setSelectedStep(null); }}
      >
        <DialogContent className="sm:max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {STEP_LABELS[selectedStep?.name ?? ""] ?? selectedStep?.name} Log
            </DialogTitle>
          </DialogHeader>

          {/* Tabs when multiple logs */}
          {selectedStep && selectedStep.logs.length > 1 && (
            <div className="flex gap-1 border-b">
              {selectedStep.logs.map((entry, i) => (
                <button
                  key={entry.name}
                  type="button"
                  onClick={() => setActiveTab(i)}
                  className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors ${
                    i === activeTab
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {entry.name}
                </button>
              ))}
            </div>
          )}

          <div className="flex-1 overflow-auto">
            {selectedStep && selectedStep.logs[activeTab] && (
              <LogViewer
                log={selectedStep.logs[activeTab].content}
                className="overflow-auto rounded-md border bg-muted p-4 text-sm font-mono whitespace-pre-wrap"
              />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
