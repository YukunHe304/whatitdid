import type { CompareResult, MetricRow, Strings } from "../api";

/** The delta drawn against the band a re-run moves it anyway.
 *
 * A bar that stays inside the shaded band is not a finding, whatever its confidence
 * interval says. Drawing the two together is the entire argument of the tool, so it is
 * shown rather than asserted. */
function Gauge({ row, scale }: { row: MetricRow; scale: number }) {
  const pct = (v: number) => 50 + (v / scale) * 50;
  const left = Math.min(pct(0), pct(row.delta));
  const width = Math.abs(pct(row.delta) - pct(0));
  const noise = row.noise ?? 0;

  return (
    <div className="gauge">
      {row.noise !== null && (
        <div
          className="band"
          style={{ left: `${pct(-noise)}%`, width: `${pct(noise) - pct(-noise)}%` }}
          title={`repeat noise ±${noise.toFixed(3)}`}
        />
      )}
      <div className="axis" />
      <div
        className="whisker"
        style={{ left: `${Math.min(pct(row.low), pct(row.high))}%`, width: `${Math.abs(pct(row.high) - pct(row.low))}%` }}
      />
      <div
        className={`bar ${row.verdict === "above_noise" ? "above" : row.verdict === "within_noise" ? "within" : ""}`}
        style={{ left: `${left}%`, width: `${Math.max(width, 0.6)}%` }}
      />
    </div>
  );
}

export function CompareView({ result, s }: { result: CompareResult; s: Strings }) {
  const scale = Math.max(
    ...result.metrics.map((r) => Math.max(Math.abs(r.low), Math.abs(r.high), r.noise ?? 0)),
    0.05,
  );
  const source = result.noise.source;
  const sourceNote =
    source === "measured"
      ? s.ui.cmp_src_measured.replace("{n}", String(result.noise.n_runs ?? 0))
      : source === "reference"
        ? s.ui.cmp_src_reference
        : s.ui.cmp_src_none;

  const verdictLabel: Record<string, string> = {
    above_noise: s.ui.verdict_above_noise,
    within_noise: s.ui.verdict_within_noise,
    unstable: s.ui.verdict_unstable,
    no_baseline: s.ui.noise_unknown,
  };

  const real = result.metrics.filter((r) => r.verdict === "above_noise").length;
  const headline =
    source === "none"
      ? s.ui.cmp_none_h.replace("{n}", String(result.metrics.length))
      : real === 0
        ? s.ui.cmp_zero_h
        : s.ui.cmp_some_h
            .replace("{real}", String(real))
            .replace("{n}", String(result.metrics.length));

  return (
    <>
      <span className="eyebrow">{result.questions}</span>
      <h1>{headline}</h1>
      <div className="meta">
        <span>{s.ui.cmp_header.replace("{n}", String(result.tasks.n)).replace("{rounds}", String(result.rounds))}</span>
      </div>
      <p className={`note${source === "none" ? " alert" : ""}`}>{sourceNote}</p>

      <div className="table-scroll">
      <table className="cmp">
        <thead>
          <tr>
            <th>{s.ui.cmp_metric}</th>
            <th className="num">{s.ui.cmp_delta}</th>
            <th style={{ minWidth: 160 }} />
            <th className="num">{s.ui.cmp_interval}</th>
            <th className="num">{s.ui.cmp_improved}</th>
            <th className="num">{s.ui.cmp_noise}</th>
            <th>{s.ui.cmp_verdict}</th>
          </tr>
        </thead>
        <tbody>
          {result.metrics.map((row) => (
            <tr key={`${row.group}:${row.id}`} className={row.verdict === "above_noise" ? "" : "quiet"}>
              <td>{row.group === "phase" ? (s.phases[row.id] ?? row.id) : (s.metrics[row.id] ?? row.id)}</td>
              <td className="num">
                {row.delta >= 0 ? "+" : ""}
                {row.delta.toFixed(3)}
              </td>
              <td>
                <Gauge row={row} scale={scale} />
              </td>
              <td className="num">
                ({row.low >= 0 ? "+" : ""}
                {row.low.toFixed(3)}, {row.high >= 0 ? "+" : ""}
                {row.high.toFixed(3)})
              </td>
              <td className="num">
                {row.improved}/{row.n}
              </td>
              <td className="num">{row.noise === null ? "—" : `±${row.noise.toFixed(3)}`}</td>
              <td>
                <span className={`verdict ${row.verdict}`}>{verdictLabel[row.verdict]}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}
