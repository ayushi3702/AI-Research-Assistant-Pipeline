import { useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import Sidebar from "./components/Sidebar";
import AgentCard from "./components/AgentCard";
import Navbar from "./components/Navbar";
import TrustHeatmap from "./components/TrustHeatmap";
import ReasoningPanel from "./components/ReasoningPanel";

const API_BASE = "/api";

const AGENTS = [
  { id: "search", label: "Search agent", icon: "🔍" },
  { id: "extractor", label: "Extractor agent", icon: "📄" },
  { id: "validator", label: "Validator agent", icon: "✅" },
  { id: "rag", label: "RAG agent", icon: "🧠" },
  { id: "writer", label: "Writer agent", icon: "✍️" },
];

export default function App() {
  const [query, setQuery] = useState("");
  const [jobId, setJobId] = useState(null);
  const [agentStatuses, setAgentStatuses] = useState({});
  const [report, setReport] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState(null);
  const [reportLanguage, setReportLanguage] = useState("English");
  const [running, setRunning] = useState(false);
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem("token") || null);
  const [mode, setMode] = useState("report"); // "report" | "ask"
  const [chatMessages, setChatMessages] = useState([]); // [{role, content, sources, followups}]
  const [chatSessionId, setChatSessionId] = useState(null);
  const [attachedFile, setAttachedFile] = useState(null);
  const [attachedDocId, setAttachedDocId] = useState(null);
  const [showReportModal, setShowReportModal] = useState(false);
  const [showDownloadMenu, setShowDownloadMenu] = useState(false);
  const [thinkingStage, setThinkingStage] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [reportMessages, setReportMessages] = useState([]); // [{role, content, streaming}]
  const [listening, setListening] = useState(false);
  const [claims, setClaims] = useState([]);
  const [claimsLoading, setClaimsLoading] = useState(false);
  const [reasoningTraces, setReasoningTraces] = useState([]);
  const [reasoningExpanded, setReasoningExpanded] = useState(true);
  const [exportConnections, setExportConnections] = useState({ notion: false, google_docs: false });
  const [exporting, setExporting] = useState(null); // null | "notion" | "google_docs"

  const wsRef = useRef(null);
  const chatEndRef = useRef(null);
  const recognitionRef = useRef(null);

  // Saved state for each mode so switching preserves context
  const savedQAState = useRef({ chatMessages: [], chatSessionId: null, attachedDocId: null, query: "" });
  const savedReportState = useRef({ jobId: null, agentStatuses: {}, report: null, tasks: [], query: "", reportMessages: [] });

  const switchMode = (newMode) => {
    if (newMode === mode) return;
    // Save current mode's state
    if (mode === "ask") {
      savedQAState.current = { chatMessages, chatSessionId, attachedDocId, query };
    } else {
      savedReportState.current = { jobId, agentStatuses, report, tasks, query, reportMessages };
    }
    // Clear shared state
    setError(null);
    setThinkingStage(null);
    setShowReportModal(false);
    setShowDownloadMenu(false);
    setAttachedFile(null);
    // Restore target mode's state
    if (newMode === "ask") {
      const s = savedQAState.current;
      setChatMessages(s.chatMessages);
      setChatSessionId(s.chatSessionId);
      setAttachedDocId(s.attachedDocId);
      setQuery(s.query);
      setJobId(null);
      setAgentStatuses({});
      setReport(null);
      setTasks([]);
    } else {
      const s = savedReportState.current;
      setJobId(s.jobId);
      setAgentStatuses(s.agentStatuses);
      setReport(s.report);
      setTasks(s.tasks);
      setQuery(s.query);
      setReportMessages(s.reportMessages || []);
      setChatMessages([]);
      setChatSessionId(null);
      setAttachedDocId(null);
    }
    setMode(newMode);
  };

  // Auth helpers
  const getAuthHeaders = () => {
    if (!token) return {};
    return { Authorization: `Bearer ${token}` };
  };

  // Check for token in URL (Google OAuth redirect) or restore session
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    if (urlToken) {
      setToken(urlToken);
      localStorage.setItem("token", urlToken);
      window.history.replaceState({}, "", "/");
    }
  }, []);

  // Fetch user info when token is set
  useEffect(() => {
    if (!token) { setUser(null); return; }
    fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => { if (!res.ok) throw new Error(); return res.json(); })
      .then((data) => setUser(data))
      .catch(() => { setToken(null); setUser(null); localStorage.removeItem("token"); });
  }, [token]);

  const handleLogout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem("token");
  };

  const handleGoogleLogin = () => {
    window.location.href = `${API_BASE}/auth/google`;
  };

  // Fetch export connections status
  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/export/connections`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => res.ok ? res.json() : {})
      .then((data) => setExportConnections(data))
      .catch(() => {});
  }, [token]);

  // Handle export_success/export_error URL params (from OAuth redirects)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("export_success")) {
      const provider = params.get("export_success");
      setExportConnections((prev) => ({ ...prev, [provider]: true }));
      window.history.replaceState({}, "", "/");
    }
    if (params.get("export_error")) {
      setError(`Export connection failed: ${params.get("export_error")}`);
      window.history.replaceState({}, "", "/");
    }
  }, []);

  const handleExport = async (provider) => {
    if (!jobId) return;
    setExporting(provider);
    try {
      const res = await fetch(`${API_BASE}/export/${provider}/${jobId}`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Export failed");
      // Open the created document
      window.open(data.url, "_blank");
    } catch (e) {
      setError(`Export to ${provider} failed: ${e.message}`);
    } finally {
      setExporting(null);
    }
  };

  const resetState = () => {
    setAgentStatuses({});
    setReport(null);
    setTasks([]);
    setError(null);
    setChatMessages([]);
    setChatSessionId(null);
    setAttachedDocId(null);
    setShowReportModal(false);
    setShowDownloadMenu(false);
    setThinkingStage(null);
    setReportMessages([]);
    setClaims([]);
    setClaimsLoading(false);
    setReasoningTraces([]);
  };

  const handleNewChat = () => {
    resetState();
    setQuery("");
    setJobId(null);
    setAttachedFile(null);
    localStorage.removeItem("pendingJob");
    savedQAState.current = { chatMessages: [], chatSessionId: null, attachedDocId: null, query: "" };
    savedReportState.current = { jobId: null, agentStatuses: {}, report: null, tasks: [], query: "", reportMessages: [] };
  };

  const handleFileAttach = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setAttachedFile(file);
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const uploadRes = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: formData,
      });
      if (!uploadRes.ok) {
        const err = await uploadRes.json();
        throw new Error(err.detail || "File upload failed");
      }
      const uploadData = await uploadRes.json();
      setAttachedDocId(uploadData.doc_id);
    } catch (err) {
      setError(`Upload failed: ${err.message}`);
      setAttachedFile(null);
      setAttachedDocId(null);
    } finally {
      setUploading(false);
    }
  };

  const handleSelectJob = async (chat) => {
    resetState();
    setRunning(false);

    if (chat.type === "Research") {
      setMode("report");
      setJobId(chat.ref_id);
      try {
        const res = await fetch(`${API_BASE}/research/${chat.ref_id}`);
        const data = await res.json();
        if (data.report) setReport(data.report);
        if (data.query) setQuery(data.query);

        const tasksRes = await fetch(`${API_BASE}/research/${chat.ref_id}/tasks`);
        const tasksData = await tasksRes.json();
        if (tasksData.length) setTasks(tasksData);

        fetchClaims(chat.ref_id);
        fetchReasoning(chat.ref_id);
      } catch (e) {
        setError(`Could not load job: ${e.message}`);
      }
    } else if (chat.type === "Q&A") {
      setMode("ask");
      try {
        const headers = { ...getAuthHeaders() };
        const res = await fetch(`${API_BASE}/chats/${chat.id}`, { headers });
        const data = await res.json();
        if (data.chat_session_id) setChatSessionId(data.chat_session_id);
        if (data.messages && data.messages.length > 0) {
          const msgs = [];
          for (const m of data.messages) {
            msgs.push({ role: "user", content: m.question });
            msgs.push({
              role: "assistant",
              content: m.answer,
              sources: m.sources || [],
              followups: [],
            });
          }
          setChatMessages(msgs);
        }
      } catch (e) {
        setError(`Could not load chat: ${e.message}`);
      }
    }
  };

  const fetchClaims = useCallback(async (id) => {
    setClaimsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/research/${id}/claims`);
      const data = await res.json();
      if (Array.isArray(data)) setClaims(data);
    } catch (e) {
      console.warn("Could not fetch claims:", e);
    } finally {
      setClaimsLoading(false);
    }
  }, []);

  const fetchReasoning = useCallback(async (id) => {
    try {
      const res = await fetch(`${API_BASE}/research/${id}/reasoning`);
      const data = await res.json();
      if (Array.isArray(data)) setReasoningTraces(data);
    } catch (e) {
      console.warn("Could not fetch reasoning traces:", e);
    }
  }, []);

  const fetchReport = useCallback(async (id) => {
    try {
      const res = await fetch(`${API_BASE}/research/${id}`);
      const data = await res.json();
      if (data.report) setReport(data.report);

      const tasksRes = await fetch(`${API_BASE}/research/${id}/tasks`);
      const tasksData = await tasksRes.json();
      if (tasksData.length) setTasks(tasksData);

      fetchClaims(id);
      fetchReasoning(id);
    } catch (e) {
      setError(`Could not fetch report: ${e.message}`);
    } finally {
      setRunning(false);
    }
  }, [fetchClaims, fetchReasoning]);

  // Load a report opened from an email "View Report" link (?job=<id>)
  const loadReportFromLink = useCallback(async (jobParam) => {
    setMode("report");
    setJobId(jobParam);
    try {
      const res = await fetch(`${API_BASE}/research/${jobParam}`);
      if (!res.ok) throw new Error("Job not found");
      const data = await res.json();
      if (data.report) setReport(data.report);
      if (data.query) setQuery(data.query);

      const tasksRes = await fetch(`${API_BASE}/research/${jobParam}/tasks`);
      const tasksData = await tasksRes.json();
      if (Array.isArray(tasksData) && tasksData.length) setTasks(tasksData);

      fetchClaims(jobParam);
      fetchReasoning(jobParam);
    } catch (e) {
      setError(`Could not load report: ${e.message}`);
    }
  }, [fetchClaims, fetchReasoning]);

  // On arrival from an email link, open the report. If the user isn't logged in
  // yet, stash the job so it survives the login round-trip (e.g. Google OAuth).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const jobParam = params.get("job");
    if (!jobParam) return;

    // Clean the job param from the URL once captured
    window.history.replaceState({}, "", "/");

    if (localStorage.getItem("token")) {
      // Already authenticated — open immediately, no need to persist
      localStorage.removeItem("pendingJob");
      loadReportFromLink(jobParam);
    } else {
      // Not logged in yet — remember it and show what we can now
      localStorage.setItem("pendingJob", JSON.stringify({ id: jobParam, ts: Date.now() }));
      loadReportFromLink(jobParam);
    }
  }, [loadReportFromLink]);

  // After login completes, open any report that was pending from an email link.
  useEffect(() => {
    if (!user) return;
    const raw = localStorage.getItem("pendingJob");
    if (!raw) return;
    localStorage.removeItem("pendingJob");
    try {
      const { id, ts } = JSON.parse(raw);
      // Ignore stale links (older than 15 minutes) to avoid surprise reopens
      if (id && Date.now() - ts < 15 * 60 * 1000) {
        loadReportFromLink(id);
      }
    } catch {
      /* malformed value — ignore */
    }
  }, [user, loadReportFromLink]);

  const connectWebSocket = useCallback(
    (id) => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/ws/${id}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "ping") return; // keepalive, ignore
        if (msg.type === "log") return; // ignore log messages
        if (msg.type === "reasoning") {
          setReasoningTraces((prev) => [...prev, msg]);
          return;
        }
        const { agent, status } = msg;
        if (AGENTS.some((a) => a.id === agent)) {
          setAgentStatuses((prev) => ({ ...prev, [agent]: status }));
        }
        if (agent === "orchestrator" && (status === "done" || status === "failed")) {
          // Mark any still-waiting agents as done/skipped
          if (status === "done") {
            setAgentStatuses((prev) => {
              const updated = { ...prev };
              AGENTS.forEach((a) => {
                if (!updated[a.id] || updated[a.id] === "waiting") {
                  updated[a.id] = "done";
                }
              });
              return updated;
            });
          }
          ws.close();
          fetchReport(id);
        }
      };

      ws.onerror = () => {
        // Fallback to polling
        pollStatus(id);
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    },
    [fetchReport]
  );

  const pollStatus = useCallback(
    async (id) => {
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          const res = await fetch(`${API_BASE}/research/${id}`);
          const data = await res.json();
          if (data.status === "done" || data.status === "failed") {
            fetchReport(id);
            return;
          }
        } catch {
          break;
        }
      }
      setRunning(false);
    },
    [fetchReport]
  );

  const handleSubmit = async (e, overrideQuestion) => {
    if (e) e.preventDefault();
    const questionText = overrideQuestion || query;
    if (!questionText.trim()) return;

    if (mode === "report" && !report) {
      // Only reset for a brand new report, not refinement
      resetState();
    } else if (mode === "ask") {
      // In Q&A mode, only clear report/task state, keep chat messages
      setError(null);
      setReport(null);
      setTasks([]);
    } else {
      setError(null);
    }
    setRunning(true);

    if (mode === "ask") {
      // Quick Q&A mode — multi-turn conversation
      const currentQuestion = questionText;
      setQuery("");

      // Add user message to chat immediately
      setChatMessages((prev) => [...prev, { role: "user", content: currentQuestion }]);
      setThinkingStage({ icon: "🔍", text: "Analyzing your question..." });

      try {
        const docId = attachedDocId;

        // Build conversation history from previous messages
        const conversationHistory = chatMessages.map((m) => ({
          role: m.role,
          content: m.content,
        }));

        // Show real stage: what the backend is doing now
        setThinkingStage(docId
          ? { icon: "📄", text: "Retrieving document context..." }
          : { icon: "📚", text: "Searching knowledge base..." }
        );

        // Choose streaming endpoint
        const streamUrl = docId
          ? `${API_BASE}/documents/ask/stream`
          : `${API_BASE}/ask/stream`;
        const streamBody = docId
          ? { question: currentQuestion, doc_id: docId, conversation_history: conversationHistory, chat_session_id: chatSessionId }
          : { question: currentQuestion, conversation_history: conversationHistory, chat_session_id: chatSessionId };

        const res = await fetch(streamUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify(streamBody),
        });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || "Failed");
        }

        // Read SSE stream — assistant message added on first token
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let streamSources = [];
        let streamHasContext = true;
        let assistantAdded = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.replace(/^data: /, "").trim();
            if (!trimmed) continue;
            let evt;
            try { evt = JSON.parse(trimmed); } catch { continue; }

            if (evt.type === "stage") {
              // Backend is indicating a processing stage change (e.g. web search fallback)
              setThinkingStage({ icon: "🌐", text: evt.message || "Searching the web..." });
            } else if (evt.type === "meta") {
              // RAG retrieval done — sources are ready
              streamSources = evt.sources || [];
              streamHasContext = evt.has_context !== undefined ? evt.has_context : true;
              if (evt.chat_session_id) setChatSessionId(evt.chat_session_id);
              setThinkingStage({ icon: "✨", text: "Generating answer..." });
            } else if (evt.type === "token") {
              if (!assistantAdded) {
                // First token: transition from thinking → streaming cursor
                setThinkingStage(null);
                setChatMessages((prev) => [
                  ...prev,
                  { role: "assistant", content: evt.token, sources: streamSources, followups: [], has_context: streamHasContext, streaming: true },
                ]);
                assistantAdded = true;
              } else {
                setChatMessages((prev) => {
                  const updated = [...prev];
                  const last = { ...updated[updated.length - 1] };
                  last.content += evt.token;
                  updated[updated.length - 1] = last;
                  return updated;
                });
              }
            } else if (evt.type === "followups") {
              setChatMessages((prev) => {
                const updated = [...prev];
                const last = { ...updated[updated.length - 1] };
                last.followups = evt.followups || [];
                updated[updated.length - 1] = last;
                return updated;
              });
            } else if (evt.type === "done") {
              setChatMessages((prev) => {
                const updated = [...prev];
                const last = { ...updated[updated.length - 1] };
                last.streaming = false;
                updated[updated.length - 1] = last;
                return updated;
              });
            } else if (evt.type === "error") {
              throw new Error(evt.error);
            }
          }
        }
      } catch (e) {
        setThinkingStage(null);
        setError(`Could not get answer: ${e.message}`);
      } finally {
        setRunning(false);
      }
      return;
    }

    // Report mode
    if (report && jobId) {
      // Refine existing report
      const instruction = query;
      setQuery("");
      setReportMessages((prev) => [...prev, { role: "user", content: instruction }]);
      setThinkingStage({ icon: "🔍", text: "Analyzing your request..." });

      try {
        const conversationHistory = reportMessages.map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const res = await fetch(`${API_BASE}/research/${jobId}/refine`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({
            instruction,
            conversation_history: conversationHistory,
          }),
        });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || "Failed");
        }

        setThinkingStage({ icon: "✨", text: "Refining report..." });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let assistantAdded = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.replace(/^data: /, "").trim();
            if (!trimmed) continue;
            let evt;
            try { evt = JSON.parse(trimmed); } catch { continue; }

            if (evt.type === "token") {
              if (!assistantAdded) {
                setThinkingStage(null);
                setReportMessages((prev) => [
                  ...prev,
                  { role: "assistant", content: evt.token, streaming: true },
                ]);
                assistantAdded = true;
              } else {
                setReportMessages((prev) => {
                  const updated = [...prev];
                  const last = { ...updated[updated.length - 1] };
                  last.content += evt.token;
                  updated[updated.length - 1] = last;
                  return updated;
                });
              }
            } else if (evt.type === "done") {
              setReportMessages((prev) => {
                const updated = [...prev];
                const last = { ...updated[updated.length - 1] };
                last.streaming = false;
                updated[updated.length - 1] = last;
                if (evt.is_report_update && last.content) {
                  // Schedule report update
                  setTimeout(() => setReport(last.content), 0);
                }
                return updated;
              });
            } else if (evt.type === "error") {
              throw new Error(evt.error);
            }
          }
        }
      } catch (e) {
        setThinkingStage(null);
        setError(`Could not refine report: ${e.message}`);
      } finally {
        setRunning(false);
      }
      return;
    }

    // New report — full pipeline
    try {
      resetState();
      setRunning(true);
      const res = await fetch(`${API_BASE}/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ query, language: reportLanguage }),
      });
      const data = await res.json();
      setJobId(data.job_id);
      connectWebSocket(data.job_id);
    } catch (e) {
      setError(`Could not connect to API: ${e.message}`);
      setRunning(false);
    }
  };

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatMessages, running]);

  return (
    <div className="app-wrapper">
      <Navbar
        user={user}
        onLogout={handleLogout}
        onGoogleLogin={handleGoogleLogin}
        apiBase={API_BASE}
        token={token}
      />
      <div className="app-layout">
        <Sidebar apiBase={API_BASE} onSelectChat={handleSelectJob} onNewChat={handleNewChat} token={token} user={user} />

      <main className="main-content">
        <div className="input-area">
          <div className="mode-toggle">
            <button
              className={`mode-btn ${mode === "report" ? "active" : ""}`}
              onClick={() => switchMode("report")}
              type="button"
            >
              📝 Generate Report
            </button>
            <button
              className={`mode-btn ${mode === "ask" ? "active" : ""}`}
              onClick={() => switchMode("ask")}
              type="button"
            >
              💬 Quick Q&A
            </button>
          </div>

          <form className="query-form" onSubmit={handleSubmit}>
            <div className="query-input-wrapper">
              <input
                type="text"
                className="query-input"
                placeholder={mode === "report"
                  ? (report ? "e.g. Add a section about methodology, Remove the conclusion..." : "e.g. Recent advances in protein folding using AI")
                  : "Ask anything — uses your past research as context..."
                }
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button
                type="button"
                className={`voice-btn${listening ? " listening" : ""}`}
                onClick={() => {
                  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                  if (!SpeechRecognition) { setError("Speech recognition not supported in this browser"); return; }
                  if (listening) {
                    recognitionRef.current?.stop();
                    return;
                  }
                  const recognition = new SpeechRecognition();
                  recognition.lang = "en-US";
                  recognition.interimResults = true;
                  recognition.continuous = false;
                  recognitionRef.current = recognition;
                  recognition.onstart = () => setListening(true);
                  recognition.onresult = (event) => {
                    const transcript = Array.from(event.results).map(r => r[0].transcript).join("");
                    setQuery(transcript);
                  };
                  recognition.onend = () => setListening(false);
                  recognition.onerror = () => setListening(false);
                  recognition.start();
                }}
                title={listening ? "Stop listening" : "Voice input"}
              >
                {listening ? "⏹️" : "🎤"}
              </button>
              {mode === "ask" && (
                <label className="attach-btn" title="Attach a document">
                  📎
                  <input
                    type="file"
                    accept=".pdf,.txt,.md,.docx"
                    onChange={handleFileAttach}
                    hidden
                  />
                </label>
              )}
            </div>
            {mode === "report" && !report && (
              <select
                className="language-select"
                value={reportLanguage}
                onChange={(e) => setReportLanguage(e.target.value)}
              >
                <option value="English">🇬🇧 English</option>
                <option value="Hindi">🇮🇳 Hindi</option>
                <option value="Spanish">🇪🇸 Spanish</option>
                <option value="French">🇫🇷 French</option>
                <option value="German">🇩🇪 German</option>
                <option value="Chinese">🇨🇳 Chinese</option>
                <option value="Japanese">🇯🇵 Japanese</option>
                <option value="Korean">🇰🇷 Korean</option>
                <option value="Arabic">🇸🇦 Arabic</option>
                <option value="Portuguese">🇧🇷 Portuguese</option>
                <option value="Russian">🇷🇺 Russian</option>
              </select>
            )}
            <button
              type="submit"
              className="run-button"
              disabled={!query.trim() || running || uploading}
            >
              {uploading ? "Uploading..." : running ? "Running..." : mode === "report" ? (report ? "Refine" : "Run research pipeline") : "Ask"}
            </button>
          </form>
          {attachedFile && (
            <div className="attached-file-badge">
              {uploading ? "⏳" : "📄"} {attachedFile.name}
              {uploading && <span className="upload-status"> Uploading...</span>}
              {!uploading && <button className="remove-attach" onClick={() => { setAttachedFile(null); setAttachedDocId(null); }}>✕</button>}
            </div>
          )}
        </div>

        <div className="results-area">

        {error && <div className="error-banner">{error}</div>}

        {chatMessages.length > 0 && (
          <div className="chat-messages">
            {chatMessages.map((msg, i) => (
              <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
                <div className="chat-msg-label">{msg.role === "user" ? "You" : "Assistant"}</div>
                <div className={`chat-msg-content${msg.streaming ? " streaming-cursor" : ""}`}>
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
                {msg.sources && msg.sources.length > 0 && (
                  <details className="qa-sources">
                    <summary>Sources ({msg.sources.length} references)</summary>
                    <ul>
                      {msg.sources.map((s, j) => (
                        <li key={j}>
                          {s.url ? (
                            <a href={s.url} target="_blank" rel="noopener noreferrer">{s.url}</a>
                          ) : (
                            <span>Chunk {s.chunk_index + 1} (relevance: {(1 - s.distance).toFixed(2)})</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {msg.followups && msg.followups.length > 0 && i === chatMessages.length - 1 && (
                  <div className="followup-chips">
                    {msg.followups.map((q, j) => (
                      <button
                        key={j}
                        className="followup-chip"
                        disabled={running}
                        onClick={() => handleSubmit(null, q)}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {running && thinkingStage && (
              <div className="chat-msg chat-msg-assistant thinking-bubble">
                <div className="thinking-stage">
                  <span className="thinking-icon">{thinkingStage.icon}</span>
                  <span className="thinking-text">{thinkingStage.text}</span>
                  <span className="thinking-dots"><span>.</span><span>.</span><span>.</span></span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}

        {mode === "report" && (running || reasoningTraces.length > 0) && (
          <ReasoningPanel
            traces={reasoningTraces}
            isLive={running}
            expanded={reasoningExpanded}
            onToggle={() => setReasoningExpanded(!reasoningExpanded)}
          />
        )}

        {report && (
          <>
            <div className="report-actions">
              <h2>Report ready</h2>
              <div className="report-buttons">
                <button className="btn-view" onClick={() => setShowReportModal(true)}>
                  👁️ View Report
                </button>
                <div className="download-wrapper">
                  <button className="btn-download" onClick={() => setShowDownloadMenu(!showDownloadMenu)}>
                    ⬇️ Export / Download
                  </button>
                  {showDownloadMenu && (
                    <div className="download-menu">
                      <div className="download-menu-section">Download</div>
                      <button onClick={() => { window.open(`${API_BASE}/research/${jobId}/download?format=pdf`); setShowDownloadMenu(false); }}>
                        📄 PDF
                      </button>
                      <button onClick={() => { window.open(`${API_BASE}/research/${jobId}/download?format=docx`); setShowDownloadMenu(false); }}>
                        📝 DOCX
                      </button>
                      <div className="download-menu-section">Export to</div>
                      {exportConnections.notion ? (
                        <button
                          disabled={exporting === "notion"}
                          onClick={() => { handleExport("notion"); setShowDownloadMenu(false); }}
                        >
                          📓 {exporting === "notion" ? "Exporting..." : "Notion"}
                        </button>
                      ) : (
                        <button onClick={() => { window.location.href = `${API_BASE}/export/notion/connect?token=${token}`; }}>
                          📓 Connect Notion
                        </button>
                      )}
                      {exportConnections.google_docs ? (
                        <button
                          disabled={exporting === "google-docs"}
                          onClick={() => { handleExport("google-docs"); setShowDownloadMenu(false); }}
                        >
                          📑 {exporting === "google-docs" ? "Exporting..." : "Google Docs"}
                        </button>
                      ) : (
                        <button onClick={() => { window.location.href = `${API_BASE}/export/google-docs/connect?token=${token}`; }}>
                          📑 Connect Google Docs
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </>
        )}

        {tasks.length > 0 && (
          <details className="qa-sources agent-perf-details">
            <summary>Agent Performance ({tasks.length} agents)</summary>
            <table className="tasks-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Duration (ms)</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t, i) => (
                  <tr key={i}>
                    <td>{t.agent}</td>
                    <td>{t.status}</td>
                    <td>{t.duration_ms}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}

        {/* Report refinement conversation */}
        {mode === "report" && reportMessages.length > 0 && (
          <>
            <hr className="divider" />
            <div className="chat-messages report-refine-chat">
              {reportMessages.map((msg, i) => (
                <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
                  <div className="chat-msg-label">{msg.role === "user" ? "You" : "Assistant"}</div>
                  <div className={`chat-msg-content${msg.streaming ? " streaming-cursor" : ""}`}>
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              ))}
              {running && thinkingStage && mode === "report" && (
                <div className="chat-msg chat-msg-assistant thinking-bubble">
                  <div className="thinking-stage">
                    <span className="thinking-icon">{thinkingStage.icon}</span>
                    <span className="thinking-text">{thinkingStage.text}</span>
                    <span className="thinking-dots"><span>.</span><span>.</span><span>.</span></span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          </>
        )}
        </div>
      </main>
      </div>

      {/* Report Modal */}
      {showReportModal && (
        <div className="modal-overlay" onClick={() => setShowReportModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Research Report</h2>
              <button className="modal-close" onClick={() => setShowReportModal(false)}>✕</button>
            </div>
            <div className="modal-body">
              <TrustHeatmap report={report} claims={claims} loading={claimsLoading} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
