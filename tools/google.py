"""
Google Workspace 통합 — Sheets / Docs / Drive
Service Account 인증 방식.
자격증명: GOOGLE_CREDENTIALS_PATH (기본: ./data/google_credentials.json)
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

_MIME = {
    "spreadsheet": "application/vnd.google-apps.spreadsheet",
    "document": "application/vnd.google-apps.document",
    "folder": "application/vnd.google-apps.folder",
}


def _creds_path() -> str:
    from core.config import get_settings
    path = get_settings().google_credentials_path
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Google 자격증명 파일 없음: {path}\n"
            "Google Cloud Console → 서비스 계정 키 JSON을 해당 경로에 저장하세요."
        )
    return path


def _credentials():
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_file(
        _creds_path(), scopes=_SCOPES
    )


def _gc():
    import gspread
    return gspread.authorize(_credentials())


def _docs_svc():
    from googleapiclient.discovery import build
    return build("docs", "v1", credentials=_credentials(), cache_discovery=False)


def _drive_svc():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_credentials(), cache_discovery=False)


def _extract_id(url_or_id: str) -> str:
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", url_or_id)
    return m.group(1) if m else url_or_id


def _parse_range(range_str: str):
    """'Sheet1!A1:D10' → (sheet_name, cell_range) or (None, range_str)."""
    if "!" in range_str:
        sheet, cells = range_str.split("!", 1)
        return sheet, cells
    return None, range_str


# ── Google Sheets ─────────────────────────────────────────────────────────────

def sheets_read(spreadsheet_id: str, range: str) -> dict:
    """셀/범위 읽기. range 예: 'Sheet1!A1:D10' 또는 'A1:D10'."""
    sid = _extract_id(spreadsheet_id)
    sh = _gc().open_by_key(sid)
    sheet_name, cells = _parse_range(range)
    ws = sh.worksheet(sheet_name) if sheet_name else sh.sheet1
    values = ws.get(cells)
    return {"range": range, "rows": len(values), "values": values}


def sheets_get_all(spreadsheet_id: str, sheet: str = "") -> dict:
    """시트 전체 데이터를 헤더-레코드 형태로 반환."""
    sid = _extract_id(spreadsheet_id)
    sh = _gc().open_by_key(sid)
    ws = sh.worksheet(sheet) if sheet else sh.sheet1
    records = ws.get_all_records()
    raw = ws.get_all_values()
    return {
        "sheet": ws.title,
        "rows": len(raw),
        "columns": len(raw[0]) if raw else 0,
        "records": records,
    }


def sheets_write(spreadsheet_id: str, range: str, values: list) -> dict:
    """셀/범위 쓰기. values: 2D 배열 [['값1', '값2'], ...]."""
    sid = _extract_id(spreadsheet_id)
    sh = _gc().open_by_key(sid)
    sheet_name, cells = _parse_range(range)
    ws = sh.worksheet(sheet_name) if sheet_name else sh.sheet1
    ws.update(cells, values)
    return {"range": range, "updated_rows": len(values)}


def sheets_append(spreadsheet_id: str, sheet: str, values: list) -> dict:
    """시트 마지막에 행 추가. values: [['col1', 'col2', ...], ...]."""
    sid = _extract_id(spreadsheet_id)
    sh = _gc().open_by_key(sid)
    ws = sh.worksheet(sheet) if sheet else sh.sheet1
    ws.append_rows(values, value_input_option="USER_ENTERED")
    return {"sheet": ws.title, "appended_rows": len(values)}


def sheets_list_sheets(spreadsheet_id: str) -> dict:
    """스프레드시트의 시트 목록."""
    sid = _extract_id(spreadsheet_id)
    sh = _gc().open_by_key(sid)
    sheets = [
        {"title": ws.title, "sheet_id": ws.id, "rows": ws.row_count, "cols": ws.col_count}
        for ws in sh.worksheets()
    ]
    return {"spreadsheet_id": sid, "title": sh.title, "sheets": sheets}


def sheets_create(title: str, share_with: str = "") -> dict:
    """새 스프레드시트 생성. share_with: 공유할 이메일 (선택)."""
    sh = _gc().create(title)
    if share_with:
        sh.share(share_with, perm_type="user", role="writer")
    return {"spreadsheet_id": sh.id, "title": sh.title, "url": sh.url}


# ── Google Docs ───────────────────────────────────────────────────────────────

def docs_read(document_id: str) -> dict:
    """Google 문서 내용 읽기."""
    did = _extract_id(document_id)
    svc = _docs_svc()
    doc = svc.documents().get(documentId=did).execute()

    text_parts = []
    for elem in doc.get("body", {}).get("content", []):
        para = elem.get("paragraph")
        if para:
            for run in para.get("elements", []):
                tr = run.get("textRun")
                if tr:
                    text_parts.append(tr.get("content", ""))

    return {
        "document_id": did,
        "title": doc.get("title", ""),
        "content": "".join(text_parts).strip(),
    }


def docs_append(document_id: str, text: str) -> dict:
    """문서 끝에 텍스트 추가."""
    did = _extract_id(document_id)
    svc = _docs_svc()
    doc = svc.documents().get(documentId=did).execute()
    content = doc.get("body", {}).get("content", [])
    end_index = content[-1].get("endIndex", 2) - 1

    svc.documents().batchUpdate(
        documentId=did,
        body={"requests": [{"insertText": {"location": {"index": end_index}, "text": "\n" + text}}]},
    ).execute()
    return {"document_id": did, "appended_chars": len(text)}


# ── Google Drive ──────────────────────────────────────────────────────────────

def drive_search(query: str, file_type: str = "") -> dict:
    """Drive 파일 이름 검색. file_type: spreadsheet|document|folder."""
    safe = query.replace("'", "\\'")
    q = f"name contains '{safe}' and trashed=false"
    if file_type in _MIME:
        q += f" and mimeType='{_MIME[file_type]}'"

    results = _drive_svc().files().list(
        q=q,
        fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        orderBy="modifiedTime desc",
        pageSize=10,
    ).execute()
    files = results.get("files", [])
    return {"query": query, "count": len(files), "files": files}


def drive_list_recent(file_type: str = "spreadsheet", limit: int = 10) -> dict:
    """최근 수정된 파일 목록."""
    q = "trashed=false"
    if file_type in _MIME:
        q += f" and mimeType='{_MIME[file_type]}'"

    results = _drive_svc().files().list(
        q=q,
        fields="files(id, name, mimeType, modifiedTime, webViewLink)",
        orderBy="modifiedTime desc",
        pageSize=limit,
    ).execute()
    files = results.get("files", [])
    return {"file_type": file_type, "count": len(files), "files": files}


# ── Dispatch ──────────────────────────────────────────────────────────────────

TOOL_NAMES = {
    "sheets_read", "sheets_get_all", "sheets_write", "sheets_append",
    "sheets_list_sheets", "sheets_create",
    "docs_read", "docs_append",
    "drive_search", "drive_list_recent",
}

_FN = {
    "sheets_read": sheets_read,
    "sheets_get_all": sheets_get_all,
    "sheets_write": sheets_write,
    "sheets_append": sheets_append,
    "sheets_list_sheets": sheets_list_sheets,
    "sheets_create": sheets_create,
    "docs_read": docs_read,
    "docs_append": docs_append,
    "drive_search": drive_search,
    "drive_list_recent": drive_list_recent,
}


def dispatch(tool: str, args: dict) -> dict:
    fn = _FN.get(tool)
    if not fn:
        return {"error": f"알 수 없는 Google 도구: {tool}"}
    try:
        return fn(**args)
    except Exception as e:
        logger.error(f"[google] {tool} 오류: {e}", exc_info=True)
        return {"error": str(e)}
