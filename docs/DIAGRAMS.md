# HyperSpin Extreme Toolkit — Architecture Diagrams

> All diagrams use [Mermaid](https://mermaid.js.org/) syntax and render natively on GitHub.

---

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph User Layer
        USER["User (Natural Language)"]
        CLI["CLI (main.py)"]
        DASH["Web Dashboard<br/>:8888"]
        GOOSE["Goose Desktop / CLI"]
    end

    subgraph Orchestration Layer
        MCP["MCP Bridge<br/>236 tools<br/>mcp_bridge.py"]
        CIA["CLI-Anything Bridge<br/>2 tools"]
        NEMO["NemoClaw Agents<br/>3 tools / 6 roles"]
        OH["OpenHands Bridge<br/>5 tools"]
    end

    subgraph Engine Layer
        ENG["58 Python Engines"]
        DB["SQLite Database<br/>12 tables"]
        HEAL["Self-Healer"]
        AUDIT["ROM / Media Auditor"]
        UPDATE["Safe Update Pipeline"]
        BACKUP["Backup & Snapshot"]
    end

    subgraph LLM Layer
        LMS["LM Studio<br/>:1234 (primary)"]
        OLL["Ollama<br/>:11434 (secondary)"]
        VLLM["vLLM<br/>:8000 (tertiary)"]
    end

    subgraph Data Layer
        ARCADE["D:\Arcade<br/>12 TB Collection"]
        DRIVES["Multi-HDD Storage<br/>L: / G: / N:"]
    end

    USER --> GOOSE
    USER --> CLI
    USER --> DASH
    GOOSE --> MCP
    GOOSE --> CIA
    GOOSE --> NEMO
    GOOSE --> OH
    CLI --> ENG
    DASH --> ENG
    MCP --> ENG
    CIA --> ENG
    NEMO --> LMS
    OH -->|Docker :3000| ENG
    ENG --> DB
    ENG --> ARCADE
    ENG --> DRIVES
    GOOSE --> LMS
    GOOSE --> OLL
    ENG --> LMS
    ENG --> OLL
    ENG --> VLLM
```

---

## 2. Agentic Stack — MCP Communication Flow

```mermaid
sequenceDiagram
    participant U as User
    participant G as Goose
    participant LM as LM Studio
    participant MCP as MCP Bridge
    participant E as Engines
    participant FS as Filesystem

    U->>G: "Audit my SNES collection"
    G->>LM: Chat completion (Devstral-24B)
    LM-->>G: Tool call: audit_system("SNES")
    G->>MCP: JSON-RPC: tools/call audit_system
    MCP->>E: auditor.audit_system("SNES")
    E->>FS: Scan D:\Arcade\ROMs\SNES\
    FS-->>E: File list + hashes
    E->>E: Cross-ref XML database
    E-->>MCP: AuditReport JSON
    MCP-->>G: Tool result
    G->>LM: Format results for user
    LM-->>G: Natural language summary
    G-->>U: "Your SNES collection has 847 ROMs..."
```

---

## 3. Safe Update Pipeline

```mermaid
flowchart LR
    A[Register Update] --> B[Pre-Snapshot]
    B --> C[Quarantine Stage]
    C --> D{DLL Conflict<br/>Check}
    D -->|Clean| E[Apply Update]
    D -->|Conflict| F[Block & Alert]
    E --> G[Post-Snapshot]
    G --> H{Exe Test<br/>Passed?}
    H -->|Yes| I[Commit]
    H -->|No| J[Auto-Rollback]
    J --> K[Restore Snapshot]

    style A fill:#2563eb,color:#fff
    style I fill:#16a34a,color:#fff
    style J fill:#dc2626,color:#fff
    style F fill:#dc2626,color:#fff
```

---

## 4. Engine Module Map

```mermaid
graph LR
    subgraph Core
        CFG[config.py]
        DBS[database.py]
        LOG[logger.py]
    end

    subgraph Discovery
        SCAN[scanner.py]
        DRIVE[drive_indexer.py]
        BIOS[bios_manager.py]
    end

    subgraph Audit
        AUD[auditor.py]
        ROM[rom_audit.py]
        MED[media_auditor.py]
        DAT[dat_verifier.py]
        ASSET[asset_auditor.py]
    end

    subgraph Updates
        VER[version_tracker.py]
        REL[release_checker.py]
        UPD[update_applier.py]
        SNAP[snapshot_verify.py]
        ROLL[auto_rollback.py]
        DEP[dependency_detector.py]
    end

    subgraph AI
        AIE[ai_engine.py]
        NLQ[nl_query.py]
        LLM[llm_detector.py]
        REC[game_recommender.py]
        TRB[troubleshooter.py]
    end

    subgraph Agents
        CIA2[cli_anything_bridge.py]
        NEMO2[nemoclaw_agents.py]
        OH2[openhands_bridge.py]
        GST[gstack_roles.py]
        SEC[security_orchestrator.py]
    end

    subgraph Backup
        BKP[backup.py]
        HEAL2[self_healer.py]
    end

    subgraph RocketLauncher
        RLM[rl_media_manager.py]
        RLS[rl_stats_keymapper.py]
        RLC[rl_config_validator.py]
    end

    CFG --> SCAN
    CFG --> AUD
    CFG --> AIE
    DBS --> AUD
    DBS --> VER
    SCAN --> AUD
    VER --> UPD
    UPD --> SNAP
    SNAP --> ROLL
    DEP --> UPD
```

---

## 5. Web Dashboard Architecture

```mermaid
graph TB
    subgraph Browser
        HTML["8 Jinja2 Pages"]
        JS["app.js + Alpine.js"]
        CSS["style.css (Dark Theme)"]
        WS["WebSocket Client"]
    end

    subgraph FastAPI Server [:8888]
        APP["app.py<br/>89 REST endpoints"]
        WSE["WebSocket /ws"]
        HUB["Event Hub"]
        TPL["Jinja2 Templates"]
    end

    subgraph Backend
        ENG2["58 Engines"]
        DB2["SQLite"]
    end

    HTML --> JS
    JS --> APP
    WS --> WSE
    WSE --> HUB
    HUB -->|scan.progress<br/>update.applied<br/>heal.complete| WS
    APP --> ENG2
    ENG2 --> DB2
    TPL --> HTML
```

---

## 6. Multi-Agent Orchestration (GStack)

```mermaid
graph TB
    subgraph GStack Roles
        CEO["CEO Agent<br/>Strategic planning"]
        ENG3["Engineer Agent<br/>Implementation"]
        STAFF["Staff Agent<br/>Data collection"]
        QA["QA Agent<br/>Verification"]
    end

    subgraph Workflow
        PLAN["Plan Phase"]
        EXEC["Execute Phase"]
        REVIEW["Review Phase"]
    end

    CEO --> PLAN
    PLAN --> ENG3
    ENG3 --> EXEC
    EXEC --> STAFF
    STAFF --> QA
    QA --> REVIEW
    REVIEW -->|Issues found| ENG3
    REVIEW -->|All clear| DONE["Complete"]
```

---

## 7. LLM Provider Chain

```mermaid
flowchart TB
    REQ[Inference Request] --> R{Router}
    R -->|Primary| LMS2["LM Studio :1234<br/>63 models loaded<br/>Qwen3.5 27B active"]
    R -->|Fallback| OLL2["Ollama :11434<br/>25 models<br/>llama3.1:8b default"]
    R -->|Batch/Perf| VLLM2["vLLM :8000<br/>High-throughput"]

    LMS2 -->|Success| RES[Response]
    LMS2 -->|Fail| OLL2
    OLL2 -->|Success| RES
    OLL2 -->|Fail| VLLM2
    VLLM2 --> RES

    style LMS2 fill:#2563eb,color:#fff
    style OLL2 fill:#6b7280,color:#fff
    style VLLM2 fill:#6b7280,color:#fff
```

---

## 8. Data Flow — ROM Audit

```mermaid
flowchart TB
    START["audit full"] --> SCAN2["Scanner: discover systems"]
    SCAN2 --> EACH["For each system"]
    EACH --> XML["Parse XML database"]
    EACH --> ROM2["Scan ROM directory"]
    EACH --> MEDIA2["Scan media directories"]
    XML --> CROSS["Cross-reference"]
    ROM2 --> CROSS
    CROSS --> MISS["Missing ROMs"]
    CROSS --> EXTRA["Extra ROMs (no XML)"]
    CROSS --> DUP["Duplicates"]
    MEDIA2 --> MCOV["Media coverage %"]
    MISS --> RPT["Audit Report"]
    EXTRA --> RPT
    DUP --> RPT
    MCOV --> RPT
    RPT --> DB3["SQLite audit_results"]
    RPT --> DASH2["Dashboard /api/audit"]
    RPT --> MCP2["MCP tool response"]
```

---

## 9. Self-Healing System

```mermaid
flowchart TB
    TRIGGER["Trigger: API call or scheduled"] --> DIAG["Run Diagnostics<br/>5 categories"]
    DIAG --> CONFIG["Config Checks"]
    DIAG --> PATH["Path Checks"]
    DIAG --> SETTINGS["Settings Checks"]
    DIAG --> BIOS2["BIOS Checks"]
    DIAG --> PERM["Permission Checks"]

    CONFIG --> ISSUES["Issue List<br/>severity + repairable flag"]
    PATH --> ISSUES
    SETTINGS --> ISSUES
    BIOS2 --> ISSUES
    PERM --> ISSUES

    ISSUES --> FILTER{Repairable?}
    FILTER -->|Yes| BACKUP2["Create Backup"]
    FILTER -->|No| LOG2["Log Warning"]
    BACKUP2 --> REPAIR["Execute Repair"]
    REPAIR --> VERIFY["Verify Fix"]
    VERIFY -->|OK| DONE2["Mark Healed"]
    VERIFY -->|Fail| ROLLBACK2["Rollback from Backup"]
```

---

## 10. Project File Structure

```mermaid
graph LR
    ROOT["D:\hyperspin_toolkit\"]
    ROOT --> MAIN["main.py"]
    ROOT --> MCPB["mcp_bridge.py"]
    ROOT --> CORE["core/<br/>config, database, logger"]
    ROOT --> ENGINES["engines/<br/>58 modules"]
    ROOT --> AGENTS2["agents/<br/>base_agent.py"]
    ROOT --> DASHBOARD["dashboard/<br/>app.py + templates/"]
    ROOT --> DOCS["docs/<br/>13 markdown files"]
    ROOT --> SETUP["setup/<br/>install + validate"]
    ROOT --> GUI["gui/<br/>WPF C# Arcade GUI"]
    ROOT --> TESTS["tests/<br/>unit + integration"]
    ROOT --> PLUGINS["plugins/<br/>auto-discovered"]
    ROOT --> SKILLS["skills/<br/>11 Goose skill files"]
```
