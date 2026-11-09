#!/usr/bin/env python3
import html as html_lib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

PASS_1 = 630.00
PASS_2 = 525.3333333333333333


def get_issue_data():
    title = os.environ.get("ISSUE_TITLE", "").strip()
    body = os.environ.get("ISSUE_BODY", "").strip()
    return title, body


def parse_issue_form(body):
    """Parse GitHub Issue Form markdown sections (### Label\\n\\nValue)."""
    sections = {}
    current_label = None
    buffer = []

    for line in body.splitlines():
        header_match = re.match(r"^###\s+(.+?)\s*$", line)
        if header_match:
            if current_label is not None:
                val = "\n".join(buffer).strip()
                sections[current_label] = "" if val == "_No response_" else val
            current_label = header_match.group(1)
            buffer = []
        else:
            buffer.append(line)

    if current_label is not None:
        val = "\n".join(buffer).strip()
        sections[current_label] = "" if val == "_No response_" else val

    return sections


def normalize_date(date_text):
    today = datetime.now().strftime("%d.%m.%Y")
    if not date_text:
        return today
    for date_match in re.finditer(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b", date_text):
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = date_match.group(3)
        if 1 <= day <= 31 and 1 <= month <= 12:
            if not year:
                year = str(datetime.now().year)
            elif len(year) == 2:
                year = f"20{year}"
            return f"{day:02d}.{month:02d}.{year}"
    return today


def parse_price(text):
    if not text:
        return None
    clean = text.strip().replace(",", ".")
    match = re.search(r"\d+(?:\.\d{1,2})?", clean)
    if match:
        return float(match.group(0))
    return None


def extract_from_text(title, body):
    sections = parse_issue_form(body)

    if "Skigebiet" in sections:
        resort = sections.get("Skigebiet", "").strip()
        if not resort and title and title != "[Skigebiet eintragen]":
            resort = title
        resort = resort or "Skigebiet"

        date_str = normalize_date(sections.get("Datum", ""))
        notes = sections.get("Notizen", "").strip()
        manual_price = parse_price(sections.get("Ticketpreis Jugend (optional)", ""))
        return resort, date_str, notes, manual_price

    # Fallback: free-text issue (e.g. Title: "Nassfeld", Body: "14.12.2024, Kaiserwetter, 54€")
    combined = f"{title}\n{body}"
    price_match = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euro\b|eur\b)", combined, re.IGNORECASE)
    manual_price = float(price_match.group(1).replace(",", ".")) if price_match else None

    date_search_text = combined.replace(price_match.group(0), "") if price_match else combined
    date_str = normalize_date(date_search_text)

    resort = title
    if title.lower() in ["skitag", "skifahren", "neu", "ski tag", "[skigebiet eintragen]", ""]:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        resort = lines[0] if lines else "Skigebiet"

    notes = body
    if notes:
        if price_match:
            notes = notes.replace(price_match.group(0), "")
        notes = re.sub(r"\b\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\b", "", notes)
        notes = notes.replace(resort, "").strip(" ,-\n\t")

    return resort, date_str, notes, manual_price


def query_gemini_for_ticket_price(resort, date_str, notes):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("WARN: Kein GEMINI_API_KEY gesetzt.")
        return None, None, "Kein GEMINI_API_KEY Secret gesetzt"

    prompt = f"""Du bist ein Assistent für Skipass-Preise.
Aufgabe:
Ein 17-jähriger Skifahrer (Tarifkategorie: Jugend / Youth / Jugendlicher, nicht Erwachsener!) war skifahren.
Skigebiet: {resort}
Datum: {date_str}
Notizen: {notes}

Recherchiere per Google-Suche den aktuellen Tageskarten-Preis (1 Tag, regulärer Jugendtarif in EUR) für dieses Skigebiet.
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt (ohne Markdown oder Erklärungstext):
{{
  "resort": "Offizieller Name des Skigebiets",
  "price": 54.00,
  "source": "Kurze Quellenangabe oder URL"
}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.1},
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "\n".join(p.get("text", "") for p in parts if "text" in p).strip()
                json_match = re.search(r"\{.*\}", text, re.DOTALL)
                if json_match:
                    res = json.loads(json_match.group(0))
                    official_resort = res.get("resort") or resort
                    price_val = parse_price(str(res.get("price", "")))
                    source = res.get("source", "Gemini Websuche")
                    if price_val is not None:
                        return official_resort, price_val, source
            return None, None, "Unerwartete Gemini-Antwort"
    except Exception as e:
        print(f"Fehler bei Gemini API Aufruf: {e}")
        return None, None, str(e)


def update_index_html(resort, date_str, notes, price, source):
    html_path = "index.html"
    if not os.path.exists(html_path):
        print("index.html nicht gefunden!")
        sys.exit(1)

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    pattern = r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>"
    existing_rows = re.findall(pattern, html, re.DOTALL)

    prev_sum = 0.0
    for r in existing_rows:
        p_val = re.sub(r"[^0-9.]", "", r[3].replace(",", "."))
        if p_val:
            try:
                prev_sum += float(p_val)
            except ValueError:
                pass

    new_sum = prev_sum + price
    diff1 = new_sum - PASS_1
    diff2 = new_sum - PASS_2

    diff1_str = f"{diff1:+.2f} €"
    diff2_str = f"{diff2:+.2f} €"

    safe_date = html_lib.escape(date_str)
    safe_resort = html_lib.escape(resort)
    safe_notes = html_lib.escape(notes if notes else "-").replace("\n", "<br>")

    new_row = f"""    <tr>
      <td>{safe_date}</td>
      <td>{safe_resort}</td>
      <td>{safe_notes}</td>
      <td>{price:.2f} €</td>
      <td>{new_sum:.2f} €</td>
      <td>{diff1_str}</td>
      <td>{diff2_str}</td>
    </tr>
"""

    if "</table>" in html:
        updated_html = html.replace("</table>", new_row + "  </table>", 1)
    else:
        print("Fehler: </table> Tag nicht gefunden!")
        sys.exit(1)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(updated_html)

    summary = f"""### 🎿 Skitag erfolgreich eingetragen!
* **Datum:** {date_str}
* **Skigebiet:** {resort}
* **Notizen:** {notes if notes else '-'}
* **Tageskarte Jugend (17 Jahre):** {price:.2f} € *(Quelle: {source})*
* **Summe aller Tageskarten bisher:** {new_sum:.2f} €
* **Saldo zu jugend einzeln (630 €):** {diff1_str}
* **Saldo zu jugend jugend erwachsen (525.33 €):** {diff2_str}

Die Website **anien.me** wurde automatisch aktualisiert!
"""
    return summary


def main():
    title, body = get_issue_data()
    print(f"Verarbeite Issue: Title='{title}', Body='{body}'")

    resort, date_str, notes, manual_price = extract_from_text(title, body)

    price = manual_price
    source = "Manuelle Eingabe im Issue"
    if price is None:
        official_resort, gemini_price, gemini_source = query_gemini_for_ticket_price(resort, date_str, notes)
        if gemini_price is not None:
            resort = official_resort or resort
            price = gemini_price
            source = gemini_source
        else:
            price = 55.00
            source = f"Standard-Schätzwert ({gemini_source})"

    print(f"Ermittelter Preis für {resort}: {price:.2f} € (Quelle: {source})")
    summary = update_index_html(resort, date_str, notes, price, source)

    with open("issue_comment.md", "w", encoding="utf-8") as f:
        f.write(summary)


if __name__ == "__main__":
    main()
