#!/usr/bin/env python3
"""
Google Sheets Writer for Pursuit Maps
======================================
Handles OAuth authentication and writing data to Google Sheets.

Usage:
    python3 sheets_writer.py --auth          # first-time OAuth setup
    python3 sheets_writer.py --write-new     # write new maps to sheet
    python3 sheets_writer.py --write-all     # overwrite all sheet data
    python3 sheets_writer.py --test          # test connection

The OAuth flow opens a browser for first-time auth.
After that, token.json is saved and reused automatically.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

# Fix sys.path to avoid Python313/314 contamination
sys.path = [p for p in sys.path if "Python313" not in p and "Python314" not in p]

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ── Config ────────────────────────────────────────────────────────────────────

SHEET_ID = "1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ"
SHEET_GID = 763170857
SHEET_NAME = "Pursuit Channels New"  # tab name

# Google API scopes needed
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Token and credentials paths
TOKEN_PATH = Path(__file__).parent / "token.json"
# Column order matching the Sheet
COLUMNS = ["#", "Map name", "Author login", "Environment", "Uploaded at",
           "UID", "MapType", "Notes"]


def get_credentials():
    """Get valid credentials from token.json or run OAuth flow."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        print(f"Loaded token from {TOKEN_PATH}", file=sys.stderr)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing token...", file=sys.stderr)
            creds.refresh(GoogleRequest())
        else:
            # Check for client_secrets file
            client_secrets_env = os.environ.get("GOOGLE_CLIENT_SECRETS", "")
            if client_secrets_env and os.path.exists(client_secrets_env):
                secrets_path = client_secrets_env
            elif (Path(__file__).parent / "client_secrets.json").exists():
                secrets_path = str(Path(__file__).parent / "client_secrets.json")
            else:
                print("ERROR: No client_secrets.json found!", file=sys.stderr)
                print("Create a Google Cloud OAuth Client ID and download the JSON.", file=sys.stderr)
                print("Save it as 'client_secrets.json' in the same directory, or set", file=sys.stderr)
                print("GOOGLE_CLIENT_SECRETS env var to its path.", file=sys.stderr)
                sys.exit(1)

            print("Starting OAuth flow - browser will open...", file=sys.stderr)
            flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next time
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved to {TOKEN_PATH}", file=sys.stderr)

    return creds


def get_service():
    """Build Google Sheets API service."""
    creds = get_credentials()
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_sheet(service):
    """Read current sheet data."""
    # First find the actual sheet name by GID
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheet_title = None
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("sheetId") == SHEET_GID:
                sheet_title = props.get("title", SHEET_NAME)
                break
        if not sheet_title:
            sheet_title = SHEET_NAME
    except HttpError:
        sheet_title = SHEET_NAME

    range_spec = f"'{sheet_title}'!A1:H300"
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=range_spec
    ).execute()

    values = result.get("values", [])
    rows = []
    for i, row in enumerate(values[1:], 2):  # skip header
        if len(row) > 5 and row[5]:  # has UID
            rows.append({
                "row_num": i,
                "#": row[0] if len(row) > 0 else "",
                "Map name": row[1] if len(row) > 1 else "",
                "Author login": row[2] if len(row) > 2 else "",
                "Environment": row[3] if len(row) > 3 else "",
                "Uploaded at": row[4] if len(row) > 4 else "",
                "UID": row[5] if len(row) > 5 else "",
                "MapType": row[6] if len(row) > 6 else "",
                "Notes": row[7] if len(row) > 7 else "",
            })
    return rows


def find_sheet_title(service):
    """Find the actual sheet title by GID."""
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("sheetId") == SHEET_GID:
                return props.get("title", SHEET_NAME)
    except HttpError:
        pass
    return SHEET_NAME


