/**
 * VoiceBubble — the ChatGPT / Gemini-Live-style reactive blob.
 *
 * Renders a stack of concentric SVG circles whose radii are driven by a
 * normalised amplitude value (0–1) supplied by the parent. The parent
 * (`VoiceRoom`) runs a WebAudio `AnalyserNode` on the local mic and the
 * remote agent audio track and pushes the louder of the two — gated by
 * the current `state` — into `amplitude`.
 *
 * Visual states:
 *   idle      — gentle breathing, gray
 *   listening — reacts to *user* mic, cyan
 *   thinking  — pulse (no audio yet), violet
 *   speaking  — reacts to *agent* TTS, emerald
 *   error     — static red
 *
 * The bubble has zero dependencies beyond framer-motion (already in the
 * project). It's intentionally self-contained so it can be dropped into
 * any voice UI.
 */

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { useEffect } from "react";

export type BubbleState =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

interface Props {
  state: BubbleState;
  /** Normalised 0..1 amplitude. Ignored in `idle` / `thinking` / `error`. */
  amplitude: number;
  /** Pixel diameter of the outer bubble. */
  size?: number;
  /** Optional label rendered under the bubble. */
  label?: string;
}

const STATE_COLORS: Record<BubbleState, { core: string; ring: string; glow: string }> = {
  idle:      { core: "#475569", ring: "#94a3b8", glow: "#334155" },
  listening: { core: "#06b6d4", ring: "#67e8f9", glow: "#0891b2" },
  thinking:  { core: "#8b5cf6", ring: "#c4b5fd", glow: "#6d28d9" },
  speaking:  { core: "#10b981", ring: "#6ee7b7", glow: "#047857" },
  error:     { core: "#ef4444", ring: "#fca5a5", glow: "#b91c1c" },
};

export function VoiceBubble({ state, amplitude, size = 240, label }: Props) {
  // Spring-smooth the amplitude so the bubble doesn't jitter on every frame.
  const raw = useMotionValue(0);
  const smoothed = useSpring(raw, { stiffness: 200, damping: 25, mass: 0.4 });

  useEffect(() => {
    // Idle / thinking / error don't read amplitude — drive a synthetic
    // breathing wave instead.
    if (state === "listening" || state === "speaking") {
      raw.set(Math.min(1, Math.max(0, amplitude)));
    }
  }, [amplitude, state, raw]);

  // Synthetic breathing for non-audio-reactive states.
  useEffect(() => {
    if (state === "listening" || state === "speaking") return;
    let cancelled = false;
    let t = 0;
    const tick = () => {
      if (cancelled) return;
      t += 0.04;
      const wave =
        state === "thinking"
          ? 0.35 + 0.25 * Math.sin(t * 3.0)   // faster pulse while thinking
          : 0.10 + 0.07 * Math.sin(t * 1.2);  // gentle breath when idle
      raw.set(wave);
      requestAnimationFrame(tick);
    };
    const id = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(id);
    };
  }, [state, raw]);

  const colors = STATE_COLORS[state];

  // Derived radii: core grows with amplitude, rings expand further out.
  const baseR = size * 0.18;
  const coreR    = useTransform(smoothed, (a) => baseR + a * size * 0.18);
  const ring1R   = useTransform(smoothed, (a) => baseR + a * size * 0.30 + size * 0.05);
  const ring2R   = useTransform(smoothed, (a) => baseR + a * size * 0.42 + size * 0.12);
  const glowR    = useTransform(smoothed, (a) => baseR + a * size * 0.55 + size * 0.18);
  const glowAlpha = useTransform(smoothed, (a) => 0.10 + a * 0.45);

  return (
    <div className="flex flex-col items-center gap-3 select-none">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="overflow-visible"
      >
        {/* Outer glow */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={glowR}
          fill={colors.glow}
          style={{ opacity: glowAlpha as unknown as number }}
        />
        {/* Outer ring */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={ring2R}
          fill={colors.ring}
          opacity={0.18}
        />
        {/* Mid ring */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={ring1R}
          fill={colors.ring}
          opacity={0.32}
        />
        {/* Core */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={coreR}
          fill={colors.core}
        />
        {/* Highlight */}
        <motion.circle
          cx={size / 2 - size * 0.05}
          cy={size / 2 - size * 0.05}
          r={useTransform(coreR, (r) => r * 0.35)}
          fill="white"
          opacity={0.22}
        />
      </svg>
      {label && (
        <span className="text-xs uppercase tracking-widest text-slate-400">
          {label}
        </span>
      )}
    </div>
  );
}

export default VoiceBubble;
