import { useRef, useState } from "react";
import { api, type CompareResult, type Config, type Strings } from "../api";
import { ComparePanel, WatchPanel } from "./Workflow";

/** The first screen has one job: answer "what do I do now".
 *
 * Three entries, ordered by how much they cost the visitor. Looking at the bundled
 * example costs nothing and needs no key, so it goes first — you should be able to judge
 * whether this tool is worth anything before you hand it credentials. */
export function Landing({
  config,
  s,
  onDemo,
  onProfiled,
  onCompared,
  saved = [],
}: {
  config: Config;
  s: Strings;
  onDemo: (which: "agents" | "compare") => void;
  onProfiled: (id: string) => void;
  onCompared: (r: CompareResult) => void;
  saved?: { id: string; agent: string }[];
}) {
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [questions, setQuestions] = useState("sre.v1");
  const [key, setKey] = useState("");
  const [hasKey, setHasKey] = useState(config.has_key);
  const fileInput = useRef<HTMLInputElement>(null);

  async function follow(jobId: string) {
    for (;;) {
      await new Promise((r) => setTimeout(r, 600));
      const job = await api.job(jobId);
      setBusy({ done: job.done, total: job.total });
      if (job.state === "done" && job.result) {
        setBusy(null);
        onProfiled(job.result);
        return;
      }
      if (job.state === "error") {
        setBusy(null);
        setError(job.error ?? "profiling failed");
        return;
      }
    }
  }

  async function submitFile(file: File) {
    setError(null);
    setBusy({ done: 0, total: 0 });
    try {
      const { job } = await api.profileFile(file, questions);
      await follow(job);
    } catch (e) {
      setBusy(null);
      setError(String(e instanceof Error ? e.message : e));
    }
  }

  async function submitPath() {
    if (!path.trim()) return;
    setError(null);
    setBusy({ done: 0, total: 0 });
    try {
      const { job } = await api.profilePath(path.trim(), questions);
      await follow(job);
    } catch (e) {
      setBusy(null);
      setError(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <>
      <span className="eyebrow">{s.ui.land_eyebrow}</span>
      <h1>whatitdid</h1>
      <p className="lede">{s.ui.land_lede}</p>

      <div className="entries">
        <button className="entry" onClick={() => onDemo("agents")}>
          <span className="step-no">01</span>
          <b>{s.ui.land_demo_title}</b>
          <span>{s.ui.land_demo_body}</span>
        </button>
        <button className="entry" onClick={() => onDemo("compare")}>
          <span className="step-no">02</span>
          <b>{s.ui.land_cmp_title}</b>
          <span>{s.ui.land_cmp_body}</span>
        </button>
        <button
          className="entry"
          disabled={config.demo_only}
          onClick={() => fileInput.current?.click()}
        >
          <span className="step-no">03</span>
          <b>{s.ui.land_own_title}</b>
          <span>{config.demo_only ? s.ui.land_own_disabled : s.ui.land_own_body}</span>
        </button>
      </div>

      {!config.demo_only && (
        <>
          <h2>{s.ui.land_profile_h}</h2>

          {!hasKey && (
            <div className="note alert">
              <p style={{ margin: "0 0 10px" }}>{s.ui.land_key_note}</p>
              <div className="row">
                <input
                  className="field"
                  type="password"
                  placeholder="TYPESAFE_API_KEY"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                />
                <button
                  className="btn"
                  disabled={!key.trim()}
                  onClick={async () => {
                    try {
                      const res = await api.setKey(key.trim());
                      setHasKey(res.has_key);
                      setKey("");
                    } catch (e) {
                      setError(String(e instanceof Error ? e.message : e));
                    }
                  }}
                >
                  {s.ui.land_key_save}
                </button>
              </div>
            </div>
          )}

          <div
            className={`drop${over ? " over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(false);
              const file = e.dataTransfer.files[0];
              if (file) void submitFile(file);
            }}
          >
            {s.ui.land_drop}{" "}
            <label>
              {s.ui.land_choose}
              <input
                ref={fileInput}
                type="file"
                accept=".json,.jsonl"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void submitFile(file);
                }}
              />
            </label>
            . {s.ui.land_detect}
          </div>

          <div className="row" style={{ marginTop: 12 }}>
            <input
              className="field"
              placeholder={s.ui.land_path}
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void submitPath()}
            />
            <select
              className="field"
              style={{ minWidth: 0, flex: "0 0 auto" }}
              value={questions}
              onChange={(e) => setQuestions(e.target.value)}
            >
              {config.question_sets.map((q) => (
                <option key={q.id} value={q.id}>
                  {q.id}
                </option>
              ))}
            </select>
            <button className="btn" onClick={() => void submitPath()} disabled={!path.trim() || !!busy}>
              {s.ui.land_go}
            </button>
          </div>

          {busy && (
            <div className="progress" aria-label="profiling">
              <i style={{ width: busy.total ? `${(busy.done / busy.total) * 100}%` : "8%" }} />
            </div>
          )}
          {busy && (
            <p className="meta" style={{ marginTop: 8 }}>
              {s.ui.land_labelling.replace(
                "{done}",
                busy.total ? `${busy.done}/${busy.total}` : String(busy.done),
              )}
            </p>
          )}
          {error && <p className="err">{error}</p>}
        </>
      )}

      {!config.demo_only && (
        <>
          <WatchPanel
            s={s}
            questionSets={config.question_sets.map((q) => q.id)}
            onOpen={onProfiled}
          />
          <ComparePanel s={s} onResult={onCompared} />
        </>
      )}

      {saved.length > 0 && (
        <>
          <h2>{s.ui.land_saved}</h2>
          <div className="findings">
            {saved.map((r) => (
              <button key={r.id} className="finding saved" onClick={() => onProfiled(r.id)}>
                <span className="text">
                  <b>{r.agent}</b> <span className="meta">{r.id}</span>
                </span>
              </button>
            ))}
          </div>
        </>
      )}

      <h2>{s.ui.questions}</h2>
      <p className="lede">{s.ui.land_q_lede}</p>
      <div className="stats" style={{ marginTop: 14 }}>
        {Object.entries(s.metrics)
          .filter(([k]) => k !== "labeler_confidence")
          .map(([k, label]) => (
            <div className="stat" key={k}>
              <b style={{ fontSize: 13 }}>{label}</b>
              <span>{s.metric_help[k]}</span>
            </div>
          ))}
      </div>
    </>
  );
}
