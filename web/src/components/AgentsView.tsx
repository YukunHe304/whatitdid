import { useMemo, useState } from "react";
import type { Report, Strings } from "../api";
import { Legend, Ribbon } from "./Ribbon";

/** Seven agents, one problem, stacked.
 *
 * The point of stacking is that the differences are visible before any number is read:
 * who probes and who only reads, who spends a quarter of the run writing up, whose steps
 * the labeler could not place. */
export function AgentsView({
  agents,
  s,
  onOpen,
}: {
  agents: Record<string, Report>;
  s: Strings;
  onOpen: (id: string) => void;
}) {
  const names = useMemo(() => Object.keys(agents).sort(), [agents]);
  const [metric, setMetric] = useState<string>("probe");

  const phases = agents[names[0]]?.phases ?? [];
  const longest = Math.max(...names.map((n) => agents[n].n_turns));
  // One shared pixels-per-step across every row, so the traces are to scale.
  const tickWidth = Math.max(4, Math.min(14, Math.floor(620 / longest)));

  const metricKeys = [
    ...phases.map((p) => ({ id: p, group: "phase" as const })),
    ...Object.keys(agents[names[0]]?.stats ?? {}).map((k) => ({ id: k, group: "metric" as const })),
    { id: "truthfulness", group: "metric" as const },
  ];

  const valueOf = (report: Report, id: string) =>
    id === "truthfulness" ? report.truthfulness : (report.mix[id] ?? report.stats[id] ?? null);

  const column = names
    .map((n) => valueOf(agents[n], metric))
    .filter((v): v is number => v !== null);
  const peak = Math.max(...column, 0.0001);

  return (
    <>
      <span className="eyebrow">{s.ui.agents_eyebrow.replace("{n}", String(names.length))}</span>
      <h1>service_port_conflict</h1>
      <p className="lede">{s.ui.agents_lede.replace("{n}", String(names.length))}</p>

      <h2>{s.ui.step_by_step}</h2>
      {names.map((name) => {
        const report = agents[name];
        return (
          <div className="ribbon-row" key={name}>
            <div className="who">
              <button className="linkish" onClick={() => onOpen(name)}>
                {name}
              </button>
              <small>{report.model ?? s.ui.agents_no_model}</small>
            </div>
            <div className="trace">
              <Ribbon
                turns={report.per_turn}
                phases={phases}
                onSelect={() => onOpen(name)}
                animate={false}
                tickWidth={tickWidth}
              />
              <div className="ribbon-rule" />
            </div>
            <div className="count">
              {report.n_turns} {s.ui.steps}
            </div>
          </div>
        );
      })}

      <div style={{ marginTop: 22 }}>
        <Legend phases={phases} names={s.phases} />
      </div>

      <h2>{s.ui.cmp_metric}</h2>
      <div className="row" style={{ marginBottom: 16 }}>
        <select className="field" value={metric} onChange={(e) => setMetric(e.target.value)}>
          {metricKeys.map(({ id, group }) => (
            <option key={`${group}:${id}`} value={id}>
              {group === "phase" ? (s.phases[id] ?? id) : (s.metrics[id] ?? id)}
            </option>
          ))}
        </select>
      </div>

      <table className="cmp">
        <tbody>
          {names
            .map((n) => ({ name: n, value: valueOf(agents[n], metric) }))
            .sort((a, b) => (b.value ?? -1) - (a.value ?? -1))
            .map(({ name, value }) => (
              <tr key={name}>
                <td style={{ width: 130 }}>{name}</td>
                <td className="num" style={{ width: 62 }}>
                  {value === null ? "—" : value.toFixed(2)}
                </td>
                <td>
                  <div style={{ height: 10, background: "var(--rule)", width: "100%" }}>
                    <div
                      style={{
                        height: "100%",
                        width: `${((value ?? 0) / peak) * 100}%`,
                        background: value === null ? "transparent" : "var(--ink)",
                      }}
                    />
                  </div>
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </>
  );
}
