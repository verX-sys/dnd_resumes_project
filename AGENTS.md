# 🐉 Istruzioni Operative per l'Agente (D&D Live Summarizer)

Questo file definisce il contesto, le regole di esecuzione PowerShell e i flussi di lavoro per gli agenti AI che operano nel progetto `c:\Users\peppe\Coding\dnd_project`.

---

## 💻 Ambiente e Regole di Esecuzione PowerShell

1. **Interprete Python del Virtual Environment (`.venv`)**:
   - Invoca **sempre** l'eseguibile Python del virtual environment locale usando forme di comando dirette e prefissabili (così l'utente può approvarle una sola volta con *"Always Allow"*):
     ```powershell
     .\.venv\Scripts\python.exe dnd_summarizer.py <argomenti>
     ```
2. **Modalità di Esecuzione (`run_command`)**:
   - Su Windows, se la sandbox standard restituisce l'errore `CreateProcessSecurityEnvironment: Impossibile trovare il percorso specificato` o se il comando richiede accesso di rete verso **YouTube**, **Gemini API** o **Discord Webhook**, esegui il comando con `BypassSandbox: true`.
   - Mantieni i comandi **semplici e con prefisso costante** (`.\.venv\Scripts\python.exe dnd_summarizer.py ...`) senza concatenare più comandi con `&&` o `;`, così l'auto-approvazione di Antigravity funziona senza richiedere conferma ogni volta.

---

## 🛠️ Comandi PowerShell Principali (`dnd_summarizer.py`)

### 1. Riassumere l'ultima live pubblicata sul canale YouTube (Solo Bozza Markdown Locale)
```powershell
.\.venv\Scripts\python.exe dnd_summarizer.py --update-glossary
```
- Controlla il canale YouTube `https://www.youtube.com/@stefanoleone4578/streams`.
- Scarica la trascrizione in `trascrizioni/<video_id>.txt`.
- Genera il riassunto Markdown in `riassunti/<YYYY-MM>/<YYYY-MM-DD>_<id>_<titolo>.md`.
- Aggiorna `glossario.md` con le nuove voci emerse.
- **Non invia subito su Discord** (permette prima la revisione locale).

### 2. Visualizzare lo storico del canale diviso per mesi (`YYYY-MM`)
```powershell
.\.venv\Scripts\python.exe dnd_summarizer.py --list-months
```
- Scansiona il canale (usando la cache locale `channel_videos_cache.json`) e mostra tutte le puntate raggruppate per mese e il loro stato (`⏳ Da riassumere`, `📝 Solo Riassunto Locale`, `✅ Inviato Discord`).

### 3. Riassumere lo storico di 1 mese intero (in ordine cronologico)
```powershell
.\.venv\Scripts\python.exe dnd_summarizer.py --month YYYY-MM --update-glossary
```
*(Esempio: `.\.venv\Scripts\python.exe dnd_summarizer.py --month 2026-09 --update-glossary`)*
- Elabora tutte le puntate di quel mese dalla più vecchia alla più recente, aggiornando progressivamente `glossario.md` e salvando i file `.md` in `riassunti/YYYY-MM/`.

### 4. Riassumere una trascrizione già presente in locale
```powershell
.\.venv\Scripts\python.exe dnd_summarizer.py --transcript-file "trascrizioni/<nome_file>.txt" --update-glossary
```
- **Alternativa Diretta dell'Agente (Consigliata se le API Gemini sono sovraccariche / 503)**: L'agente può leggere direttamente il file `trascrizioni/<id>.txt` e `glossario.md` con `read_file`, generare lui stesso il riassunto seguendo il formato standard e salvarlo con `write_file` in `riassunti/<YYYY-MM>/`, aggiornando `glossario.md` e `processed_videos.json`.

### 5. Pubblicare su Discord i riassunti locali (dopo la revisione)
- **Pubblica tutti i riassunti locali in sospeso (in ordine cronologico):**
  ```powershell
  .\.venv\Scripts\python.exe dnd_summarizer.py --post-pending
  ```
- **Pubblica solo i riassunti in sospeso di uno specifico mese:**
  ```powershell
  .\.venv\Scripts\python.exe dnd_summarizer.py --post-pending --month YYYY-MM
  ```
- **Pubblica un singolo file Markdown specifico:**
  ```powershell
  .\.venv\Scripts\python.exe dnd_summarizer.py --post-file "riassunti/YYYY-MM/nome_file.md"
  ```

---

## 📖 Regole di Dominio per i Riassunti D&D

Quando l'agente genera o modifica un riassunto (tramite script o direttamente):
1. **Consultare sempre `glossario.md`**:
   - Convertire sempre i nomi reali dei giocatori sentiti nella trascrizione nei rispettivi **Personaggi Giocanti (PG)**:
     - **Stefano** ➔ Dungeon Master
     - **Michele (Mike)** ➔ **Aerial Aldebaran** (Druido — Squadra del Saggio Gideon con Caret, Velura, Serah)
     - **Carlo (Carle)** ➔ **Prometheus** (Mago/Necromante — Squadra del Saggio Baltasar con Cassius Orland, Sivra, Tarnel)
     - **Nicola (Niky)** ➔ **Lucio Malaver** (Barbaro — Squadra legata alla Forgia/Yokul con Errick, Runa, Velendoran)
     - **Giuseppe (Cici)** ➔ **Rogus Harndrekker** (Squadra del Saggio Osiro con Cassian, Fendrel, Liren)
     - **Raffaele (Raffa)** ➔ **Rey Sekigan** (Squadra con Liora, Mirena, Darin)
2. **Struttura obbligatoria dei file in `riassunti/<YYYY-MM>/`**:
   - `# 🐉 <Titolo Episodio>`
   - `📅 **Data Live:** YYYY-MM-DD | 📺 **YouTube:** [<Titolo>](<URL>)`
   - `## 📜 Sinossi della Puntata`
   - `## ⚔️ Vicende delle Squadre e dei Personaggi` (suddivise per PG)
   - `## 🔍 Eventi Chiave, Indizi e Rivelazioni`
   - `## 💎 Reliquie, Oggetti e Ricompense` (inclusi i punteggi delle lezioni)
   - `## 🧭 Prossimi Obiettivi / In Sospeso`
   - `## 📖 Nuove Voci Rilevate per il Glossario`

