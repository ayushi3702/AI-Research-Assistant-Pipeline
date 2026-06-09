# AI Research Assistant Pipeline

A production-grade **multi-agent research pipeline** that generates comprehensive, fact-checked research reports with real-time agent reasoning transparency, trust heatmaps, and export integrations.

Built with LangGraph, FastAPI, React, and Azure OpenAI.

---

## Features

### Core Pipeline
- **5-agent research pipeline** — Search → Extract → Validate → RAG → Writer
- **Real-time WebSocket streaming** — live status updates as agents work
- **Agent Reasoning Traces** — transparent step-by-step decision log with live indicator
- **Multi-source search** — Tavily web search + Arxiv academic papers + Playwright scraping
- **RAG (Retrieval-Augmented Generation)** — ChromaDB vector store with sentence-transformers
- **Report refinement chat** — follow-up conversation to refine generated reports

### Trust & Verification
- **Fact-Check Heatmap** — color-coded report with verified (green), uncertain (yellow), and contradicted (red) claims
- **Confidence bar** — aggregate verification summary with click-to-inspect tooltips
- **Claim verification** — automated cross-referencing against source material

### Quick Q&A Mode
- **Document upload** — PDF, DOCX, TXT, MD — chunked and indexed for Q&A
- **Conversational Q&A** — multi-turn chat with source citations
- **Follow-up suggestions** — AI-generated follow-up questions
- **Voice input** — speech-to-text via Web Speech API

### Export
- **Export to Notion** — OAuth integration, creates a formatted Notion page
- **Export to Google Docs** — OAuth integration with token refresh, creates a Google Doc
- **Download** — PDF and DOCX export

### Notifications
- **Email notifications** — Gmail SMTP, sends report-ready alerts
- **In-app notification bell** — unread badge, dropdown with mark-read, auto-polls every 30s

