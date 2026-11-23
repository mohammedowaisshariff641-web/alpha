"""
Google Sheets data adapter.
Google Sheets is the only persistent database. Replace the placeholder workbook
with your actual dataset using the sheet names and headers documented in README.md.
"""
import os
from datetime import date, datetime, timedelta
from pathlib import Path

DEMO = os.getenv("DEMO_MODE", "false").lower() == "true"

SHEET_HEADERS = {
    "Inventory": ["Item_ID","Item_Name","Category","Tracking_Method","Total_Quantity","Available_Quantity","Borrowed_Quantity","Condition","Location","Specifications","Compatibility_Notes","Item_Status","Last_Verified","Remarks"],
    "Users": ["User_ID","Full_Name","USN_or_Staff_ID","Email","Role","Department","Account_Status","Block_Reason","Outstanding_Fine"],
    "Borrow_Transactions": ["Transaction_ID","User_ID","Item_ID","Quantity","Issue_Date","Due_Date","Return_Date","Return_Condition","Inspection_Notes","Issued_By","Received_By","Transaction_Status","Overdue_Flag","Fine_Status","Fine_Amount","Purpose","Request_Reason","Remarks"],
    "Reservations": ["Reservation_ID","User_ID","Item_ID","Quantity","Request_Date","Expected_Availability_Date","Approved_By","Reservation_Status","Priority_Number","Notification_Status","Purpose","Booking_Notes","Remarks"],
    "Damage_Reports": ["Damage_Report_ID","Transaction_ID","Item_ID","Issue_Type","Reported_At","Condition_On_Return","Inspection_Status","Description","Photo_Link","Resolution_Status","Reported_By","Reviewed_By","Fine_Decision","Fine_Amount","Remarks"],
    "Rules_Config": ["Rule_ID","Setting_Name","Setting_Value","Unit","Description","Updated_By","Updated_At","Remarks"],
    "Research_Requirements": ["Requirement_ID","Type","Source_Role_or_Name","User_Quote_or_Observation","Need_Identified","Proposed_Design_Response","Priority","Status","Owner","Evidence_Link","Remarks"],
    "Login_Credentials": ["Credential_ID","User_ID","Username","Email","Password_Hash","Role","Account_Status","Failed_Login_Attempts","Last_Login","Created_At","Remarks"],
}

DEMO_DATA = {
    "Inventory": [
        dict(zip(SHEET_HEADERS["Inventory"], ["ITM-001","Arduino Uno","Microcontroller Board","Individual ID",10,8,2,"Functional","ALPHA Lab","ATmega328P; 5V","USB; GPIO","Available","","Sample item – replace with actual inventory"])),
        dict(zip(SHEET_HEADERS["Inventory"], ["ITM-002","Ultrasonic Sensor HC-SR04","Sensor","Quantity-based",8,8,0,"Functional","ALPHA Lab","5V; TRIG/ECHO","Arduino-compatible","Available","","Sample item – replace with actual inventory"])),
        dict(zip(SHEET_HEADERS["Inventory"], ["ITM-003","Jumper Wires","Accessory","Quantity-based",50,42,8,"Functional","ALPHA Lab","Male-male assortment","Breadboard prototyping","Available","","Sample item – replace with actual inventory"])),
        dict(zip(SHEET_HEADERS["Inventory"], ["ITM-004","Digital Multimeter","Testing Tool","Individual ID",3,2,1,"Functional","ALPHA Lab","Digital meter","Electrical testing","Available","","Sample item – replace with actual inventory"])),
    ],
    "Users": [
        dict(zip(SHEET_HEADERS["Users"], ["USR-001","Demo Student","2026CS0001","student@example.com","Student","CSE","Active","",0])),
        dict(zip(SHEET_HEADERS["Users"], ["USR-002","Lab Administrator","ADMIN001","admin@example.com","Staff","ALPHA Lab","Active","",0])),
    ],
    "Borrow_Transactions": [],
    "Reservations": [],
    "Damage_Reports": [],
    "Rules_Config": [
        dict(zip(SHEET_HEADERS["Rules_Config"], ["CFG-001","Default_Borrowing_Duration",3,"Days","Default loan period","","",""])),
        dict(zip(SHEET_HEADERS["Rules_Config"], ["CFG-002","Fine_Per_Day",10,"INR","Suggested fine; admin must approve","","",""])),
        dict(zip(SHEET_HEADERS["Rules_Config"], ["CFG-003","Max_Concurrent_Borrowings",3,"Items","Maximum active loans per user","","",""])),
    ],
    "Research_Requirements": [],
    "Login_Credentials": [],
}

import os
from pathlib import Path

# Keep your existing DEMO and DEMO_DATA definitions
# from the same file above this class.


class SheetsStore:
    def __init__(self):
        self.demo = DEMO
        self.client = None
        self.spreadsheet = None

        if not self.demo:
            import gspread
            from google.oauth2.service_account import Credentials

            spreadsheet_id = os.getenv(
                "GOOGLE_SHEETS_SPREADSHEET_ID", ""
            )

            credential_path = os.getenv(
                "GOOGLE_SERVICE_ACCOUNT_FILE",
                "credentials/service-account.json"
            )

            if not spreadsheet_id or "PASTE_" in spreadsheet_id:
                raise RuntimeError(
                    "Set GOOGLE_SHEETS_SPREADSHEET_ID in .env"
                )

            if not Path(credential_path).exists():
                raise RuntimeError(
                    f"Google service-account JSON not found: {credential_path}"
                )

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets"
            ]

            creds = Credentials.from_service_account_file(
                credential_path,
                scopes=scopes
            )

            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(spreadsheet_id)

    # Get all rows
    def rows(self, name):
        if self.demo:
            return DEMO_DATA[name]

        ws = self.spreadsheet.worksheet(name)
        values = ws.get_all_values()

        if not values:
            return []

        headers = values[0]

        return [
            dict(
                zip(
                    headers,
                    row + [""] * (len(headers) - len(row))
                )
            )
            for row in values[1:]
            if any(row)
        ]

    # Add a new record
    def append(self, name, record):
        if self.demo:
            DEMO_DATA[name].append(record)
            return

        ws = self.spreadsheet.worksheet(name)

        headers = ws.row_values(1)

        if not headers:
            raise RuntimeError(
                f"Headers are missing in {name} sheet"
            )

        row_data = [
            record.get(header, "")
            for header in headers
        ]

        next_row = len(ws.get_all_values()) + 1

        ws.update(
            range_name=f"A{next_row}",
            values=[row_data],
            value_input_option="USER_ENTERED"
        )

        print(
            f"Successfully added record to {name}, row {next_row}"
        )

    # Update an existing record
    def update(self, name, key, key_value, updates):
        if self.demo:
            for row in DEMO_DATA[name]:
                if str(row.get(key)) == str(key_value):
                    row.update(updates)
                    return True

            return False

        ws = self.spreadsheet.worksheet(name)

        headers = ws.row_values(1)

        if key not in headers:
            raise RuntimeError(
                f"Column '{key}' not found in {name} sheet"
            )

        key_col = headers.index(key) + 1

        cell = ws.find(
            str(key_value),
            in_column=key_col
        )

        if not cell:
            return False

        for field, value in updates.items():
            if field not in headers:
                raise RuntimeError(
                    f"Column '{field}' not found in {name} sheet"
                )

            col = headers.index(field) + 1

            ws.update_cell(
                cell.row,
                col,
                value
            )

        return True


# Store instance
_store = None


def get_store():
    global _store

    if _store is None:
        _store = SheetsStore()

    return _store