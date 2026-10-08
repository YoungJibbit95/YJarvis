# Source this file from Bash: source setup/activate.sh
# No shell-profile or permanent PATH changes.
_yj_setup_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$_yj_setup_root/.venv/bin:$_yj_setup_root/.setup-tools/node/bin:$_yj_setup_root/.setup-tools/ollama/bin:$_yj_setup_root/.setup-tools/whisper/build/bin:$PATH"
if [[ "$(uname -s)" == Darwin ]] && command -v brew >/dev/null 2>&1; then
    export PATH="$(brew --prefix node@22)/bin:$(brew --prefix python@3.11)/bin:$PATH"
fi
export JARVIS_PYTHON_BIN="$_yj_setup_root/.venv/bin/python"
unset _yj_setup_root
