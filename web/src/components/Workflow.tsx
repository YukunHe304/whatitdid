import { useEffect, useRef, useState } from "react";
import { api, type CompareResult, type Strings, type WatchState } from "../api";

/** Watching a benchmark, and comparing two rounds — from the page rather than a terminal.
 *
 * These are the two things the tool is actually for, and until now both lived only in the
 * CLI. A product whose main workflow is unreachable from its own UI is half a product.
 */
export function WatchPanel({
  s,
  questionSets,
  onOpen,
}: {
  s: Strings;
  questionSets: string[];
  onOpen: (id: string) => void;
}) {
  const [root, setRoot] = useState("");
  const [questions, setQuestions] = useState(questionSets[0] ?? "sre.v1");
  const [watch, setWatch] = useState<WatchState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!watch || watch.state !== "running") return;
    timer.current = window.setInterval(async () => {
      try {
        setWatch(await api.watch(watch.id));
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
      }
    }, 3000);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [watch?.id, watch?.state]);

  async function start() {
    if (!root.trim()) return;
    setError(null);
    try {
      setWatch(await api.startWatch(root.trim(), questions));
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <>
      <h2>{s.ui.watch_h}</h2>
      <p className="lede">{s.ui.watch_lede}</p>

      <div className="row" style={{ marginTop: 14 }}>
        <input
          className="field"
          placeholder={s.ui.watch_root}
          value={root}
          onChange={(e) => setRoot(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void start()}
          disabled={watch?.state === "running"}
        />
        <select
          className="field"
          style={{ minWidth: 0, flex: "0 0 auto" }}
          value={questions}
          onChange={(e) => setQuestions(e.target.value)}
          disabled={watch?.state === "running"}
        >
          {questionSets.map((q) => (
            <option key={q} value={q}>
              {q}
            </option>
          ))}
        </select>
        {watch?.state === "running" ? (
          <button className="btn ghost" onClick={() => void api.stopWatch(watch.id).then(setWatch)}>
            {s.ui.watch_stop}
          </button>
        ) : (
          <button className="btn" onClick={() => void start()} disabled={!root.trim()}>
            {s.ui.watch_start}
          </button>
        )}
      </div>

      {error && <p className="err">{error}</p>}

      {watch && (
        <>
          <p className="meta" style={{ marginTop: 12 }}>
            {watch.state === "running" ? s.ui.watch_running : s.ui.watch_stopped} · {watch.root} ·{" "}
            {watch.found === 0
              ? s.ui.watch_waiting
              : s.ui.watch_found
                  .replace("{done}", String(watch.done.length))
                  .replace("{found}", String(watch.found))}{" "}
            · {watch.seconds}s
          </p>
          {watch.error && <p className="err">{watch.error}</p>}
          {watch.done.length > 0 && (
            <div className="findings">
              {watch.done.map((d) => (
                <button key={d.problem} className="finding saved" onClick={() => onOpen(d.problem)}>
                  <span className="text">
                    <b>{d.problem}</b>
                    <span className="meta">
                      {d.n_turns} {s.ui.steps} · {d.seconds}s
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
          {watch.failed.length > 0 && (
            <div className="findings" style={{ marginTop: 8 }}>
              {watch.failed.map((f) => (
                <div key={f.problem} className="finding">
                  <i className="sev" />
                  <div className="text">
                    <b>{f.problem}</b> <span className="meta">{f.why}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}

export function ComparePanel({
  s,
  onResult,
}: {
  s: Strings;
  onResult: (r: CompareResult) => void;
}) {
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function go() {
    if (!before.trim() || !after.trim()) return;
    setError(null);
    setBusy(true);
    try {
      onResult(
        await api.compare({
          before: before.trim(),
          after: after.trim(),
          repeats: repeat.trim() ? [repeat.trim()] : [],
        }),
      );
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h2>{s.ui.cmp_h}</h2>
      <p className="lede">{s.ui.cmp_lede}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14 }}>
        <input className="field" placeholder={s.ui.cmp_before} value={before}
               onChange={(e) => setBefore(e.target.value)} />
        <input className="field" placeholder={s.ui.cmp_after} value={after}
               onChange={(e) => setAfter(e.target.value)} />
        <input className="field" placeholder={s.ui.cmp_repeat} value={repeat}
               onChange={(e) => setRepeat(e.target.value)} />
        <div className="row">
          <button className="btn" onClick={() => void go()}
                  disabled={busy || !before.trim() || !after.trim()}>
            {s.ui.cmp_go}
          </button>
        </div>
      </div>
      {error && <p className="err">{error}</p>}
    </>
  );
}
