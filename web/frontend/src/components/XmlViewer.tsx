import { useState, useCallback } from "react";

function Tag({ children }: { children: string }) {
  return <span className="text-blue-600 dark:text-blue-400">{children}</span>;
}

function Bracket({ children }: { children: React.ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>;
}

function Attrs({ attrs }: { attrs: Attr[] }) {
  if (attrs.length === 0) return null;
  return (
    <>
      {attrs.map((a, i) => (
        <span key={i}>
          {" "}
          <span className="text-amber-700 dark:text-amber-400">{a.name}</span>
          <span className="text-muted-foreground">=</span>
          <span className="text-green-700 dark:text-green-400">"{a.value}"</span>
        </span>
      ))}
    </>
  );
}

interface XmlViewerProps {
  xml: string;
}

export function XmlViewer({ xml }: XmlViewerProps) {
  const [expandAll, setExpandAll] = useState(false);
  const [key, setKey] = useState(0);

  const toggleAll = useCallback(() => {
    setExpandAll((v) => !v);
    setKey((k) => k + 1);
  }, []);

  const parser = new DOMParser();
  const doc = parser.parseFromString(xml, "application/xml");
  const parseError = doc.querySelector("parsererror");

  if (parseError) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-red-600">Failed to parse XML</p>
        <pre className="overflow-auto whitespace-pre-wrap rounded-md border bg-muted p-4 text-sm font-mono">
          {xml}
        </pre>
      </div>
    );
  }

  // Render processing instructions (like <?xml version="1.0"?>)
  const pis: string[] = [];
  for (const child of Array.from(doc.childNodes)) {
    if (child.nodeType === Node.PROCESSING_INSTRUCTION_NODE) {
      const pi = child as ProcessingInstruction;
      pis.push(`<?${pi.target} ${pi.data}?>`);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={toggleAll}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          {expandAll ? "Collapse all" : "Expand all"}
        </button>
      </div>
      <div className="overflow-auto rounded-md border bg-background p-4 text-sm font-mono">
        {pis.map((pi, i) => (
          <div key={i} className="leading-6 text-muted-foreground">{pi}</div>
        ))}
        {doc.documentElement && (
          <XmlNodeControlled
            key={key}
            node={doc.documentElement}
            depth={0}
            defaultExpanded={expandAll}
          />
        )}
      </div>
    </div>
  );
}

// Tags whose subtrees should be expanded by default.
const AUTO_EXPAND_TAGS = new Set(["article", "front", "article-meta"]);

/** Version of XmlNode that respects a defaultExpanded prop for expand/collapse all. */
function XmlNodeControlled({
  node,
  depth = 0,
  defaultExpanded = false,
}: {
  node: Element;
  depth?: number;
  defaultExpanded?: boolean;
}) {
  const autoExpand = AUTO_EXPAND_TAGS.has(node.tagName);
  const [collapsed, setCollapsed] = useState(
    defaultExpanded || autoExpand ? false : depth > 2,
  );

  const children = Array.from(node.childNodes);
  const elementChildren = children.filter((c) => c.nodeType === Node.ELEMENT_NODE);
  const hasElementChildren = elementChildren.length > 0;
  const textOnly =
    !hasElementChildren &&
    children.length > 0 &&
    children.every((c) => c.nodeType === Node.TEXT_NODE || c.nodeType === Node.COMMENT_NODE);

  const attrs = Array.from(node.attributes);
  const tagName = node.tagName;
  const indent = depth * 20;

  if (textOnly) {
    const text = node.textContent ?? "";
    return (
      <div className="leading-6 hover:bg-muted/50" style={{ paddingLeft: indent }}>
        <Bracket>&lt;</Bracket>
        <Tag>{tagName}</Tag>
        <Attrs attrs={attrs} />
        <Bracket>&gt;</Bracket>
        <span className="text-foreground break-all">{text}</span>
        <Bracket>&lt;/</Bracket>
        <Tag>{tagName}</Tag>
        <Bracket>&gt;</Bracket>
      </div>
    );
  }

  if (children.length === 0) {
    return (
      <div className="leading-6 hover:bg-muted/50" style={{ paddingLeft: indent }}>
        <Bracket>&lt;</Bracket>
        <Tag>{tagName}</Tag>
        <Attrs attrs={attrs} />
        <Bracket>/&gt;</Bracket>
      </div>
    );
  }

  return (
    <div>
      <div
        className="leading-6 hover:bg-muted/50 cursor-pointer select-none"
        style={{ paddingLeft: indent }}
        onClick={() => setCollapsed((v) => !v)}
      >
        <span className="inline-block w-4 text-center text-muted-foreground text-xs">
          {hasElementChildren ? (collapsed ? "▸" : "▾") : ""}
        </span>
        <Bracket>&lt;</Bracket>
        <Tag>{tagName}</Tag>
        <Attrs attrs={attrs} />
        <Bracket>&gt;</Bracket>
        {collapsed && (
          <>
            <span className="text-muted-foreground">{"\u2026"}</span>
            <Bracket>&lt;/</Bracket>
            <Tag>{tagName}</Tag>
            <Bracket>&gt;</Bracket>
          </>
        )}
      </div>
      {!collapsed && (
        <>
          {children.map((child, i) => {
            if (child.nodeType === Node.ELEMENT_NODE) {
              return (
                <XmlNodeControlled
                  key={i}
                  node={child as Element}
                  depth={depth + 1}
                  defaultExpanded={defaultExpanded}
                />
              );
            }
            if (child.nodeType === Node.COMMENT_NODE) {
              return (
                <div
                  key={i}
                  className="leading-6 text-muted-foreground italic"
                  style={{ paddingLeft: (depth + 1) * 20 }}
                >
                  &lt;!-- {child.textContent} --&gt;
                </div>
              );
            }
            const text = child.textContent?.trim();
            if (text) {
              return (
                <div
                  key={i}
                  className="leading-6 text-foreground break-words"
                  style={{ paddingLeft: (depth + 1) * 20 }}
                >
                  {text}
                </div>
              );
            }
            return null;
          })}
          <div className="leading-6 hover:bg-muted/50" style={{ paddingLeft: indent }}>
            <span className="inline-block w-4" />
            <Bracket>&lt;/</Bracket>
            <Tag>{tagName}</Tag>
            <Bracket>&gt;</Bracket>
          </div>
        </>
      )}
    </div>
  );
}