### Auth & UX
- **Google OAuth** login
- **Email/password** signup with JWT
- **Dark/light theme** toggle
- **Chat history sidebar** — pinned chats, search, grouped by date
- **Multi-language reports** — English, Hindi, Spanish, French, German, Chinese, Japanese, Korean, Arabic, Portuguese, Russian

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  nginx (port 3000)                                          │
│  React + Vite SPA                                           │
│  ┌──────────┬──────────┬────────────┬──────────┬──────────┐ │
│  │ Sidebar  │ Navbar   │TrustHeatmap│Reasoning │ AgentCard│ │
│  │          │(Bell)    │            │Panel     │          │ │
│  └──────────┴──────────┴────────────┴──────────┴──────────┘ │
│         /api/* proxy  │  /ws/* proxy                        │
└───────────────────────┼─────────────────────────────────────┘
                        │
┌───────────────────────┼─────────────────────────────────────┐
│  FastAPI (port 8000)  │                                     │
│  ┌────────────────────┼───────────────────────────────────┐ │
│  │ REST API           │ WebSocket (live status + reasoning)│ │
│  │ Auth, Research,    │                                    │ │
│  │ Q&A, Notifications,│                                    │ │
│  │ Export              │                                    │ │
│  └────────────────────┼───────────────────────────────────┘ │
│           │           │                                     │
│  ┌────────▼──────────────────────────────────────────────┐  │
│  │ LangGraph Orchestrator                                │  │
│  │ Search → Extractor → Validator → RAG → Writer         │  │
│  │         (Tavily, Arxiv, Playwright, ChromaDB)         │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                              │
    ┌────▼────┐                   ┌─────▼─────┐
    │Supabase │                   │ ChromaDB  │
    │PostgreSQL│                   │(embedded) │
    └─────────┘                   └───────────┘
```

---

## Project Structure

```
├── services/
│   ├── agents/                    # LangGraph pipeline + 5 agents
│   │   ├── orchestrator.py        # State machine with reasoning traces
│   │   ├── search_agent.py        # Tavily + Arxiv search
│   │   ├── extractor_agent.py     # Content extraction + Playwright scraping
│   │   ├── validator_agent.py     # Claim verification + confidence scoring
│   │   ├── writer_agent.py        # Report generation + email notification
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── api/                       # FastAPI backend
│   │   ├── main.py                # REST + WebSocket + OAuth + Export
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── ui/                        # React frontend
│       ├── src/
│       │   ├── App.jsx            # Main app — research, Q&A, report modal
│       │   ├── App.css            # Full theme (light/dark, all components)
│       │   ├── main.jsx           # React entry point
│       │   └── components/
│       │       ├── Navbar.jsx     # Theme toggle, notifications
│       │       ├── Sidebar.jsx    # Chat history, search, pin
│       │       ├── TrustHeatmap.jsx   # Fact-check heatmap + confidence bar
│       │       ├── ReasoningPanel.jsx # Agent reasoning trace timeline
│       │       └── AgentCard.jsx      # Agent status display
│       ├── nginx.conf
│       ├── package.json
│       └── Dockerfile
├── shared/                        # Shared Python code
│   ├── database.py                # SQLAlchemy models (11 tables), auto-migration
│   ├── auth.py                    # JWT, bcrypt, Google OAuth, SMTP notifications
│   ├── state.py                   # Pydantic ResearchState for LangGraph
│   ├── message_bus.py             # Async pub/sub (no Redis needed)
│   ├── vector_store.py            # ChromaDB + sentence-transformers
│   ├── document_processor.py      # PDF/DOCX/TXT chunking for RAG
│   ├── export_converters.py       # Markdown → Notion blocks / Google Docs requests
│   └── tools.py                   # OpenAI function-calling tool schemas
├── tests/
│   └── test_pipeline.py
├── docker-compose.yml
└── .env.example
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- API keys: Azure OpenAI, Tavily

### Run

```bash
cp .env.example .env        # fill in your API keys
docker-compose up --build
```

- **UI** → http://localhost:3000
- **API docs** → http://localhost:8000/docs

---

## Environment Variables

```env
# LLM
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your_deployment_name
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# Search
TAVILY_API_KEY=

# Observability
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=research-pipeline
LANGCHAIN_TRACING_V2=true

# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Auth
JWT_SECRET_KEY=your_random_secret_key
APP_BASE_URL=http://localhost:3000
GOOGLE_CLIENT_ID=               # Google OAuth (login + Docs export)
GOOGLE_CLIENT_SECRET=

# Notion Export (optional)
NOTION_CLIENT_ID=               # from notion.so/my-integrations
NOTION_CLIENT_SECRET=

# Email Notifications (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=your-email@gmail.com
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | Azure OpenAI GPT-5.2 with function calling |
| **Orchestration** | LangGraph state machine |
| **Web Search** | Tavily API |
| **Academic Search** | Arxiv API |
| **Scraping** | Playwright (headless Chromium) |
| **Vector Store** | ChromaDB + sentence-transformers (all-MiniLM-L6-v2) |
| **Database** | Supabase PostgreSQL via SQLAlchemy |
| **API** | FastAPI + WebSockets |
| **Auth** | JWT + Google OAuth + bcrypt |
| **Frontend** | React 18 + Vite + ReactMarkdown |
| **Styling** | CSS custom properties (light/dark theme) |
| **PDF/DOCX** | WeasyPrint + python-docx |
| **Observability** | LangSmith |
| **Infra** | Docker Compose |

---

## Database Models

| Model | Purpose |
|-------|---------|
| `User` | Email/password + Google OAuth users |
| `ResearchJob` | Research query, status, report |
| `AgentTask` | Per-agent execution log (timing, I/O) |
| `Source` | URLs, titles, snippets found during research |
| `Document` | Uploaded files for Q&A |
| `ChatHistory` | Sidebar entries (Research + Q&A) |
| `QAInteraction` | Q&A conversation messages |
| `ClaimVerification` | Fact-check results per claim |
| `ReasoningTrace` | Agent reasoning steps with decisions |
| `NotificationLog` | Email/in-app notification records |
| `OAuthConnection` | Notion + Google Docs OAuth tokens |

---

## API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/signup` | Email/password registration |
| POST | `/auth/login` | JWT login |
| GET | `/auth/google` | Google OAuth redirect |
| GET | `/auth/me` | Current user info |

### Research
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/research` | Start a research job |
| GET | `/research/{id}` | Get job status + report |
| GET | `/research/{id}/tasks` | Agent execution details |
| GET | `/research/{id}/claims` | Fact-check verifications |
| GET | `/research/{id}/reasoning` | Agent reasoning traces |
| GET | `/research/{id}/download` | Download PDF/DOCX |
| WS | `/ws/{job_id}` | Live status + reasoning stream |

### Q&A
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload document for Q&A |
| POST | `/qa` | Ask a question (streaming SSE) |

### Chat History
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/chats` | List user's chat history |
| GET | `/chats/{id}` | Load a specific chat |
| PATCH | `/chats/{id}/pin` | Pin/unpin a chat |

### Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/export/connections` | Check connected services |
| GET | `/export/notion/connect` | Start Notion OAuth |
| GET | `/export/google-docs/connect` | Start Google Docs OAuth |
| POST | `/export/notion/{job_id}` | Export report to Notion |
| POST | `/export/google-docs/{job_id}` | Export report to Google Docs |

### Notifications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/notifications` | List notifications |
| PATCH | `/notifications/{id}/read` | Mark as read |
| POST | `/notifications/read-all` | Mark all as read |

---

## Tests

```bash
export PYTHONPATH=$(pwd)
pytest tests/ -v
```
