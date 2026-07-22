#!/usr/bin/env bash
# =============================================================================
# RVTool Genesis — One-Click Setup Script
# =============================================================================
# Usage: ./setup.sh
# Run this once after cloning to start the full application.
# It's safe to run again at any time to restart the stack.
# =============================================================================

set -e

# Colour helpers (gracefully degrades if terminal doesn't support colour)
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Colour

info()    { echo -e "${BOLD}→ $*${NC}"; }
success() { echo -e "${GREEN}✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $*${NC}"; }
error()   { echo -e "${RED}✗ $*${NC}"; }

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}   RVTool Genesis — Starting Up            ${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""

# =============================================================================
# Step 1 — Check prerequisites
# =============================================================================
info "Checking prerequisites..."

# Docker
if ! command -v docker &>/dev/null; then
  error "Docker is not installed."
  echo "  Install OrbStack (recommended): https://orbstack.dev"
  echo "  Or Docker Desktop:              https://www.docker.com/products/docker-desktop"
  exit 1
fi

# Docker Compose v2 (space, not hyphen)
if ! docker compose version &>/dev/null; then
  error "Docker Compose v2 is not available."
  echo "  Make sure OrbStack or Docker Desktop is running."
  exit 1
fi

success "Docker and Docker Compose are available"

# Ollama — check if the service is reachable on localhost:11434
if ! curl -sf http://localhost:11434 &>/dev/null; then
  error "Ollama is not running."
  echo ""
  echo "  Please start Ollama:"
  echo "  • If you installed the Ollama macOS app: open it from your Applications folder"
  echo "    or look for the llama icon in your menu bar."
  echo "  • If you installed via Homebrew/CLI: run  ollama serve"
  echo ""
  echo "  Then re-run:  ./setup.sh"
  exit 1
fi

success "Ollama is running at http://localhost:11434"

# Read the configured model from .env.example as the canonical source
OLLAMA_MODEL="${OLLAMA_MODEL:-phi4-mini}"

# Check if the model is already available
if ! ollama list 2>/dev/null | grep -q "^${OLLAMA_MODEL}"; then
  warn "Model '${OLLAMA_MODEL}' not found locally."
  echo ""
  info "Pulling ${OLLAMA_MODEL} (one-time download, ~3–5 GB)..."
  echo "  This may take a few minutes depending on your connection."
  echo ""
  if ! ollama pull "${OLLAMA_MODEL}"; then
    error "Failed to pull model '${OLLAMA_MODEL}'."
    echo "  Try manually: ollama pull ${OLLAMA_MODEL}"
    exit 1
  fi
  success "Model '${OLLAMA_MODEL}' is ready"
else
  success "Model '${OLLAMA_MODEL}' is already available"
fi

# =============================================================================
# Step 2 — Environment setup
# =============================================================================
echo ""
info "Setting up environment..."

if [ ! -f ".env" ]; then
  cp .env.example .env

  # Auto-generate a strong SECRET_KEY so the API starts cleanly on first run.
  # Tries openssl first (macOS, Linux, Git Bash, WSL), then python3 as a
  # cross-platform fallback. If neither is available the placeholder is left
  # in place and the user is prompted to set it manually.
  if command -v openssl &>/dev/null; then
    _secret=$(openssl rand -hex 32)
  elif command -v python3 &>/dev/null; then
    _secret=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  else
    _secret=""
  fi

  if [ -n "$_secret" ]; then
    # Replace only the SECRET_KEY= line — no other lines are affected
    sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=${_secret}|" .env && rm -f .env.bak
    success "Created .env with auto-generated SECRET_KEY — keep this file private"
  else
    warn "Created .env from .env.example — openssl and python3 not found."
    warn "Before starting, run:  make generate-secret"
    warn "Paste the output into .env as:  SECRET_KEY=<generated-value>"
  fi
else
  success ".env already exists — skipping (delete it to reset to defaults)"
fi

# =============================================================================
# Step 3 — Start containers
# =============================================================================
echo ""
info "Building and starting containers (this takes ~1 minute on first run)..."
docker compose up --build -d

success "Containers started"

# =============================================================================
# Step 4 — Wait for API health check
# =============================================================================
echo ""
info "Waiting for API to be ready..."

MAX_WAIT=90
WAITED=0
INTERVAL=3

while true; do
  if curl -sf http://localhost:8001/api/health &>/dev/null; then
    echo ""
    success "API is ready"
    break
  fi

  if [ $WAITED -ge $MAX_WAIT ]; then
    echo ""
    error "API did not become ready within ${MAX_WAIT} seconds."
    echo ""
    echo "  Troubleshooting:"
    echo "    docker compose logs api     — view API startup errors"
    echo "    docker compose logs db      — view database errors"
    echo "    docker compose ps           — check container status"
    echo ""
    echo "  Common causes:"
    echo "    • First-time Docker image build still in progress (wait a bit and retry)"
    echo "    • Port 8001 already in use on your machine"
    exit 1
  fi

  printf "."
  sleep $INTERVAL
  WAITED=$((WAITED + INTERVAL))
done

# =============================================================================
# Step 5 — Open browser and print summary
# =============================================================================
echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}   RVTool Genesis is ready!                ${NC}"
echo -e "${BOLD}============================================${NC}"
echo ""
echo -e "  ${BOLD}App:${NC}       http://localhost:3001"
echo -e "  ${BOLD}API docs:${NC}  http://localhost:8001/api/docs"
echo -e "  ${BOLD}AI model:${NC}  ${OLLAMA_MODEL} (running locally via Ollama)"
echo ""
echo -e "  ${BOLD}To stop:${NC}   docker compose down"
echo -e "  ${BOLD}Logs:${NC}      docker compose logs -f"
echo -e "  ${BOLD}Restart:${NC}   ./setup.sh"
echo ""

# Open the app in the default browser (macOS)
if command -v open &>/dev/null; then
  open http://localhost:3001
fi
