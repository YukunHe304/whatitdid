import { phaseColor, type Turn } from "../api";

/** The run as a trace, read left to right.
 *
 * One tick per step. Colour says what the step was doing; height says how sure the
 * labeler was, so a run full of ambiguous steps looks visibly ragged instead of being
 * rounded up into a clean bar chart. A red foot means a finding points at that step.
 */
/** Findings worth a mark on the trace. `plumbing` and `drift` routinely cover half a run,
 *  so marking them would turn the whole ribbon red and mean nothing. */
const MARKED = new Set(["waste", "unverified_change"]);

export function Ribbon({
  turns,
  phases,
  selected,
  onSelect,
  animate = true,
  tickWidth,
}: {
  turns: Turn[];
  phases: string[];
  selected?: number | null;
  onSelect?: (turn: number) => void;
  animate?: boolean;
  /** Pixels per step. Set it when several runs are stacked: a fixed tick width is what
   *  makes a longer run a physically longer trace, which is the whole point of stacking
   *  them. Leave it off for a single run, which should fill the width it is given. */
  tickWidth?: number;
}) {
  return (
    <div className={`ribbon${animate ? " draw" : ""}`}>
      {turns.map((t, i) => {
        const confidence = t.top_p ?? 0.5;
        const flagged = t.marks.some((m) => MARKED.has(m));
        return (
          <button
            key={t.turn}
            className={`tick${flagged ? " flagged" : ""}`}
            aria-current={selected === t.turn}
            aria-label={`step ${t.turn}`}
            onClick={() => onSelect?.(t.turn)}
            style={{
              height: `${28 + confidence * 72}%`,
              background: phaseColor(t.top ?? "other", phases),
              animationDelay: animate ? `${Math.min(i * 5, 700)}ms` : undefined,
              ...(tickWidth ? { flex: "0 0 auto", width: `${tickWidth}px` } : null),
            }}
            title={`${t.turn}. ${t.command || t.tool || ""}`}
          />
        );
      })}
    </div>
  );
}

export function Legend({
  phases,
  mix,
  names,
}: {
  phases: string[];
  mix?: Record<string, number>;
  names: Record<string, string>;
}) {
  const shown = mix ? phases.filter((p) => (mix[p] ?? 0) >= 0.02) : phases;
  return (
    <div className="legend">
      {shown.map((p) => (
        <span key={p}>
          <i style={{ background: phaseColor(p, phases) }} />
          {names[p] ?? p}
          {mix ? ` ${Math.round((mix[p] ?? 0) * 100)}%` : ""}
        </span>
      ))}
    </div>
  );
}
