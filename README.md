# 🐉 D&D Live Summarizer (YouTube ➔ Markdown Locale ➔ Discord)

Questo progetto controlla il canale YouTube di **Stefano Leone** (`https://www.youtube.com/@stefanoleone4578`), scarica le trascrizioni delle live di D&D, le analizza tramite **Gemini (`gemini-3.8-flash`)** sfruttando il [glossario.md](file:///c:/Users/peppe/Coding/dnd_project/glossario.md) della campagna, e **salva prima i riassunti in Markdown in locale** (organizzati per mese), permettendoti di controllarli o modificarli prima di inviarli su **Discord**.

---

## 🚀 Setup Rapido

1. **Installa le dipendenze Python**:
   ```powershell
   pip install -r requirements.txt
   ```
2. **Configura il file `.env`** con `GEMINI_API_KEY` e `DISCORD_WEBHOOK_URL`.

---

## 🛠️ Flusso di Lavoro Consigliato (2 Fasi: Prima Locale, Poi Discord)

Per impostazione predefinita, lo script **salva solo i file `.md` in locale** dentro `riassunti/<YYYY-MM>/` senza pubblicare subito su Discord. In questo modo puoi leggere il riassunto, ritoccare eventuali dettagli e poi inviarlo con un comando!

### 1️⃣ Creare lo Storico (1 mese alla volta)

1. **Vedi l'elenco di tutte le puntate passate sul canale divise per mese (`YYYY-MM`):**
   ```powershell
   python dnd_summarizer.py --list-months
   ```
   *(Mostrerà per ogni mese quante puntate ci sono e quali sono `⏳ Da riassumere`, `📝 Solo Riassunto Locale` o `✅ Inviato Discord`).*

2. **Riassumi in locale tutte le puntate di un mese specifico (in ordine cronologico):**
   ```powershell
   python dnd_summarizer.py --month 2026-09 --update-glossary
   ```
   - Elabora le puntate di quel mese **dalla più vecchia alla più recente**.
   - Con `--update-glossary`, aggiorna [glossario.md](file:///c:/Users/peppe/Coding/dnd_project/glossario.md) dopo ogni puntata, così la puntata successiva conosce già i nuovi PNG/luoghi appena introdotti!
   - Salva tutti i file in `riassunti/2026-09/YYYY-MM-DD_<id>_<titolo>.md`.

3. **Controlla/modifica i file `.md` in locale e poi inviali a Discord:**
   - Per inviare su Discord (in ordine cronologico) tutti i riassunti di quel mese:
     ```powershell
     python dnd_summarizer.py --post-pending --month 2026-09
     ```
   - Oppure per inviare un singolo file Markdown specifico:
     ```powershell
     python dnd_summarizer.py --post-file "riassunti/2026-09/nome_file.md"
     ```

---

### 2️⃣ Appuntamento Settimanale del Martedì (Ultima Puntata)

- **Genera il riassunto dell'ultima live solo in locale (per revisionarlo prima):**
  ```powershell
  python dnd_summarizer.py --update-glossary
  ```
- **Poi, quando sei soddisfatto del file `.md`, pubblicalo su Discord:**
  ```powershell
  python dnd_summarizer.py --post-pending
  ```
- *(Se invece in futuro vorrai generare e pubblicare su Discord in un colpo solo, ti basterà aggiungere `--discord`)*:
  ```powershell
  python dnd_summarizer.py --update-glossary --discord
  ```
