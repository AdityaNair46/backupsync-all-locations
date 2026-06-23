# """
# backup_sync_auditor.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scans a Google Chat space for "Daily Backup Sync" completion logs,
# fetches the master location list from MySQL, then writes checkboxes
# to a Google Sheet.

# Setup checklist
# ───────────────
# 1. pip install google-auth google-auth-oauthlib google-api-python-client mysql-connector-python
# 2. Place credentials.json (OAuth 2.0 desktop client) in the same folder.
# 3. Fill in every value under ── CONFIG ──.
# 4. Run once; a browser window will open for OAuth consent and save token.json.
# """

# import os
# import json
# import mysql.connector
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build

# # ══════════════════════════════════════════════════════════════════════
# # ── CONFIG  (edit everything in this block) ──────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# # ── MySQL connection ─────────────────────────────────────────────────
# MYSQL_CONFIG = {
#     "host":     "172.16.1.89",       # e.g. "localhost" or "db.example.com"
#     "port":     3307,
#     "user":     "readonly_user",
#     "password": "Dekhomagr_Pyarse@7758",
#     "database": "masterdb",
# }

# # SQL that returns one column: the location name
# LOCATIONS_QUERY = "select location_name from adit_main where is_active = 1 and Ehr_name = 'Revolution';"

# # ── Google Chat space ────────────────────────────────────────────────
# SPACE_NAME = "spaces/AAQATvSu0go"     # e.g. "spaces/AAQAOQN4H9g"

# # ── Google Sheet ─────────────────────────────────────────────────────
# SPREADSHEET_ID      = "1zLdTRhZc-BP7ZchJnUd0MeG1Djh-aOvdKbuHco2jcpI"
# SHEET_NAME          = "All_loc"
# LOCATIONS_START_ROW = 2                 # row 1 = date headers; locations from row 2

# # ── Target date (YYYY-MM-DD) ─────────────────────────────────────────
# TARGET_DATE = "2026-06-22"

# # ── OAuth scopes ─────────────────────────────────────────────────────
# SCOPES = [
#     "https://www.googleapis.com/auth/chat.messages.readonly",
#     "https://www.googleapis.com/auth/spreadsheets",
# ]

# # ══════════════════════════════════════════════════════════════════════
# # ── Helpers ───────────────────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def clean_name(name: str) -> str:
#     """Normalise a location name for comparison (lowercase, alphanumeric only)."""
#     return "".join(c for c in name.lower() if c.isalnum())


# def index_to_col_letter(idx: int) -> str:
#     """Convert 0-based column index to spreadsheet letter (0→A, 25→Z, 26→AA …)."""
#     result = ""
#     idx += 1
#     while idx:
#         idx, rem = divmod(idx - 1, 26)
#         result = chr(rem + ord("A")) + result
#     return result


# # ══════════════════════════════════════════════════════════════════════
# # ── MySQL: fetch locations ────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def fetch_locations_from_db() -> list[str]:
#     """Return the master list of location names from MySQL."""
#     print("🗄️  Connecting to MySQL …")
#     conn = mysql.connector.connect(**MYSQL_CONFIG)
#     cursor = conn.cursor()
#     cursor.execute(LOCATIONS_QUERY)
#     locations = [row[0].strip() for row in cursor.fetchall() if row[0]]
#     cursor.close()
#     conn.close()
#     print(f"   ✔  Fetched {len(locations)} locations from database.")
#     return locations


# # ══════════════════════════════════════════════════════════════════════
# # ── Google Auth ───────────────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def get_services():
#     """Authenticate and return (chat_service, sheets_service)."""
#     creds = None
#     if os.path.exists("token.json"):
#         creds = Credentials.from_authorized_user_file("token.json", SCOPES)
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
#             creds = flow.run_local_server(port=0)
#         with open("token.json", "w") as fh:
#             fh.write(creds.to_json())
#     chat_service   = build("chat",   "v1", credentials=creds)
#     sheets_service = build("sheets", "v4", credentials=creds)
#     return chat_service, sheets_service


# # ══════════════════════════════════════════════════════════════════════
# # ── Google Chat: scan space ───────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def try_parse_log(raw_text: str) -> dict | None:
#     """Parse a Chat message as a JSON backup log, stripping code fences if needed."""
#     text = raw_text.strip()
#     if text.startswith("```"):
#         lines = text.splitlines()
#         text = "\n".join(lines[1:-1]).strip()
#     try:
#         return json.loads(text)
#     except json.JSONDecodeError:
#         return None


# def scan_space(chat_service, target_date: str) -> set[str]:
#     """
#     Page through all messages in SPACE_NAME, find completed Daily Backup Sync
#     logs for target_date, and return a set of clean location names.
#     """
#     completed: set[str] = set()
#     next_page_token = None
#     page_count = total_msgs = matched_logs = 0

#     print(f"\n🔍 Scanning space: {SPACE_NAME}")
#     print(f"⚠️  Brute-force scan — no API filter applied\n")

#     while True:
#         result = chat_service.spaces().messages().list(
#             parent=SPACE_NAME,
#             pageSize=1000,
#             pageToken=next_page_token,
#         ).execute()

#         messages = result.get("messages", [])
#         page_count  += 1
#         total_msgs  += len(messages)
#         print(f"   📄 Page {page_count}: {len(messages)} messages (total so far: {total_msgs})")

#         for msg in messages:
#             raw = msg.get("text", "")
#             if target_date not in raw:
#                 continue                        # fast pre-filter

#             log = try_parse_log(raw)
#             if not log:
#                 continue
#             if log.get("event") != "Daily Backup Sync":
#                 continue
#             if log.get("timestamp", "")[:10] != target_date:
#                 continue

#             matched_logs += 1
#             location = log.get("location", "").strip()
#             details  = log.get("details", "").lower()

