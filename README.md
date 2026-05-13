# Intent-Grounded CAD — AI-Powered 3D Part Generator

> **Describe a part in plain English. Get a validated, physics-correct, downloadable 3D model.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit)](https://streamlit.io)
[![build123d](https://img.shields.io/badge/CAD-build123d-orange)](https://build123d.readthedocs.io)
[![Gemini](https://img.shields.io/badge/LLM-Gemini%202.0%20Flash-4285F4?logo=google)](https://ai.google.dev)
[![Groq](https://img.shields.io/badge/LLM-Groq%20%2F%20LLaMA--3.3-00A67E)](https://groq.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 📌 Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [System Architecture](#system-architecture)
4. [Multi-Agent Pipeline](#multi-agent-pipeline)
5. [Technology Stack](#technology-stack)
6. [Project Structure](#project-structure)
7. [Installation & Setup](#installation--setup)
8. [Configuration](#configuration)
9. [Running the Application](#running-the-application)
10. [How It Works](#how-it-works)
11. [Supported Shapes & Constraints](#supported-shapes--constraints)
12. [Benchmarking & Evaluation](#benchmarking--evaluation)
13. [Research & Publication](#research--publication)

---

## Overview

**Intent-Grounded CAD** is an end-to-end agentic AI system that transforms natural language descriptions into production-ready 3D CAD models — exported as both **STEP** (solid CAD) and **STL** (mesh for 3D printing) files.

Unlike simple code-generation tools, this system implements a multi-agent, self-correcting pipeline with a real **Physics & Engineering Validator** that actively checks generated geometry against physical laws and manufacturing constraints before returning output to the user. If the geometry fails, the error is automatically fed back to the LLM for correction — up to 15 retry attempts.

This project was developed as part of a research paper exploring **intent-grounded, self-correcting AI pipelines for CAD automation**.

---

## Key Features

| Feature | Description |
|---|---|
| 🧠 **Intent Understanding** | Deterministic extraction of design intent (hollow, bracket, holes, printable) from natural language |
| 🔁 **Self-Correcting Retry Loop** | Automatically feeds errors back to the LLM and re-generates code, up to 15 times |
| ⚙️ **Physics Engine** | Validates manifold integrity, volume, scale accuracy, wall thickness, center-of-mass stability |
| 🛡️ **Guardrails System** | A 40+ entry lookup table intercepts known LLM API hallucinations and provides corrective hints |
| 📚 **RAG Documentation Retrieval** | Retrieves relevant `build123d` documentation snippets using Sentence Transformers + ChromaDB |
| 🔧 **Tool Calling (Function Calling)** | LLMs can autonomously call `get_shape_blueprint()` to fetch validated shape templates |
| 🏭 **DFM Validation** | Checks for flat print beds, 45-degree overhang violations, and thin walls for 3D printability |
| 🌐 **Multi-LLM Support** | Interchangeable backends: Google Gemini 2.0 Flash, Groq LLaMA-3.3-70B, or local Ollama |
| 📥 **Dual Export** | Outputs both `.step` (for CAD software) and `.stl` (for 3D printing slicers) |
| 🖥️ **Streamlit UI** | Clean, minimal web interface with one-click download buttons for both formats |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE (Streamlit)                    │
│            "Make a hollow cylindrical cup with 2mm walls"            │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     AGENT 1: PLANNER (backend.py)                    │
│  • Deterministic intent extraction (is_container, requires_holes…)   │
│  • RAG: Retrieves build123d documentation from ChromaDB              │
│  • Determines forced blueprint type for tool injection               │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   AGENT 2: CODER (core/llm_client.py)               │
│  • Provider: Gemini 2.0 Flash / Groq LLaMA-3.3-70B / Ollama        │
│  • Tool Calling: get_shape_blueprint() → injects validated template  │
│  • Outputs Python code block using build123d                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PYTHON EXECUTION ENGINE (backend.py)                │
│  • exec() executes generated code in isolated scope                  │
│  • Guardrails intercept known API hallucinations (core/guardrails.py)│
│  • Auto-grounds floating parts to Z=0                                │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHYSICS & ENGINEERING VALIDATOR (core/validators.py)   │
│  • Manifold / Volume check                                           │
│  • Scale accuracy (±50% tolerance)                                   │
│  • Container hollowness (fill ratio < 0.7)                           │
│  • Bracket geometry (L-shape check)                                  │
│  • Hole detection (cylindrical face counting)                        │
│  • Center-of-mass stability (tip-over prevention)                    │
│  • DFM: flat base, 45° overhang, minimum wall thickness              │
└────────────────────────┬───────────────────────┬────────────────────┘
                         │                       │
                    PASS ▼                  FAIL ▼
             ┌───────────────────┐   ┌────────────────────────────┐
             │  Export STEP+STL  │   │  Append error to history   │
             │  Return to UI     │   │  Re-prompt LLM (retry loop)│
             └───────────────────┘   └────────────────────────────┘
```

---

## Multi-Agent Pipeline

The system implements a **3-agent architecture**:

### Agent 1 — Planner
- Runs deterministic keyword analysis on the user prompt
- Identifies design intent flags: `is_bracket`, `is_container`, `requires_holes`, `is_3d_printable`
- Selects and retrieves the correct **shape blueprint** to force-inject into the coder's context
- Performs **RAG retrieval** from the local ChromaDB vector store (populated from `build123d` docs)

### Agent 2 — Coder (LLM)
- Receives a structured JSON prompt containing: system instructions, RAG context, user request, error history
- Calls the `get_shape_blueprint()` tool autonomously when needed (via native function calling APIs)
- Generates Python code using the `build123d` parametric CAD library
- On retry: receives a full JSON error report and must mathematically correct the code

### Agent 3 — Validator (Physics Engine)
- Executes the generated code via `exec()`
- Runs a 7-layer physics validation pipeline:
  1. Manifold & volume check
  2. Scale accuracy guard (±50%)
  3. Container hollowness check (fill ratio)
  4. Bracket geometry enforcement
  5. Mounting hole detection (cylindrical faces)
  6. Center-of-mass stability (tip-over prevention)
  7. DFM printability (bed adhesion, 45° overhang rule, wall thickness)

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **UI** | Streamlit | Web interface with chat input & download buttons |
| **LLM (Cloud 1)** | Google Gemini 2.0 Flash | Primary cloud coder agent with tool-calling |
| **LLM (Cloud 2)** | Groq — LLaMA-3.3-70B Versatile | High-speed alternative cloud coder |
| **LLM (Local)** | Ollama — Qwen2.5-Coder | Fully offline, private code generation |
| **CAD Engine** | build123d | Python-native parametric CAD solid modelling |
| **Vector DB** | ChromaDB | Persistent local vector store for documentation RAG |
| **Embeddings** | Sentence Transformers (`all-MiniLM-L6-v2`) | Semantic documentation search |
| **Export** | build123d (`export_stl`, `export_step`) | STEP and STL CAD file export |
| **Config** | python-dotenv | API key management via `.env` file |

---

## Project Structure

```
Intent-Grounded-CAD/
│
├── main.py                     # Streamlit UI entry point
├── backend.py                  # Orchestrator: full AI workflow & retry loop
├── prompts.py                  # System prompts for Gemini, Groq, and Local LLMs
├── requirements.txt            # Python dependencies
├── .gitignore
│
├── core/                       # Core engine modules
│   ├── llm_client.py           # Universal LLM router (Gemini / Groq / Ollama)
│   ├── validators.py           # Physics & engineering validation engine
│   ├── guardrails.py           # LLM hallucination interception (40+ rules)
│   ├── rag_manager.py          # ChromaDB vector store & documentation retrieval
│   ├── tools.py                # Shape Blueprint Vault + function-calling schema
│   └── logger.py               # Experiment logging to CSV
│
├── build123d-docs/             # Official build123d documentation (RST/MD)
│   └── docs/                   # Used to populate ChromaDB vector store
│
├── chroma_db/                  # Persistent ChromaDB vector store (auto-generated)
│
├── generated_files/            # Output directory for generated CAD files (auto-created)
│   └── models/
│       └── <prompt_id>/
│           ├── generated_part.step
│           └── generated_part.stl
│
├── showcase_run/               # Example outputs from benchmark runs
│
├── Architecture.png            # System architecture diagram
│
├── batch_tester.py             # Automated batch benchmarking script
├── showcase_tester.py          # Curated showcase test runner
├── benchmark_results_master.csv# Benchmark results (v1)
├── benchmark_results_master_v2.csv # Benchmark results (v2)
├── detailed_attempt_logs.json  # Per-attempt error & retry logs
├── experiment_logs.csv         # Full experiment history
│
├── gen_figures.py              # Figure generation for research paper
├── gen_stat_tables.py          # Statistical table generation
├── gen_white_figs.py           # White-background figure export
├── regen_user_figs.py          # Regenerate paper figures (standard)
└── regen_user_figs_huge.py     # Regenerate paper figures (large fonts)
```

---

## Installation & Setup

### Prerequisites

- Python **3.10 or higher**
- `pip` package manager
- (Optional) [Ollama](https://ollama.com) installed locally for offline mode

### Step 1 — Clone the Repository

```bash
git clone https://github.com/your-username/Intent-Grounded-CAD.git
cd Intent-Grounded-CAD
```

### Step 2 — Create a Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies installed:**

| Package | Purpose |
|---|---|
| `streamlit` | Web UI framework |
| `build123d` | Parametric CAD engine |
| `google-genai` | Google Gemini API client |
| `python-dotenv` | Environment variable management |
| `requests` | HTTP client |
| `chromadb` | Local vector database |
| `sentence-transformers` | Embedding model for RAG |

> **Note:** Installing `build123d` also installs its dependencies including `OCP` (Open CASCADE Technology Python bindings), which is a large package (~500MB).

### Step 4 — Build the Vector Database (RAG)

This step indexes the `build123d` documentation into ChromaDB for retrieval-augmented generation.

```bash
python -c "from core.rag_manager import build_vector_db; n = build_vector_db(); print(f'Indexed {n} document chunks.')"
```

---

## Configuration

Create a `.env` file in the project root directory:

```env
# Required for Gemini provider
GEMINI_API_KEY=your_gemini_api_key_here

# Required for Groq provider
GROQ_API_KEY=your_groq_api_key_here
```

### Getting API Keys

| Provider | API Key URL | Free Tier |
|---|---|---|
| Google Gemini | https://aistudio.google.com/app/apikey | Yes (15 RPM) |
| Groq | https://console.groq.com/keys | Yes (5 RPM) |
| Ollama (Local) | No key needed — install Ollama + pull `qwen2.5-coder` | Fully free |

### Ollama Setup (Local/Offline Mode)

```bash
# Install Ollama from https://ollama.com
# Then pull the coding model:
ollama pull qwen2.5-coder
```

---

## Running the Application

```bash
streamlit run main.py
```

The web interface will open automatically at `http://localhost:8501`.

### Usage

1. Type your part description into the chat input field.
2. The system will show a real-time status while the AI generates and validates the model.
3. On success, two download buttons appear:
   - **📥 Download STEP** — Standard CAD format (open in FreeCAD, Fusion 360, SolidWorks, etc.)
   - **📥 Download STL** — 3D mesh format (open in any slicer: Cura, PrusaSlicer, etc.)

### Example Prompts

```
Make a hollow cylindrical cup with 15mm outer radius and 2mm thick walls
Create an L-bracket with two mounting holes
Design a cantilever stand with a wide base
Generate a 50x50x5mm flat plate with 4 corner mounting holes
Make a sphere with a flat base for 3D printing
Create a 30mm cube
```

---

## How It Works

### 1. Prompt Structuring
The user's natural language input is combined with:
- System engineering instructions (from `prompts.py`)
- Relevant `build123d` documentation retrieved from ChromaDB via semantic search
- Formatting rules (force output inside `<code>...</code>` or triple-backtick blocks)
- On retries: the full error history as a JSON array

All of this is serialised to a **JSON string** and sent as a single message to the LLM. This JSON-structured prompting is specifically designed to help smaller 7B models satisfy all constraints.

### 2. Tool Calling
When the user requests a known shape category (sphere, bracket, cantilever, cone, hollow container, etc.), the backend **forces** the LLM to call `get_shape_blueprint()` before generating code. This injects a pre-validated, syntax-correct template into the LLM's context.

Supported blueprint shapes: `sphere`, `cantilever`, `bracket`, `hollow_container`, `overhang_support`, `cone`, `cube`, `cylinder`, `gear`, `pyramid`.

### 3. Code Execution & Auto-Grounding
The generated Python code is executed via `exec()` in an isolated scope. Before physics validation, the system checks if the part is floating above Z=0 (a common LLM mistake) and automatically translates it down. This is called **Auto-Grounding**.

### 4. Guardrails Interception
Before returning a generic error message to the LLM, `guardrails.py` checks the raw Python traceback against a lookup table of 40+ known `build123d` API hallucinations (e.g., using `diameter=` instead of `radius=`, calling `shell()`, using `translate()`, etc.) and replaces the message with a precise corrective instruction.

### 5. Self-Correcting Loop
If validation fails, the error report is appended to the prompt's `error_history` JSON array, the prompt is updated with a `current_objective` instruction, and the LLM is called again. This loop runs for a maximum of **15 attempts** before the system reports failure.

---

## Supported Shapes & Constraints

### Primitive Shapes
- Box / Cube / Plate / Block
- Cylinder / Disk
- Sphere (auto-flattened base)
- Cone
- Pyramid
- Gear (simplified polygon approximation)

### Composite / Functional Shapes
- L-Bracket / U-Bracket / Mounting Bracket
- Hollow Container (Cup, Bowl, Vase, Pipe, Box)
- Cantilever Stand / Shelf Stand
- Overhang Structures (with auto-support validation)

### Engineering Validations

| Check | Rule |
|---|---|
| Manifold integrity | Part must be watertight (non-zero volume) |
| Scale accuracy | Generated size within ±50% of requested dimension |
| Hollowness | Fill ratio < 0.70 for containers |
| Wall thickness | Minimum 1.2mm for hollow parts |
| Bracket geometry | Fill ratio < 0.70 (must have L/U shape, not a flat plate) |
| Mounting holes | ≥ 1 cylindrical face detected for hole requests |
| Center of mass | CoM must be within base footprint (no tip-over) |
| Bed adhesion (DFM) | Lowest face must be a flat plane |
| Overhang (DFM) | No face with normal Z < -0.707 floating above Z-min |

---

## Benchmarking & Evaluation

The project includes a full benchmarking suite:

### Running Batch Tests

```bash
python batch_tester.py
```

This runs all prompts from `prompts.csv` against the pipeline and logs results to `benchmark_results_master.csv` and `detailed_attempt_logs.json`.

### Running the Showcase Suite

```bash
python showcase_tester.py
```

Runs the curated set of demonstration prompts and saves output models to `showcase_run/`.

### Result Files

| File | Contents |
|---|---|
| `benchmark_results_master.csv` | Success/failure, attempt count, error type per prompt |
| `benchmark_results_master_v2.csv` | Updated benchmark with post-fix improvements |
| `detailed_attempt_logs.json` | Full per-attempt error history for every prompt |
| `experiment_logs.csv` | Complete raw experiment log (all runs) |

### Generating Research Figures

```bash
# Standard figures
python gen_figures.py

# Statistical CI and variance plots
python gen_stat_tables.py

# White-background publication-ready figures (large fonts)
python regen_user_figs_huge.py
```

---

## Research & Publication

This project is the implementation for the research paper:

> **"Intent-Grounded Self-Correcting AI Pipeline for Automated CAD Generation"**

Key contributions documented in the paper:
- Multi-agent AI pipeline with deterministic intent extraction
- Physics-grounded validation with 7-layer constraint enforcement
- Guardrail interception for LLM API hallucination correction
- RAG-augmented prompting from official CAD library documentation
- Comparative benchmarking across Gemini 2.0 Flash, Groq LLaMA-3.3-70B, and Ollama Qwen2.5-Coder
- Statistical analysis: Wilson confidence intervals, McNemar's significance test, retry iteration distribution

---

Author
Vishwa Sundar S
