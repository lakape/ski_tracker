# 🎿 ski_tracker

Vollautomatischer Skitage-Tracker und Saisonkarten-Amortisationsrechner für **anien.me**.

## 🚀 Funktionsweise (Vollautomatisch via GitHub Issues)

1. **Neues Issue am Handy erstellen:**
   * Klicke in der GitHub-App auf **Issues** ➔ **Neues Issue** (Vorlage *🎿 Neuer Skitag*).
   * Gib einfach das Skigebiet (z. B. `Nassfeld`), optional das Datum und deine Notizen ein.
2. **Automatische Verarbeitung im Hintergrund:**
   * Eine GitHub Action startet sofort.
   * Google Gemini (via `GEMINI_API_KEY`) recherchiert den tagesaktuellen **Jugendpreis (17 Jahre)** des Skigebiets.
   * Die Tabelle in `index.html` wird automatisch ergänzt, Summen und Differenzen werden neu berechnet.
   * Die Änderungen werden direkt committet und das Issue wird mit einer Bestätigung geschlossen.

## 💶 Vergleichs-Saisonkarten

1. **jugend einzeln**: `630,00 €`
2. **jugend jugend erwachsen**: `525.3333333333333333 €` (~`525,33 €`)
