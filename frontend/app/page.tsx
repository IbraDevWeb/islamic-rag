"use client";

import {
  Archive,
  ArrowUpRight,
  BookMarked,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  Clipboard,
  Clock3,
  Command,
  Copy,
  Database,
  FileSearch,
  Fingerprint,
  History,
  Languages,
  Library,
  LoaderCircle,
  PanelLeftClose,
  Search,
  ShieldCheck,
  Sparkles,
  TextQuote,
  X,
  XCircle,
} from "lucide-react";
import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

const WORK_URI = "0595IbnRushdHafid.BidayatMujtahid";
const HISTORY_KEY = "athar.research-history.v1";

const EXAMPLES = [
  "في أي كتاب يناقش ابن رشد القراض؟",
  "ما المسائل التي يذكرها ابن رشد في كتاب الصلاة؟",
  "Que dit le corpus sur la prière du voyageur ?",
];

type Citation = {
  author?: string | null;
  work?: string | null;
  work_uri?: string | null;
  version_uri?: string | null;
  volume?: number | null;
  page?: number | null;
  section_path?: string[];
  chunk_id?: string;
  text_hash?: string;
  provider?: string | null;
  source_url?: string | null;
};

type EvidenceSource = {
  source_id: string;
  rank: number;
  score: number;
  citation: Citation;
  passage_original: string;
};

type EvidenceBundle = {
  bundle_id: string;
  bundle_version: string;
  retrieval: string;
  evidence_count: number;
  source_ids: string[];
  query_variants: string[];
  sources: EvidenceSource[];
};

type DraftClaim = {
  text: string;
  citation_ids: string[];
};

type FaithfulnessCheck = {
  claim_index: number;
  claim_text: string;
  citation_ids: string[];
  verdict: "SUPPORTED" | "NOT_SUPPORTED" | "UNCLEAR";
  reason: string;
};

type Synthesis = {
  status: string;
  provider: {
    provider: string;
    model: string;
    elapsed_ms: number;
    prompt_eval_count?: number | null;
    eval_count?: number | null;
  };
  draft: {
    status: "ANSWERED" | "INSUFFICIENT_EVIDENCE";
    answer: string;
    claims: DraftClaim[];
  };
  structural_validation: {
    valid: boolean;
    errors: string[];
  };
  faithfulness_validation: {
    checked: boolean;
    overall_verdict: string;
    all_claims_supported: boolean | null;
    independent_verifier_model: boolean;
    model?: string | null;
    checks?: FaithfulnessCheck[];
  };
  semantic_entailment_checked: boolean;
};

type ResearchResponse = {
  mode: "synthesis" | "evidence";
  evidence: EvidenceBundle;
  synthesis?: Synthesis;
};

type Health = {
  status: string;
  services?: Record<string, { status: string }>;
};

type HistoryItem = {
  question: string;
  mode: "synthesis" | "evidence";
  at: number;
};

type SourceFilter = "all" | "cited";

function readableProvider(value?: string) {
  if (!value) return "—";
  if (value.includes("groq")) return "Groq Cloud";
  if (value.includes("ollama")) return "Ollama local";
  return value;
}

function ms(value?: number) {
  if (value === undefined) return "—";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

function shortHash(value?: string | null) {
  if (!value) return "—";
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

function formatHistoryTime(timestamp: number) {
  const elapsed = Date.now() - timestamp;
  const minutes = Math.floor(elapsed / 60000);
  if (minutes < 1) return "à l’instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short" }).format(
    new Date(timestamp),
  );
}

function verdictLabel(value?: string) {
  if (!value || value === "NOT_APPLICABLE") return "Non vérifié";
  if (value === "SUPPORTED") return "Soutenu";
  if (value === "NOT_SUPPORTED") return "Non soutenu";
  if (value === "UNCLEAR") return "Incertain";
  return value;
}