#             if "backup sync completed successfully" in details:
#                 if location:
#                     print(f"   ✅  Completed: {location}")
#                     completed.add(clean_name(location))
#             else:
#                 print(f"   ⚠️   Not completed: {location} — {log.get('details')}")

#         next_page_token = result.get("nextPageToken")
#         if not next_page_token:
#             print(f"\n   ✔  Scan complete. Total: {total_msgs} messages | Matched logs: {matched_logs}")
#             break

#     return completed


# # ══════════════════════════════════════════════════════════════════════
# # ── Google Sheets helpers ─────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def get_sheet_id(sheets_service) -> int:
#     meta = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
#     for sheet in meta["sheets"]:
#         if sheet["properties"]["title"] == SHEET_NAME:
#             return sheet["properties"]["sheetId"]
#     available = [s["properties"]["title"] for s in meta["sheets"]]
#     raise ValueError(f"Tab '{SHEET_NAME}' not found. Available: {available}")


# def read_sheet_data(sheets_service, sheet_id: int) -> list[list[str]]:
#     result = sheets_service.spreadsheets().get(
#         spreadsheetId=SPREADSHEET_ID,
#         includeGridData=True,
#         ranges=[],
#     ).execute()
#     for sheet in result["sheets"]:
#         if sheet["properties"]["sheetId"] == sheet_id:
#             row_data = sheet.get("data", [{}])[0].get("rowData", [])
#             rows = []
#             for row in row_data:
#                 cells = row.get("values", [])
#                 rows.append([
#                     (c.get("formattedValue") or
#                      c.get("effectiveValue", {}).get("stringValue", "") or "")
#                     for c in cells
#                 ])
#             return rows
#     return []


# def expand_sheet_columns(sheets_service, sheet_id: int, required_col_count: int):
#     meta = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
#     for sheet in meta["sheets"]:
#         if sheet["properties"]["sheetId"] == sheet_id:
#             current = sheet["properties"]["gridProperties"]["columnCount"]
#             if required_col_count > current:
#                 new_count = required_col_count + 10
#                 sheets_service.spreadsheets().batchUpdate(
#                     spreadsheetId=SPREADSHEET_ID,
#                     body={"requests": [{
#                         "updateSheetProperties": {
#                             "properties": {
#                                 "sheetId": sheet_id,
#                                 "gridProperties": {"columnCount": new_count},
#                             },
#                             "fields": "gridProperties.columnCount",
#                         }
#                     }]},
#                 ).execute()
#                 print(f"   📐 Expanded columns: {current} → {new_count}")
#             break


# def write_string_cells(sheets_service, sheet_id: int, updates: list[tuple]):
#     """Write (row_0, col_0, value) string tuples via batchUpdate."""
#     requests = [
#         {
#             "updateCells": {
#                 "range": {
#                     "sheetId": sheet_id,
#                     "startRowIndex": r, "endRowIndex": r + 1,
#                     "startColumnIndex": c, "endColumnIndex": c + 1,
#                 },
#                 "rows": [{"values": [{"userEnteredValue": {"stringValue": str(v)}}]}],
#                 "fields": "userEnteredValue",
#             }
#         }
#         for r, c, v in updates
#     ]
#     if requests:
#         sheets_service.spreadsheets().batchUpdate(
#             spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
#         ).execute()


# def write_bool_cells(sheets_service, sheet_id: int, updates: list[tuple]):
#     """Write (row_0, col_0, bool_value) tuples via batchUpdate."""
#     requests = [
#         {
#             "updateCells": {
#                 "range": {
#                     "sheetId": sheet_id,
#                     "startRowIndex": r, "endRowIndex": r + 1,
#                     "startColumnIndex": c, "endColumnIndex": c + 1,
#                 },
#                 "rows": [{"values": [{"userEnteredValue": {"boolValue": v}}]}],
#                 "fields": "userEnteredValue",
#             }
#         }
#         for r, c, v in updates
#     ]
#     if requests:
#         sheets_service.spreadsheets().batchUpdate(
#             spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
#         ).execute()


# def seed_checkboxes(sheets_service, sheet_id: int, col_idx: int, row_indices: list[int]):
#     requests = [
#         {
#             "setDataValidation": {
#                 "range": {
#                     "sheetId": sheet_id,
#                     "startRowIndex": r, "endRowIndex": r + 1,
#                     "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1,
#                 },
#                 "rule": {"condition": {"type": "BOOLEAN"}, "strict": True, "showCustomUi": True},
#             }
#         }
#         for r in row_indices
#     ]
#     if requests:
#         sheets_service.spreadsheets().batchUpdate(
#             spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
#         ).execute()
#         print(f"   ☑️  Seeded {len(requests)} checkboxes")


# def ensure_sheet_structure(sheets_service, master_locations: list[str], target_date: str):
#     """
#     • Reads column A to find existing locations; appends any missing ones from DB.
#     • Finds or creates the date column header.
#     Returns (sheet_id, date_col_idx, location_row_map {clean_name: row_0based})
#     """
#     sheet_id = get_sheet_id(sheets_service)
#     rows     = read_sheet_data(sheets_service, sheet_id)

#     # Build location → row map from column A
#     location_row_map: dict[str, int] = {}
#     existing_names: list[str] = []
#     for r_idx in range(LOCATIONS_START_ROW - 1, len(rows)):
#         cell = (rows[r_idx][0].strip()) if rows[r_idx] else ""
#         if cell:
#             existing_names.append(cell)
#             location_row_map[clean_name(cell)] = r_idx

#     # Append locations that are in MySQL but not yet in the sheet
#     missing = [loc for loc in master_locations if clean_name(loc) not in location_row_map]
#     if missing:
#         next_row = (LOCATIONS_START_ROW - 1) + len(existing_names)
#         write_string_cells(sheets_service, sheet_id,
#                            [(next_row + i, 0, loc) for i, loc in enumerate(missing)])
#         for i, loc in enumerate(missing):
#             location_row_map[clean_name(loc)] = next_row + i
#         print(f"   📝 Added {len(missing)} new locations from DB to column A")

