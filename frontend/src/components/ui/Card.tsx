import { type ReactNode } from "react";
import clsx from "clsx";

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}

export function Card({ title, children, className, action }: CardProps) {
  return (
    <div className={clsx(
      "rounded-lg border border-[#30363d] bg-[#161b22] p-5",
      className
    )}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-4">
          {title && <h3 className="text-sm font-semibold text-[#e6edf3]">{title}</h3>}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function StatRow({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-[#21262d] last:border-0">
      <span className="text-xs text-[#8b949e]">{label}</span>
      <span className="text-xs font-mono font-medium" style={{ color: color ?? "#e6edf3" }}>
        {value}
      </span>
    </div>
  );
}

export function Badge({ children, variant = "default" }: { children: ReactNode; variant?: "default" | "error" | "warn" | "ok" }) {
  const colors = {
    default: "bg-[#21262d] text-[#8b949e]",
    error:   "bg-red-900/30 text-red-400",
    warn:    "bg-amber-900/30 text-amber-400",
    ok:      "bg-green-900/30 text-green-400",
  };
  return (
    <span className={clsx("inline-flex items-center px-2 py-0.5 rounded text-xs font-medium", colors[variant])}>
      {children}
    </span>
  );
}
