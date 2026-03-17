# NVIDIA OpenShell Setup Plan — HyperSpin Toolkit

> **Last Updated:** 2026-03-17  
> **Status:** Not yet installed — planning phase

---

## What is NVIDIA OpenShell?

NVIDIA OpenShell is a secure, open-source runtime for autonomous AI agents designed to run on Windows using Docker. It provides:
- **Sandboxed execution** via Docker containers with kernel-level isolation
- **Policy-enforced security** via YAML policies controlling filesystem, network, and GPU access
- **GPU acceleration** for local AI inference (RTX series)
- **Agent lifecycle management** — create, run, monitor, and destroy sandboxes

---

## Prerequisites Checklist

### Hardware
- [ ] NVIDIA RTX GPU confirmed (check with `nvidia-smi`)
- [ ] Sufficient RAM (16GB+ recommended for containers + models)
- [ ] Sufficient disk space on system drive for Docker images (~20GB)

### Software
- [ ] **Windows 10/11** with WSL2 enabled
  ```powershell
  # Check WSL2 status
  wsl --status
  # Install/update if needed
  wsl --install
  wsl --set-default-version 2
  ```

- [ ] **Docker Desktop** installed with WSL2 backend
  ```powershell
  # Verify Docker
  docker --version
  docker info | Select-String "Server Version"
  ```

- [ ] **NVIDIA GPU Driver** (latest Game Ready or Studio driver)
  ```powershell
  nvidia-smi
  # Should show driver version and GPU info
  ```

- [ ] **NVIDIA Container Toolkit** (`nvidia-ctk`)
  ```powershell
  # Install via WSL2 Ubuntu
  wsl -d Ubuntu -e bash -c "
    distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
      sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
      sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
  "
  # Restart Docker Desktop after installation
  ```

- [ ] **Verify GPU passthrough in Docker**
  ```powershell
  docker run --rm --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi
  # Should show GPU info inside container
  ```

---

## Installation Steps

### 1. Install OpenShell CLI

```powershell
# Download latest release from GitHub
# https://github.com/NVIDIA/OpenShell/releases

# Option A: Via GitHub release download
Invoke-WebRequest -Uri "https://github.com/NVIDIA/OpenShell/releases/latest/download/openshell-windows-amd64.exe" -OutFile "$env:LOCALAPPDATA\openshell\openshell.exe"
$env:PATH += ";$env:LOCALAPPDATA\openshell"

# Option B: Via package manager (if available)
# winget install NVIDIA.OpenShell
```

### 2. Verify Installation

```powershell
openshell version
openshell doctor  # Checks all prerequisites
```

### 3. Pull Sandbox Base Image

```powershell
openshell image pull  # Pulls default Linux sandbox image
```

---

## HyperSpin Toolkit Sandbox Policy

Create `D:\hyperspin_toolkit\openshell-policy.yaml`:

```yaml
# OpenShell Sandbox Policy for HyperSpin Toolkit
# Restricts agent access to only gaming drives and toolkit directories

name: hyperspin-toolkit
description: Sandboxed environment for HyperSpin Toolkit AI agent operations

# Filesystem access rules
filesystem:
  # Allow read-write to toolkit project directory
  - path: /mnt/d/hyperspin_toolkit
    access: read-write
    
  # Allow read-write to toolkit output
  - path: /mnt/d/HyperSpin_Toolkit_Output
    access: read-write

  # Testing drive — read-write for M11-M15 operations
  - path: /mnt/d/Arcade
    access: read-write

  # Other gaming drives — READ ONLY (safety)
  - path: /mnt/i
    access: read-only
  - path: /mnt/k
    access: read-only
  - path: /mnt/l
    access: read-only
  - path: /mnt/j
    access: read-only
  - path: /mnt/n
    access: read-only
  - path: /mnt/e
    access: read-only
  - path: /mnt/m
    access: read-only

  # DENY all system drives
  - path: /mnt/c
    access: deny
  - path: /mnt/f
    access: deny

# Network access rules
network:
  # Allow GitHub API for emulator update checks (M11, M12)
  - host: api.github.com
    access: allow
    ports: [443]
  - host: github.com
    access: allow
    ports: [443]
    
  # Allow Ollama local inference
  - host: localhost
    access: allow
    ports: [11434]
  - host: 127.0.0.1
    access: allow
    ports: [11434]
    
  # Allow LM Studio local inference  
  - host: localhost
    access: allow
    ports: [1234]
    
  # Deny all other network access
  - host: "*"
    access: deny

# GPU access
gpu:
  enabled: true
  devices: all  # Use all available GPUs

# Resource limits
resources:
  memory: 8GB
  cpu_cores: 4
  timeout: 3600  # 1 hour max per session

# Environment variables
environment:
  HYPERSPIN_ROOT: /mnt/d/Arcade
  TOOLKIT_ROOT: /mnt/d/hyperspin_toolkit
  OUTPUT_ROOT: /mnt/d/HyperSpin_Toolkit_Output
  PYTHONPATH: /mnt/d/hyperspin_toolkit
```