#     # Find or create the date column
#     header_row = rows[0] if rows else []
#     date_col_idx = None
#     last_occupied = 0
#     for c_idx, cell in enumerate(header_row):
#         if cell.strip() == target_date:
#             date_col_idx = c_idx
#             break
#         if cell.strip():
#             last_occupied = c_idx

#     if date_col_idx is None:
#         date_col_idx = max(last_occupied + 1, 1)
#         expand_sheet_columns(sheets_service, sheet_id, date_col_idx + 1)
#         write_string_cells(sheets_service, sheet_id, [(0, date_col_idx, target_date)])
#         print(f"   📅 Added date header '{target_date}' in column {index_to_col_letter(date_col_idx)}")

#     return sheet_id, date_col_idx, location_row_map


# # ══════════════════════════════════════════════════════════════════════
# # ── Main ──────────────────────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def main():
#     try:
#         # 1. Fetch location master list from MySQL
#         master_locations = fetch_locations_from_db()
#         if not master_locations:
#             print("🛑 No locations returned from DB. Check your query and connection.")
#             return

#         # 2. Authenticate Google services
#         chat_service, sheets_service = get_services()

#         # 3. Scan the Chat space
#         print(f"\n{'='*55}")
#         print(f"📡 SCANNING SPACE FOR: {TARGET_DATE}")
#         print(f"{'='*55}")

#         completed_locations = scan_space(chat_service, TARGET_DATE)

#         # 4. Console summary — compare Chat results against DB locations
#         final_completed  = [loc for loc in master_locations if clean_name(loc) in completed_locations]
#         final_incomplete = [loc for loc in master_locations if clean_name(loc) not in completed_locations]

#         print(f"\n{'='*55}")
#         print(f"📊 BACKUP AUDIT SUMMARY — {TARGET_DATE}")
#         print(f"{'='*55}")
#         print(f"\n✅ COMPLETED ({len(final_completed)}):")
#         for loc in sorted(final_completed):
#             print(f"   • {loc}")
#         print(f"\n❌ INCOMPLETE ({len(final_incomplete)}):")
#         for loc in sorted(final_incomplete):
#             print(f"   • {loc}")

#         # 5. Update Google Sheet
#         print(f"\n📊 Updating Google Sheet …")
#         sheet_id, date_col_idx, location_row_map = ensure_sheet_structure(
#             sheets_service, master_locations, TARGET_DATE
#         )

#         seed_checkboxes(sheets_service, sheet_id, date_col_idx,
#                         list(location_row_map.values()))

#         bool_updates = [
#             (row_0, date_col_idx, clean_loc in completed_locations)
#             for clean_loc, row_0 in location_row_map.items()
#         ]
#         write_bool_cells(sheets_service, sheet_id, bool_updates)

#         ticked = sum(1 for _, _, v in bool_updates if v)
#         print(f"   ✅ {ticked} checked / {len(bool_updates) - ticked} unchecked")
#         print(f"\n🎉 Done! https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")

#     except Exception as exc:
#         print(f"🛑 Error: {exc}")
#         import traceback
#         traceback.print_exc()


# if __name__ == "__main__":
#     main()


# """
# backup_sync_auditor.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scans a Google Chat space for "Daily Backup Sync" completion logs,
# fetches the master location list from MySQL, then writes checkboxes
# to a Google Sheet.

# Setup checklist
# ───────────────
# 1. pip install google-auth google-auth-oauthlib google-api-python-client mysql-connector-python
# 2. Place credentials.json (OAuth 2.0 desktop client) in the same folder.
# 3. Fill in every value under ── CONFIG ──.
# 4. Run once; a browser window will open for OAuth consent and save token.json.
# """

# import os
# import json
# import csv
# import mysql.connector
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build

# # ══════════════════════════════════════════════════════════════════════
# # ── CONFIG  (edit everything in this block) ──────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# # ── MySQL connection ─────────────────────────────────────────────────
# MYSQL_CONFIG = {
#     "host":     "your-mysql-host",       # e.g. "localhost" or "db.example.com"
#     "port":     3306,
#     "user":     "your-db-user",
#     "password": "your-db-password",
#     "database": "your-database-name",
# }

# # SQL that returns one column: the location name
# LOCATIONS_QUERY = "SELECT name FROM locations ORDER BY name;"

# # ── Google Chat space ────────────────────────────────────────────────
# SPACE_NAME = "spaces/YOUR_SPACE_ID"     # e.g. "spaces/AAQAOQN4H9g"

# # ── Google Sheet ─────────────────────────────────────────────────────
# SPREADSHEET_ID      = "your-spreadsheet-id"
# SHEET_NAME          = "BackupAudit"
# LOCATIONS_START_ROW = 2                 # row 1 = date headers; locations from row 2

# # ── Target date (YYYY-MM-DD) ─────────────────────────────────────────
# TARGET_DATE = "2026-06-22"

# # ── OAuth scopes ─────────────────────────────────────────────────────
# SCOPES = [
#     "https://www.googleapis.com/auth/chat.messages.readonly",
#     "https://www.googleapis.com/auth/spreadsheets",
# ]

# # ══════════════════════════════════════════════════════════════════════
# # ── Helpers ───────────────────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def clean_name(name: str) -> str:
#     """Normalise a location name for comparison (lowercase, alphanumeric only)."""
#     return "".join(c for c in name.lower() if c.isalnum())


# def index_to_col_letter(idx: int) -> str:
#     """Convert 0-based column index to spreadsheet letter (0→A, 25→Z, 26→AA …)."""
#     result = ""
#     idx += 1
#     while idx:
#         idx, rem = divmod(idx - 1, 26)
#         result = chr(rem + ord("A")) + result
#     return result


