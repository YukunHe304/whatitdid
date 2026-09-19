import { useState } from "react";
import { findingText, phaseColor, type Report, type Strings, type Turn } from "../api";
import { Legend, Ribbon } from "./Ribbon";

function Distribution({ turn, phases }: { turn: Turn; phases: string[] }) {
  const entries = Object.entries(turn.phase)
    .filter(([, v]) => v > 0.02)
    .sort((a, b) => b[1] - a[1]);
  return (
    <div className="dist" aria-hidden>
      {entries.map(([p, v]) => (
        <i key={p} style={{ width: `${v * 100}%`, background: phaseColor(p, phases) }} />
      ))}
    </div>
  );
}

function Step({
  turn,
  phases,
  s,
  open,
  onToggle,
  highlighted,
}: {
  turn: Turn;
  phases: string[];
  s: Strings;
  open: boolean;
  onToggle: () => void;
  highlighted: boolean;
}) {
  const top2 = Object.entries(turn.phase)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .filter(([, v]) => v > 0.08);

  return (
    <div className={`step${highlighted ? " on" : ""}`} id={`t${turn.turn}`}>
      <div className="idx">{turn.turn}</div>
      <div>
        <div className="cmd" onClick={onToggle} style={{ cursor: "pointer" }}>
          {turn.command}
        </div>
        <Distribution turn={turn} phases={phases} />
        <div className="tags">
          {top2.map(([p, v]) => (
            <span
              key={p}
              className="tag"
              style={{
                borderColor: phaseColor(p, phases),
                background: `color-mix(in srgb, ${phaseColor(p, phases)} 14%, transparent)`,
              }}
            >
              {s.phases[p] ?? p} {Math.round(v * 100)}%
            </span>
          ))}
          {turn.marks.includes("waste") && <span className="tag warn">{s.ui.flag_waste}</span>}
          {(turn.noul.changes_system ?? 0) > 0.5 && (
            <span className="tag warn">{s.ui.flag_changed}</span>
          )}
          {turn.narration_changed_label && (
            <span className="tag narr">
              {s.ui.flag_narration}
              {turn.kept_word === true && ` (${s.ui.kept_word})`}
              {turn.kept_word === false && ` (${s.ui.broke_word})`}
            </span>
          )}
        </div>
        {open && (
          <dl className="detail">
            {turn.narration && (
              <>
                <dt>narration</dt>
                <dd>{turn.narration}</dd>
              </>
            )}
            {turn.observation && (
              <>
                <dt>result{turn.observation_len > turn.observation.length ? " (clipped)" : ""}</dt>
                <dd>{turn.observation}</dd>
              </>
            )}
            <dt>labels</dt>
            <dd>
              {Object.entries(turn.phase)
                .sort((a, b) => b[1] - a[1])
                .filter(([, v]) => v > 0.01)
                .map(([p, v]) => `${s.phases[p] ?? p} ${v.toFixed(2)}`)
                .join("   ")}
            </dd>
          </dl>
        )}
      </div>
    </div>
  );
}

export function ReportView({ report, s }: { report: Report; s: Strings }) {
  const [open, setOpen] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const phases = report.phases;

  const jump = (turn: number) => {
    setSelected(turn);
    setOpen(turn);
    document.getElementById(`t${turn}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  const rate = report.truthfulness;
  const verdict =
    rate === null ? null : rate >= 0.8 ? s.ui.trust_high : rate >= 0.65 ? s.ui.trust_mid : s.ui.trust_low;
  const failures = report.label_failures?.total ?? 0;

  return (
    <>
      <span className="eyebrow">{report.questions}</span>
      <h1>{report.agent}</h1>
      <div className="meta">
        {report.model && <span>{report.model}</span>}
        <span>
          {report.n_turns} {s.ui.steps}
        </span>
        <span>{report.labeler}</span>
      </div>

      <h2>{s.ui.where_steps_went}</h2>
      <Ribbon turns={report.per_turn} phases={phases} selected={selected} onSelect={jump} />
      <div className="ribbon-rule" />
      <div className="ribbon-scale">
        <span>1</span>
        <span>{report.n_turns}</span>
      </div>
      <div style={{ marginTop: 14 }}>
        <Legend phases={phases} mix={report.mix} names={s.phases} />
        <p className="lede" style={{ fontSize: 13, marginTop: 8 }}>{s.ui.where_note}</p>
      </div>

      {failures > 0 && (
        <p className="note alert">
          {failures} label calls failed; those steps are missing from this report.
        </p>
      )}

      {rate !== null && (
        <p className="note">
          <strong>
            {s.metrics.truthfulness} {Math.round(rate * 100)}%
          </strong>{" "}
          — {s.ui.trust_line
            .replace("{stated}", String(report.stated))
            .replace("{carried}", String(report.carried))
            .replace("{rate:.0%}", `${Math.round(rate * 100)}%`)}{" "}
          {verdict}.
        </p>
      )}

      <h2>{s.ui.per_step_measures}</h2>
      <p className="lede" style={{ marginBottom: 14 }}>{s.ui.per_step_note}</p>
      <div className="stats">
        {Object.entries(report.stats).map(([k, v]) => (
          <div className="stat" key={k} title={s.metric_help[k] ?? ""}>
            <b>{v.toFixed(2)}</b>
            <span>
              {s.metrics[k] ?? k}
              <i className="scale">{k === "targeting" ? s.ui.scale_0_4 : s.ui.scale_0_1}</i>
            </span>
          </div>
        ))}
      </div>

      <h2>{s.ui.worth_acting_on}</h2>
      {report.findings.length === 0 ? (
        <p className="lede">{s.ui.nothing_found}</p>
      ) : (
        <div className="findings">
          {report.findings.map((f, i) => (
            <div className="finding" key={i}>
              <i className="sev" style={{ opacity: 0.35 + f.severity * 0.65 }} />
              <div className="text">
                <div>{findingText(f, s.findings, s.phases)}</div>
                {f.turns.length > 0 && (
                  <div className="turns">
                    {f.turns.slice(0, 40).map((t) => (
                      <button key={t} onClick={() => jump(t)}>
                        {t}
                      </button>
                    ))}
                    {f.turns.length > 40 && <span>…</span>}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <h2>{s.ui.step_by_step}</h2>
      <div className="steps">
        {report.per_turn.map((t) => (
          <Step
            key={t.turn}
            turn={t}
            phases={phases}
            s={s}
            open={open === t.turn}
            highlighted={selected === t.turn}
            onToggle={() => setOpen(open === t.turn ? null : t.turn)}
          />
        ))}
      </div>
    </>
  );
}
