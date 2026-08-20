# Orient an agent to flip

Here's flip: a tool for structured research notebooks that survive the session, the agent, and the model.

## The goal

Read this repository and tell the person whether flip is worth adopting, and what adopting it would look like in their context.

You decide what "worth adopting" means. Look at the examples, the spec, the CLI, the skills. Surface what matters. Ask questions if the repo doesn't answer them.

## What flip is

flip is a CLI and plain-file format for reporter's notebooks. A notebook captures the sources, the judgments, the claims, the questions, and an append-only record of who did what. It is an OKF v0.2 bundle that lives in Git, opens in Obsidian, and can be read without flip.

It is not a retrieval system, vector store, or agent framework. It is the durable record beneath those tools.

## If it looks promising

The [AGENTS.md](../AGENTS.md) contract and the skills in `src/flip/skills/` are the runtime-neutral layer. The [SPEC.md](../SPEC.md) defines the notebook format. The [quickstart](quickstart.md) and harness guides explain the mechanics.

Install the plugin for your harness first. The creation skill will guide the one-time CLI setup if needed.

Humans steer the research. The agent maintains the record. The notebook compounds across sessions.