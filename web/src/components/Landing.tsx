import { useRef, useState } from "react";
import { api, type Config, type Strings } from "../api";

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
}: {
  config: Config;
  s: Strings;
  onDemo: (which: "agents" | "compare") => void;
  onProfiled: (id: string) => void;
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
      <span className="eyebrow">what the run actually did</span>
      <h1>agentvitals</h1>
      <p className="lede">
        Read any CLI agent's session file and label every step: what it was doing, whether it
        brought anything new, whether it changed something and then checked. Then compare two
        rounds against the noise a re-run produces anyway.
      </p>

      <div className="entries">
        <button className="entry" onClick={() => onDemo("agents")}>
          <span className="step-no">01</span>
          <b>Look at an example</b>
          <span>
            Seven CLI agents on the same fault, 153 steps, real labels. Nothing to install, no
            key.
          </span>
        </button>
        <button className="entry" onClick={() => onDemo("compare")}>
          <span className="step-no">02</span>
          <b>See two rounds compared</b>
          <span>
            The same agent at two settings over 21 problems. The score says nothing; the
            behaviour says three things.
          </span>
        </button>
        <button
          className="entry"
          disabled={config.demo_only}
          onClick={() => fileInput.current?.click()}
        >
          <span className="step-no">03</span>
          <b>Profile your own run</b>
          <span>
            {config.demo_only
              ? "Run `agentvitals serve` to use your own trajectories."
              : "Drop a session file from Claude Code, Codex, Gemini, Copilot, OpenCode or Stratus."}
          </span>
        </button>
      </div>

      {!config.demo_only && (
        <>
          <h2>Profile a run</h2>

          {!hasKey && (
            <div className="note alert">
              <p style={{ margin: "0 0 10px" }}>
                Labelling needs a TypeSafe API key. It is written to{" "}
                <code>~/.config/agentvitals/typesafe.env</code> with owner-only permissions and
                never leaves this machine.
              </p>
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
                  Save key
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
            Drop a session file here, or{" "}
            <label>
              choose one
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
            . The format is detected from the contents, not the filename.
          </div>

          <div className="row" style={{ marginTop: 12 }}>
            <input
              className="field"
              placeholder="…or a path on this machine"
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
              Profile
            </button>
          </div>

          {busy && (
            <div className="progress" aria-label="profiling">
              <i style={{ width: busy.total ? `${(busy.done / busy.total) * 100}%` : "8%" }} />
            </div>
          )}
          {busy && (
            <p className="meta" style={{ marginTop: 8 }}>
              labelling {busy.done}
              {busy.total ? `/${busy.total}` : ""} steps
            </p>
          )}
          {error && <p className="err">{error}</p>}
        </>
      )}

      <h2>{s.ui.questions}</h2>
      <p className="lede">
        Six questions per step. One names what kind of move it was and changes with the domain;
        the other five are the same for every domain, so a coding agent and an ops agent stay
        comparable on those.
      </p>
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
