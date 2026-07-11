"""
Google Workspace MCP 서버 — Claude Code에서 Sheets/Docs/Drive 직접 조작.
등록: ~/.claude/settings.json mcpServers.google
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from tools.google import dispatch

mcp = FastMCP("google")


@mcp.tool()
def sheets_read(spreadsheet_id: str, range: str) -> dict:
    """Google Sheets 셀/범위 읽기. range 예: 'Sheet1!A1:D10'"""
    return dispatch("sheets_read", {"spreadsheet_id": spreadsheet_id, "range": range})


@mcp.tool()
def sheets_get_all(spreadsheet_id: str, sheet: str = "") -> dict:
    """시트 전체 데이터 조회. 헤더 기반 records 형태로 반환."""
    return dispatch("sheets_get_all", {"spreadsheet_id": spreadsheet_id, "sheet": sheet})


@mcp.tool()
def sheets_write(spreadsheet_id: str, range: str, values: list) -> dict:
    """셀/범위 쓰기. values: 2D 배열 [['값1', '값2']]"""
    return dispatch("sheets_write", {"spreadsheet_id": spreadsheet_id, "range": range, "values": values})


@mcp.tool()
def sheets_append(spreadsheet_id: str, sheet: str, values: list) -> dict:
    """시트 마지막에 행 추가. values: [['col1', 'col2', ...]]"""
    return dispatch("sheets_append", {"spreadsheet_id": spreadsheet_id, "sheet": sheet, "values": values})


@mcp.tool()
def sheets_list_sheets(spreadsheet_id: str) -> dict:
    """스프레드시트의 시트 목록 조회."""
    return dispatch("sheets_list_sheets", {"spreadsheet_id": spreadsheet_id})


@mcp.tool()
def sheets_create(title: str, share_with: str = "") -> dict:
    """새 스프레드시트 생성. share_with: 공유할 이메일 (선택)."""
    return dispatch("sheets_create", {"title": title, "share_with": share_with})


@mcp.tool()
def docs_read(document_id: str) -> dict:
    """Google 문서 내용 읽기."""
    return dispatch("docs_read", {"document_id": document_id})


@mcp.tool()
def docs_append(document_id: str, text: str) -> dict:
    """Google 문서 끝에 텍스트 추가."""
    return dispatch("docs_append", {"document_id": document_id, "text": text})


@mcp.tool()
def drive_search(query: str, file_type: str = "") -> dict:
    """Drive 파일 검색. file_type: spreadsheet|document|folder"""
    return dispatch("drive_search", {"query": query, "file_type": file_type})


@mcp.tool()
def drive_list_recent(file_type: str = "spreadsheet", limit: int = 10) -> dict:
    """최근 수정된 Drive 파일 목록."""
    return dispatch("drive_list_recent", {"file_type": file_type, "limit": limit})


if __name__ == "__main__":
    mcp.run()
