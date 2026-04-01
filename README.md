# Cognitive Twin

> A memory-driven AI system that learns how a user thinks and simulates their decisions.

---

## Overview

**Cognitive Twin** is a full-stack AI system designed to model user behavior, thinking patterns, and decision-making processes.

Unlike traditional chatbots that generate generic responses, this system builds a **persistent cognitive profile** and uses it to **simulate what the user would do in new situations**.

---

## Problem

Most AI systems today:

- Provide generic, one-size-fits-all responses
- Lack persistent understanding of the user
- Do not learn from behavior over time

There is no system that understands **how a user thinks and decides**.

---

## Solution

Cognitive Twin introduces a **behavior-aware AI system** that:

- Learns thinking patterns from conversations
- Stores structured and semantic memory
- Builds a dynamic cognitive profile
- Simulates user decisions with reasoning

---

## Key Features

### Cognitive Modeling

- Extracts thinking style, decision traits, and preferences
- Builds a structured cognitive profile over time

### Memory System

- JSON storage -> structured behavioral data
- FAISS -> semantic retrieval of past experiences

### Simulation Engine

- Predicts user decisions in new scenarios
- Generates reasoning grounded in past behavior

### Lifecycle-Based Twin Generation

- Training -> Deployment -> Reset
- After sufficient interactions, a stable Cognitive Twin is formed
- System resets to model a new user while preserving previous twin

### Real-Time Sync

- WebSocket-based updates for memory, profile, and simulation

---

## System Architecture

```text
User Input
 -> Extraction Engine
 -> Memory System (JSON + FAISS)
 -> Cognitive Profile
 -> Simulation Engine
 -> Output (Decision + Reasoning)
```

## Tech Stack

### Frontend

- React 19 + TypeScript + Vite
- Tailwind CSS

### Backend Setup

- FastAPI + Pydantic

### AI Layer

- OpenRouter (Gemma 27B + LLaMA 70B)

### Memory Layer

- JSON (structured memory)
- FAISS (vector search)

## Example

### User Input

I prefer risky opportunities over safe jobs.

### Simulation

The user would likely reject a stable corporate job due to a strong preference for growth, risk-taking, and building new ventures.

## What Makes It Unique

- Moves beyond chatbots into a cognitive modeling system
- Simulates decisions, not just answers questions
- Combines memory, reasoning, and personalization
- Supports lifecycle-based AI identity generation

## API Overview

- POST /api/v1/chat -> interact with Cognitive Twin
- GET /api/v1/memory/{session_id} -> retrieve memory
- GET /api/v1/twin/{session_id}/profile -> cognitive profile
- POST /api/v1/twin/simulate -> decision simulation
- WS /ws/{session_id} -> real-time updates

## Setup

### Backend

```powershell
cd backend
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set:

```env
OPENROUTER_API_KEY=your_key
DEFAULT_MODEL=meta-llama/llama-3.3-70b-instruct
```

Run:

```powershell
fastapi dev app/main.py
```

### Frontend Setup

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

## Data Storage

- data/json -> structured memory
- data/faiss -> vector index
- data/json/archive -> archived cognitive twins

## Development

### Backend Commands

```powershell
pytest -q
ruff check app tests
mypy app
bandit -r app
```

### Frontend Commands

```powershell
npm run lint
npm run typecheck
npm run build
```

## Future Enhancements

- Emotion-aware cognitive modeling
- Reinforcement learning-based adaptation
- Multi-user scalable deployment
- Behavioral analytics dashboard

## Final Thought

Cognitive Twin represents a shift from:

- AI that answers questions
- AI that understands and simulates human behavior

## Notes

- Designed for local development and experimentation
- Do not commit .env files
- Ensure required environment variables are set before running
