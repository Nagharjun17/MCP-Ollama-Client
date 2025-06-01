# MCP-Ollama Client

Minimal chat client that:

1. **Runs fully offline with a local LLM provided by Ollama**  
2. **Talks to any number of Model-Context-Protocol (MCP) servers** described in a single `config.json` file.

The client merges the tools exposed by every running MCP server into one unified chat interface, so the model can decide which server to call at each step.

---

## Features

| What | Details |
|------|---------|
| **Local LLM first** | Uses the `qwen3:14b` (or any other **function-calling capable**) Ollama model. Everything stays on your machine – no cloud keys required. |
| **Multi-server out of the box** | Spin up Postgres, filesystem, or custom MCP servers side-by-side. The client reads their launch commands from `config.json` and routes tool calls automatically. |
| **Single session, merged tools** | The LLM sees tools as `postgres.list_schemas`, `filesystem.read_file`, etc., so name collisions are avoided without extra prompting. |

---

## Requirements

| Component | Tested version |
|-----------|----------------|
| Python | ≥ 3.12 |
| Ollama | ≥ 0.8.0 |
| MCP servers | any that support **stdio** transport (Postgres-MCP ≥ 0.3.1, filesystem server, …) |

---

## Quick start

```bash
# 1. clone
git clone https://github.com/<you>/mcp-ollama-client.git
cd mcp-ollama-client

# 2. create venv & install
uv venv
source .venv/bin/activate
uv pip install --upgrade -r uv.lock  # or uv pip sync

# 3. pull a local LLM
ollama pull qwen3:14b

# 4. edit DATABASE_URI etc. in config.json

# 5. run
uv run client.py

You’ll see:
🔌 Starting MCP server: postgres
🔌 Starting MCP server: filesystem
🛠️  Aggregated tools: ['postgres.list_schemas', 'filesystem.read_file', ...]
>>> 

Type natural-language queries; the client (via the model) will decide when to call which tool.

config.json format

{
  "mcpServers": {
    "postgres": {
      "command": "postgres-mcp",
      "args": ["--access-mode=restricted"],
      "env": {
        "DATABASE_URI": "postgresql://username:password@localhost:5432/dbname"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/mnt/smbshare/"
      ]
    }
  }
}

Keys under mcpServers become prefixes (postgres.*, filesystem.*).

Every server is launched through its own stdio process; use Docker/uv run/npx/direct binary as you prefer.

Add or remove servers without touching client.py.
