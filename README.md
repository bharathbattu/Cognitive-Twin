# Cognitive Twin

> A memory-driven AI system that builds a persistent cognitive profile and simulates how a user is likely to decide in new situations.

## Overview

Cognitive Twin is an open-source full-stack AI system for modeling user behavior, preferences, and decision patterns over time. Instead of producing generic replies, it combines structured memory, semantic retrieval, and reasoning to generate decisions grounded in prior interactions.

The project is designed as a reference architecture for developers interested in personalized AI, long-term memory systems, behavior-aware assistants, and simulation-driven agent workflows.

## Why this project matters

Most AI products still operate with shallow session memory. They can answer questions, but they usually do not preserve a durable understanding of how a person thinks, what they value, or how they make trade-offs.

Cognitive Twin explores a different approach:

- Persistent user understanding instead of session-only context.
- Memory-backed reasoning instead of generic one-shot responses.
- Decision simulation instead of simple text generation.
- A reusable architecture for building personalized AI systems.

This makes the project useful not only as an application, but also as an open-source foundation for experimentation in memory, personalization, and cognitive modeling.

## Core idea

The system learns from user interactions, extracts behavioral traits and preferences, stores them in long-term memory, and uses that history to simulate likely actions in unfamiliar scenarios.

In simple terms:

1. A user interacts with the system.
2. The system extracts useful behavioral signals.
3. Those signals are stored in structured and semantic memory.
4. A cognitive profile is updated over time.
5. The simulation engine predicts what the user would likely choose, with reasoning tied to prior evidence.

## Problem

Most AI systems today have three major limitations:

- They provide broad, one-size-fits-all responses.
- They do not maintain a meaningful model of the user across time.
- They rarely reason from behavioral history when generating suggestions or decisions.

As a result, even advanced chat systems often feel stateless, repetitive, or weakly personalized.

## Solution

Cognitive Twin introduces a behavior-aware architecture that:

- Learns thinking style, preferences, and decision tendencies from interactions.
- Stores both structured memory and semantic memory.
- Maintains a dynamic cognitive profile that evolves over time.
- Simulates user decisions with reasoning grounded in past behavior.

## Key features

### Cognitive modeling

- Extracts thinking style, preferences, and decision traits from conversations.
- Builds a structured cognitive profile that becomes more useful over repeated interactions.
- Separates behavioral understanding from raw chat history.

### Memory system

- JSON storage for structured long-term behavioral data.
- FAISS-based vector retrieval for semantic access to relevant past experiences.
- Archived memory lifecycle to support reuse, reset, and future extension.

### Simulation engine

- Predicts likely user choices in new situations.
- Produces reasoning based on observed preferences and prior patterns.
- Moves beyond response generation into behavior-oriented inference.

### Lifecycle-based twin generation

- Training -> profile formation -> deployment -> reset.
- Supports forming a stable twin after enough interaction.
- Preserves previous twins while allowing the system to begin modeling a new user.

### Real-time sync

- WebSocket-based updates for memory, profile state, and simulation output.
- Improves responsiveness for interactive interfaces and monitoring.

## Architecture

```text
User Input
 -> Extraction Engine
 -> Memory System (JSON + FAISS)
 -> Cognitive Profile
 -> Simulation Engine
 -> Output (Decision + Reasoning)
```

### System flow

- **Extraction Engine**: Identifies preferences, traits, reasoning cues, and behavioral signals.
- **Memory Layer**: Stores facts and experiences in both structured JSON and semantic vector memory.
- **Cognitive Profile**: Aggregates persistent user patterns into a usable profile.
- **Simulation Engine**: Uses memory plus profile context to infer likely future decisions.
- **Response Layer**: Returns both the predicted decision and the reasoning behind it.

## Example

### User input

> I usually choose risky opportunities over safe jobs if there is strong learning potential.

### Simulated outcome

The system may infer that the user is more likely to reject a stable corporate role in favor of a higher-growth but uncertain opportunity, especially when autonomy, upside, or learning potential is high.

## Tech stack

### Frontend

- React 19
- TypeScript
- Vite
- Tailwind CSS

### Backend

- FastAPI
- Pydantic

### AI layer

- OpenRouter
- Gemma 27B
- LLaMA 70B

### Memory layer

- JSON for structured memory
- FAISS for semantic retrieval

## API overview

- `POST /api/v1/chat` -> interact with Cognitive Twin
- `GET /api/v1/memory/{session_id}` -> retrieve memory state
- `GET /api/v1/twin/{session_id}/profile` -> retrieve cognitive profile
- `POST /api/v1/twin/simulate` -> simulate user decision-making
- `WS /ws/{session_id}` -> stream real-time updates

## Project structure

```text
backend/
frontend/
data/
  json/
  faiss/
  json/archive/
```

## Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
```

Set the environment variables:

```env
OPENROUTER_API_KEY=your_key
DEFAULT_MODEL=meta-llama/llama-3.3-70b-instruct
```

Run the backend:

```bash
fastapi dev app/main.py
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Development commands

### Backend

```bash
pytest -q
ruff check app tests
mypy app
bandit -r app
```

### Frontend

```bash
npm run lint
npm run typecheck
npm run build
```

## Use cases

Cognitive Twin can serve as a foundation for:

- Personalized AI assistants with long-term user understanding.
- Decision-support systems that adapt to individual behavior.
- Research prototypes in memory-augmented agents.
- Behavioral simulation systems for coaching, reflection, or recommendation.
- Experimental products built around persistent AI identity.

## What makes it different

- It focuses on modeling how a user thinks, not just what they say.
- It treats memory as a first-class system component.
- It generates decision simulations, not only responses.
- It combines personalization, retrieval, and reasoning in one architecture.
- It is designed as an extensible open-source project rather than a closed demo.

## Roadmap

Planned directions include:

- Emotion-aware cognitive modeling.
- Reinforcement learning-based adaptation.
- Better evaluation pipelines for simulation accuracy.
- Multi-user deployment and scaling.
- Behavioral analytics and developer-facing dashboards.

## Open-source direction

This repository is being developed as a collaborative open-source project focused on memory-aware and behavior-aware AI systems. Contributions, architectural feedback, experiments, and extensions are welcome.

Good first contribution areas include:

- Improving memory extraction quality.
- Expanding simulation evaluation and benchmarks.
- Strengthening API documentation.
- Building cleaner frontend visualizations for profile and memory state.
- Adding test coverage and developer tooling.

## Notes

- Built for local development and experimentation.
- Do not commit `.env` files.
- Ensure required environment variables are configured before running the project.

## Maintainers

The project is being built collaboratively by Bharath Kumar and B. Rickwith as an exploration of personalized, memory-driven AI systems.