# # ══════════════════════════════════════════════════════════════════════
# # ── MySQL: fetch locations ────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def fetch_locations_from_db() -> list[str]:
#     """Return the master list of location names from MySQL."""
#     print("🗄️  Connecting to MySQL …")
#     conn = mysql.connector.connect(**MYSQL_CONFIG)
#     cursor = conn.cursor()
#     cursor.execute(LOCATIONS_QUERY)
#     locations = [row[0].strip() for row in cursor.fetchall() if row[0]]
#     cursor.close()
#     conn.close()
#     print(f"   ✔  Fetched {len(locations)} locations from database.")
#     return locations


# # ══════════════════════════════════════════════════════════════════════
# # ── Google Auth ───────────────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def get_services():
#     """Authenticate and return (chat_service, sheets_service)."""
#     creds = None
#     if os.path.exists("token.json"):
#         creds = Credentials.from_authorized_user_file("token.json", SCOPES)
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
#             creds = flow.run_local_server(port=0)
#         with open("token.json", "w") as fh:
#             fh.write(creds.to_json())
#     chat_service   = build("chat",   "v1", credentials=creds)
#     sheets_service = build("sheets", "v4", credentials=creds)
#     return chat_service, sheets_service


# # ══════════════════════════════════════════════════════════════════════
# # ── Google Chat: scan space ───────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def try_parse_log(raw_text: str) -> dict | None:
#     """Parse a Chat message as a JSON backup log, stripping code fences if needed."""
#     text = raw_text.strip()
#     if text.startswith("```"):
#         lines = text.splitlines()
#         text = "\n".join(lines[1:-1]).strip()
#     try:
#         return json.loads(text)
#     except json.JSONDecodeError:
#         return None


# def scan_space(chat_service, target_date: str) -> set[str]:
#     """
#     Page through all messages in SPACE_NAME, find completed Daily Backup Sync
#     logs for target_date, and return a set of clean location names.
#     """
#     completed: set[str] = set()
#     next_page_token = None
#     page_count = total_msgs = matched_logs = 0

#     print(f"\n🔍 Scanning space: {SPACE_NAME}")
#     print(f"⚠️  Brute-force scan — no API filter applied\n")

#     while True:
#         result = chat_service.spaces().messages().list(
#             parent=SPACE_NAME,
#             pageSize=1000,
#             pageToken=next_page_token,
#         ).execute()

#         messages = result.get("messages", [])
#         page_count  += 1
#         total_msgs  += len(messages)
#         print(f"   📄 Page {page_count}: {len(messages)} messages (total so far: {total_msgs})")

#         for msg in messages:
#             raw = msg.get("text", "")
#             if target_date not in raw:
#                 continue                        # fast pre-filter

#             log = try_parse_log(raw)
#             if not log:
#                 continue
#             if log.get("event") != "Daily Backup Sync":
#                 continue
#             if log.get("timestamp", "")[:10] != target_date:
#                 continue

#             matched_logs += 1
#             location = log.get("location", "").strip()
#             details  = log.get("details", "").lower()

#             if "backup sync completed successfully" in details:
#                 if location:
#                     print(f"   ✅  Completed: {location}")
#                     completed.add(clean_name(location))
#             else:
#                 print(f"   ⚠️   Not completed: {location} — {log.get('details')}")

#         next_page_token = result.get("nextPageToken")
#         if not next_page_token:
#             print(f"\n   ✔  Scan complete. Total: {total_msgs} messages | Matched logs: {matched_logs}")
#             break

#     return completed


# # ══════════════════════════════════════════════════════════════════════
# # ── Google Sheets helpers ─────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def get_sheet_id(sheets_service) -> int:
#     meta = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
#     for sheet in meta["sheets"]:
#         if sheet["properties"]["title"] == SHEET_NAME:
#             return sheet["properties"]["sheetId"]
#     available = [s["properties"]["title"] for s in meta["sheets"]]
#     raise ValueError(f"Tab '{SHEET_NAME}' not found. Available: {available}")


# def read_sheet_data(sheets_service, sheet_id: int) -> list[list[str]]:
#     result = sheets_service.spreadsheets().get(
#         spreadsheetId=SPREADSHEET_ID,
#         includeGridData=True,
#         ranges=[],
#     ).execute()
#     for sheet in result["sheets"]:
#         if sheet["properties"]["sheetId"] == sheet_id:
#             row_data = sheet.get("data", [{}])[0].get("rowData", [])
#             rows = []
#             for row in row_data:
#                 cells = row.get("values", [])
#                 rows.append([
#                     (c.get("formattedValue") or
#                      c.get("effectiveValue", {}).get("stringValue", "") or "")
#                     for c in cells
#                 ])
#             return rows
#     return []


# def expand_sheet_columns(sheets_service, sheet_id: int, required_col_count: int):
#     meta = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
#     for sheet in meta["sheets"]:
#         if sheet["properties"]["sheetId"] == sheet_id:
#             current = sheet["properties"]["gridProperties"]["columnCount"]
#             if required_col_count > current:
#                 new_count = required_col_count + 10
#                 sheets_service.spreadsheets().batchUpdate(
#                     spreadsheetId=SPREADSHEET_ID,
#                     body={"requests": [{
#                         "updateSheetProperties": {
#                             "properties": {
#                                 "sheetId": sheet_id,
#                                 "gridProperties": {"columnCount": new_count},
#                             },
#                             "fields": "gridProperties.columnCount",
#                         }
#                     }]},
#                 ).execute()
#                 print(f"   📐 Expanded columns: {current} → {new_count}")
#             break