---

## Docker Compose Integration

Create `D:\hyperspin_toolkit\docker-compose.openshell.yml`:

```yaml
version: '3.8'

services:
  toolkit-sandbox:
    image: nvidia/openshell:latest
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    volumes:
      # Toolkit project (read-write)
      - D:/hyperspin_toolkit:/app/toolkit:rw
      - D:/HyperSpin_Toolkit_Output:/app/output:rw
      
      # Testing drive (read-write)
      - D:/Arcade:/mnt/arcade:rw
      
      # Gaming drives (read-only)
      - I:/:/mnt/primary_hyperspin:ro
      - K:/:/mnt/attraction:ro
      - L:/:/mnt/core_type_r:ro
      - J:/:/mnt/rom_backup:ro
      - N:/:/mnt/batocera:ro
      
      # AI models (read-only)
      - E:/.lmstudio:/mnt/lmstudio:ro
      - E:/.ollama:/mnt/ollama:ro
    
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - HYPERSPIN_ROOT=/mnt/arcade
      - TOOLKIT_ROOT=/app/toolkit
      - OUTPUT_ROOT=/app/output
    
    ports:
      - "8501:8501"  # Dashboard
      - "3001:3001"  # MCP Bridge
    
    working_dir: /app/toolkit
    command: ["python", "main.py", "--help"]

  ollama:
    image: ollama/ollama:latest
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    volumes:
      - E:/.ollama:/root/.ollama:rw
    ports:
      - "11434:11434"
```

---

## Usage

### Start Sandbox
```powershell
# Using OpenShell CLI
openshell sandbox create --policy openshell-policy.yaml --name toolkit-dev

# Using Docker Compose
docker-compose -f docker-compose.openshell.yml up -d
```

### Run Toolkit Inside Sandbox
```powershell
# Attach to sandbox
openshell sandbox exec toolkit-dev -- python main.py audit full

# Run specific engine
openshell sandbox exec toolkit-dev -- python -c "
from engines.auto_rollback import run_health_checks
print(run_health_checks('MAME', emu_root='/mnt/arcade'))
"
```

### Monitor Sandbox
```powershell
openshell sandbox status toolkit-dev
openshell sandbox logs toolkit-dev
```

### Destroy Sandbox
```powershell
openshell sandbox destroy toolkit-dev
```

---

## Security Considerations

1. **Testing drive only writable** — D:\Arcade is the only gaming drive with write access
2. **System drives denied** — C: and F: are completely blocked
3. **Network restricted** — only GitHub API (for updates) and localhost (for AI models)
4. **GPU isolated** — container gets GPU access but can't escape sandbox
5. **Resource limited** — 8GB RAM, 4 CPU cores, 1-hour timeout prevents runaway processes
6. **Drive registry validation** — toolkit should verify drive serials before any write operation

---

## Troubleshooting

### Docker Desktop Not Starting
```powershell
# Restart Docker Desktop service
Restart-Service docker
# Or restart WSL2
wsl --shutdown
# Then restart Docker Desktop from Start Menu
```

### GPU Not Available in Container
```powershell
# Verify NVIDIA driver
nvidia-smi

# Verify Container Toolkit
docker run --rm --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi

# If fails, reinstall NVIDIA Container Toolkit
wsl -d Ubuntu -e bash -c "sudo apt-get install -y nvidia-container-toolkit"
# Restart Docker Desktop
```

### Drive Mounts Not Working
```powershell
# Ensure drives are accessible in WSL2
wsl -d Ubuntu -e ls /mnt/d/
wsl -d Ubuntu -e ls /mnt/i/

# If not visible, enable drive auto-mount in WSL config
# Edit /etc/wsl.conf in Ubuntu:
# [automount]
# enabled = true
# root = /mnt/
```
