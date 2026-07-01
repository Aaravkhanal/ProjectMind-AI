"use client";

import { useCallback, useEffect, useRef } from "react";
import type { GraphEdge, GraphNode } from "@/lib/types";

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
}

const KIND_COLOR: Record<string, string> = {
  file:     "#0ea5e9",
  function: "#a78bfa",
  class:    "#34d399",
};

const EDGE_COLOR: Record<string, string> = {
  imports:    "#8b949e",
  defines:    "#a78bfa",
  contains:   "#34d399",
  inherits:   "#f59e0b",
  references: "#6b7280",
};

export function KnowledgeGraph({ nodes, edges, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || typeof window === "undefined") return;

    let fg: ReturnType<typeof import("react-force-graph-2d").default> | undefined;

    import("react-force-graph-2d").then((mod) => {
      const ForceGraph2D = mod.default;
      const { createRoot } = require("react-dom/client");
      const React = require("react");

      const graphData = {
        nodes: nodes.map((n) => ({ ...n, id: n.id })),
        links: edges.map((e) => ({ source: e.source, target: e.target, kind: e.kind })),
      };

      const root = createRoot(containerRef.current!);
      root.render(
        React.createElement(ForceGraph2D, {
          graphData,
          width: containerRef.current!.clientWidth,
          height: containerRef.current!.clientHeight,
          backgroundColor: "#0f1117",
          nodeColor: (n: GraphNode) => KIND_COLOR[n.kind] ?? "#8b949e",
          nodeRelSize: 5,
          nodeLabel: (n: GraphNode) => n.name,
          linkColor: (e: { kind: string }) => EDGE_COLOR[e.kind] ?? "#6b7280",
          linkOpacity: 0.4,
          linkWidth: 1,
          onNodeClick: (n: GraphNode) => onNodeClick?.(n),
          nodeCanvasObject: (
            n: GraphNode & { x?: number; y?: number },
            ctx: CanvasRenderingContext2D,
            globalScale: number
          ) => {
            const label = n.name.split("/").pop() ?? n.name;
            const fontSize = Math.max(10 / globalScale, 3);
            ctx.font = `${fontSize}px monospace`;
            ctx.fillStyle = KIND_COLOR[n.kind] ?? "#8b949e";
            ctx.beginPath();
            ctx.arc(n.x ?? 0, n.y ?? 0, 5 / globalScale, 0, 2 * Math.PI);
            ctx.fill();
            if (globalScale > 1.5) {
              ctx.fillStyle = "#e6edf3";
              ctx.fillText(label, (n.x ?? 0) + 6 / globalScale, (n.y ?? 0) + 2 / globalScale);
            }
          },
        })
      );
    });
  }, [nodes, edges, onNodeClick]);

  return <div ref={containerRef} className="w-full h-full" />;
}