# def write_string_cells(sheets_service, sheet_id: int, updates: list[tuple]):
#     """Write (row_0, col_0, value) string tuples via batchUpdate."""
#     requests = [
#         {
#             "updateCells": {
#                 "range": {
#                     "sheetId": sheet_id,
#                     "startRowIndex": r, "endRowIndex": r + 1,
#                     "startColumnIndex": c, "endColumnIndex": c + 1,
#                 },
#                 "rows": [{"values": [{"userEnteredValue": {"stringValue": str(v)}}]}],
#                 "fields": "userEnteredValue",
#             }
#         }
#         for r, c, v in updates
#     ]
#     if requests:
#         sheets_service.spreadsheets().batchUpdate(
#             spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
#         ).execute()


# def write_bool_cells(sheets_service, sheet_id: int, updates: list[tuple]):
#     """Write (row_0, col_0, bool_value) tuples via batchUpdate."""
#     requests = [
#         {
#             "updateCells": {
#                 "range": {
#                     "sheetId": sheet_id,
#                     "startRowIndex": r, "endRowIndex": r + 1,
#                     "startColumnIndex": c, "endColumnIndex": c + 1,
#                 },
#                 "rows": [{"values": [{"userEnteredValue": {"boolValue": v}}]}],
#                 "fields": "userEnteredValue",
#             }
#         }
#         for r, c, v in updates
#     ]
#     if requests:
#         sheets_service.spreadsheets().batchUpdate(
#             spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
#         ).execute()


# def seed_checkboxes(sheets_service, sheet_id: int, col_idx: int, row_indices: list[int]):
#     requests = [
#         {
#             "setDataValidation": {
#                 "range": {
#                     "sheetId": sheet_id,
#                     "startRowIndex": r, "endRowIndex": r + 1,
#                     "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1,
#                 },
#                 "rule": {"condition": {"type": "BOOLEAN"}, "strict": True, "showCustomUi": True},
#             }
#         }
#         for r in row_indices
#     ]
#     if requests:
#         sheets_service.spreadsheets().batchUpdate(
#             spreadsheetId=SPREADSHEET_ID, body={"requests": requests}
#         ).execute()
#         print(f"   ☑️  Seeded {len(requests)} checkboxes")


# def ensure_sheet_structure(sheets_service, master_locations: list[str], target_date: str):
#     """
#     • Reads column A to find existing locations; appends any missing ones from DB.
#     • Finds or creates the date column header.
#     Returns (sheet_id, date_col_idx, location_row_map {clean_name: row_0based})
#     """
#     sheet_id = get_sheet_id(sheets_service)
#     rows     = read_sheet_data(sheets_service, sheet_id)

#     # Build location → row map from column A
#     location_row_map: dict[str, int] = {}
#     existing_names: list[str] = []
#     for r_idx in range(LOCATIONS_START_ROW - 1, len(rows)):
#         cell = (rows[r_idx][0].strip()) if rows[r_idx] else ""
#         if cell:
#             existing_names.append(cell)
#             location_row_map[clean_name(cell)] = r_idx

#     # Append locations that are in MySQL but not yet in the sheet
#     missing = [loc for loc in master_locations if clean_name(loc) not in location_row_map]
#     if missing:
#         next_row = (LOCATIONS_START_ROW - 1) + len(existing_names)
#         write_string_cells(sheets_service, sheet_id,
#                            [(next_row + i, 0, loc) for i, loc in enumerate(missing)])
#         for i, loc in enumerate(missing):
#             location_row_map[clean_name(loc)] = next_row + i
#         print(f"   📝 Added {len(missing)} new locations from DB to column A")

#     # Find or create the date column
#     header_row = rows[0] if rows else []
#     date_col_idx = None
#     last_occupied = 0
#     for c_idx, cell in enumerate(header_row):
#         if cell.strip() == target_date:
#             date_col_idx = c_idx
#             break
#         if cell.strip():
#             last_occupied = c_idx

#     if date_col_idx is None:
#         date_col_idx = max(last_occupied + 1, 1)
#         expand_sheet_columns(sheets_service, sheet_id, date_col_idx + 1)
#         write_string_cells(sheets_service, sheet_id, [(0, date_col_idx, target_date)])
#         print(f"   📅 Added date header '{target_date}' in column {index_to_col_letter(date_col_idx)}")

#     return sheet_id, date_col_idx, location_row_map


# # ══════════════════════════════════════════════════════════════════════
# # ── CSV Export ────────────────────────────────────────────────────────
# # ══════════════════════════════════════════════════════════════════════

# def export_to_csv(target_date: str, completed: list[str], incomplete: list[str]):
#     """
#     Writes audit results to a CSV file named backup_audit_YYYY-MM-DD.csv
#     with columns: location, status, date
#     """
#     filename = f"backup_audit_{target_date}.csv"
#     rows = (
#         [(loc, "Completed", target_date) for loc in sorted(completed)] +
#         [(loc, "Incomplete", target_date) for loc in sorted(incomplete)]
#     )
#     with open(filename, "w", newline="", encoding="utf-8") as f:
#         writer = csv.writer(f)
#         writer.writerow(["Location", "Status", "Date"])
#         writer.writerows(rows)

#     print(f"\n📁 CSV exported: {filename}")
#     print(f"   ✅ Completed : {len(completed)}")
#     print(f"   ❌ Incomplete: {len(incomplete)}")
#     print(f"   📝 Total rows: {len(rows)}")


# # ══════════════════════════════════════════════════════════════════════
# # ── Main ──────────────────────────────────────────────────────────════
# # ══════════════════════════════════════════════════════════════════════

# def main():
#     try:
#         # 1. Fetch location master list from MySQL
#         master_locations = fetch_locations_from_db()
#         if not master_locations:
#             print("🛑 No locations returned from DB. Check your query and connection.")
#             return

#         # 2. Authenticate Google services
#         chat_service, sheets_service = get_services()

#         # 3. Scan the Chat space
#         print(f"\n{'='*55}")
#         print(f"📡 SCANNING SPACE FOR: {TARGET_DATE}")
#         print(f"{'='*55}")

#         completed_locations = scan_space(chat_service, TARGET_DATE)

