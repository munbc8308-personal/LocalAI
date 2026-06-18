"""
orchard CLI 래퍼 — LocalAI 하네스와 MCP 서버가 공유하는 실행 레이어.
"""
import json
import subprocess
from datetime import date, timedelta

ORCHARD = "/usr/local/bin/orchard"


def run(args: list[str]) -> dict:
    """orchard CLI 실행 후 --json 결과를 파싱해 반환."""
    cmd = [ORCHARD] + args + ["--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return {"error": result.stderr.strip() or "orchard 실행 실패"}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"text": result.stdout.strip()}

    if not (isinstance(data, dict) and "output" in data):
        return data

    raw = data["output"]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    parts = raw.split("\n", 1)
    if len(parts) == 2:
        try:
            return json.loads(parts[1])
        except json.JSONDecodeError:
            pass
    return {"text": raw}


def dispatch(tool: str, args: dict) -> dict:
    """tool 이름 + args dict → orchard 실행 후 결과 반환."""
    today = date.today().isoformat()
    week_later = (date.today() + timedelta(days=7)).isoformat()

    match tool:
        # ── 캘린더 ──────────────────────────────────────────────────────────
        case "calendar_list_calendars":
            return run(["calendar", "info", "--type", "calendars"])

        case "calendar_list_events":
            return run([
                "calendar", "info", "--type", "events",
                "--from", args.get("from_date", today),
                "--to",   args.get("to_date",   week_later),
            ])

        case "calendar_create_event":
            cmd = [
                "calendar", "create",
                "--title", args["title"],
                "--start", args["start"],
                "--end",   args["end"],
            ]
            if args.get("calendar_id"): cmd += ["--calendar-id", args["calendar_id"]]
            if args.get("location"):    cmd += ["--location",    args["location"]]
            if args.get("notes"):       cmd += ["--notes",       args["notes"]]
            return run(cmd)

        # ── 리마인더 ────────────────────────────────────────────────────────
        case "reminder_list":
            return run([
                "reminder", "info", "--type", "reminders",
                "--status", args.get("status", "incomplete"),
            ])

        case "reminder_create":
            cmd = ["reminder", "create", "--title", args["title"]]
            if args.get("due_date"): cmd += ["--due-date", args["due_date"]]
            if args.get("notes"):    cmd += ["--notes",    args["notes"]]
            if args.get("list_id"):  cmd += ["--list-id",  args["list_id"]]
            return run(cmd)

        # ── 날씨 ────────────────────────────────────────────────────────────
        case "weather_get":
            cmd = [
                "weather", "get",
                "--location",    args.get("location", "Seoul"),
                "--granularity", args.get("granularity", "daily"),
            ]
            if args.get("start_date"): cmd += ["--start-date", args["start_date"]]
            if args.get("end_date"):   cmd += ["--end-date",   args["end_date"]]
            return run(cmd)

        # ── 노트 ────────────────────────────────────────────────────────────
        case "notes_search":
            return run([
                "notes", "search",
                "--query", args["query"],
                "--limit", str(args.get("limit", 10)),
            ])

        case "notes_get":
            return run(["notes", "get", "--id", args["note_id"]])

        case "notes_create":
            cmd = ["notes", "create", "--content", args["content"]]
            if args.get("title"):  cmd += ["--title",  args["title"]]
            if args.get("folder"): cmd += ["--folder", args["folder"]]
            return run(cmd)

        # ── 메시지 ──────────────────────────────────────────────────────────
        case "messages_list_chats":
            return run([
                "messages", "read", "--type", "chats",
                "--limit", str(args.get("limit", 20)),
            ])

        case "messages_read":
            return run([
                "messages", "read", "--type", "messages",
                "--chat",  args["chat"],
                "--limit", str(args.get("limit", 20)),
            ])

        case "messages_send":
            return run([
                "messages", "send",
                "--chat",    args["chat"],
                "--message", args["message"],
            ])

        # ── 연락처 ──────────────────────────────────────────────────────────
        case "contacts_search":
            return run([
                "contacts", "search",
                "--query", args["query"],
                "--limit", str(args.get("limit", 10)),
            ])

        case "contacts_details":
            return run(["contacts", "details", "--id", args["contact_id"]])

        # ── 음악 ────────────────────────────────────────────────────────────
        case "music_info":
            return run(["music", "info"])

        case "music_control":
            return run(["music", "control", "--action", args["action"]])

        case "music_play":
            return run(["music", "play", "--query", args["query"]])

        # ── 위치 ────────────────────────────────────────────────────────────
        case "location_current":
            return run(["location", "current"])

        case "location_search":
            return run(["location", "search", "--query", args["query"]])

        case "location_route":
            return run([
                "location", "route",
                "--from", args["from_place"],
                "--to",   args["to_place"],
            ])

        case _:
            return {"error": f"알 수 없는 도구: {tool}"}
