#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

if [[ "${1:-}" == --dry-run && $# == 1 ]]; then
    echo 'macOS: Homebrew (bei Bedarf) und git python@3.11 node@22 ollama ffmpeg whisper.cpp portaudio libsndfile installieren.'
    echo 'Danach: .venv, beide requirements-Dateien, pip check, npm ci. Keine Modelle.'
    exit 0
fi
[[ $# == 0 ]] || setup_error 'Aufruf: bash setup/macos.sh [--dry-run]'
[[ "$(uname -s)" == Darwin ]] || setup_error 'Dieses Skript ist nur fuer macOS.'
[[ "$EUID" != 0 ]] || setup_error 'Als normaler Benutzer starten, nicht mit sudo.'

setup_tmp="$(mktemp -d)"
trap 'rm -rf -- "$setup_tmp"' EXIT
if ! command -v brew >/dev/null 2>&1; then
    for setup_brew in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [[ -x "$setup_brew" ]]; then
            export PATH="$(dirname "$setup_brew"):$PATH"
            break
        fi
    done
fi
if ! command -v brew >/dev/null 2>&1; then
    setup_download 'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh' "$setup_tmp/homebrew.sh"
    # Apple's command-line tools / administrator authentication can require UI.
    /bin/bash "$setup_tmp/homebrew.sh"
    case "$(uname -m)" in
        arm64) export PATH="/opt/homebrew/bin:$PATH" ;;
        x86_64) export PATH="/usr/local/bin:$PATH" ;;
        *) setup_error 'Unbekannte macOS-Architektur.' ;;
    esac
fi
brew install git python@3.11 node@22 ollama ffmpeg whisper.cpp portaudio libsndfile
export PATH="$(brew --prefix node@22)/bin:$(brew --prefix python@3.11)/bin:$PATH"
setup_python="$(brew --prefix python@3.11)/bin/python3.11"
setup_project