#         # 4. Console summary — compare Chat results against DB locations
#         final_completed  = [loc for loc in master_locations if clean_name(loc) in completed_locations]
#         final_incomplete = [loc for loc in master_locations if clean_name(loc) not in completed_locations]

#         print(f"\n{'='*55}")
#         print(f"📊 BACKUP AUDIT SUMMARY — {TARGET_DATE}")
#         print(f"{'='*55}")
#         print(f"\n✅ COMPLETED ({len(final_completed)}):")
#         for loc in sorted(final_completed):
#             print(f"   • {loc}")
#         print(f"\n❌ INCOMPLETE ({len(final_incomplete)}):")
#         for loc in sorted(final_incomplete):
#             print(f"   • {loc}")

#         # 5. Export to CSV
#         export_to_csv(TARGET_DATE, final_completed, final_incomplete)

#         # 6. Update Google Sheet
#         print(f"\n📊 Updating Google Sheet …")
#         sheet_id, date_col_idx, location_row_map = ensure_sheet_structure(
#             sheets_service, master_locations, TARGET_DATE
#         )

#         seed_checkboxes(sheets_service, sheet_id, date_col_idx,
#                         list(location_row_map.values()))

#         bool_updates = [
#             (row_0, date_col_idx, clean_loc in completed_locations)
#             for clean_loc, row_0 in location_row_map.items()
#         ]
#         write_bool_cells(sheets_service, sheet_id, bool_updates)

#         ticked = sum(1 for _, _, v in bool_updates if v)
#         print(f"   ✅ {ticked} checked / {len(bool_updates) - ticked} unchecked")
#         print(f"\n🎉 Done! https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")

#     except Exception as exc:
#         print(f"🛑 Error: {exc}")
#         import traceback
#         traceback.print_exc()


# if __name__ == "__main__":
#     main()


"""
backup_sync_auditor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scans a Google Chat space for "Daily Backup Sync" completion logs,
fetches the master location list from MySQL, writes checkboxes to a
Google Sheet, and pushes an updated historic CSV to GitHub so the
Backup Sync Dashboard reflects the latest data automatically.

Setup checklist
───────────────
1. pip install google-auth google-auth-oauthlib google-api-python-client mysql-connector-python requests
2. Place credentials.json (OAuth 2.0 desktop client) in the same folder.
3. Fill in every value under ── CONFIG ──.
4. Run once; a browser window will open for OAuth consent and save token.json.
"""

import os
import json
import csv
import base64
import requests
import mysql.connector
from io import StringIO
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ══════════════════════════════════════════════════════════════════════
# ── CONFIG  (edit everything in this block) ──────────────────────────
# ══════════════════════════════════════════════════════════════════════

# ── MySQL connection ─────────────────────────────────────────────────
MYSQL_CONFIG = {
    "host":     "172.16.1.89",
    "port":     3307,
    "user":     "readonly_user",
    "password": "Dekhomagr_Pyarse@7758",
    "database": "masterdb",
}

# SQL that returns one column: the location name
LOCATIONS_QUERY = "select location_name from adit_main where is_active = 1 and Ehr_name = 'Revolution';"

# ── Google Chat space ────────────────────────────────────────────────
SPACE_NAME = "spaces/AAQATvSu0go"

# ── Google Sheet ─────────────────────────────────────────────────────
SPREADSHEET_ID      = "1zLdTRhZc-BP7ZchJnUd0MeG1Djh-aOvdKbuHco2jcpI"
SHEET_NAME          = "All_loc"
LOCATIONS_START_ROW = 2                 # row 1 = date headers; locations from row 2

# ── Target date (YYYY-MM-DD) ─────────────────────────────────────────
TARGET_DATE = "2026-06-22"

# ── GitHub (for dashboard CSV) ───────────────────────────────────────
GITHUB_TOKEN = "your-github-personal-access-token"   # needs repo scope
GITHUB_USER  = "AdityaNair46"
GITHUB_REPO  = "backupsync-dashboard"
GITHUB_CSV_PATH = "backupsync_historic.csv"           # path inside the repo

# ── OAuth scopes ─────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

# ══════════════════════════════════════════════════════════════════════
# ── Helpers ───────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def clean_name(name: str) -> str:
    """Normalise a location name for comparison (lowercase, alphanumeric only)."""
    return "".join(c for c in name.lower() if c.isalnum())


def index_to_col_letter(idx: int) -> str:
    """Convert 0-based column index to spreadsheet letter (0→A, 25→Z, 26→AA …)."""
    result = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(rem + ord("A")) + result
    return result


# ══════════════════════════════════════════════════════════════════════
# ── MySQL: fetch locations ────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def fetch_locations_from_db() -> list[str]:
    """Return the master list of location names from MySQL."""
    print("🗄️  Connecting to MySQL …")
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()
    cursor.execute(LOCATIONS_QUERY)
    locations = [row[0].strip() for row in cursor.fetchall() if row[0]]
    cursor.close()
    conn.close()
    print(f"   ✔  Fetched {len(locations)} locations from database.")
    return locations


