from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PROFILE: dict[str, Any] = {
    "persona": {
        "name": "Jarvis",
        "identity_instructions": [
            "Du bist J.A.R.V.I.S., ein hochpraeziser technischer Assistent fuer einen einzelnen Benutzer auf diesem Mac.",
            "Du bist loyal, diskret und sicherheitsorientiert.",
            "Du bist sachlich, schnell und elegant in der Formulierung.",
        ],
        "style_instructions": [
            "Sprich auf Deutsch, praezise, ruhig und professionell.",
            "Sprich den Benutzer, wenn du ihn direkt ansprichst, mit `Sir` an. Verwende niemals `mein Herr`.",
            "Klinge wie ein technischer Assistent im Stil von Jarvis (Tony Stark), ohne uebertriebenes Rollenspiel.",
            "Nutze kurze, klare Saetze und gib bei Aktionen den Status transparent an.",
            "Klinge freundlich, warm und zugewandt, ohne an Praezision zu verlieren.",
            "Vermeide monotone Formulierungen und nutze natuerliche Interpunktion fuer eine lebendige Sprechweise.",
            "Wenn sinnvoll, beginne mit einer knappen Lageeinschaetzung und dann der konkreten Aktion.",
            "Sei hoeflich, aber niemals geschwaetzig oder flapsig.",
        ],
        "response_contract": [
            "Bei Risikoentscheidungen zuerst Sicherheitsbewertung, dann Handlungsvorschlag.",
            "Keine spekulativen Behauptungen zu Systemzustand; Unsicherheiten explizit markieren.",
            "Bei blockierten Aktionen immer sichere Alternative anbieten.",
            "Nutze lokale Lernsignale (Erfolgsquote/Latenz), um robuste und schnelle Vorgehensweisen zu bevorzugen.",
            "Wenn eine Aufgabe unklar, sicherheitskritisch oder potentiell missverstaendlich ist, stelle eine kurze Rueckfrage.",
        ],
    },
    "safety": {
        "blocked_request_patterns": [
            "loesch das gesamte system",
            "loesch alle daten",
            "loesch den ganzen pc",
            "zerstoere das system",
            "delete all data",
            "delete the whole system",
            "delete everything",
            "wipe the system",
            "wipe all data",
            "formatiere die festplatte",
            "format disk",
            "rm -rf /",
            "sudo rm -rf /",
            "diskutil erasedisk",
            "diskutil apfs deletecontainer",
            "destroy all files",
            "vernichte alle daten",
            "mach den mac unbrauchbar",
            "disable system integrity protection",
            "csrutil disable",
            "delete /system",
            "erase this mac",
        ],
        "confirmation_required_patterns": [
            "sudo ",
            "admin rechte",
            "administratorrechte",
            "keychain",
            "passwort anzeigen",
            "ssh key",
            "private key",
            "zugriff auf sensible daten",
            "firewall deaktivieren",
            "sicherheitsfunktionen ausschalten",
            "launchdaemon",
            "launchctl",
            "autostart einrichten",
            "cronjob systemweit",
            "netzwerkscan",
            "portscan",
            "exfiltriere",
            "tracking script",
        ],
        "blocked_path_prefixes": [
            "/System",
            "/bin",
            "/sbin",
            "/usr",
            "/etc",
            "/private",
            "/Library",
            "/var",
            "/dev",
        ],
        "blocked_content_patterns": [
            "rm -rf /",
            "sudo rm -rf",
            "diskutil eraseDisk",
            "diskutil apfs deleteContainer",
            "mkfs",
            "dd if=/dev/zero",
            "shutdown -h now",
            "reboot now",
            "csrutil disable",
        ],
        "refusal_message": "Diese Anfrage ist systemkritisch oder destruktiv. Ich fuehre sie aus Sicherheitsgruenden nicht aus.",
        "confirmation_required_message": "Diese Anfrage ist sicherheitsrelevant und wird nur nach expliziter Freigabe ausgefuehrt.",
        "confirmation_instruction": "Wenn ich fortfahren soll, antworte exakt mit `Bestaetige`.",
        "confirmation_accept_phrases": [
            "bestaetige",
        ],
        "confirmation_accept_prefixes": [
            "bestaetige",
            "ich bestaetige",
        ],
    },
}


def ensure_profile(profile_path: Path) -> None:
    if profile_path.exists():
        return
    profile_path.write_text(json.dumps(DEFAULT_PROFILE, indent=2, ensure_ascii=True), encoding="utf-8")


def load_profile(profile_path: Path) -> dict[str, Any]:
    ensure_profile(profile_path)
    try:
        parsed = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_PROFILE

    if not isinstance(parsed, dict):
        return DEFAULT_PROFILE

    merged = dict(DEFAULT_PROFILE)
    persona = dict(DEFAULT_PROFILE.get("persona", {}))
    persona.update(parsed.get("persona", {}) if isinstance(parsed.get("persona"), dict) else {})

    safety = dict(DEFAULT_PROFILE.get("safety", {}))
    safety.update(parsed.get("safety", {}) if isinstance(parsed.get("safety"), dict) else {})

    merged["persona"] = persona
    merged["safety"] = safety
    return merged


def build_persona_system_prompt(profile: dict[str, Any]) -> str:
    persona = profile.get("persona", {}) if isinstance(profile.get("persona"), dict) else {}
    identity_instructions = persona.get("identity_instructions", [])
    style_instructions = persona.get("style_instructions", [])
    response_contract = persona.get("response_contract", [])
    identity_lines = []
    style_lines = []
    contract_lines = []

    if isinstance(identity_instructions, list):
        identity_lines = [str(item) for item in identity_instructions if str(item).strip()]
    if isinstance(style_instructions, list):
        style_lines = [str(item) for item in style_instructions if str(item).strip()]
    if isinstance(response_contract, list):
        contract_lines = [str(item) for item in response_contract if str(item).strip()]

    safety_text = (
        "Fuehre niemals destruktive oder systemkritische Aktionen aus. "
        "Bei solchen Anfragen immer kurz ablehnen und sichere Alternative anbieten."
    )

    lines = [
        "Du bist Jarvis, ein lokaler Assistent auf macOS.",
        *identity_lines,
        *style_lines,
        *contract_lines,
        safety_text,
    ]
    return "\n".join(lines)
