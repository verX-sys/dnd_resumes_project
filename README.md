# 🐉 D&D Live Summarizer (YouTube ➔ Markdown Locale ➔ Discord)

Questo progetto controlla il canale YouTube di **Stefano Leone** (`https://www.youtube.com/@stefanoleone4578/streams`), scarica le trascrizioni delle live di D&D, genera i riassunti sfruttando il [glossario.md](./glossario.md) della campagna e **salva prima i riassunti in Markdown in locale** (`riassunti/<YYYY-MM>/`), permettendoti di controllarli o modificarli prima di inviarli su **Discord**.

Il progetto può essere usato direttamente tramite **Agente AI in Chat** (modalità consigliata, che evita i limiti di quota e gli errori `503 / 429` del piano gratuito delle API Gemini esterne) oppure tramite riga di comando con [dnd_summarizer.py](./dnd_summarizer.py).

---

## 🚀 Setup Rapido

1. **Crea l'ambiente virtuale e installa le dipendenze Python**:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```
2. **Configura il file `.env`** con:
   - `DISCORD_WEBHOOK_URL` (per pubblicare i riassunti sul canale Discord)
   - `GEMINI_API_KEY` *(opzionale se usi l'Agente in chat per generare i riassunti)*

---

## 🤖 Utilizzo tramite Agente in Chat (Consigliato)

Grazie alle istruzioni definite in [AGENTS.md](./AGENTS.md), puoi chiedere direttamente in chat all'Agente di occuparsi di tutto. L'Agente userà lo script Python solo per scaricare le trascrizioni (`--fetch-only`) e per inviare i messaggi a Discord, mentre leggerà personalmente le trascrizioni, genererà i riassunti Markdown, aggiornerà [glossario.md](./glossario.md) e registrerà lo stato in `processed_videos.json`.

### 💬 Esempi di Richieste in Chat all'Agente

| Cosa vuoi fare | Esempio di prompt in chat | Cosa fa l'Agente dietro le quinte |
| :--- | :--- | :--- |
| **Consultare lo storico del canale** | *"Mostrami i mesi disponibili e cosa manca da riassumere"* | Esegue `--list-months` e ti mostra in chat tutte le live raggruppate per mese (`YYYY-MM`) con il loro stato (`⏳ Da riassumere`, `📝 Solo Locale`, `✅ Inviato Discord`). |
| **Riassumere l'ultima puntata** | *"Riassumi l'ultima live"* | Scarica la trascrizione dell'ultima live (`--fetch-only`), legge `glossario.md` e la trascrizione, crea il file `.md` in `riassunti/<YYYY-MM>/`, aggiorna `glossario.md` con le nuove voci e aggiorna `processed_videos.json`. |
| **Riassumere un video specifico** | *"Riassumi il video https://www.youtube.com/watch?v=..."* | Scarica la trascrizione di quel video specifico (`--video <ID> --fetch-only`), genera il riassunto Markdown completo e aggiorna glossario e registro. |
| **Recuperare un intero mese passato** | *"Riassumi il mese 2026-09"* | Scarica tutte le trascrizioni del mese (`--month 2026-09 --fetch-only`) ed elabora le puntate **una alla volta in ordine cronologico**, aggiornando `glossario.md` dopo ogni puntata prima di passare alla successiva. |
| **Riassumere una trascrizione locale** | *"Riassumi il file `trascrizioni/xyz.txt`"* | Legge direttamente il file di testo locale e `glossario.md`, genera il riassunto Markdown e aggiorna il glossario. |
| **Revisionare o ritoccare un riassunto** | *"Aggiungi nei prossimi obiettivi del riassunto di ieri che devono parlare con Osiro"* | Modifica direttamente il file `.md` salvato in `riassunti/<YYYY-MM>/` prima dell'invio su Discord. |
| **Pubblicare su Discord** | *"Pubblica i riassunti in sospeso su Discord"* *(oppure *"Pubblica su Discord il mese 2026-09"*)* | Esegue `--post-pending` (o `--post-file`) per inviare sul Webhook di Discord i riassunti pronti in ordine cronologico e segnarli come pubblicati (`✅`). |

---

## 🛠️ Comandi Manuali da Terminale (`dnd_summarizer.py`)

Se preferisci eseguire i comandi manualmente da PowerShell:

### 1️⃣ Consultare lo Storico e Scaricare le Trascrizioni
- **Elenco di tutte le puntate passate sul canale divise per mese (`YYYY-MM`):**
  ```powershell
  py dnd_summarizer.py --list-months
  ```
- **Scaricare solo la trascrizione senza chiamare le API Gemini (per farla riassumere all'Agente):**
  ```powershell
  # Ultima live:
  py dnd_summarizer.py --fetch-only

  # Video specifico:
  py dnd_summarizer.py --video <URL_O_ID> --fetch-only

  # Intero mese:
  py dnd_summarizer.py --month 2026-09 --fetch-only
  ```

### 2️⃣ Pubblicare i Riassunti su Discord
- **Inviare tutti i riassunti locali in attesa (in ordine cronologico):**
  ```powershell
  py dnd_summarizer.py --post-pending
  ```
- **Inviare solo i riassunti in attesa di un mese specifico:**
  ```powershell
  py dnd_summarizer.py --post-pending --month 2026-09
  ```
- **Inviare un singolo file Markdown specifico:**
  ```powershell
  py dnd_summarizer.py --post-file "riassunti/2026-09/nome_file.md"
  ```

### 3️⃣ Generazione tramite API Gemini Esterne (Opzionale)
Se hai una chiave API Gemini attiva in `.env` e vuoi far generare il riassunto direttamente allo script Python:
```powershell
# Ultima live in locale + aggiornamento glossario:
py dnd_summarizer.py --update-glossary

# Storico di un mese in locale + aggiornamento glossario:
py dnd_summarizer.py --month 2026-09 --update-glossary
```