# ══════════════════════════════════════════════════════════════════════
# ── Google Auth ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def get_services():
    """Authenticate and return (chat_service, sheets_service)."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as fh:
            fh.write(creds.to_json())
    chat_service   = build("chat",   "v1", credentials=creds)
    sheets_service = build("sheets", "v4", credentials=creds)
    return chat_service, sheets_service


# ══════════════════════════════════════════════════════════════════════
# ── Google Chat: scan space ───────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def try_parse_log(raw_text: str) -> dict | None:
    """Parse a Chat message as a JSON backup log, stripping code fences if needed."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def scan_space(chat_service, target_date: str) -> set[str]:
    """
    Page through all messages in SPACE_NAME, find completed Daily Backup Sync
    logs for target_date, and return a set of clean location names.
    """
    completed: set[str] = set()
    next_page_token = None
    page_count = total_msgs = matched_logs = 0

    print(f"\n🔍 Scanning space: {SPACE_NAME}")
    print(f"⚠️  Brute-force scan — no API filter applied\n")

    while True:
        result = chat_service.spaces().messages().list(
            parent=SPACE_NAME,
            pageSize=1000,
            pageToken=next_page_token,
        ).execute()

        messages = result.get("messages", [])
        page_count  += 1
        total_msgs  += len(messages)
        print(f"   📄 Page {page_count}: {len(messages)} messages (total so far: {total_msgs})")

        for msg in messages:
            raw = msg.get("text", "")
            if target_date not in raw:
                continue

            log = try_parse_log(raw)
            if not log:
                continue
            if log.get("event") != "Daily Backup Sync":
                continue
            if log.get("timestamp", "")[:10] != target_date:
                continue

            matched_logs += 1
            location = log.get("location", "").strip()
            details  = log.get("details", "").lower()

            if "backup sync completed successfully" in details:
                if location:
                    print(f"   ✅  Completed: {location}")
                    completed.add(clean_name(location))
            else:
                print(f"   ⚠️   Not completed: {location} — {log.get('details')}")

        next_page_token = result.get("nextPageToken")
        if not next_page_token:
            print(f"\n   ✔  Scan complete. Total: {total_msgs} messages | Matched logs: {matched_logs}")
            break

    return completed


# ══════════════════════════════════════════════════════════════════════
# ── Google Sheets helpers ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def get_sheet_id(sheets_service) -> int:
    meta = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sheet in meta["sheets"]:
        if sheet["properties"]["title"] == SHEET_NAME:
            return sheet["properties"]["sheetId"]
    available = [s["properties"]["title"] for s in meta["sheets"]]
    raise ValueError(f"Tab '{SHEET_NAME}' not found. Available: {available}")


def read_sheet_data(sheets_service, sheet_id: int) -> list[list[str]]:
    result = sheets_service.spreadsheets().get(
        spreadsheetId=SPREADSHEET_ID,
        includeGridData=True,
        ranges=[],
    ).execute()
    for sheet in result["sheets"]:
        if sheet["properties"]["sheetId"] == sheet_id:
            row_data = sheet.get("data", [{}])[0].get("rowData", [])
            rows = []
            for row in row_data:
                cells = row.get("values", [])
                rows.append([
                    (c.get("formattedValue") or
                     c.get("effectiveValue", {}).get("stringValue", "") or "")
                    for c in cells
                ])
            return rows
    return []


def expand_sheet_columns(sheets_service, sheet_id: int, required_col_count: int):
    meta = sheets_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sheet in meta["sheets"]:
        if sheet["properties"]["sheetId"] == sheet_id:
            current = sheet["properties"]["gridProperties"]["columnCount"]
            if required_col_count > current:
                new_count = required_col_count + 10
                sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=SPREADSHEET_ID,
                    body={"requests": [{
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet_id,
                                "gridProperties": {"columnCount": new_count},
                            },
                            "fields": "gridProperties.columnCount",
                        }
                    }]},
                ).execute()
                print(f"   📐 Expanded columns: {current} → {new_count}")
            break


def write_string_cells(sheets_service, sheet_id: int, updates: list[tuple]):
    requests_body = [
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r, "endRowIndex": r + 1,
                    "startColumnIndex": c, "endColumnIndex": c + 1,
                },
                "rows": [{"values": [{"userEnteredValue": {"stringValue": str(v)}}]}],
                "fields": "userEnteredValue",
            }
        }
        for r, c, v in updates
    ]
    if requests_body:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body={"requests": requests_body}
        ).execute()


def write_bool_cells(sheets_service, sheet_id: int, updates: list[tuple]):
    requests_body = [
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r, "endRowIndex": r + 1,
                    "startColumnIndex": c, "endColumnIndex": c + 1,
                },
                "rows": [{"values": [{"userEnteredValue": {"boolValue": v}}]}],
                "fields": "userEnteredValue",
            }
        }
        for r, c, v in updates
    ]
    if requests_body:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body={"requests": requests_body}
        ).execute()


def seed_checkboxes(sheets_service, sheet_id: int, col_idx: int, row_indices: list[int]):
    requests_body = [
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r, "endRowIndex": r + 1,
                    "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1,
                },
                "rule": {"condition": {"type": "BOOLEAN"}, "strict": True, "showCustomUi": True},
            }
        }
        for r in row_indices
    ]
    if requests_body:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID, body={"requests": requests_body}
        ).execute()
        print(f"   ☑️  Seeded {len(requests_body)} checkboxes")


def ensure_sheet_structure(sheets_service, master_locations: list[str], target_date: str):
    sheet_id = get_sheet_id(sheets_service)
    rows     = read_sheet_data(sheets_service, sheet_id)

    location_row_map: dict[str, int] = {}
    existing_names: list[str] = []
    for r_idx in range(LOCATIONS_START_ROW - 1, len(rows)):
        cell = (rows[r_idx][0].strip()) if rows[r_idx] else ""
        if cell:
            existing_names.append(cell)
            location_row_map[clean_name(cell)] = r_idx

    missing = [loc for loc in master_locations if clean_name(loc) not in location_row_map]
    if missing:
        next_row = (LOCATIONS_START_ROW - 1) + len(existing_names)
        write_string_cells(sheets_service, sheet_id,
                           [(next_row + i, 0, loc) for i, loc in enumerate(missing)])
        for i, loc in enumerate(missing):
            location_row_map[clean_name(loc)] = next_row + i
        print(f"   📝 Added {len(missing)} new locations from DB to column A")

    header_row = rows[0] if rows else []
    date_col_idx = None
    last_occupied = 0
    for c_idx, cell in enumerate(header_row):
        if cell.strip() == target_date:
            date_col_idx = c_idx
            break
        if cell.strip():
            last_occupied = c_idx

    if date_col_idx is None:
        date_col_idx = max(last_occupied + 1, 1)
        expand_sheet_columns(sheets_service, sheet_id, date_col_idx + 1)
        write_string_cells(sheets_service, sheet_id, [(0, date_col_idx, target_date)])
        print(f"   📅 Added date header '{target_date}' in column {index_to_col_letter(date_col_idx)}")

    return sheet_id, date_col_idx, location_row_map


