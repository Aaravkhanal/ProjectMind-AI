export interface HealthScore {
  overall: number;
  architecture: number;
  security: number;
  maintainability: number;
  code_quality: number;
  breakdown: {
    circular_dependencies: number;
    duplicate_functions: number;
    dead_functions: number;
    dead_classes: number;
    security_errors: number;
    security_warnings: number;
    high_complexity_functions: number;
    parse_errors: number;
  };
}

export interface GraphNode {
  id: string;
  kind: "file" | "function" | "class";
  name: string;
  loc?: number;
  centrality?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: "imports" | "defines" | "contains" | "inherits" | "references";
}

export interface KnowledgeGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta: {
    total_nodes: number;
    total_edges: number;
    has_cycles: boolean;
  };
}

export interface MemoryEntry {
  id: number;
  type: "decision" | "error" | "pattern" | "task";
  content: string;
  score?: number;
}

export interface AgentReview {
  architect_review: string;
  security_review: string;
  quality_review: string;
  final_review: string;
  errors: string[];
  posted_comment: boolean;
}

export interface ProjectDNA {
  language: string;
  frameworks: string[];
  architecture_pattern: string;
  database: string | null;
  auth_strategy: string | null;
  has_tests: boolean;
  test_framework: string | null;
  source_files: number;
  total_files: number;
}
