#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"

if [[ "${1:-}" == --dry-run && $# == 1 ]]; then
    echo 'Linux: Debian/Ubuntu (apt), Fedora (dnf), Arch (pacman); Git, curl, FFmpeg, Audio-Bibliotheken, CMake/C++.'
    echo 'Python 3.11 bei Bedarf ueber uv; Node 22 bei Bedarf lokal mit SHA256-Pruefung.'
    echo 'Ollama aus offiziellem CLI-Archiv lokal installieren; whisper.cpp v1.8.3 CPU-CLI bauen.'
    echo 'Danach: .venv, beide requirements-Dateien, pip check, npm ci. Keine Modelle.'
    exit 0
fi
[[ $# == 0 ]] || setup_error 'Aufruf: bash setup/linux.sh [--dry-run]'
[[ "$(uname -s)" == Linux ]] || setup_error 'Dieses Skript ist nur fuer Linux.'
[[ "$EUID" != 0 ]] || setup_error 'Als normaler Benutzer starten, nicht mit sudo.'
case "$(uname -m)" in
    x86_64) setup_ollama_arch=amd64 ;;
    aarch64|arm64) setup_ollama_arch=arm64 ;;
    *) setup_error 'Unterstuetzt werden Linux x64 und arm64.' ;;
esac
[[ -r /etc/os-release ]] || setup_error '/etc/os-release fehlt.'
source /etc/os-release
case "${ID:-}" in
    ubuntu|debian) setup_manager=apt ;;
    fedora) setup_manager=dnf ;;
    arch) setup_manager=pacman ;;
    *) setup_error "Distribution ${ID:-unbekannt} wird nicht automatisch eingerichtet. Siehe setup/README.md." ;;
esac
command -v sudo >/dev/null 2>&1 || setup_error 'sudo wird fuer Systempakete benoetigt.'
sudo -v
case "$setup_manager" in
    apt)
        sudo apt-get update
        sudo apt-get install --yes --no-install-recommends git curl ca-certificates xz-utils zstd ffmpeg libportaudio2 libsndfile1 build-essential cmake
        ;;
    dnf)
        sudo dnf install --assumeyes git curl ca-certificates xz zstd ffmpeg-free portaudio libsndfile gcc-c++ make cmake
        ;;
    pacman)
        # Avoid an unsupported partial upgrade on this rolling distribution.
        sudo pacman -Syu --needed --noconfirm git curl ca-certificates xz zstd ffmpeg portaudio libsndfile base-devel cmake
        ;;
esac

mkdir -p "$setup_tools"
setup_tmp="$(mktemp -d)"
trap 'rm -rf -- "$setup_tmp"' EXIT
export PATH="$setup_tools/node/bin:$setup_tools/uv:$setup_tools/ollama/bin:$setup_tools/whisper/build/bin:$PATH"

if command -v python3.11 >/dev/null 2>&1 && python3.11 -c 'import venv, ensurepip'; then
    setup_python="$(command -v python3.11)"
else
    if ! command -v uv >/dev/null 2>&1; then
        setup_download 'https://astral.sh/uv/install.sh' "$setup_tmp/uv.sh"
        UV_UNMANAGED_INSTALL="$setup_tools/uv" sh "$setup_tmp/uv.sh"
    fi
    export UV_PYTHON_INSTALL_DIR="$setup_tools/python"
    uv python install 3.11
    setup_python="$(uv python find --managed-python 3.11)"
fi
setup_node_linux
if ! command -v ollama >/dev/null 2>&1; then
    [[ ! -e "$setup_tools/ollama" ]] || setup_error "Lokales Ollama unvollstaendig: $setup_tools/ollama"
    # The upstream shell installer can install GPU drivers. Use its documented
    # manual archive instead, preserving bin/ and lib/ without changing services.
    setup_download "https://ollama.com/download/ollama-linux-$setup_ollama_arch.tar.zst" "$setup_tmp/ollama.tar.zst"
    mkdir -p "$setup_tools/ollama"
    tar --zstd -xf "$setup_tmp/ollama.tar.zst" -C "$setup_tools/ollama"
fi
if ! command -v whisper-cli >/dev/null 2>&1; then
    if [[ ! -d "$setup_tools/whisper" ]]; then
        git clone --depth 1 --branch v1.8.3 https://github.com/ggml-org/whisper.cpp.git "$setup_tools/whisper"
    fi
    [[ "$(git -C "$setup_tools/whisper" describe --tags --exact-match)" == v1.8.3 ]] || setup_error 'Lokale whisper.cpp-Quelle entspricht nicht v1.8.3.'
    cmake -S "$setup_tools/whisper" -B "$setup_tools/whisper/build" -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DWHISPER_BUILD_TESTS=OFF
    cmake --build "$setup_tools/whisper/build" --config Release --target whisper-cli --parallel 2
fi
command -v ollama >/dev/null 2>&1 || setup_error 'Ollama fehlt nach Installation.'
command -v whisper-cli >/dev/null 2>&1 || setup_error 'whisper-cli fehlt nach Build.'
setup_project
