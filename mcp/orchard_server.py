#!/usr/bin/env python3
"""
Orchard MCP Server
Apple 앱(캘린더·리마인더·날씨·노트·메시지·연락처·음악·위치)을
MCP 도구로 노출. Claude Code에서 직접 사용 가능.
"""
import json
import subprocess
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

ORCHARD = "/usr/local/bin/orchard"

mcp = FastMCP("orchard")


def _run(args: list[str]) -> dict:
    """orchard CLI 실행 후 --json 결과를 파싱해 반환."""
    cmd = [ORCHARD] + args + ["--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return {"error": result.stderr.strip() or "orchard 실행 실패"}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"text": result.stdout.strip()}

    # orchard --json 결과는 {"output": "...", "success": bool} 형태
    # output 안의 중첩 JSON을 추출
    if not (isinstance(data, dict) and "output" in data):
        return data

    raw = data["output"]

    # 1) output 전체를 JSON으로 시도
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2) 첫 줄(설명 텍스트 e.g. "Found 9 calendars:") 제거 후 나머지 파싱
    parts = raw.split("\n", 1)
    if len(parts) == 2:
        try:
            return json.loads(parts[1])
        except json.JSONDecodeError:
            pass

    return {"text": raw}


# ── 캘린더 ────────────────────────────────────────────────────────────────────

@mcp.tool()
def calendar_list_calendars() -> dict:
    """등록된 캘린더 목록을 반환합니다."""
    return _run(["calendar", "info", "--type", "calendars"])


@mcp.tool()
def calendar_list_events(
    from_date: str = "",
    to_date: str = "",
) -> dict:
    """
    캘린더 일정을 조회합니다.
    from_date / to_date: ISO 8601 날짜 (예: 2026-06-19). 생략 시 오늘~7일 후.
    """
    if not from_date:
        from_date = date.today().isoformat()
    if not to_date:
        to_date = (date.today() + timedelta(days=7)).isoformat()
    return _run(["calendar", "info", "--type", "events", "--from", from_date, "--to", to_date])


@mcp.tool()
def calendar_create_event(
    title: str,
    start: str,
    end: str,
    calendar_id: str = "",
    location: str = "",
    notes: str = "",
) -> dict:
    """
    캘린더 일정을 생성합니다.
    start / end: ISO 8601 형식 (예: 2026-06-20T14:00:00).
    calendar_id: 대상 캘린더 ID (미입력 시 기본 캘린더).
    """
    args = ["calendar", "create", "--title", title, "--start", start, "--end", end]
    if calendar_id:
        args += ["--calendar-id", calendar_id]
    if location:
        args += ["--location", location]
    if notes:
        args += ["--notes", notes]
    return _run(args)


# ── 리마인더 ──────────────────────────────────────────────────────────────────

@mcp.tool()
def reminder_list(status: str = "incomplete") -> dict:
    """
    리마인더를 조회합니다.
    status: incomplete | complete | all (기본: incomplete)
    """
    return _run(["reminder", "info", "--type", "reminders", "--status", status])


@mcp.tool()
def reminder_create(
    title: str,
    due_date: str = "",
    notes: str = "",
    list_id: str = "",
) -> dict:
    """
    리마인더를 생성합니다.
    due_date: ISO 8601 (예: 2026-06-20T09:00:00). 생략 가능.
    """
    args = ["reminder", "create", "--title", title]
    if due_date:
        args += ["--due-date", due_date]
    if notes:
        args += ["--notes", notes]
    if list_id:
        args += ["--list-id", list_id]
    return _run(args)


# ── 날씨 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def weather_get(
    location: str = "Seoul",
    granularity: str = "daily",
    start_date: str = "",
    end_date: str = "",
) -> dict:
    """
    날씨 정보를 가져옵니다.
    location: 도시명 (예: Seoul, Tokyo, New York).
    granularity: daily | hourly (기본: daily).
    start_date / end_date: ISO 8601 날짜 (생략 시 오늘~7일).
    """
    args = ["weather", "get", "--location", location, "--granularity", granularity]
    if start_date:
        args += ["--start-date", start_date]
    if end_date:
        args += ["--end-date", end_date]
    return _run(args)


# ── 노트 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def notes_search(query: str, limit: int = 10) -> dict:
    """Apple Notes에서 노트를 검색합니다."""
    return _run(["notes", "search", "--query", query, "--limit", str(limit)])


@mcp.tool()
def notes_get(note_id: str) -> dict:
    """노트 내용을 가져옵니다. note_id는 notes_search로 얻을 수 있습니다."""
    return _run(["notes", "get", "--id", note_id])


@mcp.tool()
def notes_create(title: str, body: str, folder: str = "") -> dict:
    """Apple Notes에 새 노트를 생성합니다."""
    args = ["notes", "create", "--title", title, "--body", body]
    if folder:
        args += ["--folder", folder]
    return _run(args)


# ── 메시지 ────────────────────────────────────────────────────────────────────

@mcp.tool()
def messages_list_chats(limit: int = 20) -> dict:
    """최근 메시지 대화 목록을 가져옵니다."""
    return _run(["messages", "read", "--type", "chats", "--limit", str(limit)])


@mcp.tool()
def messages_read(chat: str, limit: int = 20) -> dict:
    """
    특정 대화의 메시지를 읽습니다.
    chat: 전화번호 또는 이메일.
    """
    return _run(["messages", "read", "--type", "messages", "--chat", chat, "--limit", str(limit)])


@mcp.tool()
def messages_send(chat: str, message: str) -> dict:
    """
    iMessage / SMS를 전송합니다.
    chat: 전화번호 또는 이메일.
    """
    return _run(["messages", "send", "--chat", chat, "--message", message])


# ── 연락처 ────────────────────────────────────────────────────────────────────

@mcp.tool()
def contacts_search(query: str, limit: int = 10) -> dict:
    """연락처를 검색합니다."""
    return _run(["contacts", "search", "--query", query, "--limit", str(limit)])


@mcp.tool()
def contacts_details(contact_id: str) -> dict:
    """연락처 상세 정보를 가져옵니다."""
    return _run(["contacts", "details", "--id", contact_id])


# ── 음악 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def music_info() -> dict:
    """현재 재생 중인 음악 정보를 가져옵니다."""
    return _run(["music", "info"])


@mcp.tool()
def music_control(action: str) -> dict:
    """
    음악 재생을 제어합니다.
    action: play | pause | stop | next | previous
    """
    return _run(["music", "control", "--action", action])


@mcp.tool()
def music_play(query: str) -> dict:
    """곡명 또는 아티스트로 음악을 재생합니다."""
    return _run(["music", "play", "--query", query])


# ── 위치 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def location_current() -> dict:
    """현재 위치를 가져옵니다."""
    return _run(["location", "current"])


@mcp.tool()
def location_search(query: str) -> dict:
    """장소를 검색합니다 (예: 스타벅스 강남)."""
    return _run(["location", "search", "--query", query])


@mcp.tool()
def location_route(from_place: str, to_place: str) -> dict:
    """두 지점 간 경로를 계산합니다."""
    return _run(["location", "route", "--from", from_place, "--to", to_place])


if __name__ == "__main__":
    mcp.run()
