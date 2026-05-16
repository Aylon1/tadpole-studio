# Tadpole Studio - Custom Setup Documentation

**Version:** Custom deployment for `/opt/stacks` infrastructure
**Last Updated:** 2026-05-16
**Fork:** https://github.com/Aylon1/tadpole-studio.git
**Upstream:** https://github.com/proximasan/tadpole-studio.git

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Configuration Changes](#configuration-changes)
4. [Model Integration](#model-integration)
5. [Port Configuration](#port-configuration)
6. [File Changes](#file-changes)
7. [Environment Variables](#environment-variables)
8. [Management](#management)
9. [Git Workflow](#git-workflow)
10. [Troubleshooting](#troubleshooting)
11. [Future Development](#future-development)
12. [Quick Reference](#quick-reference)

---

## Overview

### What is This Custom Setup?

This is a customized deployment of [Tadpole Studio](https://github.com/proximasan/tadpole-studio) - a local-first AI music generation studio built on ACE-Step 1.5. The custom setup has been specifically configured to:

- **Integrate with existing infrastructure** at `/opt/stacks`
- **Use pre-downloaded models** from `/mnt/models/audio` instead of downloading them
- **Run on custom ports** (8500 for backend, 8700 for frontend) to avoid conflicts
- **Operate as a background service** using a custom management script
- **Maintain fork compatibility** for easy upstream updates

### Why Was It Created?

The original Tadpole Studio uses:
- Default ports 8000 (backend) and 3000 (frontend)
- Auto-downloads models to `backend/data/checkpoints/`
- Uses `start.py` launcher that runs in foreground
- Stores all data within the project directory

This custom setup was created to:
1. **Avoid port conflicts** with other services in `/opt/stacks`
2. **Reuse existing models** already downloaded to `/mnt/models/audio/`
3. **Integrate with the service management pattern** used by other stacks
4. **Centralize model storage** for multiple AI music generation tools
5. **Run as a background service** with proper logging and PID management

---

## System Architecture

### Directory Structure

```
/opt/stacks/
├── tadpole-studio/              # This installation
│   ├── backend/                 # Python FastAPI backend
│   │   ├── src/tadpole_studio/  # Application code
│   │   ├── data/                # Runtime data (generated audio, DB, etc.)
│   │   └── .venv/               # Python virtual environment
│   ├── frontend/                # Next.js frontend
│   │   ├── src/                 # React components, stores, themes
│   │   └── node_modules/        # Node dependencies
│   ├── logs/                    # Service logs
│   │   ├── backend.log          # Backend output
│   │   └── frontend.log         # Frontend output
│   ├── pids/                    # Process ID files
│   │   ├── backend.pid          # Backend PID
│   │   └── frontend.pid         # Frontend PID
│   ├── .env                     # Custom environment configuration
│   ├── setup-tadpole.sh         # Service management script
│   └── CUSTOM_SETUP.md          # This file
│
└── [other services...]

/mnt/models/audio/
├── acestep-checkpoints/         # ACE-Step models (shared)
│   ├── acestep-v15-turbo/       # DiT model
│   ├── acestep-5Hz-lm-1.7B/     # Language model
│   └── [other models...]
└── heartmula-models/            # HeartMuLa models (optional)
    └── HeartMuLa-oss-RL-3B-20260123/
```

### Integration Points

| Component | Location | Purpose |
|-----------|----------|---------|
| **Models** | `/mnt/models/audio/acestep-checkpoints/` | Shared ACE-Step model storage |
| **HeartMuLa** | `/mnt/models/audio/heartmula-models/` | Alternative generation backend |
| **Data** | `/opt/stacks/tadpole-studio/backend/data/` | Generated audio, database, LoRAs |
| **Logs** | `/opt/stacks/tadpole-studio/logs/` | Service logs |
| **PIDs** | `/opt/stacks/tadpole-studio/pids/` | Process management |

### Network Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Client Browser                        │
│              http://tjkserver:8700                       │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Next.js Frontend (Port 8700)                │
│  - React 19 UI                                           │
│  - Zustand state management                              │
│  - WaveSurfer audio visualization                        │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP/WebSocket
                     ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (Port 8500)                 │
│  - REST API endpoints                                    │
│  - WebSocket for real-time updates                       │
│  - SQLite database                                       │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
┌──────────────────┐    ┌──────────────────┐
│  ACE-Step 1.5    │    │  HeartMuLa 3B    │
│  (CUDA/MPS)      │    │  (Optional)      │
│  /mnt/models/    │    │  /mnt/models/    │
└──────────────────┘    └──────────────────┘
```

---

## Configuration Changes

### Summary of Modifications

| Aspect | Original | Custom | Reason |
|--------|----------|--------|--------|
| **Backend Port** | 8000 | 8500 | Avoid conflicts with other services |
| **Frontend Port** | 3000 | 8700 | Avoid conflicts with other services |
| **Model Path** | `backend/data/checkpoints/` | `/mnt/models/audio/acestep-checkpoints/` | Reuse existing models |
| **HeartMuLa Path** | Auto-download | `/mnt/models/audio/heartmula-models/` | Reuse existing models |
| **Launcher** | `start.py` (foreground) | `setup-tadpole.sh` (background) | Service management |
| **CORS Origins** | `localhost:3000` | `localhost:8700, tjkserver:8700` | Custom port + hostname |
| **Backend URL** | `localhost:8000` | `localhost:8500` | Custom port |

### Key Customizations

1. **Port Remapping**: All port references updated throughout the codebase
2. **Model Path Override**: Environment variables point to shared model storage
3. **Service Management**: Custom bash script for start/stop/status/logs
4. **CORS Configuration**: Updated to allow custom ports and hostname
5. **Frontend API Client**: Updated default backend URL

---

## Model Integration

### ACE-Step Models

The setup uses models from `/mnt/models/audio/acestep-checkpoints/` instead of downloading them.

**Environment Variable:**
```bash
ACESTEP_PROJECT_ROOT=/mnt/models/audio/acestep-checkpoints
```

**Available Models:**

| Model Type | Model Name | Size | Purpose |
|------------|------------|------|---------|
| **DiT** | `acestep-v15-turbo` | ~4 GB | Fast 8-step generation (default) |
| **DiT** | `acestep-v15-turbo-shift1` | ~4 GB | Turbo with shift variant 1 |
| **DiT** | `acestep-v15-turbo-shift3` | ~4 GB | Turbo with shift variant 3 |
| **DiT** | `acestep-v15-sft` | ~4 GB | 50-step supervised fine-tuned |
| **DiT** | `acestep-v15-base` | ~4 GB | 50-step base model |
| **LM** | `acestep-5Hz-lm-1.7B` | ~3.4 GB | Lyrics formatting (default) |
| **LM** | `acestep-5Hz-lm-0.6B` | ~1.2 GB | Lightweight lyrics model |
| **LM** | `acestep-5Hz-lm-4B` | ~8 GB | Best quality lyrics model |

### HeartMuLa Integration

HeartMuLa is an alternative music generation backend with better lyrics controllability.

**Environment Variable:**
```bash
HEARTMULA_MODEL_PATH=/mnt/models/audio/heartmula-models/HeartMuLa-oss-RL-3B-20260123
```

**Model Details:**
- **Size**: ~21 GB
- **Version**: 3B parameter model
- **Device**: CUDA recommended (slow on Apple Silicon)
- **Lazy Loading**: Enabled by default on macOS

### Model Discovery

The backend automatically discovers models in the configured paths:

1. **DiT Models**: Scans `$ACESTEP_PROJECT_ROOT/checkpoints/`
2. **LM Models**: Scans `$ACESTEP_PROJECT_ROOT/checkpoints/`
3. **HeartMuLa**: Uses exact path from `$HEARTMULA_MODEL_PATH`

### Avoiding Re-downloads

By setting `ACESTEP_PROJECT_ROOT` to `/mnt/models/audio/acestep-checkpoints`, the backend:
- ✅ Uses existing models
- ✅ Skips auto-download on first run
- ✅ Shares models with other ACE-Step installations
- ✅ Saves ~10 GB of disk space

---

## Port Configuration

### Port Assignments

| Service | Port | Protocol | Access |
|---------|------|----------|--------|
| **Backend** | 8500 | HTTP/WebSocket | `http://0.0.0.0:8500` |
| **Frontend** | 8700 | HTTP | `http://localhost:8700` |

### Port Configuration Files

#### Backend Port

**File**: [`backend/src/tadpole_studio/config.py`](backend/src/tadpole_studio/config.py:10)
```python
PORT: int = int(os.getenv("TADPOLE_PORT", "8000"))  # Default changed via .env
```

**Environment Variable**: `.env`
```bash
TADPOLE_PORT=8500
TADPOLE_HOST=0.0.0.0
```

#### Frontend Port

**File**: [`setup-tadpole.sh`](setup-tadpole.sh:170)
```bash
export PORT="$FRONTEND_PORT"  # Set to 8700
export NEXT_PUBLIC_TADPOLE_API_PORT="$BACKEND_PORT"  # Set to 8500
```

**Environment Variable**: `.env`
```bash
TADPOLE_FRONTEND_PORT=8700
```

#### Frontend API Client

**File**: [`frontend/src/lib/api/base.ts`](frontend/src/lib/api/base.ts:1)
```typescript
const DEFAULT_BASE_URL = "http://localhost:8500";  // Changed from 8000
```

**File**: [`frontend/src/stores/settings-store.ts`](frontend/src/stores/settings-store.ts:18)
```typescript
backendUrl: "http://localhost:8000",  // Default (can be changed in UI)
```

### CORS Configuration

**File**: [`.env`](.env:5)
```bash
TADPOLE_CORS_ORIGINS=http://localhost:8700,http://127.0.0.1:8700,http://8700,http://tjkserver:8700,http://tjkserver
```

**File**: [`backend/src/tadpole_studio/config.py`](backend/src/tadpole_studio/config.py:49)
```python
CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv(
        "TADPOLE_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",  # Original default
    ).split(",")
    if origin.strip()
]
```

### Accessing the Application

| URL | Description |
|-----|-------------|
| `http://localhost:8700` | Local access |
| `http://127.0.0.1:8700` | Local access (IP) |
| `http://tjkserver:8700` | Network access (hostname) |
| `http://<server-ip>:8700` | Network access (IP) |

**Backend API**: `http://localhost:8500/api/`  
**Backend Docs**: `http://localhost:8500/docs` (Swagger UI)

---

## File Changes

### Modified Files

#### 1. `.env` (Created)

**Purpose**: Custom environment configuration  
**Location**: `/opt/stacks/tadpole-studio/.env`

```bash
# Model paths - use shared storage instead of downloading
ACESTEP_PROJECT_ROOT=/mnt/models/audio/acestep-checkpoints
HEARTMULA_MODEL_PATH=/mnt/models/audio/heartmula-models/HeartMuLa-oss-RL-3B-20260123

# Custom ports to avoid conflicts
TADPOLE_PORT=8500
TADPOLE_HOST=0.0.0.0
TADPOLE_FRONTEND_PORT=8700

# CORS - allow custom ports and hostname
TADPOLE_CORS_ORIGINS=http://localhost:8700,http://127.0.0.1:8700,http://8700,http://tjkserver:8700,http://tjkserver

# Device configuration
TADPOLE_DEVICE=cuda

# Default models
TADPOLE_DIT_MODEL=acestep-v15-turbo
TADPOLE_LM_MODEL=acestep-5Hz-lm-1.7B

# Ollama integration (optional)
TADPOLE_OLLAMA_URL=http://localhost:11434
```

#### 2. `setup-tadpole.sh` (Created)

**Purpose**: Service management script  
**Location**: `/opt/stacks/tadpole-studio/setup-tadpole.sh`

**Features**:
- Start/stop/restart services
- Status checking with port verification
- Live log tailing
- PID-based process management
- Graceful shutdown with force-kill fallback
- Environment variable loading from `.env`

**Commands**:
```bash
./setup-tadpole.sh start      # Start both services
./setup-tadpole.sh stop       # Stop both services
./setup-tadpole.sh status     # Check service status
./setup-tadpole.sh restart    # Restart both services
./setup-tadpole.sh logs       # Tail all logs
./setup-tadpole.sh logs backend   # Tail backend logs only
./setup-tadpole.sh logs frontend  # Tail frontend logs only
```

#### 3. `frontend/src/lib/api/base.ts` (Modified)

**Change**: Updated default backend URL  
**Line 1**: `const DEFAULT_BASE_URL = "http://localhost:8500";`  
**Original**: `const DEFAULT_BASE_URL = "http://localhost:8000";`

**Impact**: Frontend connects to backend on port 8500 by default

#### 4. `frontend/next.config.ts` (Modified)

**Change**: Added custom port to allowed origins  
**Lines 5-10**: Added `http://localhost:8700` and `http://8700`  
**Original**: Only had port 3000

**Impact**: Next.js allows connections on port 8700

#### 5. `backend/src/tadpole_studio/config.py` (No changes needed)

**Why**: Uses environment variables, so `.env` file controls behavior  
**Key Variables**:
- `TADPOLE_PORT` → Backend port
- `TADPOLE_HOST` → Backend bind address
- `ACESTEP_PROJECT_ROOT` → Model path
- `HEARTMULA_MODEL_PATH` → HeartMuLa model path
- `TADPOLE_CORS_ORIGINS` → CORS configuration

### Git Tracking

**Tracked Changes** (committed to fork):
- `.env` (custom configuration)
- `setup-tadpole.sh` (service management)
- `frontend/src/lib/api/base.ts` (port change)
- `frontend/next.config.ts` (port change)
- `CUSTOM_SETUP.md` (this file)

**Untracked** (in `.gitignore`):
- `backend/data/` (generated audio, database)
- `logs/` (service logs)
- `pids/` (process IDs)
- `backend/.venv/` (Python virtual environment)
- `frontend/node_modules/` (Node dependencies)

---

## Environment Variables

### Complete `.env` Reference

```bash
# ============================================================================
# Tadpole Studio - Custom Configuration
# ============================================================================

# ── Model Paths ─────────────────────────────────────────────────────────────
# Use shared model storage instead of downloading to backend/data/checkpoints/
ACESTEP_PROJECT_ROOT=/mnt/models/audio/acestep-checkpoints
HEARTMULA_MODEL_PATH=/mnt/models/audio/heartmula-models/HeartMuLa-oss-RL-3B-20260123

# ── Network Configuration ───────────────────────────────────────────────────
# Custom ports to avoid conflicts with other services in /opt/stacks
TADPOLE_PORT=8500                    # Backend API port (default: 8000)
TADPOLE_HOST=0.0.0.0                 # Backend bind address (0.0.0.0 = all interfaces)
TADPOLE_FRONTEND_PORT=8700           # Frontend port (default: 3000)

# CORS origins - allow frontend to connect from custom ports
TADPOLE_CORS_ORIGINS=http://localhost:8700,http://127.0.0.1:8700,http://8700,http://tjkserver:8700,http://tjkserver

# ── Device Configuration ────────────────────────────────────────────────────
TADPOLE_DEVICE=cuda                  # GPU device: auto, cuda, mps, cpu

# ── Model Defaults ──────────────────────────────────────────────────────────
TADPOLE_DIT_MODEL=acestep-v15-turbo  # Default DiT model
TADPOLE_LM_MODEL=acestep-5Hz-lm-1.7B # Default language model

# ── External Services ───────────────────────────────────────────────────────
TADPOLE_OLLAMA_URL=http://localhost:11434  # Ollama API for AI DJ (optional)
```

### Optional Environment Variables

These can be added to `.env` if needed:

```bash
# ── Generation Settings ─────────────────────────────────────────────────────
TADPOLE_AUDIO_FORMAT=flac            # Output format: flac, wav, mp3
TADPOLE_BATCH_SIZE=2                 # Samples per generation batch

# ── Language Model Backend ──────────────────────────────────────────────────
TADPOLE_LM_BACKEND=nano-vllm         # LM backend: mlx (macOS), nano-vllm, transformers

# ── HeartMuLa Configuration ─────────────────────────────────────────────────
HEARTMULA_VERSION=3B                 # HeartMuLa model version
HEARTMULA_DEVICE=auto                # HeartMuLa device: auto, cuda, mps, cpu
HEARTMULA_LAZY_LOAD=false            # Lazy-load HeartMuLa on first use
```

### Environment Variable Priority

1. **`.env` file** (highest priority) - custom configuration
2. **System environment** - can override `.env` if exported
3. **Code defaults** - fallback values in `config.py`

### Loading Environment Variables

The [`setup-tadpole.sh`](setup-tadpole.sh:20) script loads `.env` automatically:

```bash
set -a                    # Auto-export all variables
source "$ENV_FILE"        # Load .env
set +a                    # Stop auto-export
```

---

## Management

### Using `setup-tadpole.sh`

The custom management script provides a unified interface for controlling Tadpole Studio.

#### Start Services

```bash
cd /opt/stacks/tadpole-studio
./setup-tadpole.sh start
```

**Output**:
```
Starting Tadpole Studio...

Starting backend on 0.0.0.0:8500...
Backend started (PID: 12345).
Starting frontend on port 8700...
Frontend started (PID: 12346).

Services starting...
  Backend:  http://0.0.0.0:8500
  Frontend: http://localhost:8700

Use './setup-tadpole.sh status' to check if services are running.
Use './setup-tadpole.sh logs' to view live logs.
```

#### Stop Services

```bash
./setup-tadpole.sh stop
```

**Output**:
```
Stopping Tadpole Studio...

Stopping Backend (PID: 12345)...
Backend stopped.
Stopping Frontend (PID: 12346)...
Frontend stopped.

All services stopped.
```

#### Check Status

```bash
./setup-tadpole.sh status
```

**Output**:
```
Tadpole Studio Status:
======================

Backend:   RUNNING (PID: 12345) - http://0.0.0.0:8500
Frontend:  RUNNING (PID: 12346) - http://localhost:8700

Port status:
  Backend port 8500:  LISTENING
  Frontend port 8700: LISTENING
```

#### Restart Services

```bash
./setup-tadpole.sh restart
```

Equivalent to `stop` followed by `start` with a 2-second delay.

#### View Logs

```bash
# Tail all logs
./setup-tadpole.sh logs

# Tail backend logs only
./setup-tadpole.sh logs backend

# Tail frontend logs only
./setup-tadpole.sh logs frontend
```

**Log Files**:
- Backend: `logs/backend.log`
- Frontend: `logs/frontend.log`

### Process Management

#### PID Files

Process IDs are stored in:
- `pids/backend.pid`
- `pids/frontend.pid`

#### Graceful Shutdown

The script attempts graceful shutdown:
1. Send `SIGTERM` to process
2. Wait up to 10 seconds
3. Force kill with `SIGKILL` if still running
4. Clean up PID file

#### Manual Process Control

If needed, you can manually control processes:

```bash
# Find processes
ps aux | grep tadpole-studio
ps aux | grep "pnpm dev"

# Kill by PID
kill $(cat pids/backend.pid)
kill $(cat pids/frontend.pid)

# Force kill
kill -9 $(cat pids/backend.pid)
```

### Service Integration

To run Tadpole Studio on system startup, you could create a systemd service:

```ini
# /etc/systemd/system/tadpole-studio.service
[Unit]
Description=Tadpole Studio AI Music Generation
After=network.target

[Service]
Type=forking
User=tjk
WorkingDirectory=/opt/stacks/tadpole-studio
ExecStart=/opt/stacks/tadpole-studio/setup-tadpole.sh start
ExecStop=/opt/stacks/tadpole-studio/setup-tadpole.sh stop
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**Note**: This is optional and not currently implemented.

---

## Git Workflow

### Repository Setup

**Fork**: https://github.com/Aylon1/tadpole-studio.git  
**Upstream**: https://github.com/proximasan/tadpole-studio.git

```bash
# Verify remotes
git remote -v
# origin    https://github.com/Aylon1/tadpole-studio.git (fetch)
# origin    https://github.com/Aylon1/tadpole-studio.git (push)
# upstream  https://github.com/proximasan/tadpole-studio.git (fetch)
# upstream  https://github.com/proximasan/tadpole-studio.git (push)
```

### Branch Strategy

**Branches**:
- `master` - tracks upstream `master`
- `custom-setup` - contains all custom modifications (current branch)

**Current Commit**:
```
f197f17 (HEAD -> custom-setup) Custom setup for local deployment with /mnt/models integration and ports 8500/8700
```

### Updating from Upstream

To pull latest changes from the original Tadpole Studio:

```bash
# Fetch upstream changes
git fetch upstream

# Switch to master and update
git checkout master
git merge upstream/master
git push origin master

# Merge into custom-setup
git checkout custom-setup
git merge master

# Resolve conflicts if any (likely in .env, base.ts, next.config.ts)
# Then commit and push
git add .
git commit -m "Merge upstream updates"
git push origin custom-setup
```

### Conflict Resolution

**Expected Conflicts**:

1. **`.env`** - Keep custom values
2. **`frontend/src/lib/api/base.ts`** - Keep port 8500
3. **`frontend/next.config.ts`** - Keep port 8700 in allowed origins
4. **`setup-tadpole.sh`** - Keep custom script (not in upstream)

**Resolution Strategy**:
```bash
# For .env - keep ours
git checkout --ours .env

# For base.ts - manually merge, keep port 8500
git checkout --theirs frontend/src/lib/api/base.ts
# Then edit to change 8000 → 8500

# For next.config.ts - manually merge, keep port 8700
git checkout --theirs frontend/next.config.ts
# Then edit to add 8700 to allowed origins
```

### Pushing Custom Changes

```bash
# Make changes
git add .
git commit -m "Description of changes"

# Push to fork
git push origin custom-setup
```

### Keeping Fork in Sync

```bash
# Periodically sync master with upstream
git checkout master
git fetch upstream
git merge upstream/master
git push origin master

# Then merge into custom-setup if needed
git checkout custom-setup
git merge master
```

---

## Troubleshooting

### Common Issues

#### 1. Services Won't Start

**Symptom**: `./setup-tadpole.sh start` fails or services exit immediately

**Diagnosis**:
```bash
# Check logs
./setup-tadpole.sh logs backend
./setup-tadpole.sh logs frontend

# Check if ports are already in use
ss -tlnp | grep 8500
ss -tlnp | grep 8700
```

**Solutions**:
- **Port conflict**: Change ports in `.env` or stop conflicting service
- **Missing dependencies**: Run `cd backend && uv sync` and `cd frontend && pnpm install`
- **Missing models**: Verify `/mnt/models/audio/acestep-checkpoints/` exists and contains models
- **Permission issues**: Ensure user has read access to `/mnt/models/`

#### 2. Frontend Can't Connect to Backend

**Symptom**: Frontend shows "Connection Error" or API requests fail

**Diagnosis**:
```bash
# Check backend is running
./setup-tadpole.sh status

# Test backend API
curl http://localhost:8500/api/health

# Check CORS configuration
grep CORS .env
```

**Solutions**:
- **Backend not running**: Start with `./setup-tadpole.sh start`
- **Wrong port**: Verify `TADPOLE_PORT=8500` in `.env`
- **CORS issue**: Ensure `TADPOLE_CORS_ORIGINS` includes `http://localhost:8700`
- **Firewall**: Check if firewall is blocking port 8500

#### 3. Models Not Found

**Symptom**: Backend logs show "Model not found" or "Checkpoint not found"

**Diagnosis**:
```bash
# Check model path
echo $ACESTEP_PROJECT_ROOT
ls -la /mnt/models/audio/acestep-checkpoints/

# Check .env configuration
grep ACESTEP_PROJECT_ROOT .env
```

**Solutions**:
- **Wrong path**: Verify `ACESTEP_PROJECT_ROOT=/mnt/models/audio/acestep-checkpoints` in `.env`
- **Missing models**: Download models to `/mnt/models/audio/acestep-checkpoints/`
- **Permission issues**: Ensure read access to model directory
- **Symlink issues**: Ensure no broken symlinks in model path

#### 4. Port Already in Use

**Symptom**: "Address already in use" error

**Diagnosis**:
```bash
# Find what's using the port
ss -tlnp | grep 8500
ss -tlnp | grep 8700

# Or with lsof
lsof -i :8500
lsof -i :8700
```

**Solutions**:
- **Stop conflicting service**: Identify and stop the service using the port
- **Change ports**: Edit `.env` to use different ports
- **Kill stale process**: `kill <PID>` of the process using the port

#### 5. Frontend Build Errors

**Symptom**: Frontend fails to start with build errors

**Diagnosis**:
```bash
# Check frontend logs
./setup-tadpole.sh logs frontend

# Try manual build
cd frontend
pnpm install
pnpm dev
```

**Solutions**:
- **Dependency issues**: Delete `node_modules` and run `pnpm install`
- **Cache issues**: Delete `.next` directory
- **Node version**: Ensure Node.js 20+ is installed
- **pnpm version**: Ensure pnpm 9+ is installed

#### 6. Backend Python Errors

**Symptom**: Backend fails to start with Python errors

**Diagnosis**:
```bash
# Check backend logs
./setup-tadpole.sh logs backend

# Try manual start
cd backend
source .venv/bin/activate
uv run tadpole-studio
```

**Solutions**:
- **Missing dependencies**: Run `cd backend && uv sync`
- **Python version**: Ensure Python 3.11+ is installed
- **Virtual environment**: Delete `.venv` and recreate with `uv venv && uv sync`
- **CUDA issues**: Verify CUDA is installed if using `TADPOLE_DEVICE=cuda`

#### 7. Database Errors

**Symptom**: "Database locked" or "Database error" messages

**Diagnosis**:
```bash
# Check database file
ls -la backend/data/tadpole-studio.db*

# Check for locks
lsof backend/data/tadpole-studio.db
```

**Solutions**:
- **Multiple instances**: Stop all instances with `./setup-tadpole.sh stop`
- **Corrupted database**: Backup and delete `backend/data/tadpole-studio.db` (will recreate)
- **Permission issues**: Ensure write access to `backend/data/`

### Debug Mode

To run services in foreground for debugging:

```bash
# Backend (foreground)
cd backend
source .venv/bin/activate
export $(cat ../.env | xargs)
uv run tadpole-studio

# Frontend (foreground, separate terminal)
cd frontend
export PORT=8700
export NEXT_PUBLIC_TADPOLE_API_PORT=8500
pnpm dev
```

### Log Analysis

**Backend Log Patterns**:
```bash
# Errors
grep -i error logs/backend.log

# Model loading
grep -i "loading model" logs/backend.log

# API requests
grep -i "GET\|POST\|PUT\|DELETE" logs/backend.log
```

**Frontend Log Patterns**:
```bash
# Compilation errors
grep -i "error" logs/frontend.log

# Build warnings
grep -i "warning" logs/frontend.log

# Ready status
grep -i "ready" logs/frontend.log
```

### Getting Help

If you encounter issues not covered here:

1. **Check logs**: `./setup-tadpole.sh logs`
2. **Check status**: `./setup-tadpole.sh status`
3. **Verify configuration**: `cat .env`
4. **Test backend**: `curl http://localhost:8500/api/health`
5. **Check upstream issues**: https://github.com/proximasan/tadpole-studio/issues

---

## Future Development

### Planned Enhancements

#### 1. Systemd Service Integration

Create a proper systemd service for automatic startup:

```ini
# /etc/systemd/system/tadpole-studio.service
[Unit]
Description=Tadpole Studio AI Music Generation
After=network.target

[Service]
Type=forking
User=tjk
WorkingDirectory=/opt/stacks/tadpole-studio
ExecStart=/opt/stacks/tadpole-studio/setup-tadpole.sh start
ExecStop=/opt/stacks/tadpole-studio/setup-tadpole.sh stop
ExecReload=/opt/stacks/tadpole-studio/setup-tadpole.sh restart
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Commands**:
```bash
sudo systemctl enable tadpole-studio
sudo systemctl start tadpole-studio
sudo systemctl status tadpole-studio
```

#### 2. Reverse Proxy Integration

Add nginx configuration for HTTPS and domain access:

```nginx
# /etc/nginx/sites-available/tadpole-studio
server {
    listen 80;
    server_name tadpole.example.com;

    location / {
        proxy_pass http://localhost:8700;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /api {
        proxy_pass http://localhost:8500;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

#### 3. Docker Containerization

Consider containerizing for easier deployment:

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8500:8500"
    volumes:
      - /mnt/models/audio:/mnt/models/audio:ro
      - ./backend/data:/app/data
    environment:
      - ACESTEP_PROJECT_ROOT=/mnt/models/audio/acestep-checkpoints
      - TADPOLE_PORT=8500
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  frontend:
    build: ./frontend
    ports:
      - "8700:8700"
    environment:
      - PORT=8700
      - NEXT_PUBLIC_TADPOLE_API_PORT=8500
    depends_on:
      - backend
```

#### 4. Monitoring Integration

Add Prometheus metrics and Grafana dashboards:

- **Backend metrics**: Generation count, latency, model usage
- **Frontend metrics**: Page views, API calls, errors
- **System metrics**: GPU usage, memory, disk I/O

#### 5. Backup Automation

Automated backup of generated content and database:

```bash
#!/bin/bash
# backup-tadpole.sh
BACKUP_DIR="/mnt/backups/tadpole-studio"
DATE=$(date +%Y%m%d-%H%M%S)

# Backup database
cp backend/data/tadpole-studio.db "$BACKUP_DIR/db-$DATE.db"

# Backup generated audio
tar -czf "$BACKUP_DIR/audio-$DATE.tar.gz" backend/data/audio/

# Backup LoRAs
tar -czf "$BACKUP_DIR/loras-$DATE.tar.gz" backend/data/loras/

# Keep only last 7 days
find "$BACKUP_DIR" -name "*.db" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete
```

#### 6. Multi-GPU Support

Configure for multiple GPUs:

```bash
# .env
TADPOLE_DEVICE=cuda:0  # Primary GPU
HEARTMULA_DEVICE=cuda:1  # Secondary GPU for HeartMuLa
```

#### 7. API Rate Limiting

Add rate limiting to prevent abuse:

```python
# backend/src/tadpole_studio/main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/generate")
@limiter.limit("10/minute")
async def generate_music(...):
    ...
```

### Customization Ideas

#### 1. Custom Themes

Create organization-specific themes:

```typescript
// frontend/src/themes/company.ts
export const companyTheme: Theme = {
  id: 'company',
  name: 'Company Theme',
  colors: {
    primary: '#your-brand-color',
    // ... other colors
  }
};
```

#### 2. Preset Templates

Add custom generation presets:

```json
// backend/data/presets/company-presets.json
{
  "corporate": {
    "caption": "upbeat corporate background music",
    "bpm": 120,
    "key": "C major",
    "duration": 30
  },
  "podcast-intro": {
    "caption": "energetic podcast intro music",
    "bpm": 140,
    "duration": 15
  }
}
```

#### 3. Webhook Integration

Add webhooks for generation completion:

```python
# backend/src/tadpole_studio/services/webhooks.py
async def notify_completion(song_id: str, webhook_url: str):
    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json={
            "event": "generation_complete",
            "song_id": song_id,
            "timestamp": datetime.utcnow().isoformat()
        })
```

#### 4. S3 Storage Integration

Store generated audio in S3:

```python
# backend/src/tadpole_studio/services/storage.py
import boto3

s3 = boto3.client('s3')

def upload_to_s3(file_path: str, bucket: str, key: str):
    s3.upload_file(file_path, bucket, key)
    return f"https://{bucket}.s3.amazonaws.com/{key}"
```

### Maintenance Notes

#### Regular Tasks

| Task | Frequency | Command |
|------|-----------|---------|
| **Update from upstream** | Weekly | `git fetch upstream && git merge upstream/master` |
| **Check logs** | Daily | `./setup-tadpole.sh logs` |
| **Backup database** | Daily | `cp backend/data/tadpole-studio.db backups/` |
| **Clean old audio** | Monthly | `find backend/data/audio -mtime +30 -delete` |
| **Update dependencies** | Monthly | `cd backend && uv sync --upgrade` |
| **Check disk space** | Weekly | `df -h /opt/stacks` |

#### Upgrade Checklist

When upgrading to a new version:

- [ ] Backup database: `cp backend/data/tadpole-studio.db backup/`
- [ ] Backup `.env` file: `cp .env .env.backup`
- [ ] Stop services: `./setup-tadpole.sh stop`
- [ ] Fetch upstream: `git fetch upstream`
- [ ] Merge changes: `git merge upstream/master`
- [ ] Resolve conflicts (especially `.env`, `base.ts`, `next.config.ts`)
- [ ] Update dependencies: `cd backend && uv sync && cd ../frontend && pnpm install`
- [ ] Review changelog for breaking changes
- [ ] Test in development mode first
- [ ] Start services: `./setup-tadpole.sh start`
- [ ] Verify functionality: Test generation, check logs
- [ ] Commit and push: `git commit -am "Upgrade to vX.Y.Z" && git push`

#### Performance Tuning

**Backend Optimization**:
```bash
# .env additions
TADPOLE_BATCH_SIZE=4           # Increase for better GPU utilization
TADPOLE_WORKERS=2              # Multiple uvicorn workers
TADPOLE_MAX_QUEUE_SIZE=10      # Limit concurrent generations
```

**Frontend Optimization**:
```bash
# Build for production
cd frontend
pnpm build
pnpm start  # Production server instead of dev
```

**Database Optimization**:
```bash
# Vacuum database monthly
sqlite3 backend/data/tadpole-studio.db "VACUUM;"

# Analyze for query optimization
sqlite3 backend/data/tadpole-studio.db "ANALYZE;"
```

---

## Quick Reference

### Essential Commands

```bash
# Start services
./setup-tadpole.sh start

# Stop services
./setup-tadpole.sh stop

# Check status
./setup-tadpole.sh status

# View logs
./setup-tadpole.sh logs

# Restart services
./setup-tadpole.sh restart
```

### Important Paths

| Path | Description |
|------|-------------|
| `/opt/stacks/tadpole-studio/` | Installation directory |
| `/mnt/models/audio/acestep-checkpoints/` | ACE-Step models |
| `/mnt/models/audio/heartmula-models/` | HeartMuLa models |
| `backend/data/audio/` | Generated music files |
| `backend/data/tadpole-studio.db` | SQLite database |
| `logs/backend.log` | Backend logs |
| `logs/frontend.log` | Frontend logs |
| `.env` | Configuration file |

### Important URLs

| URL | Description |
|-----|-------------|
| `http://localhost:8700` | Frontend UI |
| `http://localhost:8500/api/` | Backend API |
| `http://localhost:8500/docs` | API documentation (Swagger) |
| `http://tjkserver:8700` | Network access |

### Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables |
| `setup-tadpole.sh` | Service management |
| `backend/src/tadpole_studio/config.py` | Backend configuration |
| `frontend/src/lib/api/base.ts` | Frontend API client |
| `frontend/next.config.ts` | Next.js configuration |

### Environment Variables Quick Reference

```bash
# Ports
TADPOLE_PORT=8500
TADPOLE_FRONTEND_PORT=8700

# Models
ACESTEP_PROJECT_ROOT=/mnt/models/audio/acestep-checkpoints
HEARTMULA_MODEL_PATH=/mnt/models/audio/heartmula-models/HeartMuLa-oss-RL-3B-20260123

# Device
TADPOLE_DEVICE=cuda

# CORS
TADPOLE_CORS_ORIGINS=http://localhost:8700,http://tjkserver:8700
```

### Git Commands

```bash
# Update from upstream
git fetch upstream
git merge upstream/master

# Push changes to fork
git add .
git commit -m "Description"
git push origin custom-setup

# Check current branch
git branch

# View remotes
git remote -v
```

### Troubleshooting Quick Checks

```bash
# Check if services are running
./setup-tadpole.sh status

# Check if ports are listening
ss -tlnp | grep -E "8500|8700"

# Test backend API
curl http://localhost:8500/api/health

# Check model path
ls -la /mnt/models/audio/acestep-checkpoints/

# View recent logs
tail -n 50 logs/backend.log
tail -n 50 logs/frontend.log

# Check disk space
df -h /opt/stacks
df -h /mnt/models
```

---

## Document History

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-16 | 1.0 | Initial comprehensive documentation |

---

## License

This custom setup documentation is provided as-is for the `/opt/stacks/tadpole-studio` installation. The underlying Tadpole Studio software is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

**End of Documentation**