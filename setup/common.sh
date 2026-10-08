# Shared Bash helpers. Callers enable errexit/pipefail before sourcing.
setup_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
setup_tools="$setup_root/.setup-tools"

setup_error() { echo "[setup] $*" >&2; exit 1; }

setup_download() {
    curl --fail --location --retry 3 --proto '=https' --tlsv1.2 "$1" --output "$2"
}

setup_node_linux() {
    if command -v node >/dev/null 2>&1 && [[ "$(node --version)" == v22.* ]] && command -v npm >/dev/null 2>&1; then
        return
    fi
    [[ ! -e "$setup_tools/node" ]] || setup_error "Lokale Node-Installation unvollstaendig/falsche Version: $setup_tools/node"
    local arch archive checksum
    case "$(uname -m)" in
        x86_64) arch=x64 ;;
        aarch64|arm64) arch=arm64 ;;
        *) setup_error "Node-Download unterstuetzt nur Linux x64/arm64." ;;
    esac
    setup_download 'https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt' "$setup_tmp/SHASUMS256.txt"
    archive="$(awk -v suffix="-linux-$arch.tar.xz" '$2 ~ (suffix "$") {print $2}' "$setup_tmp/SHASUMS256.txt")"
    [[ "$archive" =~ ^node-v22\.[0-9]+\.[0-9]+-linux-(x64|arm64)\.tar\.xz$ ]] || setup_error 'Node-Downloadliste ungueltig.'
    checksum="$(awk -v name="$archive" '$2 == name {print $1}' "$setup_tmp/SHASUMS256.txt")"
    setup_download "https://nodejs.org/dist/latest-v22.x/$archive" "$setup_tmp/$archive"
    (cd "$setup_tmp" && printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --status)
    mkdir -p "$setup_tools/node"
    tar -xJf "$setup_tmp/$archive" -C "$setup_tools/node" --strip-components=1
}

setup_project() {
    "$setup_python" "$setup_root/setup/install_dependencies.py"
    echo "[setup] Fertig. Keine Modelle installiert."
    echo "[setup] Im Repo: source setup/activate.sh"
    echo "[setup] Modelle spaeter auswaehlen; Startbefehle stehen in setup/README.md."
}
