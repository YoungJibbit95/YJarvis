from __future__ import annotations

import csv
import os
import platform
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..base import run_command


@dataclass
class ProviderResult:
    success: bool
    output: str = ""
    error: str | None = None
    data: dict[str, Any] | None = None


def _platform_name() -> str:
    return platform.system().lower()


def _clean_lines(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _safe_task_token(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip())
    token = token.strip("-")
    return token[:80] or "jarvis-task"


def _parse_time_label(value: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*$", str(value or ""))
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return (f"{hour:02d}", f"{minute:02d}")


class GenericProvider:
    def __init__(self) -> None:
        self.platform = _platform_name()

    async def open_app(self, app_name: str) -> ProviderResult:
        name = str(app_name or "").strip()
        if not name:
            return ProviderResult(success=False, error="app_name fehlt.")
        if self.platform == "darwin":
            process = await run_command(["open", "-a", name])
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"App geoeffnet: {name}")
            return ProviderResult(success=False, error=process.stderr.strip() or "open -a fehlgeschlagen")
        if self.platform == "windows":
            process = await run_command(["powershell", "-NoProfile", "-Command", f"Start-Process '{name}'"])
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"App geoeffnet: {name}")
            fallback = await run_command(["cmd", "/c", "start", "", name])
            if fallback.returncode == 0:
                return ProviderResult(success=True, output=f"App geoeffnet: {name}")
            return ProviderResult(success=False, error=(process.stderr or fallback.stderr or "").strip() or "Start fehlgeschlagen")
        if self.platform == "linux":
            process = await run_command(["xdg-open", name])
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"App geoeffnet: {name}")
            return ProviderResult(success=False, error=process.stderr.strip() or "xdg-open fehlgeschlagen")
        return ProviderResult(success=False, error="Betriebssystem nicht unterstuetzt")

    async def focus_app(self, app_name: str) -> ProviderResult:
        return await self.open_app(app_name)

    async def close_app(self, app_name: str) -> ProviderResult:
        name = str(app_name or "").strip()
        if not name:
            return ProviderResult(success=False, error="app_name fehlt.")
        if self.platform == "darwin":
            script = f'tell application "{name}" to quit'
            process = await run_command(["osascript", "-e", script])
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"App geschlossen: {name}")
            return ProviderResult(success=False, error=process.stderr.strip() or "quit fehlgeschlagen")
        if self.platform == "windows":
            process = await run_command(["taskkill", "/IM", name, "/T"])
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"App geschlossen: {name}")
            return ProviderResult(success=False, error=process.stderr.strip() or "taskkill fehlgeschlagen")
        if self.platform == "linux":
            process = await run_command(["pkill", "-f", name])
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"App geschlossen: {name}")
            return ProviderResult(success=False, error=process.stderr.strip() or "pkill fehlgeschlagen")
        return ProviderResult(success=False, error="Betriebssystem nicht unterstuetzt")

    async def list_running_apps(self, limit: int = 40) -> ProviderResult:
        safe_limit = max(1, min(int(limit), 200))
        if self.platform == "windows":
            process = await run_command(["tasklist", "/FO", "CSV", "/NH"])
            if process.returncode != 0:
                return ProviderResult(success=False, error=process.stderr.strip() or "tasklist fehlgeschlagen")
            reader = csv.reader(process.stdout.splitlines())
            names = [row[0].strip() for row in reader if row and row[0].strip()]
        else:
            process = await run_command(["ps", "-eo", "comm="])
            if process.returncode != 0:
                return ProviderResult(success=False, error=process.stderr.strip() or "ps fehlgeschlagen")
            names = _clean_lines(process.stdout)
        unique = list(dict.fromkeys(names))[:safe_limit]
        return ProviderResult(success=True, output="\n".join(unique), data={"apps": unique})

    async def process_list(self, limit: int = 25) -> ProviderResult:
        safe_limit = max(1, min(int(limit), 200))
        if self.platform == "windows":
            process = await run_command(["tasklist", "/FO", "CSV", "/NH"])
            if process.returncode != 0:
                return ProviderResult(success=False, error=process.stderr.strip() or "tasklist fehlgeschlagen")
            reader = csv.reader(process.stdout.splitlines())
            rows: list[dict[str, str]] = []
            for row in reader:
                if len(row) < 2:
                    continue
                rows.append({"name": row[0].strip(), "pid": row[1].strip()})
                if len(rows) >= safe_limit:
                    break
            lines = [f"{item['name']} (PID {item['pid']})" for item in rows]
            return ProviderResult(success=True, output="\n".join(lines), data={"processes": rows})

        process = await run_command(["ps", "-Ao", "pid,pcpu,comm"])
        if process.returncode != 0:
            return ProviderResult(success=False, error=process.stderr.strip() or "ps fehlgeschlagen")
        lines = _clean_lines(process.stdout)
        header = lines[:1]
        body = lines[1 : safe_limit + 1]
        return ProviderResult(success=True, output="\n".join(header + body), data={"rows": body})

    async def process_terminate(self, *, pid: int | None = None, name: str | None = None, force: bool = False) -> ProviderResult:
        if pid is None and not name:
            return ProviderResult(success=False, error="pid oder name erforderlich.")
        if self.platform == "windows":
            if pid is not None:
                args = ["taskkill", "/PID", str(pid)]
            else:
                args = ["taskkill", "/IM", str(name)]
            if force:
                args.append("/F")
            process = await run_command(args)
            if process.returncode == 0:
                return ProviderResult(success=True, output="Prozess beendet.")
            return ProviderResult(success=False, error=process.stderr.strip() or "taskkill fehlgeschlagen")

        if pid is not None:
            args = ["kill", "-9" if force else "-15", str(pid)]
        else:
            args = ["pkill", "-9" if force else "-15", "-f", str(name)]
        process = await run_command(args)
        if process.returncode == 0:
            return ProviderResult(success=True, output="Prozess beendet.")
        return ProviderResult(success=False, error=process.stderr.strip() or "Prozess konnte nicht beendet werden")

    async def file_search(self, *, query: str, roots: list[str], limit: int = 20) -> ProviderResult:
        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            return ProviderResult(success=False, error="query fehlt.")
        safe_limit = max(1, min(int(limit), 200))
        matches: list[str] = []
        for root in roots:
            root_path = Path(root).expanduser()
            if not root_path.exists() or not root_path.is_dir():
                continue
            process = await run_command(["rg", "--files", str(root_path)])
            if process.returncode != 0:
                continue
            for line in _clean_lines(process.stdout):
                if normalized_query in line.lower():
                    matches.append(line)
                    if len(matches) >= safe_limit:
                        break
            if len(matches) >= safe_limit:
                break
        if not matches:
            return ProviderResult(success=True, output=f"Keine Dateien zu `{query}` gefunden.", data={"matches": []})
        return ProviderResult(success=True, output="\n".join(matches), data={"matches": matches})

    async def send_notification(self, *, title: str, text: str) -> ProviderResult:
        safe_title = str(title or "Jarvis").strip() or "Jarvis"
        safe_text = str(text or "").strip()
        if self.platform == "darwin":
            script = (
                "display notification "
                f"\"{safe_text.replace(chr(34), chr(92) + chr(34))}\" "
                f"with title \"{safe_title.replace(chr(34), chr(92) + chr(34))}\""
            )
            process = await run_command(["osascript", "-e", script])
            if process.returncode == 0:
                return ProviderResult(success=True, output="Benachrichtigung gesendet.")
            return ProviderResult(success=False, error=process.stderr.strip() or "Notification fehlgeschlagen")
        if self.platform == "windows":
            process = await run_command(["powershell", "-NoProfile", "-Command", f"Write-Output '{safe_title}: {safe_text}'"])
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"Notification vorbereitet: {safe_title}")
            return ProviderResult(success=False, error=process.stderr.strip() or "Notification fehlgeschlagen")
        process = await run_command(["notify-send", safe_title, safe_text])
        if process.returncode == 0:
            return ProviderResult(success=True, output="Benachrichtigung gesendet.")
        return ProviderResult(success=False, error=process.stderr.strip() or "Notification fehlgeschlagen")

    async def scheduler_create_task(self, *, task_name: str, time_label: str, command: str) -> ProviderResult:
        token = _safe_task_token(task_name)
        parsed_time = _parse_time_label(time_label)
        if parsed_time is None:
            return ProviderResult(success=False, error="time muss HH:MM sein.")
        hour, minute = parsed_time
        safe_command = str(command or "").strip()
        if not safe_command:
            return ProviderResult(success=False, error="command fehlt.")

        if self.platform == "windows":
            schedule_time = f"{hour}:{minute}"
            process = await run_command(
                [
                    "schtasks",
                    "/Create",
                    "/SC",
                    "DAILY",
                    "/TN",
                    token,
                    "/TR",
                    safe_command,
                    "/ST",
                    schedule_time,
                    "/F",
                ]
            )
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"Task erstellt: {token} um {schedule_time}")
            return ProviderResult(success=False, error=process.stderr.strip() or "schtasks fehlgeschlagen")

        if self.platform == "darwin":
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.jarvis.{token}.plist"
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.jarvis.{token}</string>
  <key>ProgramArguments</key><array><string>/bin/sh</string><string>-lc</string><string>{safe_command}</string></array>
  <key>RunAtLoad</key><false/>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>{int(hour)}</integer><key>Minute</key><integer>{int(minute)}</integer></dict>
