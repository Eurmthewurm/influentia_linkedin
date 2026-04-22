# ─────────────────────────────────────────────────────────────────────────────
# leads_loader.py  —  Read the 20 leads from the Excel file into state
# ─────────────────────────────────────────────────────────────────────────────
import openpyxl
from config import LEADS_EXCEL_PATH
from state_manager import load_state, upsert_lead, save_state


HEADER_ROW = 3   # Row 3 in the Excel is the column header row
# Columns (1-indexed):
#  1=#, 2=Full Name, 3=Job Title, 4=Company, 5=Industry,
#  6=Email, 7=Phone, 8=LinkedIn URL, 9=Website, 10=City, 11=State, 12=Country


def load_leads_from_excel() -> list:
    """
    Read all data rows from the Excel file.
    Returns a list of dicts, one per lead.
    Skips section divider rows (merged cells / no LinkedIn URL).
    """
    wb = openpyxl.load_workbook(LEADS_EXCEL_PATH)
    ws = wb.active

    leads = []
    for row in ws.iter_rows(min_row=HEADER_ROW + 1, values_only=True):
        num, name, title, company, industry, email, phone, linkedin, website, city, state, country = row

        # Skip blank/divider rows
        if not linkedin or not isinstance(linkedin, str) or "linkedin.com" not in linkedin:
            continue

        leads.append({
            "linkedin_url": linkedin.strip(),
            "name":         str(name or "").strip(),
            "title":        str(title or "").strip(),
            "company":      str(company or "").strip(),
            "sector":       str(industry or "").strip(),
            "email":        str(email or "").strip(),
            "phone":        str(phone or "").strip(),
            "website":      str(website or "").strip(),
            "city":         str(city or "").strip(),
            "state":        str(state or "").strip(),
            "country":      str(country or "Australia").strip(),
        })

    print(f"Loaded {len(leads)} leads from {LEADS_EXCEL_PATH}")
    return leads


def sync_leads_to_state():
    """
    Load leads from Excel and add any new ones to state.
    Existing entries (already tracked) are NOT overwritten.
    """
    state = load_state()
    leads = load_leads_from_excel()

    new_count = 0
    for lead in leads:
        url = lead["linkedin_url"]
        if url not in state["leads"]:
            upsert_lead(state, lead)
            new_count += 1

    save_state(state)
    print(f"Synced leads: {new_count} new, {len(leads)-new_count} already tracked.")
    return state
