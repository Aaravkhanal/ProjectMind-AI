"use client";

import { RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis } from "recharts";

interface Props {
  score: number;
  label?: string;
  size?: number;
}

function scoreColor(s: number): string {
  if (s >= 8.5) return "#22c55e";
  if (s >= 7.0) return "#84cc16";
  if (s >= 5.0) return "#f59e0b";
  return "#ef4444";
}

function scoreLabel(s: number): string {
  if (s >= 8.5) return "Excellent";
  if (s >= 7.0) return "Good";
  if (s >= 5.0) return "Fair";
  return "Needs Work";
}

export function HealthGauge({ score, label = "Health Score", size = 180 }: Props) {
  const color = scoreColor(score);
  const data = [{ value: score * 10, fill: color }];

  return (
    <div className="flex flex-col items-center gap-2">
      <div style={{ width: size, height: size }} className="relative">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            cx="50%" cy="50%"
            innerRadius="65%" outerRadius="90%"
            startAngle={220} endAngle={-40}
            data={data}
          >
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar
              dataKey="value"
              cornerRadius={6}
              background={{ fill: "#21262d" }}
            />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold" style={{ color }}>
            {score.toFixed(1)}
          </span>
          <span className="text-xs text-[#8b949e]">/ 10</span>
        </div>
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-[#e6edf3]">{label}</p>
        <p className="text-xs font-medium" style={{ color }}>{scoreLabel(score)}</p>
      </div>
    </div>
  );
}