# ══════════════════════════════════════════════════════════════════════
# ── Historic CSV + GitHub push ────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def update_historic_csv(target_date: str, master_locations: list[str],
                        completed_set: set[str]) -> str:
    """
    Reads backupsync_historic.csv (if it exists locally), removes any rows
    for target_date (so re-runs overwrite instead of duplicate), appends
    fresh rows for every location, then writes it back.

    CSV columns: date, location, completed
    'completed' is TRUE or FALSE — matches what the dashboard expects.

    Returns the full CSV content as a string.
    """
    historic_path = "backupsync_historic.csv"
    existing_rows: list[dict] = []

    # Load existing data, skipping rows for target_date (will be replaced)
    if os.path.exists(historic_path):
        with open(historic_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("date", "").strip() != target_date:
                    existing_rows.append(row)

    # Build today's rows
    new_rows = [
        {
            "date":      target_date,
            "location":  loc,
            "completed": "TRUE" if clean_name(loc) in completed_set else "FALSE",
        }
        for loc in master_locations
    ]

    all_rows = existing_rows + new_rows

    # Write back locally
    with open(historic_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "location", "completed"])
        writer.writeheader()
        writer.writerows(all_rows)

    # Return as string for GitHub upload
    buf = StringIO()
    writer2 = csv.DictWriter(buf, fieldnames=["date", "location", "completed"])
    writer2.writeheader()
    writer2.writerows(all_rows)

    total = len(all_rows)
    done  = sum(1 for r in new_rows if r["completed"] == "TRUE")
    print(f"\n📁 Historic CSV updated: {historic_path}")
    print(f"   📅 Date: {target_date} | ✅ {done} completed | ❌ {len(new_rows)-done} incomplete")
    print(f"   📝 Total rows in file: {total}")

    return buf.getvalue()


def push_csv_to_github(csv_content: str):
    """
    Pushes backupsync_historic.csv to GitHub via the Contents API.
    Creates the file if it doesn't exist; updates (with SHA) if it does.
    """
    print(f"\n🚀 Pushing CSV to GitHub ({GITHUB_USER}/{GITHUB_REPO}) …")

    api_url = (
        f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}"
        f"/contents/{GITHUB_CSV_PATH}"
    )
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    # Check if file already exists (need SHA to update)
    sha = None
    get_resp = requests.get(api_url, headers=headers)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")

    encoded = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")

    payload: dict = {
        "message": f"chore: update backup sync data for {TARGET_DATE}",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha

    put_resp = requests.put(api_url, headers=headers, json=payload)

    if put_resp.status_code in (200, 201):
        action = "updated" if sha else "created"
        print(f"   ✅ File {action} successfully on GitHub.")
        print(f"   🔗 https://github.com/{GITHUB_USER}/{GITHUB_REPO}/blob/main/{GITHUB_CSV_PATH}")
    else:
        print(f"   🛑 GitHub push failed: {put_resp.status_code} — {put_resp.text}")


# ══════════════════════════════════════════════════════════════════════
# ── Main ──────────────────────────────────────────────────────────════
# ══════════════════════════════════════════════════════════════════════

def main():
    try:
        # 1. Fetch location master list from MySQL
        master_locations = fetch_locations_from_db()
        if not master_locations:
            print("🛑 No locations returned from DB. Check your query and connection.")
            return

        # 2. Authenticate Google services
        chat_service, sheets_service = get_services()

        # 3. Scan the Chat space
        print(f"\n{'='*55}")
        print(f"📡 SCANNING SPACE FOR: {TARGET_DATE}")
        print(f"{'='*55}")

        completed_locations = scan_space(chat_service, TARGET_DATE)

        # 4. Console summary — compare Chat results against DB locations
        final_completed  = [loc for loc in master_locations if clean_name(loc) in completed_locations]
        final_incomplete = [loc for loc in master_locations if clean_name(loc) not in completed_locations]

        print(f"\n{'='*55}")
        print(f"📊 BACKUP AUDIT SUMMARY — {TARGET_DATE}")
        print(f"{'='*55}")
        print(f"\n✅ COMPLETED ({len(final_completed)}):")
        for loc in sorted(final_completed):
            print(f"   • {loc}")
        print(f"\n❌ INCOMPLETE ({len(final_incomplete)}):")
        for loc in sorted(final_incomplete):
            print(f"   • {loc}")

        # 5. Update historic CSV and push to GitHub (feeds the dashboard)
        csv_content = update_historic_csv(TARGET_DATE, master_locations, completed_locations)
        push_csv_to_github(csv_content)

        # 6. Update Google Sheet
        print(f"\n📊 Updating Google Sheet …")
        sheet_id, date_col_idx, location_row_map = ensure_sheet_structure(
            sheets_service, master_locations, TARGET_DATE
        )

        seed_checkboxes(sheets_service, sheet_id, date_col_idx,
                        list(location_row_map.values()))

        bool_updates = [
            (row_0, date_col_idx, clean_loc in completed_locations)
            for clean_loc, row_0 in location_row_map.items()
        ]
        write_bool_cells(sheets_service, sheet_id, bool_updates)

        ticked = sum(1 for _, _, v in bool_updates if v)
        print(f"   ✅ {ticked} checked / {len(bool_updates) - ticked} unchecked")
        print(f"\n🎉 Done! https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")

    except Exception as exc:
        print(f"🛑 Error: {exc}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