</dict>
</plist>
"""
            plist_path.write_text(plist_content, encoding="utf-8")
            process = await run_command(["launchctl", "load", str(plist_path)])
            if process.returncode == 0:
                return ProviderResult(success=True, output=f"launchd Task erstellt: {token} um {hour}:{minute}")
            return ProviderResult(success=False, error=process.stderr.strip() or "launchctl load fehlgeschlagen")

        return ProviderResult(success=False, error="Scheduler auf diesem System nicht unterstuetzt")

    async def create_note(self, *, title: str, content: str, folder: str = "") -> ProviderResult:
        safe_title = _safe_task_token(title).replace("-", " ").strip() or "note"
        safe_folder = _safe_task_token(folder or "General")
        safe_content = str(content or "").strip() or safe_title

        root = Path.home() / "Documents" / "JarvisNotes" / safe_folder
        root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = root / f"{timestamp}-{_safe_task_token(safe_title)}.md"
        target.write_text(f"# {safe_title}\n\n{safe_content}\n", encoding="utf-8")
        return ProviderResult(success=True, output=f"Notiz gespeichert: {target}")

    async def create_calendar_event(self, *, title: str, start_at: str, duration_minutes: int) -> ProviderResult:
        safe_title = str(title or "").strip() or "Jarvis Event"
        try:
            start_dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
        except Exception:
            return ProviderResult(success=False, error="start_at ungueltig.")
        safe_duration = max(5, min(int(duration_minutes), 24 * 60))
        calendar_dir = Path.home() / "Documents" / "JarvisCalendar"
        calendar_dir.mkdir(parents=True, exist_ok=True)
        token = _safe_task_token(safe_title)
        target = calendar_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{token}.ics"
        dt_stamp = start_dt.strftime("%Y%m%dT%H%M%S")
        end_dt = start_dt.timestamp() + safe_duration * 60
        end_label = datetime.fromtimestamp(end_dt, tz=start_dt.tzinfo).strftime("%Y%m%dT%H%M%S")
        content = (
            "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\n"
            f"DTSTART:{dt_stamp}\nDTEND:{end_label}\nSUMMARY:{safe_title}\n"
            "END:VEVENT\nEND:VCALENDAR\n"
        )
        target.write_text(content, encoding="utf-8")
        return ProviderResult(success=True, output=f"Kalenderdatei erstellt: {target}")

    async def create_reminder(self, *, title: str, due_at: str | None = None) -> ProviderResult:
        safe_title = str(title or "").strip() or "Jarvis Reminder"
        due = str(due_at or "").strip() or "ohne Faelligkeit"
        notes_dir = Path.home() / "Documents" / "JarvisReminders"
        notes_dir.mkdir(parents=True, exist_ok=True)
        target = notes_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_safe_task_token(safe_title)}.txt"
        target.write_text(f"{safe_title}\nDue: {due}\n", encoding="utf-8")
        return ProviderResult(success=True, output=f"Reminder gespeichert: {target}")
