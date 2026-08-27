"use client";

import {
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Database,
  FileSearch,
  Library,
  LoaderCircle,
  Search,
  ServerCog,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

const WORK_URI = "0595IbnRushdHafid.BidayatMujtahid";

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

type Synthesis = {
  status: string;
  provider: {
    provider: string;
    model: string;
    elapsed_ms: number;
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

const EXAMPLES = [
  "في أي كتاب يناقش ابن رشد القراض؟",
  "ما المسائل التي يذكرها ابن رشد في كتاب الصلاة؟",
  "Que dit le corpus sur la prière du voyageur ?",
];

function readableProvider(value?: string) {
  if (!value) return "—";
  if (value.includes("groq")) return "Groq";
  if (value.includes("ollama")) return "Ollama local";
  return value;
}

function ms(value?: number) {
  if (value === undefined) return "—";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

export default function HomePage() {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<"synthesis" | "evidence">("synthesis");
  const [verifyClaims, setVerifyClaims] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetch("/api/research", { cache: "no-store" })
      .then((res) => res.json())
      .then((payload) => setHealth(payload))
      .catch(() => setHealth({ status: "offline" }));
  }, []);

  const citedIds = useMemo(() => {
    const ids = result?.synthesis?.draft.claims.flatMap((claim) => claim.citation_ids) ?? [];
    return new Set(ids);
  }, [result]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || loading) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          mode,
          limit: 5,
          work_uri: WORK_URI,
          verify_claims: verifyClaims,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "La recherche a échoué.");
      }
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue.");
    } finally {
      setLoading(false);
    }
  }

  const synthesis = result?.synthesis;
  const evidence = result?.evidence;
  const isHealthy = health?.status === "ok";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Library size={22} /></div>
          <div>
            <strong>Athar</strong>
            <span>Recherche islamique sourcée</span>
          </div>
        </div>

        <nav className="nav-stack" aria-label="Navigation">
          <button className="nav-item active"><Search size={18} /> Recherche</button>
          <button className="nav-item" disabled><BookOpen size={18} /> Bibliothèque <span>Bientôt</span></button>
          <button className="nav-item" disabled><ServerCog size={18} /> Administration <span>Bientôt</span></button>
        </nav>

        <div className="sidebar-card">
          <div className="sidebar-card-title"><Database size={16} /> Corpus actif</div>
          <strong>Bidāyat al-Mujtahid</strong>
          <p>Ibn Rushd al-Ḥafīd</p>
          <div className="mini-row"><span>OpenITI</span><span>1 538 passages</span></div>
        </div>

        <div className="system-status">
          <span className={`status-dot ${isHealthy ? "ok" : "warn"}`} />
          <div>
            <strong>{isHealthy ? "Système opérationnel" : "État du système"}</strong>
            <span>PostgreSQL + Qdrant</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <span className="eyebrow">BIBLIOTHÈQUE DOCUMENTAIRE</span>
            <h1>Interroger les sources, pas la mémoire d’une IA.</h1>
            <p>Pose une question en français ou en arabe. Chaque réponse reste reliée aux passages du corpus.</p>
          </div>
          <div className="topbar-badge"><ShieldCheck size={17} /> Sources traçables</div>
        </header>

        <section className="search-panel">
          <div className="mode-tabs" role="tablist">
            <button className={mode === "synthesis" ? "selected" : ""} onClick={() => setMode("synthesis")} type="button">
              <Sparkles size={17} /> Réponse sourcée
            </button>
            <button className={mode === "evidence" ? "selected" : ""} onClick={() => setMode("evidence")} type="button">
              <FileSearch size={17} /> Preuves seulement
            </button>
          </div>

          <form onSubmit={submit}>
            <label htmlFor="question">Ta question</label>
            <div className="composer">
              <textarea
                id="question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ex. Que dit Ibn Rushd au sujet du qirāḍ ?"
                dir="auto"
                rows={4}
              />
              <button className="submit-button" disabled={loading || !question.trim()} type="submit">
                {loading ? <LoaderCircle className="spin" size={19} /> : <Search size={19} />}
                {loading ? "Recherche…" : "Rechercher"}
              </button>
            </div>

            <div className="search-footer">
              <div className="examples">
                {EXAMPLES.map((example) => (
                  <button key={example} type="button" onClick={() => setQuestion(example)} dir="auto">{example}</button>
                ))}
              </div>
              {mode === "synthesis" && (
                <label className="toggle-line">
                  <input type="checkbox" checked={verifyClaims} onChange={(e) => setVerifyClaims(e.target.checked)} />
                  Vérifier le soutien des citations
                </label>
              )}
            </div>
          </form>
        </section>

        {loading && (
          <section className="loading-card">
            <LoaderCircle className="spin" size={22} />
            <div>
              <strong>{mode === "synthesis" ? "Construction d’une réponse sourcée" : "Recherche des meilleurs passages"}</strong>
              <span>Retrieval → PostgreSQL → preuves {mode === "synthesis" ? "→ synthèse → vérification" : ""}</span>
            </div>
          </section>
        )}

        {error && (
          <section className="error-card">
            <XCircle size={20} />
            <div><strong>La requête n’a pas abouti</strong><p>{error}</p></div>
          </section>
        )}

        {result && !loading && (
          <div className="results-grid">
            <section className="answer-column">
              {synthesis ? (
                <article className="answer-card">
                  <div className="card-heading">
                    <div>
                      <span className="section-label">RÉPONSE CANDIDATE</span>
                      <h2>{synthesis.draft.status === "INSUFFICIENT_EVIDENCE" ? "Preuves insuffisantes" : "Synthèse du corpus"}</h2>
                    </div>
                    <span className={`verdict ${synthesis.draft.status === "ANSWERED" ? "good" : "neutral"}`}>
                      {synthesis.draft.status === "ANSWERED" ? <CheckCircle2 size={15} /> : <FileSearch size={15} />}
                      {synthesis.draft.status === "ANSWERED" ? "Réponse structurée" : "Abstention"}
                    </span>
                  </div>

                  <div className="answer-text" dir="auto">{synthesis.draft.answer}</div>

                  {synthesis.draft.claims.length > 0 && (
                    <div className="claims-block">
                      <span className="section-label">AFFIRMATIONS ET SOURCES</span>
                      {synthesis.draft.claims.map((claim, index) => (
                        <div className="claim-row" key={`${claim.text}-${index}`}>
                          <div className="claim-index">{index + 1}</div>
                          <div>
                            <p dir="auto">{claim.text}</p>
                            <div className="citation-pills">
                              {claim.citation_ids.map((id) => <span key={id}>{id}</span>)}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="validation-grid">
                    <div>
                      <span>Structure</span>
                      <strong className={synthesis.structural_validation.valid ? "text-good" : "text-bad"}>
                        {synthesis.structural_validation.valid ? "Validée" : "Rejetée"}
                      </strong>
                    </div>
                    <div>
                      <span>Faithfulness</span>
                      <strong className={synthesis.faithfulness_validation.overall_verdict === "SUPPORTED" ? "text-good" : ""}>
                        {synthesis.faithfulness_validation.checked ? synthesis.faithfulness_validation.overall_verdict : "Non vérifié"}
                      </strong>
                    </div>
                    <div>
                      <span>Générateur</span>
                      <strong>{readableProvider(synthesis.provider.provider)}</strong>
                    </div>
                    <div>
                      <span>Modèle</span>
                      <strong className="truncate">{synthesis.provider.model}</strong>
                    </div>
                    <div>
                      <span>Temps génération</span>
                      <strong>{ms(synthesis.provider.elapsed_ms)}</strong>
                    </div>
                    <div>
                      <span>Vérificateur distinct</span>
                      <strong>{synthesis.faithfulness_validation.independent_verifier_model ? "Oui" : "Non"}</strong>
                    </div>
                  </div>

                  <div className="safety-note">
                    <ShieldCheck size={17} />
                    <span>Cette interface affiche une synthèse documentaire expérimentale, jamais une fatwa autonome. Les passages cités restent la référence.</span>
                  </div>
                </article>
              ) : (
                <article className="answer-card evidence-intro">
                  <span className="section-label">MODE DOCUMENTAIRE</span>
                  <h2>{evidence?.evidence_count ?? 0} passages retrouvés</h2>
                  <p>Aucune réponse n’a été générée. Consulte directement les textes sources classés par pertinence.</p>
                </article>
              )}
            </section>

            <aside className="meta-column">
              <div className="meta-card">
                <span className="section-label">DOSSIER DE PREUVES</span>
                <div className="meta-value">{evidence?.evidence_count ?? 0}</div>
                <p>passages PostgreSQL hydratés</p>
                <div className="meta-list">
                  <div><span>Bundle</span><strong>{evidence?.bundle_id ?? "—"}</strong></div>
                  <div><span>Retrieval</span><strong>{evidence?.retrieval ?? "—"}</strong></div>
                </div>
              </div>
            </aside>
          </div>
        )}

        {evidence && !loading && (
          <section className="sources-section">
            <div className="sources-heading">
              <div>
                <span className="section-label">SOURCES</span>
                <h2>Passages utilisés par le moteur</h2>
              </div>
              <span>{evidence.evidence_count} résultats</span>
            </div>

            <div className="source-list">
              {evidence.sources.map((source) => {
                const cited = citedIds.has(source.source_id);
                const path = source.citation.section_path ?? [];
                return (
                  <article className={`source-card ${cited ? "cited" : ""}`} key={source.source_id}>
                    <div className="source-topline">
                      <div className="source-id">{source.source_id}</div>
                      <div className="source-title">
                        <strong>{source.citation.work ?? "Bidāyat al-Mujtahid"}</strong>
                        <span>{source.citation.author ?? "Ibn Rushd al-Ḥafīd"}</span>
                      </div>
                      {cited && <span className="used-badge"><CheckCircle2 size={14} /> Citée</span>}
                    </div>

                    <div className="breadcrumb" dir="auto">
                      {path.length ? path.map((item, index) => (
                        <span key={`${item}-${index}`}>{index > 0 && <ChevronRight size={13} />} {item}</span>
                      )) : <span>Section non renseignée</span>}
                    </div>

                    <blockquote dir="auto">{source.passage_original}</blockquote>

                    <div className="source-meta">
                      <span>Volume {source.citation.volume ?? "—"}</span>
                      <span>Page {source.citation.page ?? "—"}</span>
                      <span>{source.citation.provider ?? "OpenITI"}</span>
                      <span>Rang #{source.rank}</span>
                    </div>

                    <details>
                      <summary>Traçabilité technique</summary>
                      <div className="trace-grid">
                        <div><span>Version</span><code>{source.citation.version_uri ?? "—"}</code></div>
                        <div><span>Chunk</span><code>{source.citation.chunk_id ?? "—"}</code></div>
                        <div><span>Text hash</span><code>{source.citation.text_hash ?? "—"}</code></div>
                      </div>
                    </details>
                  </article>
                );
              })}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
