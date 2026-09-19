import { useCallback, useEffect, useState } from "react";
import { api, type CompareResult, type Config, type Report, type Strings } from "./api";
import { AgentsView } from "./components/AgentsView";
import { CompareView } from "./components/CompareView";
import { Landing } from "./components/Landing";
import { ReportView } from "./components/ReportView";

type View = "home" | "agents" | "compare" | "report";

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [s, setStrings] = useState<Strings | null>(null);
  const [lang, setLang] = useState<string>(
    () => localStorage.getItem("agentvitals.lang") ?? "en",
  );
  const [view, setView] = useState<View>("home");
  const [agents, setAgents] = useState<Record<string, Report> | null>(null);
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    api.strings(lang).then(setStrings).catch((e) => setError(String(e)));
    localStorage.setItem("agentvitals.lang", lang);
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [view]);

  const openDemo = useCallback(async (which: "agents" | "compare") => {
    setError(null);
    try {
      if (which === "agents") {
        setAgents(await api.demoAgents());
        setView("agents");
      } else {
        setCompare(await api.demoCompare());
        setView("compare");
      }
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    }
  }, []);

  const openAgent = useCallback(
    (id: string) => {
      if (agents?.[id]) {
        setReport(agents[id]);
        setView("report");
      }
    },
    [agents],
  );

  const openProfiled = useCallback(async (id: string) => {
    try {
      setReport(await api.report(id));
      setView("report");
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    }
  }, []);

  if (error && !config) {
    return (
      <div className="main">
        <h1>agentvitals</h1>
        <p className="err">{error}</p>
      </div>
    );
  }
  if (!config || !s) return <div className="main" />;

  const tabs: { id: View; label: string; enabled: boolean }[] = [
    { id: "home", label: s.ui.nav_start, enabled: true },
    { id: "agents", label: s.ui.nav_agents, enabled: !!agents },
    { id: "compare", label: s.ui.nav_compare, enabled: !!compare },
    { id: "report", label: report ? report.agent : s.ui.nav_report, enabled: !!report },
  ];

  return (
    <div className="shell">
      <nav className="rail">
        <div className="wordmark">
          agent<em>vitals</em>
        </div>
        <div className="version">
          v{config.version}
          {config.demo_only ? " · demo" : ""}
        </div>
        <div className="nav">
          {tabs.map((t) => (
            <button
              key={t.id}
              aria-current={view === t.id}
              disabled={!t.enabled}
              onClick={() => t.enabled && setView(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="rail-foot">
          <div className="langs">
            {config.langs.map((l) => (
              <button key={l} aria-pressed={lang === l} onClick={() => setLang(l)}>
                {l}
              </button>
            ))}
          </div>
        </div>
      </nav>

      <main className="main">
        {error && <p className="err">{error}</p>}
        {view === "home" && (
          <Landing config={config} s={s} onDemo={openDemo} onProfiled={openProfiled} />
        )}
        {view === "agents" && agents && <AgentsView agents={agents} s={s} onOpen={openAgent} />}
        {view === "compare" && compare && <CompareView result={compare} s={s} />}
        {view === "report" && report && <ReportView report={report} s={s} />}
      </main>
    </div>
  );
}
