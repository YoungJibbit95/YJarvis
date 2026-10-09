import { useMemo } from "react";
import { motion } from "motion/react";

export type AssistantMode = "idle" | "thinking" | "speaking";

type ArcReactorProps = {
  mode: AssistantMode;
  motionIntensity?: number;
  lowMotion?: boolean;
  variant?: "full" | "backdrop";
  className?: string;
};

type StatusKind = "idle" | "thinking" | "speaking";

type ModeConfig = {
  color: string;
  ringDuration: number;
  pulseDuration: number;
  coreScale: [number, number, number];
  arcOpacity: [number, number, number];
  arcWidth: [number, number, number];
  particleCount: number;
  haloOpacity: number;
  title: string;
  shellX: number[];
  shellY: number[];
  shellRotate: number[];
  statusKind: StatusKind;
  statusLabel: string;
  statusX: number[];
  statusY: number[];
  signalCount: number;
  signalDuration: number;
};

type StatusGlyphProps = {
  kind: StatusKind;
  color: string;
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function StatusGlyph({ kind, color }: StatusGlyphProps) {
  if (kind === "speaking") {
    return (
      <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
        <path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8l-4 3v-3H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" fill="none" stroke={color} strokeWidth="1.8" />
      </svg>
    );
  }

  if (kind === "thinking") {
    return (
      <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
        <circle cx="9" cy="11" r="4.2" fill="none" stroke={color} strokeWidth="1.8" />
        <circle cx="14.5" cy="10" r="3.2" fill="none" stroke={color} strokeWidth="1.8" />
        <circle cx="6" cy="16.5" r="1.2" fill="none" stroke={color} strokeWidth="1.8" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
      <text x="2" y="9" fill={color} fontSize="7" fontFamily="monospace">
        Z
      </text>
      <text x="9" y="13" fill={color} fontSize="6" fontFamily="monospace">
        Z
      </text>
      <text x="14" y="18" fill={color} fontSize="5" fontFamily="monospace">
        Z
      </text>
    </svg>
  );
}

const MODE_CONFIG: Record<AssistantMode, ModeConfig> = {
  idle: {
    color: "#5fa7ff",
    ringDuration: 42,
    pulseDuration: 4.2,
    coreScale: [1, 1.03, 1],
    arcOpacity: [0.2, 0.45, 0.2],
    arcWidth: [2.4, 3.2, 2.4],
    particleCount: 8,
    haloOpacity: 0.24,
    title: "Standby",
    shellX: [0, 1.5, 0, -1.5, 0],
    shellY: [0, -1, 0, 1, 0],
    shellRotate: [0, 0.25, 0, -0.25, 0],
    statusKind: "idle",
    statusLabel: "Idle",
    statusX: [0, 10, 0, -10, 0],
    statusY: [-104, -116, -106, -118, -104],
    signalCount: 10,
    signalDuration: 2.8
  },
  thinking: {
    color: "#00d8ff",
    ringDuration: 28,
    pulseDuration: 2.5,
    coreScale: [1, 1.08, 1],
    arcOpacity: [0.3, 0.78, 0.3],
    arcWidth: [2.8, 4.4, 2.8],
    particleCount: 13,
    haloOpacity: 0.33,
    title: "Thinking",
    shellX: [0, 3, -2, 1, 0],
    shellY: [0, -2, 1, -1, 0],
    shellRotate: [0, 1.2, -0.8, 0.4, 0],
    statusKind: "thinking",
    statusLabel: "Thinking",
    statusX: [0, 20, 8, -14, 0],
    statusY: [-100, -122, -110, -126, -100],
    signalCount: 16,
    signalDuration: 2.15
  },
  speaking: {
    color: "#00fff2",
    ringDuration: 15,
    pulseDuration: 1.35,
    coreScale: [1, 1.17, 1],
    arcOpacity: [0.48, 1, 0.48],
    arcWidth: [3.2, 5.5, 3.2],
    particleCount: 22,
    haloOpacity: 0.48,
    title: "Speaking",
    shellX: [0, 5, -4, 3, -2, 0],
    shellY: [0, -4, 2, -3, 1, 0],
    shellRotate: [0, 2.4, -1.8, 1.2, -0.6, 0],
    statusKind: "speaking",
    statusLabel: "Speaking",
    statusX: [0, 26, 10, -18, -4, 0],
    statusY: [-96, -120, -102, -124, -108, -96],
    signalCount: 22,
    signalDuration: 1.45
  }
};

export default function ArcReactor({
  mode,
  motionIntensity = 1,
  lowMotion = false,
  variant = "full",
  className
}: ArcReactorProps) {
  const config = MODE_CONFIG[mode];
  const intensity = clamp(Number(motionIntensity) || 1, 0.6, 1.8);
  const speedFactor = 1 / intensity;
  const isBackdrop = variant === "backdrop";

  const stars = useMemo(
    () =>
      Array.from({ length: 24 }, (_, index) => ({
        id: index,
        cx: (index * 17) % 100,
        cy: (index * 29) % 100,
        r: index % 3 === 0 ? 0.26 : 0.18
      })),
    []
  );

  const particles = useMemo(() => Array.from({ length: config.particleCount }, (_, index) => index), [config.particleCount]);
  const signalNodes = useMemo(() => Array.from({ length: config.signalCount }, (_, index) => index), [config.signalCount]);
  const floatNodes = useMemo(() => Array.from({ length: 2 }, (_, index) => index), []);

  if (lowMotion) {
    return (
      <div
        className={[
          "relative flex items-center justify-center space-grid",
          isBackdrop ? "h-[300px] w-[300px] lg:h-[340px] lg:w-[340px]" : "h-[340px] w-[340px] lg:h-[380px] lg:w-[380px]",
          className || ""
        ].join(" ")}
      >
        <div className="absolute inset-0">
          <svg viewBox="0 0 100 100" className="h-full w-full opacity-40">
            {stars.map((star) => (
              <circle key={star.id} cx={star.cx} cy={star.cy} r={star.r} fill="white" />
            ))}
          </svg>
        </div>
        <div
          className="absolute inset-[12%] rounded-full border border-jarvis-cyan/20"
          style={{ boxShadow: `inset 0 0 24px ${config.color}22` }}
        />
        <div
          className="absolute inset-[22%] rounded-full border border-jarvis-cyan/25"
          style={{ boxShadow: `inset 0 0 16px ${config.color}30` }}
        />
        <div
          className="relative z-20 flex h-[6.5rem] w-[6.5rem] items-center justify-center rounded-full border-2 bg-black/30 backdrop-blur-sm"
          style={{ borderColor: `${config.color}66` }}
        >
          <div className="h-9 w-9 rounded-full bg-white" style={{ boxShadow: `0 0 26px 8px #fff, 0 0 44px 12px ${config.color}` }} />
        </div>
        {!isBackdrop ? (
          <div
            className="pointer-events-none absolute z-30 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.2em]"
            style={{
              borderColor: `${config.color}70`,
              color: config.color,
              background: `${config.color}1a`
            }}
          >
            <StatusGlyph kind={config.statusKind} color={config.color} />
            <span>{config.statusLabel}</span>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div
      className={[
        "relative flex items-center justify-center space-grid",
        isBackdrop ? "h-[300px] w-[300px] lg:h-[340px] lg:w-[340px]" : "h-[340px] w-[340px] lg:h-[380px] lg:w-[380px]",
        className || ""
      ].join(" ")}
    >
      <motion.div
        className="absolute inset-0"
        animate={{ rotate: 360, opacity: [0.15, 0.25, 0.15] }}
        transition={{
          rotate: { duration: 120 * speedFactor, repeat: Infinity, ease: "linear" },
          opacity: { duration: 6 * speedFactor, repeat: Infinity }
        }}
      >
        <svg viewBox="0 0 100 100" className="h-full w-full">
          {stars.map((star) => (
            <circle key={star.id} cx={star.cx} cy={star.cy} r={star.r} fill="white" />
          ))}
          <path d="M 20 20 L 40 30 L 30 50 Z" fill="none" stroke="white" strokeWidth="0.1" />
          <path d="M 70 10 L 80 40 L 60 30 Z" fill="none" stroke="white" strokeWidth="0.1" />
        </svg>
      </motion.div>

      <motion.div
        className="absolute inset-0 flex items-center justify-center"
        animate={{ x: config.shellX, y: config.shellY, rotate: config.shellRotate, scale: [1, 1.01, 1] }}
        transition={{
          duration: (mode === "speaking" ? 1.6 : mode === "thinking" ? 2.3 : 3.8) * speedFactor,
          repeat: Infinity,
          ease: "easeInOut"
        }}
      >
        {[0, 1, 2].map((index) => (
          <motion.div
            key={index}
            className="absolute rounded-full border border-jarvis-cyan/15"
            style={{
              width: `${100 - index * 14}%`,
              height: `${100 - index * 14}%`,
              boxShadow: index === 0 ? `inset 0 0 40px ${config.color}20` : "none"
            }}
            animate={{ rotate: index % 2 === 0 ? 360 : -360 }}
            transition={{ duration: (config.ringDuration + index * 8) * speedFactor, repeat: Infinity, ease: "linear" }}
          >
            <div className="absolute left-1/2 top-0 h-3 w-1 -translate-x-1/2" style={{ backgroundColor: `${config.color}99` }} />
          </motion.div>
        ))}

        {particles.map((particle) => (
          <motion.div
            key={particle}
            className="absolute h-1 w-1 rounded-full"
            style={{
              backgroundColor: config.color,
              boxShadow: `0 0 10px ${config.color}`,
              transformOrigin: "190px 190px"
            }}
            animate={{ rotate: [particle * 18, particle * 18 + 360], scale: [0, 1, 0], opacity: [0, 0.9, 0] }}
            transition={{
              duration: (mode === "speaking" ? 2.2 : mode === "thinking" ? 3 : 4.7) * speedFactor,
              repeat: Infinity,
              delay: particle * 0.095,
              ease: "easeInOut"
            }}
          />
        ))}

        {signalNodes.map((node) => (
          <motion.div
            key={`signal-${node}`}
            className="absolute left-1/2 top-1/2 w-[2px] rounded-full"
            style={{
              height: mode === "speaking" ? "5.8rem" : mode === "thinking" ? "4.8rem" : "4rem",
              background: `linear-gradient(to top, transparent 0%, ${config.color}cc 55%, transparent 100%)`,
              transform: `translate(-50%, -100%) rotate(${(360 / config.signalCount) * node}deg)`,
              transformOrigin: "50% 100%"
            }}
            animate={{
              scaleY: mode === "speaking" ? [0.35, 1.8, 0.45] : mode === "thinking" ? [0.3, 1.35, 0.35] : [0.2, 0.95, 0.2],
              opacity: mode === "speaking" ? [0.12, 0.82, 0.2] : mode === "thinking" ? [0.08, 0.58, 0.12] : [0.04, 0.25, 0.05]
            }}
            transition={{
              duration: config.signalDuration * speedFactor,
              repeat: Infinity,
              delay: node * (mode === "speaking" ? 0.035 : 0.055),
              ease: "easeInOut"
            }}
          />
        ))}

        <motion.svg
          viewBox="0 0 100 100"
          className="relative z-10 h-60 w-60 lg:h-[17rem] lg:w-[17rem]"
          animate={{ rotate: -360 }}
          transition={{
            duration: (mode === "speaking" ? 12 : mode === "thinking" ? 18 : 25) * speedFactor,
            repeat: Infinity,
            ease: "linear"
          }}
        >
          <defs>
            <linearGradient id="arcGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={config.color} stopOpacity="0.18" />
              <stop offset="50%" stopColor={config.color} stopOpacity="1" />
              <stop offset="100%" stopColor={config.color} stopOpacity="0.18" />
            </linearGradient>
          </defs>

          {Array.from({ length: 12 }, (_, index) => (
            <motion.g key={index} style={{ transformOrigin: "50px 50px", rotate: index * 30 }}>
              <motion.path
                d="M 50 10 A 40 40 0 0 1 75 22"
                fill="none"
                stroke="url(#arcGrad)"
                strokeLinecap="round"
                animate={{ opacity: config.arcOpacity, strokeWidth: config.arcWidth }}
                transition={{ duration: config.pulseDuration * speedFactor, repeat: Infinity, delay: index * 0.06 }}
              />
              <circle cx="50" cy="10" r="1.5" fill="white" className="shadow-[0_0_8px_#fff]" />
            </motion.g>
          ))}
        </motion.svg>

        <motion.div
          className="absolute z-20 flex h-[10.5rem] w-[10.5rem] items-center justify-center rounded-full"
          style={{ background: `radial-gradient(circle, ${config.color}55 0%, transparent 72%)`, opacity: config.haloOpacity }}
          animate={{ scale: [1, 1.06, 1], opacity: [config.haloOpacity * 0.75, config.haloOpacity, config.haloOpacity * 0.75] }}
          transition={{ duration: config.pulseDuration * speedFactor, repeat: Infinity, ease: "easeInOut" }}
        >
          <motion.div
            className="relative flex h-[6.5rem] w-[6.5rem] items-center justify-center rounded-full border-2 bg-black/25 backdrop-blur-sm"
            style={{ borderColor: `${config.color}66` }}
            animate={{ scale: config.coreScale, rotate: 360 }}
            transition={{
              scale: { duration: config.pulseDuration * speedFactor, repeat: Infinity, ease: "easeInOut" },
              rotate: {
                duration: (mode === "speaking" ? 15 : mode === "thinking" ? 28 : 50) * speedFactor,
                repeat: Infinity,
                ease: "linear"
              }
            }}
          >
            <div className="h-9 w-9 rounded-full bg-white" style={{ boxShadow: `0 0 30px 10px #fff, 0 0 52px 16px ${config.color}` }} />
            <div className="absolute inset-2 rounded-full border border-white/20" />
            <div className="absolute inset-6 rounded-full border border-dashed border-white/15" />
          </motion.div>
        </motion.div>
      </motion.div>

      {!isBackdrop ? (
        <>
          <motion.div
            className="pointer-events-none absolute z-30 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1"
            style={{
              borderColor: `${config.color}88`,
              color: config.color,
              background: `${config.color}1a`,
              boxShadow: `0 0 18px ${config.color}55`
            }}
            animate={{ x: config.statusX, y: config.statusY, rotate: [-8, 6, -4, 8, -8], opacity: [0.55, 1, 0.6] }}
            transition={{
              duration: (mode === "speaking" ? 2.2 : mode === "thinking" ? 3.1 : 4.5) * speedFactor,
              repeat: Infinity,
              ease: "easeInOut"
            }}
          >
            <StatusGlyph kind={config.statusKind} color={config.color} />
            <span className="font-mono text-[9px] uppercase tracking-[0.2em]">{config.statusLabel}</span>
          </motion.div>

          {floatNodes.map((node) => (
            <motion.div
              key={`float-node-${node}`}
              className="pointer-events-none absolute z-30 rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.16em]"
              style={{
                borderColor: `${config.color}55`,
                color: `${config.color}dd`,
                background: `${config.color}14`,
                boxShadow: `0 0 12px ${config.color}3a`
              }}
              animate={{
                x: node === 0 ? [-124, -104, -124] : [122, 104, 122],
                y: node === 0 ? [72, 58, 72] : [76, 64, 76],
                scale: [0.9, 1.1, 0.9],
                opacity: [0.35, 0.85, 0.35]
              }}
              transition={{
                duration:
                  (mode === "speaking" ? 1.6 + node * 0.3 : mode === "thinking" ? 2.2 + node * 0.4 : 3 + node * 0.5) *
                  speedFactor,
                repeat: Infinity,
                ease: "easeInOut",
                delay: node * 0.3
              }}
            >
              {mode === "speaking" ? "voice" : mode === "thinking" ? "logic" : "sleep"}
            </motion.div>
          ))}

          <motion.div
            className="absolute left-0 top-0 font-mono text-[8px] uppercase tracking-[0.28em] text-jarvis-cyan/45"
            animate={{ y: [0, -10, 0], opacity: [0.4, 0.9, 0.4] }}
            transition={{ duration: 3.5 * speedFactor, repeat: Infinity }}
          >
            Mode: {config.title}
          </motion.div>
          <motion.div
            className="absolute bottom-0 right-0 font-mono text-[8px] uppercase tracking-[0.28em] text-jarvis-cyan/45"
            animate={{ y: [0, 8, 0], opacity: [0.4, 0.9, 0.4] }}
            transition={{ duration: 3.5 * speedFactor, repeat: Infinity, delay: 0.8 * speedFactor }}
          >
            Flux: {mode === "speaking" ? "High" : mode === "thinking" ? "Adaptive" : "Nominal"}
          </motion.div>
        </>
      ) : null}
    </div>
  );
}
