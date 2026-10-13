import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import {
  ArrowUpRight,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  FileText,
  GitBranch,
  Globe,
  Layers,
  LoaderCircle,
  MessageSquare,
  Plus,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Square,
  Upload,
  X,
  Download,
} from "lucide-react";
import * as pdfjs from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { sample } from "./sample";
import type { Analysis, Claim, Source } from "./types";
import "@xyflow/react/dist/style.css";
import "./style.css";
pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker;
const labels = {
  supported: "Supported",
  contradicted: "Contradicted",
  insufficient: "Insufficient evidence",
  value: "Value judgment",
};
const initials = ["01", "02", "03"];
const baseRoles = [
  "Individual & community perspective",
  "Practical & institutional perspective",
  "Critical evidence perspective",
];
type Tab = "debate" | "graph" | "report" | "sources";
function App() {
  const [question, setQuestion] = useState("");
  const [roles, setRoles] = useState(baseRoles);
  const [sources, setSources] = useState<Source[]>([]);
  const [pasted, setPasted] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [web, setWeb] = useState(true);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [tab, setTab] = useState<Tab>("debate");
  const [selected, setSelected] = useState<Claim | null>(null);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [progress, setProgress] = useState("");
  const [visible, setVisible] = useState(0);
  const [error, setError] = useState("");
  const [suggestion, setSuggestion] = useState("");
  const [ready, setReady] = useState(false);
  const [provider, setProvider] = useState("Not connected");
  const [rolesConfirmed, setRolesConfirmed] = useState(false);
  const [notice, setNotice] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const abort = useRef<AbortController | null>(null);
  const runId = useRef(0);
  useEffect(() => {
    fetch("/api/status")
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => {
        if (s) {
          setReady(s.configured);
          setProvider(s.configured ? s.model : "Not connected");
        }
      })
      .catch(() => {});
    return () => {
      if (timer.current) clearInterval(timer.current);
      abort.current?.abort();
    };
  }, []);
  function stop() {
    runId.current++;
    if (timer.current) clearInterval(timer.current);
    abort.current?.abort();
    setBusy(false);
    setProgress("Stopped");
  }
  function loadSample() {
    stop();
    setError("");
    setNotice("");
    setQuestion(sample.question);
    setRoles([...sample.perspectives]);
    setSuggestion("");
    setRolesConfirmed(false);
    setAnalysis(sample);
    setSelected(null);
    setTab("debate");
    setVisible(0);
    setBusy(true);
    setProgress("Playing sample · round 1");
    timer.current = setInterval(
      () =>
        setVisible((v) => {
          const next = v + 1;
          if (next >= sample.arguments.length) {
            if (timer.current) clearInterval(timer.current);
            setBusy(false);
            setProgress("Sample complete");
          } else
            setProgress(
              next < 3
                ? "Playing sample · round 1"
                : "Playing sample · round 2",
            );
          return Math.min(next, sample.arguments.length);
        }),
      700,
    );
  }
  const textSources = [
    ...sources,
    ...(pasted.trim()
      ? [
          {
            id: "pasted",
            title: "Pasted text",
            text: pasted.trim(),
            kind: "document" as const,
          },
        ]
      : []),
  ];
  async function upload(files: FileList | null) {
    if (!files) return;
    setError("");
    setReading(true);
    const additions: Source[] = [];
    try {
      for (const f of Array.from(files)) {
        if (
          f.type !== "application/pdf" &&
          !f.name.toLowerCase().endsWith(".pdf")
        )
          throw Error(
            "Please upload PDF files. You can paste other text below.",
          );
        if (f.size > 5 * 1024 * 1024)
          throw Error("Each PDF must be smaller than 5 MB.");
        const pdf = await pdfjs.getDocument({ data: await f.arrayBuffer() })
          .promise;
        try {
          if (pdf.numPages > 30)
            throw Error("Please use PDFs with 30 pages or fewer.");
          for (let page = 1; page <= pdf.numPages; page++) {
            const content = await (await pdf.getPage(page)).getTextContent();
            const text = content.items
              .map((i) => ("str" in i ? i.str : ""))
              .join(" ");
            if (text.trim())
              additions.push({
                id: crypto.randomUUID(),
                title: f.name,
                page,
                text,
                kind: "document",
              });
          }
        } finally {
          await pdf.destroy();
        }
      }
      if (additions.length === 0)
        throw Error(
          "No readable text found. Scanned PDFs need OCR; paste their text for this version.",
        );
      if (
        [...sources, ...additions].reduce((sum, s) => sum + s.text.length, 0) +
          pasted.length >
        30000
      )
        throw Error("The combined document limit is 30,000 characters.");
      setSources((v) => [...v, ...additions]);
      setWeb(false);
      setRolesConfirmed(false);
      setNotice(
        "PDF text extracted locally. It is sent to the backend only when you prepare an analysis.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read the PDF.");
    } finally {
      setReading(false);
    }
  }
  async function prepare() {
    if (!question.trim()) return;
    setError("");
    setBusy(true);
    setProgress("Preparing perspectives");
    const controller = new AbortController();
    abort.current = controller;
    const id = ++runId.current;
    try {
      const r = await fetch("/api/prepare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          sources: textSources,
          include_web: web,
        }),
        signal: controller.signal,
      });
      const data = await r.json();
      if (!r.ok) throw Error(data.detail || "Could not prepare the debate.");
      if (id !== runId.current) return;
      setRoles(data.perspectives);
      setSuggestion(data.suggested_question || "");
      setRolesConfirmed(true);
      setNotice(
        "Review the perspectives, edit them if needed, then start the debate.",
      );
    } catch (e) {
      if (id === runId.current)
        setError(
          e instanceof Error ? e.message : "Could not prepare the debate.",
        );
    } finally {
      if (id === runId.current) {
        setBusy(false);
        setProgress("");
      }
    }
  }
  async function runLive() {
    setError("");
    setBusy(true);
    setVisible(0);
    setSelected(null);
    setTab("debate");
    setProgress("Starting analysis");
    const controller = new AbortController();
    abort.current = controller;
    const id = ++runId.current;
    setAnalysis({
      question,
      perspectives: roles,
      sources: textSources,
      claims: [],
      arguments: [],
      report: "",
      mode: "live",
    });
    try {
      const r = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          perspectives: roles,
          sources: textSources,
          include_web: web,
        }),
        signal: controller.signal,
      });
      if (!r.ok) {
        const d = await r.json();
        throw Error(d.detail || "Analysis unavailable.");
      }
      const reader = r.body?.getReader();
      if (!reader) throw Error("Streaming response unavailable.");
      let buffer = "";
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";
        for (const block of blocks) {
          if (!block.startsWith("data: ")) continue;
          const event = JSON.parse(block.slice(6));
          if (id !== runId.current) return;
          if (event.type === "error") throw Error(event.message);
          if (event.type === "progress") setProgress(event.message);
          if (event.type === "argument") {
            setAnalysis((a) =>
              a ? { ...a, arguments: [...a.arguments, event.argument] } : a,
            );
            setVisible((v) => v + 1);
          }
          if (event.type === "complete") {
            setAnalysis(event.analysis);
            setVisible(event.analysis.arguments.length);
            setProgress("Analysis complete");
          }
        }
      }
    } catch (e) {
      if (id === runId.current)
        setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      if (id === runId.current) setBusy(false);
    }
  }
  function exportReport() {
    if (!analysis?.report) return;
    const body = `# ${analysis.question}\n\nMode: ${analysis.mode}\n${analysis.model ? `Model: ${analysis.model}\n` : ""}\n${analysis.report}\n\n## Evidence\n${analysis.sources.map((s) => `- ${s.id}: ${s.title}${s.page ? ` (page ${s.page})` : ""}${s.url ? ` — ${s.url}` : ""}`).join("\n")}`;
    const url = URL.createObjectURL(
      new Blob([body], { type: "text/markdown" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "decision-atlas-report.md";
    a.click();
    URL.revokeObjectURL(url);
  }
  const samplePlaying = analysis?.mode === "sample" && busy;
  const graphNodes: Node[] = analysis
    ? [
        {
          id: "question",
          position: { x: 280, y: 0 },
          data: { label: analysis.question },
          style: {
            background: "#173e35",
            color: "white",
            border: 0,
            width: 280,
            padding: 18,
            borderRadius: 12,
          },
        },
        ...analysis.claims.map((c, i) => ({
          id: c.id,
          position: { x: (i % 3) * 285, y: 140 + Math.floor(i / 3) * 180 },
          data: { label: `${labels[c.status]}\n\n${c.text}` },
          style: {
            width: 245,
            padding: 18,
            borderRadius: 12,
            borderColor: c.status === "contradicted" ? "#d98d79" : "#bdcfc3",
            background: c.status === "value" ? "#f4efe4" : "#fff",
            color: "#23382f",
            fontSize: 12,
          },
        })),
        ...analysis.arguments
          .filter((a) => a.round === 2)
          .map((a) => ({
            id: `revision-${a.agent}`,
            position: { x: a.agent * 285, y: 500 },
            data: {
              label: `${analysis.perspectives[a.agent]} · revision\n\n${a.position}`,
            },
            style: {
              width: 245,
              padding: 14,
              borderRadius: 10,
              background: "#f5eee0",
              borderColor: "#ded0ae",
              fontSize: 11,
            },
          })),
        ...analysis.sources.map((s, i) => ({
          id: s.id,
          position: { x: i * 330 + 80, y: 680 },
          data: { label: s.title },
          style: {
            width: 260,
            padding: 14,
            borderRadius: 10,
            background: "#edf1e8",
            fontSize: 12,
          },
        })),
      ]
    : [];
  const graphEdges: Edge[] = analysis
    ? [
        ...analysis.claims.map((c) => ({
          id: `q-${c.id}`,
          source: "question",
          target: c.id,
          style: { stroke: "#a9b9af" },
          markerEnd: { type: MarkerType.ArrowClosed },
        })),
        ...analysis.claims.flatMap((c) =>
          c.source_ids.map((s) => ({
            id: `${s}-${c.id}`,
            source: s,
            target: c.id,
            label: c.status === "contradicted" ? "contradicts" : "evidence",
            style: {
              stroke: c.status === "contradicted" ? "#c47462" : "#649378",
            },
            markerEnd: { type: MarkerType.ArrowClosed },
          })),
        ),
        ...analysis.arguments
          .filter((a) => a.round === 2)
          .flatMap((a) =>
            a.challenges
              .filter((c) => analysis.claims.some((x) => x.id === c))
              .map((c) => ({
                id: `challenge-${a.agent}-${c}`,
                source: `revision-${a.agent}`,
                target: c,
                label: "challenges",
                style: { stroke: "#bc9252" },
                animated: false,
              })),
          ),
      ]
    : [];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
          <span className="brand-icon">
            <Layers size={23} />
          </span>
          <span>
            decision<span className="brand-light">atlas</span>
          </span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <button className="nav-item active" onClick={() => setTab("debate")}>
          <MessageSquare size={18} /> Debate studio <span className="nav-dot" />
        </button>
        <button className="nav-item" onClick={loadSample} disabled={reading}>
          <BookOpen size={18} /> Explore a sample <ArrowUpRight size={14} />
        </button>
        <div className="sidebar-note">
          <GitBranch size={24} />
          <h3>
            Make room for
            <br />
            another perspective.
          </h3>
          <p>
            Trace the evidence.
            <br />
            Understand the trade-offs.
          </p>
          <span>THINK BEYOND THE FIRST ANSWER</span>
        </div>
        <div className="sidebar-bottom">
          <div className="avatar">DA</div>
          <div>
            Portfolio edition<small>Model-independent prototype</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            Workspace <ChevronRight size={14} /> <strong>Debate studio</strong>
          </div>
          <span className="connection">
            <span className={ready ? "status-dot online" : "status-dot"} />
            {ready ? provider : "Model connection pending"}
          </span>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">MULTI-PERSPECTIVE DECISION SUPPORT</div>
              <h1>A clearer view of the debate.</h1>
              <p>
                Bring a question. Explore the arguments. Follow the evidence.
              </p>
            </div>
            <span className="edition">
              <Sparkles size={15} /> Early build
            </span>
          </div>
          <div className="studio-grid">
            <section className="setup-panel">
              <div className="panel-heading">
                <span className="section-number">01</span>
                <h2>Frame your question</h2>
              </div>
              <label className="field-label" htmlFor="question">
                What would you like to explore?
              </label>
              <textarea
                id="question"
                className="question-input"
                placeholder="Should universities require 75% attendance?"
                maxLength={800}
                value={question}
                disabled={busy}
                onChange={(e) => {
                  setQuestion(e.target.value);
                  setRolesConfirmed(false);
                  setSuggestion("");
                }}
              />
              <div className="input-footer">
                <span>Ask a question with competing perspectives</span>
                <span>{question.length}/800</span>
              </div>
              {suggestion && (
                <div className="suggestion">
                  <Sparkles size={16} />
                  <div>
                    <strong>Optional neutral framing</strong>
                    <p>{suggestion}</p>
                    <button
                      onClick={() => {
                        setQuestion(suggestion);
                        setSuggestion("");
                        setRolesConfirmed(false);
                      }}
                    >
                      Use this question <ArrowRight size={13} />
                    </button>
                  </div>
                </div>
              )}
              <div className="divider" />
              <div className="section-title">
                <h3>Evidence collection</h3>
                <span>OPTIONAL</span>
              </div>
              <label
                className={"upload-zone " + (busy || reading ? "disabled" : "")}
              >
                <Upload size={21} />
                <strong>
                  {reading ? "Reading document…" : "Add your documents"}
                </strong>
                <span>PDF · up to 5 MB / 30 pages each</span>
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  multiple
                  disabled={busy || reading}
                  onChange={(e) => {
                    void upload(e.target.files);
                    e.target.value = "";
                  }}
                />
              </label>
              {sources.length > 0 && (
                <div className="documents">
                  {Array.from(new Set(sources.map((s) => s.title))).map(
                    (title) => (
                      <div key={title}>
                        <FileText size={14} />
                        <span>{title}</span>
                        <button
                          aria-label={`Remove ${title}`}
                          disabled={busy}
                          onClick={() => {
                            setSources((s) =>
                              s.filter((x) => x.title !== title),
                            );
                            setRolesConfirmed(false);
                          }}
                        >
                          <X size={14} />
                        </button>
                      </div>
                    ),
                  )}
                </div>
              )}
              <button
                className="text-button paste-button"
                disabled={busy}
                onClick={() => setShowPaste((v) => !v)}
              >
                <Plus size={14} />
                {showPaste ? "Hide pasted text" : "Or paste source text"}
              </button>
              {showPaste && (
                <textarea
                  aria-label="Pasted source text"
                  className="paste-input"
                  placeholder="Paste an article, policy, or document passage…"
                  maxLength={Math.max(
                    0,
                    30000 - sources.reduce((n, s) => n + s.text.length, 0),
                  )}
                  disabled={busy}
                  value={pasted}
                  onChange={(e) => {
                    setPasted(e.target.value);
                    if (e.target.value.trim()) setWeb(false);
                    setRolesConfirmed(false);
                  }}
                />
              )}
              <label className="toggle-row">
                <span>
                  <Globe size={17} />
                  <span>
                    {textSources.length
                      ? "Include web sources"
                      : "Search the web"}
                    <small>
                      {textSources.length
                        ? "Supplement your documents"
                        : "When no documents are provided"}
                    </small>
                  </span>
                </span>
                <input
                  type="checkbox"
                  checked={web}
                  disabled={busy}
                  onChange={(e) => {
                    setWeb(e.target.checked);
                    setRolesConfirmed(false);
                  }}
                />
                <span className={"toggle " + (web ? "on" : "")} />
              </label>
              <div className="divider" />
              <div className="section-title">
                <h3>Perspectives</h3>
                <span>3 AGENTS</span>
              </div>
              <p className="helper">
                {rolesConfirmed
                  ? "Suggested for your question. Edit before starting."
                  : "Editable placeholders. Topic-specific suggestions need a model."}
              </p>
              <div className="role-inputs">
                {roles.map((role, i) => (
                  <label key={i}>
                    <span className={`agent-avatar agent-${i}`}>
                      {initials[i]}
                    </span>
                    <input
                      aria-label={`Perspective ${i + 1}`}
                      maxLength={100}
                      value={role}
                      disabled={busy}
                      onChange={(e) =>
                        setRoles((v) =>
                          v.map((r, j) => (j === i ? e.target.value : r)),
                        )
                      }
                    />
                  </label>
                ))}
              </div>
              <div className="rounds">
                <GitBranch size={16} />
                <span>2 rounds</span>
                <span>
                  Arguments <ArrowRight size={12} /> Revisions
                </span>
              </div>
              {error && (
                <div className="error" role="alert">
                  {error}
                </div>
              )}
              {notice && <p className="notice">{notice}</p>}
              <button
                className="primary-button"
                disabled={
                  busy ||
                  reading ||
                  !question.trim() ||
                  !ready ||
                  roles.some((r) => !r.trim())
                }
                onClick={() => void (rolesConfirmed ? runLive() : prepare())}
              >
                {busy ? (
                  <LoaderCircle size={17} className="spin" />
                ) : (
                  <Sparkles size={17} />
                )}{" "}
                {rolesConfirmed ? "Start debate" : "Prepare perspectives"}{" "}
                <ArrowRight size={16} />
              </button>
              {!ready && (
                <p className="pending-note">
                  Live analysis becomes available when a model and evidence
                  services are connected.
                </p>
              )}
              <button
                className="secondary-button"
                disabled={reading || busy}
                onClick={loadSample}
              >
                Explore the sample debate <ArrowUpRight size={15} />
              </button>
            </section>
            <section className="analysis-panel">
              <div className="analysis-heading">
                <div className="panel-heading">
                  <span className="section-number">02</span>
                  <h2>Follow the reasoning</h2>
                </div>
                <span className="tiny-label">
                  {analysis?.mode === "sample"
                    ? "ILLUSTRATIVE SAMPLE"
                    : analysis
                      ? "LIVE ANALYSIS"
                      : "YOUR ANALYSIS"}
                </span>
              </div>
              <div className="tabs" role="tablist" aria-label="Analysis views">
                {(
                  [
                    { id: "debate", label: "Debate", icon: MessageSquare },
                    { id: "graph", label: "Argument graph", icon: GitBranch },
                    { id: "report", label: "Report", icon: FileText },
                    { id: "sources", label: "Sources", icon: BookOpen },
                  ] as const
                ).map((t) => (
                  <button
                    role="tab"
                    aria-selected={tab === t.id}
                    key={t.id}
                    className={tab === t.id ? "selected" : ""}
                    onClick={() => setTab(t.id)}
                  >
                    <t.icon size={16} />
                    {t.label}
                  </button>
                ))}
              </div>
              {!analysis ? (
                <div className="empty-state">
                  <div className="orbit">
                    <span className="orbit-icon oi-one">
                      <MessageSquare size={24} />
                    </span>
                    <span className="orbit-icon oi-two">
                      <ShieldCheck size={22} />
                    </span>
                    <span className="orbit-icon oi-three">
                      <GitBranch size={22} />
                    </span>
                    <span className="orbit-center">
                      <Layers size={37} />
                    </span>
                  </div>
                  <div className="eyebrow">A QUESTION. THREE PERSPECTIVES.</div>
                  <h2>
                    Good decisions begin
                    <br />
                    with better questions.
                  </h2>
                  <p>
                    Watch perspectives challenge each other,
                    <br />
                    then inspect what the evidence actually supports.
                  </p>
                  <button className="text-button" onClick={loadSample}>
                    See how it works <ArrowRight size={16} />
                  </button>
                  <div className="feature-row">
                    <div>
                      <MessageSquare size={19} />
                      <strong>Visible debate</strong>
                      <span>Arguments & revisions</span>
                    </div>
                    <div>
                      <ScanLine size={19} />
                      <strong>Traceable claims</strong>
                      <span>Sources & uncertainty</span>
                    </div>
                    <div>
                      <GitBranch size={19} />
                      <strong>Connected ideas</strong>
                      <span>An inspectable graph</span>
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <div className="analysis-context">
                    <span
                      className={
                        analysis.mode === "sample"
                          ? "sample-badge"
                          : "live-badge"
                      }
                    >
                      {analysis.mode === "sample"
                        ? "Sample replay"
                        : "Live run"}
                    </span>
                    <span>{analysis.question}</span>
                  </div>
                  {analysis.mode === "sample" && (
                    <div className="sample-disclaimer">
                      <CircleHelp size={15} />
                      <span>
                        Hand-authored example with illustrative sources and
                        labels. No model was called.
                      </span>
                    </div>
                  )}
                  <div className="run-status" aria-live="polite">
                    <span>
                      <span
                        className={"status-dot " + (busy ? "online" : "")}
                      />
                      {progress || "Ready"}
                    </span>
                    {busy && (
                      <button onClick={stop}>
                        <Square size={11} /> Stop
                      </button>
                    )}
                    {samplePlaying && (
                      <button
                        onClick={() => {
                          if (timer.current) clearInterval(timer.current);
                          setVisible(sample.arguments.length);
                          setBusy(false);
                          setProgress("Sample complete");
                        }}
                      >
                        Show all
                      </button>
                    )}
                  </div>
                  {tab === "debate" && (
                    <div className="debate-content">
                      {[1, 2].map((round) => (
                        <div key={round} className="debate-round">
                          <div className="round-heading">
                            <span>
                              ROUND {round.toString().padStart(2, "0")}
                            </span>
                            <h3>
                              {round === 1
                                ? "Opening perspectives"
                                : "Challenges & revisions"}
                            </h3>
                            <span className="round-line" />
                          </div>
                          {analysis.arguments
                            .slice(0, visible)
                            .filter((a) => a.round === round)
                            .map((a) => (
                              <article
                                className="argument-card"
                                key={`${a.agent}-${a.round}`}
                              >
                                <div className="argument-title">
                                  <span
                                    className={`agent-avatar agent-${a.agent}`}
                                  >
                                    {initials[a.agent]}
                                  </span>
                                  <div>
                                    <strong>
                                      {analysis.perspectives[a.agent]}
                                    </strong>
                                    <span>{a.position}</span>
                                  </div>
                                  {a.round === 2 && (
                                    <span className="revised">
                                      <Check size={12} /> Revised
                                    </span>
                                  )}
                                </div>
                                <p>{a.body}</p>
                                <div className="claim-chips">
                                  {a.claim_ids.map((id) => {
                                    const c = analysis.claims.find(
                                      (c) => c.id === id,
                                    );
                                    return c ? (
                                      <button
                                        key={id}
                                        className={`claim-chip ${c.status}`}
                                        onClick={() => setSelected(c)}
                                      >
                                        <span />
                                        {labels[c.status]}{" "}
                                        <ArrowUpRight size={12} />
                                      </button>
                                    ) : (
                                      <span className="claim-chip" key={id}>
                                        Verification pending
                                      </span>
                                    );
                                  })}
                                </div>
                                {a.challenges.length > 0 && (
                                  <div className="challenge-links">
                                    Challenges:{" "}
                                    {a.challenges.map((id) => (
                                      <button
                                        key={id}
                                        onClick={() =>
                                          setSelected(
                                            analysis.claims.find(
                                              (c) => c.id === id,
                                            ) || null,
                                          )
                                        }
                                      >
                                        {id}
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </article>
                            ))}
                          {busy &&
                            visible < round * 3 &&
                            visible >= (round - 1) * 3 && (
                              <div className="thinking">
                                <LoaderCircle size={15} className="spin" />{" "}
                                {analysis.mode === "sample"
                                  ? "Revealing the next sample perspective…"
                                  : "Waiting for the next perspective…"}
                              </div>
                            )}
                        </div>
                      ))}
                    </div>
                  )}
                  {tab === "graph" && (
                    <div className="graph-view">
                      <div className="graph-legend">
                        <span>
                          <i className="green" />
                          Evidence relation
                        </span>
                        <span>
                          <i className="orange" />
                          Challenge / contradiction
                        </span>
                        <span>Click a claim to inspect</span>
                      </div>
                      {analysis.claims.length ? (
                        <ReactFlow
                          nodes={graphNodes}
                          edges={graphEdges}
                          fitView
                          minZoom={0.3}
                          maxZoom={1.5}
                          onNodeClick={(_, node) =>
                            setSelected(
                              analysis.claims.find((c) => c.id === node.id) ||
                                null,
                            )
                          }
                          nodesDraggable={false}
                          nodesConnectable={false}
                        >
                          <Background color="#d9e0d8" gap={20} />
                          <Controls showInteractive={false} />
                        </ReactFlow>
                      ) : (
                        <p className="view-note">
                          The graph appears after claim verification.
                        </p>
                      )}
                    </div>
                  )}
                  {tab === "report" && (
                    <div className="report-view">
                      <div className="report-heading">
                        <div>
                          <div className="eyebrow">DECISION BRIEF</div>
                          <h2>The trade-offs, made clear.</h2>
                        </div>
                        <button
                          className="icon-button"
                          aria-label="Download report"
                          disabled={!analysis.report || busy}
                          onClick={exportReport}
                        >
                          <Download size={18} />
                        </button>
                      </div>
                      {!analysis.report || samplePlaying ? (
                        <p className="view-note">
                          The report will appear when the debate is complete.
                        </p>
                      ) : (
                        <>
                          {analysis.report.split("\n\n").map((p, i) => (
                            <p key={i}>{p}</p>
                          ))}
                          <div className="report-footnote">
                            {analysis.mode === "sample"
                              ? "Illustrative sample"
                              : "Model-generated analysis"}{" "}
                            · Decision support ·{" "}
                            {analysis.report.split(/\s+/).length} words
                          </div>
                        </>
                      )}
                    </div>
                  )}
                  {tab === "sources" && (
                    <div className="sources-view">
                      <h3>Evidence available to the agents</h3>
                      <p className="helper">
                        A supporting passage does not establish source quality
                        or universal truth.
                      </p>
                      {analysis.sources.map((s) => (
                        <article key={s.id} className="source-card">
                          <div>
                            <BookOpen size={18} />
                            <strong>
                              {s.title}
                              {s.page ? ` · page ${s.page}` : ""}
                            </strong>
                            <span>{s.id}</span>
                          </div>
                          <p>{s.text}</p>
                          {s.url && /^https?:\/\//.test(s.url) && (
                            <a href={s.url} target="_blank" rel="noreferrer">
                              Open original source <ArrowUpRight size={13} />
                            </a>
                          )}
                        </article>
                      ))}
                    </div>
                  )}
                </>
              )}
            </section>
          </div>
          <footer className="page-footer">
            <span>
              <ShieldCheck size={14} /> Evidence supports claims. It does not
              settle every value judgment.
            </span>
            <span>Built for thoughtful disagreement.</span>
          </footer>
        </main>
      </div>
      {selected && analysis && (
        <div className="drawer-backdrop" onClick={() => setSelected(null)}>
          <aside
            className="claim-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="claim-heading"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setSelected(null);
              if (e.key === "Tab") {
                const items =
                  e.currentTarget.querySelectorAll<HTMLElement>(
                    "button,a[href]",
                  );
                const first = items[0],
                  last = items[items.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                  e.preventDefault();
                  last?.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                  e.preventDefault();
                  first?.focus();
                }
              }
            }}
          >
            <div className="drawer-top">
              <span className="eyebrow">CLAIM INSPECTION</span>
              <button
                autoFocus
                aria-label="Close claim inspection"
                className="icon-button"
                onClick={() => setSelected(null)}
              >
                <X size={20} />
              </button>
            </div>
            <span className={`claim-chip ${selected.status}`}>
              {labels[selected.status]}
            </span>
            <h2 id="claim-heading">{selected.text}</h2>
            <p className="claim-agent">
              From {analysis.perspectives[selected.agent]}
            </p>
            <h3>Why this label?</h3>
            <p>{selected.explanation}</p>
            <h3>Source passages</h3>
            {selected.source_ids.length ? (
              selected.source_ids.map((id) => {
                const s = analysis.sources.find((s) => s.id === id);
                return s ? (
                  <blockquote key={id}>
                    <strong>
                      {s.title}
                      {s.page ? ` · page ${s.page}` : ""}
                    </strong>
                    <p>{s.text}</p>
                    {s.url && /^https?:\/\//.test(s.url) && (
                      <a href={s.url} target="_blank" rel="noreferrer">
                        View source <ArrowUpRight size={13} />
                      </a>
                    )}
                  </blockquote>
                ) : null;
              })
            ) : (
              <p>No factual source is attached to this claim.</p>
            )}
            <div className="drawer-note">
              {analysis.mode === "sample"
                ? "This label was hand-authored for the sample."
                : "This label is a model assessment of the available passages."}{" "}
              “Supported” does not mean independently proven true.
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