def write_new_rows(service, new_maps):
    """Append new rows to the sheet."""
    sheet_title = find_sheet_title(service)

    # Get current last row
    range_spec = f"'{sheet_title}'!A:A"
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=range_spec
    ).execute()
    values = result.get("values", [])
    last_row = len(values)

    # Prepare data
    rows = []
    for i, m in enumerate(new_maps, last_row + 1):
        rows.append([
            str(i),
            m.get("Map name", ""),
            m.get("Author login", ""),
            m.get("Environment", ""),
            m.get("Uploaded at", ""),
            m.get("UID", ""),
            m.get("MapType", ""),
            m.get("Notes", ""),
        ])

    if not rows:
        print("No new rows to write.")
        return 0

    body = {"values": rows}
    range_spec = f"'{sheet_title}'!A{last_row + 1}:H{last_row + len(rows)}"

    result = service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=range_spec,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

    updated = result.get("updates", {}).get("updatedRows", 0)
    print(f"Written {updated} new rows (starting at row {last_row + 1})")
    return updated


def update_empty_fields(service, updates):
    """Update specific cells with fill data. updates = [(row_num, col_letter, value), ...]"""
    sheet_title = find_sheet_title(service)

    data = []
    for row_num, col_letter, value in updates:
        range_spec = f"'{sheet_title}'!{col_letter}{row_num}"
        data.append({
            "range": range_spec,
            "values": [[value]],
        })

    if not data:
        print("No updates to write.")
        return 0

    body = {"valueInputOption": "USER_ENTERED", "data": data}
    result = service.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID, body=body
    ).execute()
    total = result.get("totalUpdatedCells", 0)
    print(f"Updated {total} cells")
    return total


def write_all_data(service, all_maps, start_row=2):
    """Overwrite all data (header + rows). Use with care."""
    sheet_title = find_sheet_title(service)

    header = COLUMNS
    rows = [header]
    for i, m in enumerate(all_maps, 1):
        rows.append([
            str(i),
            m.get("Map name", ""),
            m.get("Author login", ""),
            m.get("Environment", ""),
            m.get("Uploaded at", ""),
            m.get("UID", ""),
            m.get("MapType", ""),
            m.get("Notes", ""),
        ])

    range_spec = f"'{sheet_title}!A1:H{len(rows)}"
    body = {"values": rows}

    result = service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=range_spec,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()
    updated = result.get("updatedRows", 0)
    print(f"Overwritten {updated} rows")
    return updated


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Google Sheets Writer for Pursuit Maps")
    parser.add_argument("--auth", action="store_true", help="Run OAuth setup")
    parser.add_argument("--test", action="store_true", help="Test connection and read sheet")
    parser.add_argument("--read", action="store_true", help="Read sheet data and print")
    parser.add_argument("--write-new", metavar="JSON_FILE",
                       help="Write new maps from JSON file to sheet")
    parser.add_argument("--fill-empty", metavar="JSON_FILE",
                       help="Fill empty cells from JSON file [{row, col, value}, ...]")
    parser.add_argument("--write-all", metavar="JSON_FILE",
                       help="Overwrite all sheet data from JSON")
    args = parser.parse_args()

    if args.auth:
        creds = get_credentials()
        print("Auth successful! Token saved.")
        print(f"Token file: {TOKEN_PATH}")
        return

    service = get_service()
    print("Connected to Google Sheets API", file=sys.stderr)

    if args.test:
        rows = read_sheet(service)
        print(f"Sheet has {len(rows)} data rows (excl. header)")
        for r in rows[:3]:
            print(f"  Row {r['row_num']}: {r['Map name'][:40]} | {r['Author login']} | {r['UID'][:20]}")
        return

    if args.read:
        rows = read_sheet(service)
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
        return

    if args.write_new:
        with open(args.write_new, "r", encoding="utf-8") as f:
            new_maps = json.load(f)
        write_new_rows(service, new_maps)

    if args.fill_empty:
        with open(args.fill_empty, "r", encoding="utf-8") as f:
            updates = json.load(f)
        # Convert to (row, col_letter, value) tuples
        col_map = {"Map name": "B", "Author login": "C", "Environment": "D",
                   "Uploaded at": "E", "UID": "F", "MapType": "G", "Notes": "H"}
        tuples = []
        for u in updates:
            col = col_map.get(u.get("column", ""), "H")
            tuples.append((u["row"], col, u["value"]))
        update_empty_fields(service, tuples)

    if args.write_all:
        with open(args.write_all, "r", encoding="utf-8") as f:
            all_maps = json.load(f)
        write_all_data(service, all_maps)


if __name__ == "__main__":
    main()