function InlineAnswer({
  text,
  onCitation,
}: {
  text: string;
  onCitation: (sourceId: string) => void;
}) {
  const parts = text.split(/(\[S\d+\])/g);
  return (
    <p dir="auto">
      {parts.map((part, index) => {
        const match = part.match(/^\[(S\d+)\]$/);
        if (!match) return <span key={`${part}-${index}`}>{part}</span>;
        return (
          <button
            className="inline-citation"
            key={`${part}-${index}`}
            onClick={() => onCitation(match[1])}
            type="button"
            title={`Voir ${match[1]}`}
          >
            {match[1]}
          </button>
        );
      })}
    </p>
  );
}

function AtharMark() {
  return (
    <div className="athar-mark" aria-hidden="true">
      <span>أثر</span>
      <i />
    </div>
  );
}

export default function HomePage() {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<"synthesis" | "evidence">("synthesis");
  const [verifyClaims, setVerifyClaims] = useState(true);
  const [limit, setLimit] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [sourceQuery, setSourceQuery] = useState("");
  const [copied, setCopied] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const questionRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    fetch("/api/research", { cache: "no-store" })
      .then((res) => res.json())
      .then((payload) => setHealth(payload))
      .catch(() => setHealth({ status: "offline" }));

    try {
      const stored = window.localStorage.getItem(HISTORY_KEY);
      if (stored) setHistory(JSON.parse(stored));
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    const handler = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        questionRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const citedIds = useMemo(() => {
    const ids = result?.synthesis?.draft.claims.flatMap((claim) => claim.citation_ids) ?? [];
    return new Set(ids);
  }, [result]);

  const filteredSources = useMemo(() => {
    const sources = result?.evidence.sources ?? [];
    const query = sourceQuery.trim().toLocaleLowerCase();
    return sources.filter((source) => {
      if (sourceFilter === "cited" && !citedIds.has(source.source_id)) return false;
      if (!query) return true;
      const haystack = [
        source.source_id,
        source.passage_original,
        ...(source.citation.section_path ?? []),
        source.citation.work ?? "",
        source.citation.author ?? "",
      ]
        .join(" ")
        .toLocaleLowerCase();
      return haystack.includes(query);
    });
  }, [result, sourceFilter, sourceQuery, citedIds]);

  const isHealthy = health?.status === "ok";
  const synthesis = result?.synthesis;
  const evidence = result?.evidence;

  async function copyText(text: string, label: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      setCopied(null);
    }
  }

  function remember(item: HistoryItem) {
    const next = [
      item,
      ...history.filter((entry) => entry.question !== item.question),
    ].slice(0, 6);
    setHistory(next);
    try {
      window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
    } catch {
      // Local history is a convenience only.
    }
  }

  function selectHistory(item: HistoryItem) {
    setQuestion(item.question);
    setMode(item.mode);
    setSidebarOpen(false);
    window.setTimeout(() => questionRef.current?.focus(), 50);
  }

  function scrollToSource(sourceId: string) {
    const target = document.getElementById(`source-${sourceId}`);
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
    target?.classList.add("source-flash");
    window.setTimeout(() => target?.classList.remove("source-flash"), 1600);
  }

  async function runSearch() {
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setSourceFilter("all");
    setSourceQuery("");

    try {
      const response = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          mode,
          limit,
          work_uri: WORK_URI,
          verify_claims: verifyClaims,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "La recherche a échoué.");
      }
      setResult(payload);
      remember({ question: question.trim(), mode, at: Date.now() });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue.");
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void runSearch();
  }

  function composerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void runSearch();
    }
  }

  const answerIsSupported =
    synthesis?.faithfulness_validation.checked &&
    synthesis.faithfulness_validation.overall_verdict === "SUPPORTED";

  return (
    <div className="app-frame">
      <button
        className="mobile-menu"
        type="button"
        aria-label="Ouvrir la navigation"
        onClick={() => setSidebarOpen(true)}
      >
        <PanelLeftClose size={20} />
      </button>

      {sidebarOpen && (
        <button
          className="sidebar-scrim"
          type="button"
          aria-label="Fermer la navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="brand-lockup">
          <AtharMark />
          <div>
            <strong>Athar</strong>
            <span>أثر · recherche documentaire</span>
          </div>
          <button className="sidebar-close" type="button" onClick={() => setSidebarOpen(false)} aria-label="Fermer">
            <X size={18} />
          </button>
        </div>

        <nav className="primary-nav" aria-label="Navigation principale">
          <a className="nav-link active" href="#research" onClick={() => setSidebarOpen(false)}>
            <Search size={17} />
            <span>Recherche</span>
            <i>01</i>
          </a>
          <a className="nav-link" href="#sources" onClick={() => setSidebarOpen(false)}>
            <TextQuote size={17} />
            <span>Sources</span>
            <i>02</i>
          </a>
          <a className="nav-link" href="#corpus" onClick={() => setSidebarOpen(false)}>
            <BookMarked size={17} />
            <span>Corpus</span>
            <i>03</i>
          </a>
          <a className="nav-link" href="#method" onClick={() => setSidebarOpen(false)}>
            <Fingerprint size={17} />
            <span>Méthode</span>
            <i>04</i>
          </a>
        </nav>

        <section className="sidebar-section history-section">
          <div className="sidebar-section-title">
            <span><History size={14} /> Recherches récentes</span>
            {history.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setHistory([]);
                  window.localStorage.removeItem(HISTORY_KEY);
                }}
              >
                Effacer
              </button>
            )}
          </div>
          <div className="history-list">
            {history.length === 0 ? (
              <p className="history-empty">Tes dernières recherches apparaîtront ici, uniquement sur cet appareil.</p>
            ) : (
              history.slice(0, 4).map((item) => (
                <button key={`${item.question}-${item.at}`} type="button" onClick={() => selectHistory(item)}>
                  <span dir="auto">{item.question}</span>
                  <small>{formatHistoryTime(item.at)}</small>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="corpus-card-sidebar">
          <div className="corpus-kicker"><Library size={14} /> Corpus actif</div>
          <div className="corpus-monogram">بم</div>
          <strong>Bidāyat al-Mujtahid</strong>
          <span>Ibn Rushd al-Ḥafīd</span>
          <div className="corpus-rule" />
          <div className="corpus-facts">
            <span>OpenITI</span>
            <span>1 538 passages</span>
          </div>
        </section>

        <div className="system-status">
          <span className={`status-dot ${isHealthy ? "ok" : "warn"}`} />
          <div>
            <strong>{isHealthy ? "Index documentaire prêt" : "État du système"}</strong>
            <span>
              {isHealthy
                ? `${Object.values(health?.services ?? {}).filter((service) => service.status === "ok").length || 2} services connectés`
                : "Vérification en cours"}
            </span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <section className="masthead" id="research">
          <div className="breadcrumb-top">
            <span>ATHAR / BIBLIOTHÈQUE</span>
            <i />
            <span>IBN RUSHD</span>
            <i />
            <strong>SESSION DOCUMENTAIRE</strong>
          </div>

          <div className="hero-grid">
            <div className="hero-copy">
              <span className="eyebrow">RECHERCHE ISLAMIQUE SOURCÉE</span>
              <h1>Les textes d’abord.<br /><em>L’IA ensuite.</em></h1>
              <p>
                Athar retrouve les passages pertinents, conserve leur provenance et ne demande au modèle que d’organiser ce que le corpus permet réellement d’affirmer.
              </p>
            </div>
            <div className="hero-manifesto" aria-label="Principe Athar">
              <span className="arabic-seal">الأثر</span>
              <p>Une réponse sans preuve n’est pas une réponse Athar.</p>
              <small>Principe documentaire · v0.8</small>
            </div>
          </div>

          <div className="metrics-strip">
            <div><strong>1</strong><span>ouvrage indexé</span></div>
            <div><strong>1 538</strong><span>passages</span></div>
            <div><strong>AR · FR</strong><span>langues de travail</span></div>
            <div><strong>E5</strong><span>retrieval sémantique</span></div>
            <div className="metric-live"><span className={`status-dot ${isHealthy ? "ok" : "warn"}`} /><strong>{isHealthy ? "Prêt" : "À vérifier"}</strong><span>état du moteur</span></div>
          </div>
        </section>

        <section className="research-desk">
          <div className="desk-topline">
            <div className="desk-tabs" role="tablist" aria-label="Mode de recherche">
              <button className={mode === "synthesis" ? "selected" : ""} onClick={() => setMode("synthesis")} type="button">
                <Sparkles size={16} />
                <span>Réponse sourcée</span>
              </button>
              <button className={mode === "evidence" ? "selected" : ""} onClick={() => setMode("evidence")} type="button">
                <FileSearch size={16} />
                <span>Textes seulement</span>
              </button>
            </div>
            <div className="desk-shortcut"><Command size={13} /> K pour écrire</div>
          </div>

          <form onSubmit={submit}>
            <div className="prompt-label">
              <label htmlFor="question">Question de recherche</label>
              <span>Français ou العربية</span>
            </div>
            <div className="composer">
              <textarea
                ref={questionRef}
                id="question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={composerKeyDown}
                placeholder="Interroge le corpus…"
                dir="auto"
                rows={4}
                disabled={loading}
              />
              <div className="composer-hint">Ctrl / ⌘ + Entrée</div>
              <button className="submit-button" disabled={loading || !question.trim()} type="submit">
                {loading ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />}
                {loading ? "Lecture du corpus…" : "Lancer la recherche"}
              </button>
            </div>

            <div className="research-controls">
              <div className="examples">
                <span>Essayer</span>
                {EXAMPLES.map((example) => (
                  <button key={example} type="button" onClick={() => setQuestion(example)} dir="auto">
                    {example}
                  </button>
                ))}
              </div>

              <div className="control-cluster">
                <label className="select-control">
                  <span>Passages</span>
                  <select value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
                    <option value={3}>3</option>
                    <option value={5}>5</option>
                    <option value={8}>8</option>
                  </select>
                  <ChevronDown size={13} />
                </label>
                {mode === "synthesis" && (
                  <label className="switch-control">
                    <input type="checkbox" checked={verifyClaims} onChange={(event) => setVerifyClaims(event.target.checked)} />
                    <span className="switch-track"><i /></span>
                    <span>Vérifier les citations</span>
                  </label>
                )}
              </div>
            </div>
          </form>
        </section>

        {loading && (
          <section className="process-card" aria-live="polite">
            <div className="process-heading">
              <LoaderCircle className="spin" size={20} />
              <div>
                <strong>Le corpus est en cours de lecture</strong>
                <span>La réponse n’est construite qu’après sélection des preuves.</span>
              </div>
            </div>
            <div className="process-track">
              <div className="process-step active"><i>1</i><span>Comprendre la requête</span></div>
              <div className="process-step active"><i>2</i><span>Retrouver les passages</span></div>
              <div className="process-step"><i>3</i><span>Hydrater les sources</span></div>
              {mode === "synthesis" && <div className="process-step"><i>4</i><span>Synthétiser & vérifier</span></div>}
            </div>
          </section>
        )}

        {error && (
          <section className="error-card">
            <XCircle size={20} />
            <div>
              <strong>La recherche n’a pas abouti</strong>
              <p>{error}</p>
            </div>
          </section>
        )}

        {!result && !loading && !error && (
          <section className="welcome-grid">
            <article className="principle-card">
              <span className="card-number">01</span>
              <Fingerprint size={20} />
              <h3>Traçabilité</h3>
              <p>Chaque passage conserve son ouvrage, sa version, sa page, son chunk et ses empreintes d’intégrité.</p>
            </article>
            <article className="principle-card featured">
              <span className="card-number">02</span>
              <TextQuote size={20} />
              <h3>Texte original</h3>
              <p>Le texte arabe hydraté depuis PostgreSQL reste la preuve. Le texte normalisé sert uniquement au retrieval.</p>
            </article>
            <article className="principle-card">
              <span className="card-number">03</span>
              <ShieldCheck size={20} />
              <h3>Droit à l’abstention</h3>
              <p>Quand le corpus ne suffit pas, Athar doit pouvoir répondre qu’il ne dispose pas de preuves suffisantes.</p>
            </article>
          </section>
        )}

        {result && !loading && (
          <section className="research-result" aria-live="polite">
            <div className="result-heading">
              <div>
                <span className="eyebrow">DOSSIER DE RECHERCHE</span>
                <h2 dir="auto">{question}</h2>
              </div>
              <div className="result-stamp">
                <Archive size={16} />
                <span>{evidence?.bundle_id ?? "Bundle"}</span>
              </div>
            </div>

            {synthesis ? (
              <article className="answer-card">
                <div className="answer-ribbon">
                  <div className="answer-title-block">
                    <span className="answer-kicker">SYNTHÈSE DOCUMENTAIRE</span>
                    <h3>{synthesis.draft.status === "INSUFFICIENT_EVIDENCE" ? "Le corpus ne permet pas de conclure" : "Réponse candidate"}</h3>
                  </div>
                  <div className="answer-actions">
                    <span className={`status-chip ${answerIsSupported ? "supported" : synthesis.draft.status === "INSUFFICIENT_EVIDENCE" ? "neutral" : "pending"}`}>
                      {answerIsSupported ? <CheckCircle2 size={14} /> : <CircleDot size={14} />}
                      {synthesis.draft.status === "INSUFFICIENT_EVIDENCE" ? "Abstention" : answerIsSupported ? "Citations soutenues" : "Validation en cours"}
                    </span>
                    <button type="button" className="icon-action" onClick={() => copyText(synthesis.draft.answer, "answer")}>
                      {copied === "answer" ? <Check size={16} /> : <Copy size={16} />}
                      <span>{copied === "answer" ? "Copié" : "Copier"}</span>
                    </button>
                  </div>
                </div>

                <div className="answer-body">
                  <InlineAnswer text={synthesis.draft.answer} onCitation={scrollToSource} />
                </div>

                {synthesis.draft.claims.length > 0 && (
                  <div className="claims-section">
                    <div className="subheading-row">
                      <span>Affirmations vérifiables</span>
                      <small>{synthesis.draft.claims.length} élément{synthesis.draft.claims.length > 1 ? "s" : ""}</small>
                    </div>
                    <div className="claims-list">
                      {synthesis.draft.claims.map((claim, index) => {
                        const check = synthesis.faithfulness_validation.checks?.find((entry) => entry.claim_index === index + 1);
                        return (
                          <div className="claim-item" key={`${claim.text}-${index}`}>
                            <span className="claim-number">{String(index + 1).padStart(2, "0")}</span>
                            <div className="claim-main">
                              <p dir="auto">{claim.text}</p>
                              <div className="citation-row">
                                {claim.citation_ids.map((id) => (
                                  <button key={id} type="button" onClick={() => scrollToSource(id)}>{id}</button>
                                ))}
                                {check && <span className={`claim-verdict ${check.verdict.toLowerCase()}`}>{verdictLabel(check.verdict)}</span>}
                              </div>
                              {check?.reason && <details className="verification-detail"><summary>Voir le contrôle de soutien</summary><p dir="auto">{check.reason}</p></details>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className="audit-strip">
                  <div><span>Structure</span><strong className={synthesis.structural_validation.valid ? "good-text" : "bad-text"}>{synthesis.structural_validation.valid ? "Validée" : "Rejetée"}</strong></div>
                  <div><span>Soutien</span><strong className={answerIsSupported ? "good-text" : ""}>{verdictLabel(synthesis.faithfulness_validation.overall_verdict)}</strong></div>
                  <div><span>Générateur</span><strong>{readableProvider(synthesis.provider.provider)}</strong></div>
                  <div><span>Modèle</span><strong title={synthesis.provider.model}>{synthesis.provider.model}</strong></div>
                  <div><span>Temps</span><strong>{ms(synthesis.provider.elapsed_ms)}</strong></div>
                  <div><span>Vérificateur distinct</span><strong>{synthesis.faithfulness_validation.independent_verifier_model ? "Oui" : "Non"}</strong></div>
                </div>

                <div className="editorial-note">
                  <ShieldCheck size={17} />
                  <p><strong>Lecture documentaire, pas fatwa autonome.</strong> Le modèle organise les éléments retrouvés ; les passages sourcés ci-dessous restent la référence à examiner.</p>
                </div>
              </article>
            ) : (
              <article className="evidence-only-card">
                <div><FileSearch size={22} /><span className="eyebrow">MODE TEXTES SEULEMENT</span></div>
                <h3>{evidence?.evidence_count ?? 0} passages, aucune synthèse générée.</h3>
                <p>Tu consultes directement le dossier de preuves classé par le moteur.</p>
              </article>
            )}

            <div className="bundle-ledger">
              <div className="ledger-heading"><Fingerprint size={16} /><span>Traçabilité du dossier</span></div>
              <div className="ledger-grid">
                <div><span>Bundle</span><strong>{evidence?.bundle_id ?? "—"}</strong></div>
                <div><span>Version</span><strong>{evidence?.bundle_version ?? "—"}</strong></div>
                <div><span>Retrieval</span><strong title={evidence?.retrieval}>{evidence?.retrieval ?? "—"}</strong></div>
                <div><span>Variantes</span><strong>{evidence?.query_variants?.length ?? 0}</strong></div>
              </div>
            </div>
          </section>
        )}

        <section className="sources-section" id="sources">
          <div className="section-heading editorial-heading">
            <div>
              <span className="eyebrow">TEXTES DU DOSSIER</span>
              <h2>Les sources restent visibles.</h2>
              <p>{evidence ? `${evidence.evidence_count} passages ont été sélectionnés pour cette recherche.` : "Les passages mobilisés apparaîtront ici après une recherche."}</p>
            </div>
            {evidence && <span className="folio-count">{String(evidence.evidence_count).padStart(2, "0")} FOLIOS</span>}
          </div>

          {evidence ? (
            <>
              <div className="sources-toolbar">
                <div className="source-filters">
                  <button type="button" className={sourceFilter === "all" ? "active" : ""} onClick={() => setSourceFilter("all")}>Toutes <span>{evidence.evidence_count}</span></button>
                  {synthesis && (
                    <button type="button" className={sourceFilter === "cited" ? "active" : ""} onClick={() => setSourceFilter("cited")}>Citées <span>{citedIds.size}</span></button>
                  )}
                </div>
                <label className="source-search">
                  <Search size={15} />
                  <input value={sourceQuery} onChange={(event) => setSourceQuery(event.target.value)} placeholder="Filtrer dans ces passages" />
                </label>
              </div>

              <div className="source-list">
                {filteredSources.map((source) => {
                  const cited = citedIds.has(source.source_id);
                  const path = source.citation.section_path ?? [];
                  const copyLabel = `source-${source.source_id}`;
                  const reference = `${source.citation.work ?? "Bidāyat al-Mujtahid"} — ${path.join(" > ") || "section non renseignée"} — vol. ${source.citation.volume ?? "—"}, p. ${source.citation.page ?? "—"}\n\n${source.passage_original}`;
                  return (
                    <article className={`source-card ${cited ? "cited" : ""}`} id={`source-${source.source_id}`} key={source.source_id}>
                      <div className="source-index-rail">
                        <strong>{source.source_id}</strong>
                        <span>#{String(source.rank).padStart(2, "0")}</span>
                        {cited && <i title="Source citée"><Check size={13} /></i>}
                      </div>

                      <div className="source-content">
                        <header className="source-header">
                          <div>
                            <span className="source-work">{source.citation.work ?? "Bidāyat al-Mujtahid"}</span>
                            <strong>{source.citation.author ?? "Ibn Rushd al-Ḥafīd"}</strong>
                          </div>
                          <button type="button" className="source-copy" onClick={() => copyText(reference, copyLabel)}>
                            {copied === copyLabel ? <Check size={14} /> : <Clipboard size={14} />}
                            {copied === copyLabel ? "Copiée" : "Copier la référence"}
                          </button>
                        </header>

                        <div className="source-breadcrumb" dir="auto">
                          <BookOpen size={14} />
                          <span>{path.length ? path.join("  /  ") : "Section non renseignée"}</span>
                        </div>

                        <blockquote dir="auto">{source.passage_original}</blockquote>

                        <footer className="source-footer">
                          <div className="folio-meta">
                            <span><small>Volume</small>{source.citation.volume ?? "—"}</span>
                            <span><small>Page</small>{source.citation.page ?? "—"}</span>
                            <span><small>Source</small>{source.citation.provider ?? "OpenITI"}</span>
                          </div>
                          <details className="integrity-details">
                            <summary><Fingerprint size={13} /> Intégrité & provenance</summary>
                            <div>
                              <p><span>Version URI</span><code>{source.citation.version_uri ?? "—"}</code></p>
                              <p><span>Chunk</span><code title={source.citation.chunk_id}>{shortHash(source.citation.chunk_id)}</code></p>
                              <p><span>Text hash</span><code title={source.citation.text_hash}>{shortHash(source.citation.text_hash)}</code></p>
                            </div>
                          </details>
                        </footer>
                      </div>
                    </article>
                  );
                })}
                {filteredSources.length === 0 && <div className="no-sources"><FileSearch size={18} />Aucun passage ne correspond à ce filtre.</div>}
              </div>
            </>
          ) : (
            <div className="sources-placeholder">
              <div className="folio-ghost">S1</div>
              <div>
                <strong>Un dossier de preuves se construit à chaque recherche.</strong>
                <p>Chaque source sera affichée ici avec son texte original, sa section, sa page et ses identifiants d’intégrité.</p>
              </div>
            </div>
          )}
        </section>

        <section className="corpus-section" id="corpus">
          <div className="section-heading">
            <div>
              <span className="eyebrow">CORPUS ACTUEL</span>
              <h2>Une bibliothèque modeste, une provenance stricte.</h2>
            </div>
            <BookMarked size={28} />
          </div>
          <div className="corpus-showcase">
            <div className="book-spine">
              <span>ابن رشد</span>
              <strong>بداية المجتهد</strong>
              <small>OPENITI · 0595H</small>
            </div>
            <div className="book-details">
              <span className="book-overline">OUVRAGE 01</span>
              <h3>Bidāyat al-Mujtahid wa-Nihāyat al-Muqtaṣid</h3>
              <p>Ibn Rushd al-Ḥafīd · texte arabe OpenITI · version documentaire actuellement indexée dans Athar.</p>
              <div className="book-stats">
                <div><strong>704</strong><span>pages repérées</span></div>
                <div><strong>1 538</strong><span>chunks</span></div>
                <div><strong>UNREVIEWED</strong><span>qualité éditoriale</span></div>
              </div>
              <div className="book-warning"><CircleDot size={14} />Le corpus reste volontairement présenté avec son niveau de revue actuel ; Athar ne transforme pas une donnée non vérifiée en certitude éditoriale.</div>
            </div>
          </div>
        </section>

        <section className="method-section" id="method">
          <div className="section-heading">
            <div>
              <span className="eyebrow">MÉTHODE ATHAR</span>
              <h2>Une chaîne lisible, pas une boîte noire.</h2>
            </div>
          </div>
          <div className="method-track">
            <div><i>01</i><Languages size={19} /><strong>Question</strong><span>FR ou AR</span></div>
            <span className="method-arrow">→</span>
            <div><i>02</i><Search size={19} /><strong>Retrieval</strong><span>E5 + terminologie</span></div>
            <span className="method-arrow">→</span>
            <div><i>03</i><Database size={19} /><strong>Hydratation</strong><span>PostgreSQL</span></div>
            <span className="method-arrow">→</span>
            <div><i>04</i><TextQuote size={19} /><strong>Preuves</strong><span>S1 · S2 · S3…</span></div>
            <span className="method-arrow">→</span>
            <div><i>05</i><ShieldCheck size={19} /><strong>Contrôles</strong><span>citations & soutien</span></div>
          </div>
        </section>

        <footer className="site-footer">
          <div className="footer-brand"><AtharMark /><div><strong>Athar</strong><span>Recherche islamique sourcée</span></div></div>
          <p>Prototype documentaire · Le LLM n’est jamais une source.</p>
          <a href="#research">Nouvelle recherche <ArrowUpRight size={14} /></a>
        </footer>
      </main>
    </div>
  );
}
