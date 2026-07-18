#!/usr/bin/env bash
#
# MJOLNIR installer
# Target: Debian-based Linux (Ubuntu, Debian, Kali, Mint, ...)
#
set -euo pipefail

CYAN="\033[1;36m"
MAGENTA="\033[1;35m"
GREEN="\033[1;32m"
RED="\033[1;31m"
RESET="\033[0m"

info()  { echo -e "${CYAN}[*]${RESET} $*"; }
ok()    { echo -e "${GREEN}[+]${RESET} $*"; }
warn()  { echo -e "${MAGENTA}[!]${RESET} $*"; }
fail()  { echo -e "${RED}[x]${RESET} $*"; exit 1; }

clear
echo -e "${CYAN}"
cat << "EOF"
 ███╗   ███╗      ██╗ ██████╗ ██╗     ███╗   ██╗██╗██████╗
 ████╗ ████║      ██║██╔═══██╗██║     ████╗  ██║██║██╔══██╗
 ██╔████╔██║      ██║██║   ██║██║     ██╔██╗ ██║██║██████╔╝
 ██║╚██╔╝██║ ██   ██║██║   ██║██║     ██║╚██╗██║██║██╔══██╗
 ██║ ╚═╝ ██║ ╚█████╔╝╚██████╔╝███████╗██║ ╚████║██║██║  ██║
 ╚═╝     ╚═╝  ╚════╝  ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝
EOF
echo -e "${MAGENTA}          WHAT SHOULD BE, OR SHOULD NOT.${RESET}"
echo -e "${RESET}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

INSTALL_PREFIX="${MJOLNIR_INSTALL_PREFIX:-$HOME/.local/share/mjolnir}"
BIN_TARGET="${MJOLNIR_BIN_DIR:-$HOME/.local/bin}"
DEFAULT_MODEL="qwen2.5:3b"

# ------------------------------------------------------------
# 1. apt-get update + core dependencies
# ------------------------------------------------------------
if ! command -v apt-get >/dev/null 2>&1; then
    fail "This installer targets Debian-based systems (apt-get not found)."
fi

info "Updating package lists..."
sudo apt-get update -y

info "Installing core dependencies (python3, pip, venv, git, curl)..."
sudo apt-get install -y python3 python3-pip python3-venv git curl

# ------------------------------------------------------------
# 2. Ollama
# ------------------------------------------------------------
info "Checking for Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
    warn "Ollama not found. Installing..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    ok "Ollama already installed: $(ollama --version 2>/dev/null || echo unknown)"
fi

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q '^ollama.service'; then
    sudo systemctl enable ollama >/dev/null 2>&1 || true
    sudo systemctl start ollama >/dev/null 2>&1 || true
fi

if ! pgrep -x "ollama" >/dev/null 2>&1; then
    info "Starting ollama serve in background..."
    nohup ollama serve >/tmp/mjolnir-ollama.log 2>&1 &
    sleep 3
fi

if ! ollama list >/dev/null 2>&1; then
    fail "Ollama server did not start. Check /tmp/mjolnir-ollama.log"
fi

# ------------------------------------------------------------
# 3. Pull the default model
# ------------------------------------------------------------
info "Pulling default model: ${DEFAULT_MODEL} (this may take a while)..."
ollama pull "$DEFAULT_MODEL"

# ------------------------------------------------------------
# 4. Python virtual environment + dependencies
# ------------------------------------------------------------
info "Setting up Python virtual environment at ${INSTALL_PREFIX}..."
mkdir -p "$INSTALL_PREFIX"
cp -r "$SCRIPT_DIR"/mjolnir "$INSTALL_PREFIX"/
cp "$SCRIPT_DIR"/requirements.txt "$INSTALL_PREFIX"/

python3 -m venv "$INSTALL_PREFIX/.venv"
# shellcheck disable=SC1091
source "$INSTALL_PREFIX/.venv/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r "$INSTALL_PREFIX/requirements.txt"
deactivate

# ------------------------------------------------------------
# 5. Global `mjolnir` command
# ------------------------------------------------------------
info "Installing global 'mjolnir' command..."
mkdir -p "$BIN_TARGET"

cat > "$BIN_TARGET/mjolnir" << WRAPPER
#!/usr/bin/env bash
exec "$INSTALL_PREFIX/.venv/bin/python" -m mjolnir.main "\$@"
WRAPPER
chmod +x "$BIN_TARGET/mjolnir"

if command -v sudo >/dev/null 2>&1 && [ -w "/usr/local/bin" -o "$(id -u)" != "0" ]; then
    sudo ln -sf "$BIN_TARGET/mjolnir" /usr/local/bin/mjolnir 2>/dev/null || true
fi

# Ensure ~/.local/bin is on PATH
if [[ "$SHELL" == *"zsh"* ]]; then
    SHELL_RC="$HOME/.zshrc"
else
    SHELL_RC="$HOME/.bashrc"
fi
if ! grep -q 'HOME/.local/bin' "$SHELL_RC" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
    warn "Added ~/.local/bin to PATH in ${SHELL_RC}. Run: source ${SHELL_RC}"
fi

echo
ok "Installation complete."
echo -e "${CYAN}[*] Launch Mjolnir with:${RESET} mjolnir"
echo -e "${CYAN}[*] Config file:${RESET} ~/.config/mjolnir/config.yaml"
echo -e "${CYAN}[*] Logs:${RESET} ~/.config/mjolnir/logs/"
