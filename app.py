
from pathlib import Path
import json

ROOT = Path("super-agent-platform")

FILES = {
" .env.example": r"""
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-7-sonnet-20250219
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
NVIDIA_NIM_API_KEY=
NVIDIA_NIM_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=nvidia/llama-3.1-nemotron-70b-instruct
API_URL=http://localhost:8000
NODE_URL=http://localhost:4000
""".strip(),

"backend-python/requirements.txt": r"""
fastapi
uvicorn[standard]
httpx
python-dotenv
pydantic
python-multipart
pandas
openpyxl
python-docx
python-pptx
""".strip(),

"backend-python/Dockerfile": r"""
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""".strip(),

"backend-python/main.py": r'''
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from docx import Document
from pptx import Presentation
from openpyxl import Workbook

load_dotenv()

app = FastAPI(
    title="Super Agent API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

OUTPUT = Path("generated")
OUTPUT.mkdir(exist_ok=True)

AGENTS = {
    "openai": "Deep Research & Swarm Agent",
    "anthropic": "Claude Artifacts Agent",
    "google": "Project Astra Multimodal Agent",
    "microsoft": "Office Enterprise Agent",
    "nvidia": "Nemotron Logic & Router Agent",
}

class Task(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    agent: str = "auto"
    file_text: Optional[str] = Field(default=None, max_length=100000)

def detect_agent(prompt: str) -> str:
    p = prompt.lower()

    if any(x in p for x in [
        "excel", "spreadsheet", "xlsx", "powerpoint",
        "presentation", "pptx", "word document", "docx",
        "office report"
    ]):
        return "microsoft"

    if any(x in p for x in [
        "website", "build an app", "write code",
        "react", "html", "typescript", "javascript",
        "artifact", "program"
    ]):
        return "anthropic"

    if any(x in p for x in [
        "camera", "image", "picture", "video",
        "audio", "voice", "multimodal"
    ]):
        return "google"

    if any(x in p for x in [
        "research", "latest", "sources", "citations",
        "compare companies", "deep research", "investigate"
    ]):
        return "openai"

    return "nvidia"

async def openai_agent(prompt: str) -> dict:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, "Configure OPENAI_API_KEY in .env")

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
                "tools": [{"type": "web_search"}],
                "input": (
                    "Act as a careful research analyst. "
                    "Investigate the request, distinguish facts "
                    "from uncertainty, use web search and include "
                    "source citations and an executive summary.\n\n"
                    + prompt
                )
            }
        )

    if response.status_code >= 400:
        raise HTTPException(502, "OpenAI provider error: " + response.text[:800])

    data = response.json()
    citations = []

    for item in data.get("output", []):
        for content in item.get("content", []):
            for annotation in content.get("annotations", []):
                citation = annotation.get("url_citation")
                if citation:
                    citations.append({
                        "title": citation.get("title", "Source"),
                        "url": citation.get("url", "")
                    })

    return {
        "agent": "openai",
        "answer": data.get("output_text", ""),
        "citations": citations
    }

async def google_agent(prompt: str) -> dict:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(503, "Configure GEMINI_API_KEY in .env")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent?key={key}"
    )

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            url,
            json={
                "contents": [{
                    "parts": [{
                        "text": (
                            "You are a multimodal AI assistant. "
                            "Analyze the supplied content carefully.\n\n"
                            + prompt
                        )
                    }]
                }]
            }
        )

    if response.status_code >= 400:
        raise HTTPException(502, "Gemini provider error: " + response.text[:800])

    data = response.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    answer = "\n".join(p.get("text", "") for p in parts)

    return {"agent": "google", "answer": answer, "citations": []}

async def nvidia_agent(prompt: str) -> dict:
    key = os.getenv("NVIDIA_NIM_API_KEY")
    if not key:
        raise HTTPException(503, "Configure NVIDIA_NIM_API_KEY in .env")

    base = os.getenv(
        "NVIDIA_NIM_URL",
        "https://integrate.api.nvidia.com/v1"
    ).rstrip("/")

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.getenv(
                    "NVIDIA_MODEL",
                    "nvidia/llama-3.1-nemotron-70b-instruct"
                ),
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise logic and reasoning assistant."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 3000
            }
        )

    if response.status_code >= 400:
        raise HTTPException(502, "NVIDIA provider error: " + response.text[:800])

    data = response.json()
    answer = data["choices"][0]["message"]["content"]

    return {"agent": "nvidia", "answer": answer, "citations": []}

async def anthropic_agent(prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            response = await client.post(
                os.getenv("NODE_URL", "http://localhost:4000") + "/run",
                json={"prompt": prompt}
            )
        except httpx.RequestError:
            raise HTTPException(503, "Anthropic Node service is unavailable")

    if response.status_code >= 400:
        raise HTTPException(502, response.text[:800])

    data = response.json()
    return {
        "agent": "anthropic",
        "answer": data["answer"],
        "artifact": data.get("artifact"),
        "citations": []
    }

def create_office_files(prompt: str, answer: str) -> dict:
    identifier = uuid.uuid4().hex[:10]

    # Word document
    doc = Document()
    doc.add_heading("AI Enterprise Report", 0)
    doc.add_heading("Request", level=1)
    doc.add_paragraph(prompt)
    doc.add_heading("Generated Report", level=1)
    doc.add_paragraph(answer)
    doc.save(OUTPUT / f"{identifier}.docx")

    # Excel workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "AI Report"
    sheet.append(["Section", "Content"])
    sheet.append(["Request", prompt])
    sheet.append(["Generated Report", answer])
    sheet.column_dimensions["A"].width = 25
    sheet.column_dimensions["B"].width = 90
    workbook.save(OUTPUT / f"{identifier}.xlsx")

    # PowerPoint presentation
    presentation = Presentation()
    slide = presentation.slides.add_slide(
        presentation.slide_layouts[1]
    )
    slide.shapes.title.text = "AI Enterprise Report"
    slide.placeholders[1].text = prompt[:1000]

    slide2 = presentation.slides.add_slide(
        presentation.slide_layouts[1]
    )
    slide2.shapes.title.text = "Results"
    slide2.placeholders[1].text = answer[:3000]

    presentation.save(OUTPUT / f"{identifier}.pptx")

    return {
        "docx": f"/files/{identifier}.docx",
        "xlsx": f"/files/{identifier}.xlsx",
        "pptx": f"/files/{identifier}.pptx"
    }

@app.get("/health")
async def health():
    return {"status": "online", "agents": list(AGENTS.keys())}

@app.get("/agents")
async def agents():
    return AGENTS

@app.get("/files/{filename}")
async def download_file(filename: str):
    from fastapi.responses import FileResponse

    if not re.fullmatch(r"[a-f0-9]{10}\.(docx|xlsx|pptx)", filename):
        raise HTTPException(400, "Invalid filename")

    path = OUTPUT / filename
    if not path.is_file():
        raise HTTPException(404, "File not found")

    return FileResponse(path, filename=filename)

@app.post("/api/run")
async def run_task(task: Task):
    prompt = task.prompt.strip()

    if task.file_text:
        prompt += "\n\nUploaded file content:\n" + task.file_text

    selected = task.agent.lower()

    if selected == "auto":
        selected = detect_agent(prompt)

    if selected not in AGENTS:
        raise HTTPException(400, "Unknown agent")

    if selected == "openai":
        result = await openai_agent(prompt)

    elif selected == "google":
        result = await google_agent(prompt)

    elif selected == "nvidia":
        result = await nvidia_agent(prompt)

    elif selected == "anthropic":
        result = await anthropic_agent(prompt)

    else:
        if not os.getenv("OPENAI_API_KEY"):
            raise HTTPException(
                503,
                "Microsoft Office export currently needs OPENAI_API_KEY."
            )
        result = await openai_agent(
            "Create a structured, professional business report for "
            "the following request:\n" + prompt
        )
        result["agent"] = "microsoft"
        result["files"] = create_office_files(
            prompt,
            result["answer"]
        )

    result["agent_name"] = AGENTS[selected]
    return result
''',

"backend-node/package.json": r'''
{
  "name": "super-agent-anthropic",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "start": "tsx src/index.ts",
    "build": "tsc"
  },
  "dependencies": {
    "@anthropic-ai/sdk": "^0.39.0",
    "cors": "^2.8.5",
    "dotenv": "^16.4.7",
    "express": "^4.21.2"
  },
  "devDependencies": {
    "@types/cors": "^2.8.17",
    "@types/express": "^5.0.0",
    "@types/node": "^22.13.4",
    "tsx": "^4.19.3",
    "typescript": "^5.7.3"
  }
}
''',

"backend-node/tsconfig.json": r'''
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist"
  },
  "include": ["src/**/*.ts"]
}
''',

"backend-node/Dockerfile": r'''
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 4000
CMD ["npm", "start"]
''',

"backend-node/src/index.ts": r'''
import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import Anthropic from "@anthropic-ai/sdk";

dotenv.config();

const app = express();
app.use(cors({ origin: "http://localhost:3000" }));
app.use(express.json({ limit: "2mb" }));

app.get("/health", (_req, res) => {
  res.json({ status: "online", agent: "anthropic" });
});

app.post("/run", async (req, res) => {
  try {
    const prompt = req.body?.prompt;

    if (typeof prompt !== "string" || !prompt.trim()) {
      return res.status(400).json({ error: "Prompt required" });
    }

    if (!process.env.ANTHROPIC_API_KEY) {
      return res.status(503).json({
        error: "Configure ANTHROPIC_API_KEY in .env"
      });
    }

    const anthropic = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY
    });

    const message = await anthropic.messages.create({
      model: process.env.ANTHROPIC_MODEL ||
        "claude-3-7-sonnet-20250219",
      max_tokens: 4096,
      messages: [{
        role: "user",
        content:
          "You are an AI coding and artifact assistant. " +
          "Explain your approach, write complete code when asked, " +
          "and do not claim to have executed code that you did not execute.\n\n" +
          prompt
      }]
    });

    const answer = message.content
      .filter((block) => block.type === "text")
      .map((block) => block.text)
      .join("\n");

    res.json({ answer, artifact: null });
  } catch (error) {
    console.error("Anthropic error:", error);
    res.status(502).json({ error: "Anthropic request failed" });
  }
});

app.listen(4000, "0.0.0.0", () => {
  console.log("Anthropic service running on port 4000");
});
''',

"frontend/package.json": r'''
{
  "name": "super-agent-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev -H 0.0.0.0",
    "build": "next build",
    "start": "next start -H 0.0.0.0"
  },
  "dependencies": {
    "framer-motion": "^11.18.2",
    "lucide-react": "^0.468.0",
    "next": "14.2.24",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/node": "^22.13.4",
    "@types/react": "^18.3.18",
    "@types/react-dom": "^18.3.5",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.5.2",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.3"
  }
}
''',

"frontend/tsconfig.json": r'''
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{"name": "next"}],
    "paths": {"@/*": ["./*"]}
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
''',

"frontend/next.config.mjs": r'''
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true
};
export default nextConfig;
''',

"frontend/tailwind.config.ts": r'''
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        background: "#080b13",
        panel: "#111827",
        accent: "#8b5cf6"
      }
    }
  },
  plugins: []
};

export default config;
''',

"frontend/postcss.config.mjs": r'''
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {}
  }
};
''',

"frontend/app/globals.css": r'''
@tailwind base;
@tailwind components;
@tailwind utilities;

* { box-sizing: border-box; }

body {
  margin: 0;
  background: #080b13;
  color: #f8fafc;
  font-family: Arial, Helvetica, sans-serif;
}

button, textarea, select { font: inherit; }

.glass {
  background: rgba(17, 24, 39, .75);
  border: 1px solid rgba(148, 163, 184, .14);
  backdrop-filter: blur(20px);
}

.glow {
  box-shadow: 0 0 35px rgba(139, 92, 246, .12);
}

.gradient-text {
  background: linear-gradient(90deg, #c4b5fd, #67e8f9);
  -webkit-background-clip: text;
  color: transparent;
}

.agent-active {
  border-color: #8b5cf6 !important;
  background: rgba(139, 92, 246, .16) !important;
}

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb {
  background: #374151;
  border-radius: 10px;
}
''',

"frontend/app/layout.tsx": r'''
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nexus AI | Super Agent",
  description: "Unified multi-agent AI workspace"
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
''',

"frontend/app/page.tsx": r'''
"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles, BrainCircuit, Search, Code2, Globe2,
  FileSpreadsheet, Send, Paperclip, Loader2,
  CheckCircle2, Cpu, ArrowUpRight, FileText,
  Presentation
} from "lucide-react";

const agents = [
  { id: "auto", name: "Auto Agent", icon: Sparkles },
  { id: "openai", name: "Deep Research", icon: Search },
  { id: "anthropic", name: "Claude Artifacts", icon: Code2 },
  { id: "google", name: "Google Astra", icon: Globe2 },
  { id: "microsoft", name: "Office Agent", icon: FileSpreadsheet },
  { id: "nvidia", name: "Nemotron", icon: BrainCircuit }
];

type Result = {
  agent?: string;
  agent_name?: string;
  answer?: string;
  citations?: { title: string; url: string }[];
  files?: { docx: string; xlsx: string; pptx: string };
};

export default function Home() {
  const [agent, setAgent] = useState("auto");
  const [prompt, setPrompt] = useState("");
  const [fileText, setFileText] = useState("");
  const [fileName, setFileName] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  async function attachFile(file?: File) {
    if (!file) return;

    if (file.size > 1024 * 1024) {
      setError("Text uploads are limited to 1 MB.");
      return;
    }

    if (!/\.(txt|md|csv|json)$/i.test(file.name)) {
      setError("This starter supports TXT, MD, CSV and JSON text files.");
      return;
    }

    const text = await file.text();
    setFileText(text);
    setFileName(file.name);
    setError("");
  }

  async function submit() {
    if (!prompt.trim() || loading) return;

    setLoading(true);
    setError("");
    setResult(null);
    setHistory(["Analyzing your request", "Selecting the appropriate agent"]);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt,
            agent,
            file_text: fileText || null
          })
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.error || "Request failed");
      }

      setResult(data);
      setHistory(old => [...old, `Routed to ${data.agent_name}`, "Task completed"]);
      setPrompt("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen">
      <header className="h-16 border-b border-white/10 px-5 md:px-10 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-violet-500/20 flex items-center justify-center">
            <BrainCircuit className="text-violet-300" size={22}/>
          </div>
          <span className="font-bold tracking-tight text-lg">
            NEXUS<span className="text-violet-400">.AI</span>
          </span>
          <span className="hidden sm:block text-xs text-gray-500 border border-white/10 rounded-full px-2 py-1">
            MULTI-AGENT WORKSPACE
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs text-emerald-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400"/>
          SYSTEM ONLINE
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 md:px-8 py-12">
        <section className="text-center mb-10">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="inline-flex gap-2 items-center rounded-full border border-violet-400/20 bg-violet-400/10 px-4 py-2 text-xs text-violet-300 mb-6">
              <Sparkles size={14}/>
              FIVE SPECIALIZED AGENTS. ONE WORKSPACE.
            </div>

            <h1 className="text-4xl md:text-6xl font-bold tracking-tight">
              Your intelligence.
              <br/>
              <span className="gradient-text">Without boundaries.</span>
            </h1>

            <p className="mt-5 text-gray-400 max-w-xl mx-auto text-sm md:text-base leading-7">
              Research, build, reason, analyze and create.
              Let the master router choose the right AI engine.
            </p>
          </motion.div>
        </section>

        <section className="max-w-4xl mx-auto">
          <div className="flex flex-wrap gap-2 justify-center mb-6">
            {agents.map(a => {
              const Icon = a.icon;
              return (
                <button
                  key={a.id}
                  onClick={() => setAgent(a.id)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-xl border border-white/10 text-xs transition-all ${
                    agent === a.id ? "agent-active text-white" : "text-gray-400 hover:bg-white/5"
                  }`}
                >
                  <Icon size={15}/>
                  {a.name}
                </button>
              );
            })}
          </div>

          <div className="glass glow rounded-2xl p-4 md:p-6">
            <div className="flex items-center gap-2 mb-4 text-xs text-gray-400">
              <Cpu size={15} className="text-violet-400"/>
              {agent === "auto" ? "AUTOMATIC AGENT ROUTING ENABLED" : `MANUAL MODE: ${agent.toUpperCase()}`}
            </div>

            <textarea
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder="What would you like your AI team to accomplish?"
              className="w-full h-36 resize-none outline-none bg-transparent text-white placeholder:text-gray-600 text-base leading-7"
            />

            {fileName && (
              <div className="text-xs text-violet-300 py-2">
                <Paperclip size={13} className="inline mr-2"/>
                {fileName}
                <button onClick={() => {
                  setFileName("");
                  setFileText("");
                }} className="ml-3 text-gray-500">Remove</button>
              </div>
            )}

            <div className="flex justify-between items-center border-t border-white/10 pt-4">
              <div className="flex gap-2">
                <input
                  ref={fileInput}
                  type="file"
                  accept=".txt,.md,.csv,.json"
                  className="hidden"
                  onChange={e => attachFile(e.target.files?.[0])}
                />
                <button
                  onClick={() => fileInput.current?.click()}
                  className="p-2.5 rounded-xl bg-white/5 text-gray-400 hover:text-white"
                  title="Attach text file"
                >
                  <Paperclip size={18}/>
                </button>
                <span className="text-xs text-gray-600 self-center hidden sm:block">
                  SHIFT + ENTER FOR NEW LINE
                </span>
              </div>

              <button
                disabled={!prompt.trim() || loading}
                onClick={submit}
                className="flex gap-2 items-center bg-violet-600 hover:bg-violet-500 disabled:opacity-40 px-5 py-3 rounded-xl text-sm font-semibold transition-all"
              >
                {loading ? <Loader2 size={17} className="animate-spin"/> : <Send size={17}/>}
                Execute
              </button>
            </div>
          </div>
        </section>

        <AnimatePresence>
          {(loading || result || error) && (
            <motion.section
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="max-w-4xl mx-auto mt-8"
            >
              {loading && (
                <div className="glass rounded-xl p-5 mb-4">
                  <div className="flex gap-3 items-center text-violet-300 text-sm font-semibold">
                    <Loader2 className="animate-spin" size={18}/>
                    Master router executing...
                  </div>
                  {history.map((h, i) => (
                    <div key={i} className="mt-3 text-xs text-gray-400 flex gap-2 items-center">
                      <CheckCircle2 size={14} className="text-emerald-400"/>
                      {h}
                    </div>
                  ))}
                </div>
              )}

              {error && (
                <div className="border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl p-4 text-sm">
                  {error}
                </div>
              )}

              {result && (
                <div className="glass rounded-2xl overflow-hidden">
                  <div className="border-b border-white/10 p-5 flex flex-wrap gap-3 justify-between items-center">
                    <div>
                      <div className="text-xs text-emerald-400 mb-2">
                        <CheckCircle2 size={13} className="inline mr-2"/>
                        TASK COMPLETED
                      </div>
                      <h2 className="font-semibold">{result.agent_name}</h2>
                    </div>
                    <span className="text-xs text-violet-300 bg-violet-400/10 px-3 py-2 rounded-full">
                      ⚡ Agent routed
                    </span>
                  </div>

                  <div className="p-5 md:p-7">
                    <div className="whitespace-pre-wrap break-words text-sm leading-7 text-gray-200">
                      {result.answer}
                    </div>

                    {!!result.citations?.length && (
                      <div className="mt-8 pt-5 border-t border-white/10">
                        <h3 className="font-semibold text-sm mb-3">Research sources</h3>
                        {result.citations.map((c, i) => (
                          <a
                            key={i}
                            href={c.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex gap-2 items-center text-xs text-violet-300 py-2 hover:text-white"
                          >
                            <ArrowUpRight size={14}/>
                            {c.title}
                          </a>
                        ))}
                      </div>
                    )}

                    {result.files && (
                      <div className="mt-8 pt-5 border-t border-white/10">
                        <h3 className="font-semibold text-sm mb-4">Generated Office documents</h3>
                        <div className="grid sm:grid-cols-3 gap-3">
                          {[
                            {key:"docx",label:"Word Report",icon:FileText},
                            {key:"xlsx",label:"Excel Workbook",icon:FileSpreadsheet},
                            {key:"pptx",label:"PowerPoint",icon:Presentation}
                          ].map(item => {
                            const Icon = item.icon;
                            const path = result.files![item.key as keyof typeof result.files];
                            return (
                              <a
                                key={item.key}
                                href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${path}`}
                                className="p-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 flex flex-col gap-3"
                              >
                                <Icon size={22} className="text-violet-300"/>
                                <span className="text-xs">{item.label}</span>
                                <span className="text-xs text-violet-300">Download ↗</span>
                              </a>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </motion.section>
          )}
        </AnimatePresence>

        <footer className="text-center mt-20 text-xs text-gray-600">
          NEXUS AI · MULTI-MODEL ARCHITECTURE · PROVIDER API USAGE MAY INCUR COSTS
        </footer>
      </div>
    </main>
  );
}
''',

"frontend/Dockerfile": r'''
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
''',

"docker-compose.yml": r'''
services:
  python-api:
    build: ./backend-python
    env_file:
      - .env
    ports:
      - "8000:8000"
    volumes:
      - ./backend-python/generated:/app/generated

  anthropic-service:
    build: ./backend-node
    env_file:
      - .env
    ports:
      - "4000:4000"

  frontend:
    build:
      context: ./frontend
      args:
        NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - python-api
      - anthropic-service
'''
}

def main():
    print("\nNEXUS AI PROJECT BUILDER")
    print("=" * 45)

    ROOT.mkdir(exist_ok=True)

    for filename, content in FILES.items():
        filename = filename.strip()
        target = ROOT / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.strip() + "\n", encoding="utf-8")
        print("[CREATED]", filename)

    env_path = ROOT / ".env.example"
    actual_env = ROOT / ".env"

    if not actual_env.exists():
        actual_env.write_text(
            env_path.read_text(encoding="utf-8"),
            encoding="utf-8"
        )
        print("[CREATED] .env")

    readme = ROOT / "README.md"
    readme.write_text(
        "# Nexus AI Super Agent\n\n"
        "Multi-provider AI workspace.\n\n"
        "1. Copy API credentials into .env.\n"
        "2. Start services with docker compose up --build.\n"
        "3. Open http://localhost:3000.\n\n"
        "Provider APIs may incur usage charges. "
        "Never commit .env to version control.\n",
        encoding="utf-8"
    )

    print("\n" + "=" * 45)
    print("PROJECT GENERATED SUCCESSFULLY")
    print("Location:", ROOT.resolve())
    print("Next: configure .env and launch the services.")
    print("=" * 45)

if __name__ == "__main__":
    main()
