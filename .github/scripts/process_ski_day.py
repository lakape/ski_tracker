#!/usr/bin/env python3
import os
import re
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime

PASS_1 = 630.00
PASS_2 = 525.3333333333333333

def get_issue_data():
    title = os.environ.get("ISSUE_TITLE", "").strip()
    body = os.environ.get("ISSUE_BODY", "").strip()
    return title, body

def query_gemini_for_ticket_price(resort, date_str, notes):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("WARN: Kein GEMINI_API_KEY gesetzt. Versuche Preis aus Issue-Text zu parsen.")
        return None, "Kein API-Key gesetzt"

    prompt = f"""
Du bist ein Assistent für Skipass-Preise in Österreich/Europa.
Aufgabe:
Ein 17-jähriger Skifahrer (Tarifkategorie: Jugend / Youth / Jugendlicher, nicht Erwachsener!) war skifahren.
Skigebiet: {resort}
Datum: {date_str}
Notizen: {notes}

Recherchiere per Google-Suche den aktuellen Tageskarten-Preis (1 Tag) für Jugendliche (17 Jahre) in diesem Skigebiet.
Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt ohne Markdown-Backticks:
{{
  "resort": "Offizieller Name des Skigebiets",
  "price": 54.00,
  "source": "Quelle oder Link",
  "notes": "Zusammenfassung der Notizen"
}}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.1}
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                # clean potential ```json markdown
                text = re.sub(r"```json\s*", "", text)
                text = re.sub(r"```\s*", "", text).strip()
                res = json.loads(text)
                return float(res.get("price", 55.0)), res.get("source", "Gemini Websuche")
    except Exception as e:
        print(f"Fehler bei Gemini API Aufruf: {e}")
    return None, str(e)

def extract_from_text(title, body):
    # Check if a price was manually mentioned e.g. "55€" or "55.50 EUR"
    combined = title + " " + body
    price_match = re.search(r"(\d+([.,]\d{1,2})?)\s*(€|euro|eur)", combined, re.IGNORECASE)
    manual_price = None
    if price_match:
        manual_price = float(price_match.group(1).replace(",", "."))

    # Date match: e.g. 14.12.2024 or 14.12.
    date_match = re.search(r"\b(\d{1,2}\.\d{1,2}(\.\d{2,4})?)\b", combined)
    today = datetime.now().strftime("%d.%m.%Y")
    date_str = date_match.group(1) if date_match else today
    if len(date_str.split(".")) == 2:
        date_str += f".{datetime.now().year}"

    # Resort: Title is often the resort name, unless title is "Skitag"
    resort = title
    if title.lower() in ["skitag", "skifahren", "neu", "ski tag"]:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        resort = lines[0] if lines else "Skigebiet"

    notes = body.replace(resort, "").strip()
    return resort, date_str, notes, manual_price

def update_index_html(resort, date_str, notes, price):
    html_path = "index.html"
    if not os.path.exists(html_path):
        print("index.html nicht gefunden!")
        sys.exit(1)

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Find existing rows to calculate cumulative sum
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

    # Format values
    diff1_str = f"{diff1:+.2f} €"
    diff2_str = f"{diff2:+.2f} €"

    new_row = f"""    <tr>
      <td>{date_str}</td>
      <td>{resort}</td>
      <td>{notes if notes else '-'}</td>
      <td>{price:.2f} €</td>
      <td>{new_sum:.2f} €</td>
      <td>{diff1_str}</td>
      <td>{diff2_str}</td>
    </tr>
"""

    if "</table>" in html:
        updated_html = html.replace("</table>", new_row + "  </table>")
    else:
        print("Fehler: </table> Tag nicht gefunden!")
        sys.exit(1)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(updated_html)

    # Return summary for issue comment
    summary = f"""### 🎿 Skitag erfolgreich eingetragen!
* **Datum:** {date_str}
* **Skigebiet:** {resort}
* **Notizen:** {notes if notes else '-'}
* **Tageskarte Jugend (17 Jahre):** {price:.2f} €
* **Summe aller Tageskarten bisher:** {new_sum:.2f} €
* **Saldo zu Saisonkarte 'jugend einzeln' (630 €):** {diff1_str}
* **Saldo zu Saisonkarte 'jugend jugend erwachsen' (525.33 €):** {diff2_str}

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
        gemini_price, gemini_source = query_gemini_for_ticket_price(resort, date_str, notes)
        if gemini_price:
            price = gemini_price
            source = gemini_source
        else:
            price = 55.00
            source = f"Standard-Schätzwert ({gemini_source})"

    print(f"Ermittelter Preis für {resort}: {price} € (Quelle: {source})")
    summary = update_index_html(resort, date_str, notes, price)

    # Output summary to file for action comment
    with open("issue_comment.md", "w", encoding="utf-8") as f:
        f.write(summary)

if __name__ == "__main__":
    main()
