#!/usr/bin/env python3
"""
Orchard MCP Server
tools/orchard.py의 dispatch()를 MCP 도구로 노출.
Claude Code에서 직접 사용 가능.
"""
import sys
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta
from tools.orchard import dispatch
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("orchard")

# ── 캘린더 ────────────────────────────────────────────────────────────────────

@mcp.tool()
def calendar_list_calendars() -> dict:
    """등록된 캘린더 목록을 반환합니다."""
    return dispatch("calendar_list_calendars", {})


@mcp.tool()
def calendar_list_events(from_date: str = "", to_date: str = "") -> dict:
    """
    캘린더 일정을 조회합니다.
    from_date / to_date: ISO 8601 날짜 (예: 2026-06-19). 생략 시 오늘~7일 후.
    """
    return dispatch("calendar_list_events", {"from_date": from_date, "to_date": to_date})


@mcp.tool()
def calendar_create_event(
    title: str, start: str, end: str,
    calendar_id: str = "", location: str = "", notes: str = "",
) -> dict:
    """
    캘린더 일정을 생성합니다.
    start / end: ISO 8601 (예: 2026-06-20T14:00:00).
    """
    return dispatch("calendar_create_event", {
        "title": title, "start": start, "end": end,
        "calendar_id": calendar_id, "location": location, "notes": notes,
    })


# ── 리마인더 ──────────────────────────────────────────────────────────────────

@mcp.tool()
def reminder_list(status: str = "incomplete") -> dict:
    """리마인더를 조회합니다. status: incomplete | complete | all"""
    return dispatch("reminder_list", {"status": status})


@mcp.tool()
def reminder_create(title: str, due_date: str = "", notes: str = "", list_id: str = "") -> dict:
    """리마인더를 생성합니다. due_date: ISO 8601 (예: 2026-06-20T09:00:00)."""
    return dispatch("reminder_create", {
        "title": title, "due_date": due_date, "notes": notes, "list_id": list_id,
    })


# ── 날씨 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def weather_get(
    location: str = "Seoul", granularity: str = "daily",
    start_date: str = "", end_date: str = "",
) -> dict:
    """날씨 정보를 가져옵니다. granularity: daily | hourly"""
    return dispatch("weather_get", {
        "location": location, "granularity": granularity,
        "start_date": start_date, "end_date": end_date,
    })


# ── 노트 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def notes_search(query: str, limit: int = 10) -> dict:
    """Apple Notes에서 노트를 검색합니다."""
    return dispatch("notes_search", {"query": query, "limit": limit})


@mcp.tool()
def notes_get(note_id: str) -> dict:
    """노트 내용을 가져옵니다."""
    return dispatch("notes_get", {"note_id": note_id})


@mcp.tool()
def notes_create(title: str, content: str, folder: str = "") -> dict:
    """Apple Notes에 새 노트를 생성합니다. content는 HTML 형식."""
    return dispatch("notes_create", {"title": title, "content": content, "folder": folder})


# ── 메시지 ────────────────────────────────────────────────────────────────────

@mcp.tool()
def messages_list_chats(limit: int = 20) -> dict:
    """최근 메시지 대화 목록을 가져옵니다."""
    return dispatch("messages_list_chats", {"limit": limit})


@mcp.tool()
def messages_read(chat: str, limit: int = 20) -> dict:
    """특정 대화의 메시지를 읽습니다. chat: 전화번호 또는 이메일."""
    return dispatch("messages_read", {"chat": chat, "limit": limit})


@mcp.tool()
def messages_send(chat: str, message: str) -> dict:
    """iMessage / SMS를 전송합니다."""
    return dispatch("messages_send", {"chat": chat, "message": message})


# ── 연락처 ────────────────────────────────────────────────────────────────────

@mcp.tool()
def contacts_search(query: str, limit: int = 10) -> dict:
    """연락처를 검색합니다."""
    return dispatch("contacts_search", {"query": query, "limit": limit})


@mcp.tool()
def contacts_details(contact_id: str) -> dict:
    """연락처 상세 정보를 가져옵니다."""
    return dispatch("contacts_details", {"contact_id": contact_id})


# ── 음악 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def music_info() -> dict:
    """현재 재생 중인 음악 정보를 가져옵니다."""
    return dispatch("music_info", {})


@mcp.tool()
def music_control(action: str) -> dict:
    """음악 재생을 제어합니다. action: play | pause | stop | next | previous"""
    return dispatch("music_control", {"action": action})


@mcp.tool()
def music_play(query: str) -> dict:
    """곡명 또는 아티스트로 음악을 재생합니다."""
    return dispatch("music_play", {"query": query})


# ── 위치 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def location_current() -> dict:
    """현재 위치를 가져옵니다."""
    return dispatch("location_current", {})


@mcp.tool()
def location_search(query: str) -> dict:
    """장소를 검색합니다 (예: 스타벅스 강남)."""
    return dispatch("location_search", {"query": query})


@mcp.tool()
def location_route(from_place: str, to_place: str) -> dict:
    """두 지점 간 경로를 계산합니다."""
    return dispatch("location_route", {"from_place": from_place, "to_place": to_place})


if __name__ == "__main__":
    mcp.run()
