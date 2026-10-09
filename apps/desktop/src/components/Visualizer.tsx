import { motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import type { AssistantMode } from "./ArcReactor";

type VisualizerProps = {
  mode: AssistantMode;
  lowMotion?: boolean;
};

const BAR_COUNT = 20;

export default function Visualizer({ mode, lowMotion = false }: VisualizerProps) {
  const [bars, setBars] = useState<number[]>(() => Array.from({ length: BAR_COUNT }, () => 20));

  useEffect(() => {
    if (lowMotion && mode === "idle") {
      setBars(Array.from({ length: BAR_COUNT }, () => 18));
      return;
    }

    const intervalMs = lowMotion
      ? mode === "speaking"
        ? 120
        : mode === "thinking"
          ? 160
          : 220
      : mode === "speaking"
        ? 90
        : mode === "thinking"
          ? 130
          : 180;
    const interval = window.setInterval(() => {
      setBars(
        Array.from({ length: BAR_COUNT }, () => {
          if (mode === "idle") {
            return 12 + Math.random() * 30;
          }
          if (mode === "thinking") {
            return 20 + Math.random() * 60;
          }
          return 28 + Math.random() * 72;
        })
      );
    }, intervalMs);

    return () => {
      window.clearInterval(interval);
    };
  }, [mode, lowMotion]);

  const opacity = useMemo(() => (mode === "speaking" ? "opacity-90" : mode === "thinking" ? "opacity-80" : "opacity-60"), [mode]);

  return (
    <div className="flex h-16 items-end justify-between gap-1 px-1">
      {bars.map((height, i) => (
        <motion.div
          key={i}
          className={`w-full rounded-t-sm bg-gradient-to-t from-jarvis-blue to-jarvis-cyan ${opacity}`}
          animate={{ height: `${height}%` }}
          transition={lowMotion ? { type: "tween", duration: 0.24, ease: "easeOut" } : { type: "spring", stiffness: 280, damping: 20 }}
        />
      ))}
    </div>
  );
}
