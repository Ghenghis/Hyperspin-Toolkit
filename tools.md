# Agentic E2E Tools for HyperSpin Extreme Toolkit

## RESEARCHED — Full analysis in AGENTIC_TOOLS_INTEGRATION.md

### CRITICAL: Goose (Block) — AI Agent Runtime
- **Repo**: https://github.com/block/goose.git
- **Release**: https://github.com/block/goose/releases/tag/v1.27.2
- **What**: Open-source AI agent that works with ANY LLM (Ollama, LM Studio, vLLM)
- **Why**: Provides the agentic runtime — users speak natural language, Goose runs toolkit commands
- **Local LLM**: Full Ollama + LM Studio support, no cloud required
- **MCP**: Native MCP server integration — our toolkit exposed as tools via `mcp_bridge.py`
- **Status**: INTEGRATE FIRST

### HIGH: CLI-Anything (HKUDS) — Make Software Agent-Native
- **Repo**: https://github.com/HKUDS/CLI-Anything.git
- **What**: Auto-generates CLI wrappers for ANY software, making it agent-controllable
- **Why**: Can wrap HyperSpin, RocketLauncher, ClrMamePro, and our own toolkit
- **Features**: --json output on all commands, SKILL.md for agent discovery, REPL mode
- **Status**: INTEGRATE SECOND — generates agent-optimized CLI + SKILL.md

### MEDIUM: OpenShell (NVIDIA) — Sandboxed Agent Runtime
- **Repo**: https://github.com/NVIDIA/OpenShell
- **Release**: https://github.com/NVIDIA/OpenShell/releases/tag/v0.0.8
- **What**: Safe runtime for autonomous AI agents with network policy + filesystem isolation
- **Why**: Safety layer for when agents autonomously modify files on 12 TB collection
- **Requires**: Docker Desktop + K3s
- **Status**: OPTIONAL — add when running fully autonomous agents

### LOW: NemoClaw (NVIDIA) — OpenClaw Plugin for OpenShell
- **Repo**: https://github.com/NVIDIA/NemoClaw.git
- **What**: Plugin that routes inference through NVIDIA cloud (Nemotron models)
- **Why NOT**: We want LOCAL inference via Ollama/LM Studio, not cloud dependency
- **Status**: SKIP — doesn't align with local-first architecture

## Integration Architecture
```
User (natural language) → Goose (Ollama local) → MCP Bridge → Toolkit → D:\Arcade\
                                                    ↑
                                          CLI-Anything SKILL.md
```

## See Also
- `AGENTIC_TOOLS_INTEGRATION.md` — Full deep-dive research on all 4 tools
- `FIX_GUIDE.md` — All known issues with verified fixes
- `RESEARCH_TOOLS_INTEGRATION.md` — 53 GitHub tools for ROM mgmt, patching, scraping
- `mcp_bridge.py` — MCP server implementation for Goose integration