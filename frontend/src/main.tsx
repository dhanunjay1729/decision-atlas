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
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import * as pdfjs from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { sample } from "./sample";
import {Accounts, MyDebates, useAccount} from "./accounts";
import {featuredUrl, FeaturedDebates, PublishDebate, ShareDebate, type Allowance} from "./community";
import type { Analysis, Claim, Source } from "./types";
import "@xyflow/react/dist/style.css";
import "./style.css";
pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker;
const labels = {
  supported: "Supported",
  contradicted: "Contradicted",
  insufficient: "Insufficient evidence",
  value: "Value judgment",
  unverified: "Model knowledge · unverified",
  review: "Requires review",
};
const initials = ["01", "02", "03", "04", "05"];
type Tab = "debate" | "graph" | "report" | "sources";
function linkedDebate() {
  const query=new URLSearchParams(window.location.search);
  return query.has('share') ? 'share:'+query.get('share') : query.has('debate') ? 'featured:'+query.get('debate') : null;
}

function App() {
  const account=useAccount();
  const [historyVersion,setHistoryVersion]=useState(0);
  const previousAccount=useRef<string|null>(null);
  const [question, setQuestion] = useState("");
  const [roles, setRoles] = useState<string[]>(["", "", ""]);
  const [sources, setSources] = useState<Source[]>([]);
  const [pasted, setPasted] = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [web, setWeb] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [setupExpanded, setSetupExpanded] = useState(false);
  const analysisRef = useRef<HTMLElement>(null);
  const [tab, setTab] = useState<Tab>("debate");
  const [selected, setSelected] = useState<Claim | null>(null);
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [progress, setProgress] = useState("");
  const [visible, setVisible] = useState(0);
  const [error, setError] = useState("");
  const [suggestion, setSuggestion] = useState("");
  const [ready, setReady] = useState(false);
  const [rolesConfirmed, setRolesConfirmed] = useState(false);
  const [notice, setNotice] = useState("");
  const [allowance, setAllowance] = useState<Allowance|null>(null);
  const [page,setPage] = useState<'studio'|'featured'|'account'|'history'>('studio');
  const [featuredVersion,setFeaturedVersion] = useState(0);
  const [sharedId, setSharedId] = useState(linkedDebate);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState('');
  const accountIdentity = useRef(account.user?.uid ?? null);
  accountIdentity.current = account.user?.uid ?? null;
  const allowanceRequest = useRef(0);
  function refreshAllowance() {
    const request = ++allowanceRequest.current;
    const uid = accountIdentity.current;
    account.getToken().then(token => fetch('/api/allowance', {headers: token ? {Authorization: 'Bearer ' + token} : {}}))
      .then(response => response.ok ? response.json() : null)
      .then(data => {if (data && request === allowanceRequest.current && uid === accountIdentity.current) setAllowance(data);})
      .catch(() => {});
  }
  useEffect(()=>{refreshAllowance();const timer=setInterval(refreshAllowance,60000);return()=>clearInterval(timer);},[]);
  const validRoles = roles.every(r => r.trim()) && new Set(roles.map(r=>r.trim().toLowerCase())).size === roles.length;
  const dailyPaused=allowance?.daily?.available===false;
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const abort = useRef<AbortController | null>(null);
  const runId = useRef(0);
  useEffect(() => {
    fetch("/api/status")
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => {
        if (s) {
          setReady(s.configured);
        }
      })
      .catch(() => {});
    return () => {
      if (timer.current) clearInterval(timer.current);
      abort.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (analysis && page === "studio") {
      setSetupExpanded(false);
      analysisRef.current?.scrollIntoView({behavior: "instant", block: "start"});
      analysisRef.current?.focus({preventScroll: true});
    }
  }, [analysis?.question, page]);
  function stop() {
    runId.current++;
    if (timer.current) clearInterval(timer.current);
    abort.current?.abort();
    setBusy(false);
    setProgress("Stopped");
  }
  function newDebate() {
    clearSharedLink();
    stop();
    setAnalysis(null);
    setSelected(null);
    setQuestion("");
    setRoles(["", "", ""]);
    setSources([]);
    setPasted("");
    setShowPaste(false);
    setWeb(false);
    setSuggestion("");
    setNotice("");
    setError("");
    setRolesConfirmed(false);
    setSetupExpanded(false);
    setTab("debate");
    requestAnimationFrame(() => document.getElementById("question")?.focus());
  }
  function loadSample() {
    clearSharedLink();
    setPage("studio");
    stop();
    setError("");
    setNotice("");
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
      setRolesConfirmed(false);
      setNotice(
        "PDF text extracted locally. Documents are optional and do not change your web-search setting.",
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
          participant_count: roles.length,
        }),
        signal: controller.signal,
      });
      const data = await r.json();
      if (!r.ok) throw Error(typeof data.detail === "string" ? data.detail : "Enter a complete question and choose 2–5 distinct perspectives.");
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
    clearSharedLink();
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
      const token=await account.getToken();
      if(id!==runId.current)return;
      const r = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token?{Authorization:"Bearer "+token}:{}) },
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
          if (event.type === "sources") setAnalysis(a => a ? {...a,sources:event.sources} : a);
          if (event.type === "argument") {
            setAnalysis((a) =>
              a ? { ...a, arguments: [...a.arguments, event.argument] } : a,
            );
            setVisible((v) => v + 1);
          }
          if (event.type === "complete") {
            setAnalysis(event.analysis);
            setVisible(event.analysis.arguments.length);
            setProgress(event.analysis.history_saved ? "Analysis complete · saved privately" : "Analysis complete");
            if(event.analysis.history_saved)setHistoryVersion(value=>value+1);
            if(event.analysis.history_notice)setNotice(event.analysis.history_notice);
          }
        }
      }
    } catch (e) {
      if (id === runId.current)
        setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      if (id === runId.current) {setBusy(false);refreshAllowance();}
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
  useEffect(()=>{
    const uid=account.user?.uid??null;
    if(previousAccount.current===uid)return;
    const hadPrivateAccount=!!previousAccount.current;
    previousAccount.current=uid;
    allowanceRequest.current++;
    setAllowance(null);
    if (!analysis?.published && !analysis?.shared) {stop();setAnalysis(null);setSelected(null);setVisible(0);}
    setNotice("");setError("");refreshAllowance();
    if(hadPrivateAccount){setQuestion("");setRoles(current=>current.map(()=>""));setSources([]);setPasted("");setSuggestion("");setRolesConfirmed(false);}
  },[account.user?.uid]);
  function clearSharedLink() {
    setSharedId(null);
    setShareError('');
    setShareLoading(false);
    const url = new URL(window.location.href);
    if (url.searchParams.has('debate') || url.searchParams.has('share')) {
      url.searchParams.delete('debate');
      url.searchParams.delete('share');
      window.history.pushState({}, '', url);
    }
  }
  function openPublicDebate(value: Analysis) {
    stop();
    setAnalysis(value);
    setVisible(value.arguments.length);
    setSelected(null);
    setTab('debate');
    setProgress('Featured debate');
    setPage('studio');
    if (value.public_id) {
      window.history.pushState({}, '', featuredUrl(value.public_id));
      setSharedId('featured:'+value.public_id);
    }
  }
  useEffect(() => {
    const changed = () => {
      const id = linkedDebate();
      setSharedId(id);
      setShareError('');
      if (!id) setAnalysis(current => (current?.published || current?.shared) ? null : current);
    };
    window.addEventListener('popstate', changed);
    return () => window.removeEventListener('popstate', changed);
  }, []);
  useEffect(() => {
    if (account.loading || !sharedId) return;
    const [kind,id]=sharedId.split(':');
    const unlisted=kind==='share';
    if ((unlisted ? analysis?.share_id===id && analysis.shared : analysis?.public_id===id && analysis.published)) {setShareLoading(false);return;}
    if (!/^[a-f0-9]{24}$/.test(id)) {
      setShareError('This debate link is invalid.');
      setShareLoading(false);
      setAnalysis(current => (current?.published || current?.shared) ? null : current);
      return;
    }
    const controller = new AbortController();
    let active = true;
    stop();
    setAnalysis(null);
    setVisible(0);
    setShareLoading(true);
    setShareError('');
    fetch((unlisted ? '/api/shares/' : '/api/featured/') + id, {signal: controller.signal}).then(async response => {
      if (!response.ok) throw Error(response.status === 404 ? 'This debate link is unavailable.' : 'Could not open the shared debate. Please try again.');
      return response.json();
    }).then(data => {
      if (!active) return;
      stop();
      setAnalysis({...data.analysis, ...(unlisted ? {share_id:data.id,shared:true} : {public_id:data.id,published:true}), publish_token: undefined});
      setVisible(data.analysis.arguments.length);
      setSelected(null);
      setTab('debate');
      setProgress(unlisted ? 'Shared debate' : 'Featured debate');
      setPage('studio');
    }).catch(error => {if (active && !controller.signal.aborted) setShareError(error instanceof Error ? error.message : 'Could not open this debate.');})
      .finally(() => {if (active) setShareLoading(false);});
    return () => {active = false; controller.abort();};
  }, [sharedId, account.loading, account.user?.uid]);
  const samplePlaying = analysis?.mode === "sample" && busy;
  const graphNodes: Node[] = analysis
    ? [
        {
          id: "question",
          position: { x: (analysis.perspectives.length - 1)*142, y: 0 },
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
          position: { x: c.agent * 285, y: 140 + analysis.claims.slice(0,i).filter(x=>x.agent===c.agent).length*180 },
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
            position: { x: a.agent * 285, y: 160 + Math.max(...analysis.perspectives.map((_,j)=>analysis.claims.filter(c=>c.agent===j).length))*180 },
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
          position: { x: i * 330 + 80, y: 330 + Math.max(...analysis.perspectives.map((_,j)=>analysis.claims.filter(c=>c.agent===j).length))*180 },
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
            label: c.status === "contradicted" ? "contradicts" : c.status === "supported" ? "supports" : "referenced passage",
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
        <button className={"nav-item "+(page==="studio"?"active":"")} onClick={() => {setPage("studio");setTab("debate");}}>
          <MessageSquare size={18} /> Debate studio <span className="nav-dot" />
        </button>
        <button className="nav-item" onClick={loadSample} disabled={reading}>
          <BookOpen size={18} /> Explore a sample <ArrowUpRight size={14} />
        </button>
        <button className={"nav-item "+(page==="featured"?"active":"")} onClick={()=>setPage("featured")}><Globe size={18}/> Featured debates</button>
        <button className={"nav-item "+(page==="history"?"active":"")} onClick={()=>setPage("history")}><FileText size={18}/> My debates</button>
        <button className={"nav-item "+(page==="account"?"active":"")} onClick={()=>setPage("account")}><ShieldCheck size={18}/> {account.user ? "My account" : "Sign in / Sign up"}</button>
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
            Explore the trade-offs<small>2–5 perspectives · 2 rounds</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            Workspace <ChevronRight size={14} /> <strong>{page==="featured"?"Featured debates":page==="history"?"My debates":page==="account"?"My account":"Debate studio"}</strong>
          </div>
          <span className="connection">
            <span className={ready ? "status-dot online" : "status-dot"} />
            {ready ? "Live models connected" : "Model connection pending"}
          </span>
        </header>
        <nav className="mobile-nav" aria-label="Workspace navigation">
          <button aria-current={page==='studio'?'page':undefined} onClick={()=>setPage('studio')}>Studio</button>
          <button aria-current={page==='featured'?'page':undefined} onClick={()=>setPage('featured')}>Featured</button>
          <button aria-current={page==='history'?'page':undefined} onClick={()=>setPage('history')}>My debates</button>
          <button aria-current={page==='account'?'page':undefined} onClick={()=>setPage('account')}>{account.user?'Account':'Sign in / Sign up'}</button>
        </nav>
        <main>
          {shareLoading && <p className="notice" role="status">Opening shared debate…</p>}
          {shareError && <div className="shared-link-error" role="alert"><p>{shareError}</p><button className="secondary-button" onClick={newDebate}>Start a new debate</button></div>}
          {page === 'account' ? <Accounts account={account}/> : page === 'history' ? <><MyDebates getToken={account.getToken} version={historyVersion} onOpen={a=>{clearSharedLink();stop();setAnalysis(a);setVisible(a.arguments.length);setSelected(null);setTab('debate');setProgress('Saved private debate');setPage('studio');}}/>{!account.user&&<button className='secondary-button' onClick={()=>setPage('account')}>Sign in / Sign up</button>}</> : page === 'featured' ? <FeaturedDebates getToken={account.getToken} owner={!!account.user && !!allowance?.owner} refresh={featuredVersion} onOpen={openPublicDebate}/> : <>
          {dailyPaused && <div className="service-pause" role="status">Live debates are paused for today. The sample and Featured debates are still available. New debates resume after {new Date(allowance!.daily!.resets_at).toLocaleString()}.</div>}
          <div className="page-heading">
            <div>
              <div className="eyebrow">MULTI-PERSPECTIVE DECISION SUPPORT</div>
              <h1>See every side.<br className="mobile-break" /> Think more clearly.</h1>
              <p>
                A question, different perspectives, and the evidence between them.
              </p>
              {!analysis && <button className="text-button hero-sample" onClick={loadSample} disabled={busy || reading}><BookOpen size={15}/> Explore a sample debate <ArrowRight size={15}/></button>}
            </div>
            <span className="edition">
              <Sparkles size={15} /> {ready ? "Live workspace" : "Debate workspace"}
            </span>
          </div>
          {analysis && <div className="workspace-toolbar">
            <div><span className="eyebrow">DEBATE WORKSPACE</span><p>{analysis.perspectives.length} perspectives <span>·</span> 2 rounds <span>·</span> {analysis.sources.length} sources</p></div>
            <div className="workspace-actions"><button className="secondary-button" aria-expanded={setupExpanded} aria-controls="debate-setup" onClick={() => setSetupExpanded(v => !v)}>{setupExpanded ? <PanelLeftClose size={16}/> : <PanelLeftOpen size={16}/>} {setupExpanded ? "Hide setup" : "Edit setup"}</button>
            <button className="text-button" disabled={busy || reading} onClick={newDebate}> <Plus size={16}/> New debate</button></div>
          </div>}
          <div className={"studio-grid" + (analysis ? " has-analysis" : "") + (setupExpanded ? " setup-expanded" : "")}>

            <section className="setup-panel" id="debate-setup">
              <div className="panel-heading">
                <span className="section-number">01</span>
                <h2>Start with a question</h2>
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
                  clearSharedLink();
                  setQuestion(e.target.value);
                  setRoles(current => current.map(() => ""));
                  setRolesConfirmed(false);
                  setSuggestion("");
                  setNotice("");
                  setError("");
                  setAnalysis(null);
                  setSelected(null);
                }}
              />
              <div className="input-footer">
                <span>Ask a question with competing perspectives</span>
                <span>{question.length}/800</span>
              </div>
              {!question && <div className="question-examples"><span>TRY A QUESTION</span>{[
                {question: "Should companies adopt a four-day workweek?", roles: ["Employee advocate", "Business owner", "Organizational researcher"]},
                {question: "How should universities use AI in the classroom?", roles: ["Student advocate", "Teaching faculty", "Education researcher"]},
                {question: "Should city centers prioritize pedestrians over cars?", roles: ["Local resident", "Small business owner", "Urban planner"]},
              ].map(example => <button key={example.question} disabled={busy} onClick={() => {clearSharedLink();setQuestion(example.question);setRoles(example.roles);setRolesConfirmed(false);setError("");setNotice("");}}>{example.question}<ArrowUpRight size={13}/></button>)}</div>}
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
                <h3>Perspectives</h3>
                <span>{roles.length} DEBATERS · 2–5</span>
              </div>
              <label className="participant-count" htmlFor="participant-count">
                Number of participants
                <select id="participant-count" disabled={busy} value={roles.length} onChange={e => {
                  const count = Number(e.target.value);
                  setRoles(current => Array.from({length: count}, (_, i) => current[i] ?? ""));
                  setRolesConfirmed(false);
                  setNotice("");
                }}>
                  {[2, 3, 4, 5].map(count => <option key={count} value={count}>{count}</option>)}
                </select>
              </label>
              <button className="secondary-button" disabled={busy || reading || !ready || allowance?.remaining === 0 || dailyPaused || question.trim().length < 5} onClick={() => void prepare()}><Sparkles size={15} /> Generate {roles.length} perspectives with AI</button>
              <p className="helper">
                {rolesConfirmed
                  ? "Suggested for your question. Edit before starting."
                  : "Enter your own perspectives or generate them with AI for your topic."}
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
                      placeholder={`Enter perspective ${i + 1}`}
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
              <p className="helper">AI suggests viewpoints. You choose the final 2–5 debaters.</p>
              <label className="toggle-row web-search-control">
                <span>
                  <Globe size={17} />
                  <span>
                    Search the web
                    <small>
                      {textSources.length
                        ? "Supplement your documents"
                        : "Enable when you want current evidence"}
                    </small>
                  </span>
                </span>
                <input
                  type="checkbox"
                  aria-label="Search the web"
                  checked={web}
                  disabled={busy}
                  onChange={(e) => {
                    setWeb(e.target.checked);
                    setRolesConfirmed(false);
                  }}
                />
                <span className={"toggle " + (web ? "on" : "")} />
              </label>
              <details className="evidence-disclosure">
                <summary>
                  <span><BookOpen size={17} /> Add documents <small>{sources.length || pasted.trim() ? "Added" : "Optional"}</small></span>
                  <ChevronDown size={17} />
                </summary>
                <div className="evidence-controls"><p className="helper">Give every perspective the same sources to work from.</p>
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
                            setNotice("");
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

                </div>
              </details>
              <div className="rounds">
                <GitBranch size={16} />
                <span>2 rounds</span>
                <span>
                  Arguments <ArrowRight size={12} /> Revisions
                </span>
              </div>
              {allowance && <p className="allowance-note">{allowance.owner ? "Owner access · no personal debate limit" : `${allowance.remaining} of ${allowance.limit} debate starts remaining for this network. Suggestions do not use a debate. Starts are counted even if a run fails.`}</p>}
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
                  allowance?.remaining === 0 || dailyPaused ||
                  !validRoles
                }
                onClick={() => void runLive()}
              >
                {busy ? (
                  <LoaderCircle size={17} className="spin" />
                ) : (
                  <Sparkles size={17} />
                )}{" "}
                {dailyPaused ? "Debates paused today" : "Start debate"}{" "}
                <ArrowRight size={16} />
              </button>
              {!busy && (!question.trim() || !validRoles) && <p className="start-hint">{!question.trim() ? "Add a question to get started." : "Add a different viewpoint for each perspective to start."}</p>}
              <p className="helper">{account.user ? "Completed debates are saved privately to My debates." : "No account needed to debate. Sign in only if you want to save future debates."}</p>
              <p className="helper">{web ? "Shared web evidence will be retrieved for all debaters." : "Uses model knowledge and any documents you add. Unsourced facts remain unverified."}</p>
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
            <section className="analysis-panel" ref={analysisRef} tabIndex={-1} aria-label="Debate analysis">
              <div className="analysis-heading">
                <div className="panel-heading">
                  <span className="section-number">02</span>
                  <h2>{analysis ? "Explore the debate" : "A little perspective changes everything."}</h2>
                </div>
                <span className="tiny-label">
                  {analysis?.shared ? "SHARED DEBATE" : analysis?.published ? "COMMUNITY DEBATE" : analysis?.mode === "sample"
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
                    tabIndex={tab === t.id ? 0 : -1}
                    onKeyDown={e => {
                      if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
                      e.preventDefault();
                      const buttons = Array.from(e.currentTarget.parentElement!.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
                      const current = buttons.indexOf(e.currentTarget);
                      const next = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : (current + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
                      buttons[next].focus();
                      buttons[next].click();
                    }}
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
                  <div className="eyebrow">A QUESTION. MULTIPLE PERSPECTIVES.</div>
                  <h2>
                    One question.
                    <br />
                    A wider point of view.
                  </h2>
                  <p>
                    See where perspectives agree, where they challenge each other,
                    <br />
                    and what the evidence actually supports.
                  </p>
                  <div className="sample-preview">
                    <span className="eyebrow">EXAMPLE · PREVIEW ONLY</span>
                    <strong>{sample.question}</strong>
                    <p>{sample.perspectives.join(" · ")}</p>
                  </div>
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
                      {analysis.shared ? "Shared debate" : analysis.published ? "Community debate" : analysis.mode === "sample"
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
                  {(analysis.published || analysis.shared) && <p className="sample-disclaimer">Public debate snapshot. Original source passages are private; public source titles and links are shown where available.</p>}
                  {!busy && analysis.mode === 'live' && analysis.report && !analysis.published && (analysis.share_id || analysis.publish_token || analysis.history_id) && <>
                    <ShareDebate key={'share-'+(analysis.history_id || analysis.publish_token || analysis.share_id)} analysis={analysis} getToken={account.getToken}
                      onShared={id=>setAnalysis(current=>current===analysis?{...current,share_id:id}:current)}/>
                    {!analysis.shared && <PublishDebate key={'featured-'+(analysis.history_id || analysis.publish_token)} analysis={analysis} getToken={account.getToken}
                      onPublished={()=>setFeaturedVersion(v=>v+1)}/>}
                  </>}
                  {analysis.claims.length > 0 && (
                    <div className="evidence-overview" aria-label="Claim assessment overview">
                      <span className="overview-label"><ScanLine size={15}/> Evidence at a glance</span>
                      <div>
                        {Object.entries(labels).map(([status, label]) => {
                          const count = analysis.claims.filter(c => c.status === status).length;
                          return count ? <span key={status} className={`claim-chip ${status}`}><b>{count}</b> {label}</span> : null;
                        })}
                      </div>
                      <small>Assessments apply to individual claims, not the whole argument.</small>
                    </div>
                  )}
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
                                    {a.model && <small>{a.model.split("/").pop()}</small>}
                                  </div>
                                  {a.round === 2 && (
                                    <span className="revised">
                                      <Check size={12} /> Response
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
                                        className={`claim-chip claim-preview ${c.status}`}
                                        aria-label={`Inspect claim: ${c.text} — ${labels[c.status]}`}
                                        onClick={() => setSelected(c)}
                                      >
                                        <span className="claim-status">{labels[c.status]}</span>
                                        <span className="claim-excerpt">{c.text}</span>
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
                                        {analysis.claims.find(c => c.id === id)?.text || "Claim being assessed"}
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </article>
                            ))}
                          {busy &&
                            visible < round * analysis.perspectives.length &&
                            visible >= (round - 1) * analysis.perspectives.length && (
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
                      {!analysis.sources.length && <p className="view-note">No sources were supplied. These arguments use model knowledge; factual claims are unverified.</p>}
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
                          <p>{s.text || "Source passage withheld from the public copy."}</p>
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
          </>}
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
            {selected.assessments?.map(a => <div className="assessment-card" key={a.reviewer}><strong>{a.reviewer} · {labels[a.status]}</strong><p>{a.explanation}</p><small>Passages: {a.source_ids.join(", ") || "None"}</small></div>)}
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
                    <p>{s.text || "Source passage withheld from the public copy."}</p>
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
