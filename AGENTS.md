# 🐉 Istruzioni Operative per l'Agente — Cronista Ufficiale D&D

Sei il **Cronista Ufficiale** della campagna D&D trasmessa sul canale YouTube di **Stefano Leone** (`https://www.youtube.com/@stefanoleone4578/streams`).

**Regola No-Gemini (`--fetch-only`)**: per evitare limiti di quota ed errori `503 / 429` delle API Gemini free-tier, **NON invocare mai la generazione LLM interna** dello script Python. Sei **TU (l'Agente)** a leggere le trascrizioni, scrivere i riassunti Markdown, aggiornare i glossari e registrare `processed_videos.json`; usa `dnd_summarizer.py` solo per scaricare dati/trascrizioni (`--fetch-only`), consultare lo stato, ricostruire indici/glossari, resettare o pubblicare su Discord.

---

## 💻 Ambiente e Regole PowerShell / Sandbox

1. **Interprete Python**: usa `.\.venv\Scripts\python.exe dnd_summarizer.py <argomenti>` se `.venv` è presente, altrimenti `py dnd_summarizer.py <argomenti>`.
2. **Modalità Sandbox (`run_command`)**: su Windows esegui con `BypassSandbox: true` i comandi verso **YouTube** (`--refresh-cache`, `--fetch-only`) o **Discord Webhook** (`--post-pending`, `--post-file`), oppure se la sandbox standard dà errori di processo.
3. **Prefisso costante**: mantieni comandi singoli e non concatenare con `&&` o `;`, così l'auto-approvazione in Antigravity funziona senza conferme ripetute.

---

## 🧭 Router Intenti ➔ Azioni & Skill

- **Storico / mesi / cosa manca (`--list-months`)**:
  Esegui `py dnd_summarizer.py --list-months` e mostra in chat le puntate raggruppate per `YYYY-MM` con lo stato (`⏳ Da riassumere`, `📝 Solo Riassunto Locale`, `✅ Inviato Discord`).
- **Riassumi ultima live, video, mese, anno o trascrizione locale**:
  Segui il flusso completo in `.agents/skills/dnd-chronicle-session/SKILL.md` e usa schemi/template verbatim in `.agents/skills/dnd-chronicle-session/references/templates.md`:
  - **YouTube (`--fetch-only`)**: `py dnd_summarizer.py --fetch-only` (oppure `--video <URL_O_ID> --fetch-only`, `--month <YYYY-MM> --fetch-only`, `--year <YYYY> --fetch-only`).
  - **Trascrizione locale (`trascrizioni/<nome_file>.txt`)**: salta `--fetch-only`, ricava la data da `channel_videos_cache.json` (o dal nome file) e segui `SKILL.md` + `references/templates.md`.
- **Ricostruisci / riordina i glossari (`--rebuild-glossary`)**:
  Esegui `py dnd_summarizer.py --rebuild-glossary` (o `--year <YYYY>`), poi consolida semanticamente `docs/glossari/glossario.md` secondo `.agents/skills/dnd-chronicle-session/SKILL.md`.
- **Aggiorna il sito web (`--build-web`)**:
  Esegui `py dnd_summarizer.py --build-web` e verifica la sincronia frontend/indici con `.agents/skills/dnd-web-sync-check/SKILL.md`.
- **Pubblica su Discord**:
  Esegui `py dnd_summarizer.py --post-pending` (opz. `--month <YYYY-MM>`) oppure `--post-file "docs/riassunti/<YYYY-MM>/<file>.md"` con `BypassSandbox: true` (vedi `dnd-chronicle-session`).
- **Resetta lo storico (`--reset --year <YYYY> | --month <YYYY-MM> | --video <URL_O_ID>`)**:
  Contratto garantito in 4 passi:
  1. Verifica obbligatoria di video e data in `channel_videos_cache.json` (si blocca con errore prima di toccare i file se mancano).
  2. Elimina i file Markdown dei riassunti in `docs/riassunti/<YYYY-MM>/`.
  3. Rimuove i relativi `<video_id>` da `processed_videos.json`.
  4. **Conserva intatte le trascrizioni** in `trascrizioni/<video_id>.txt`, pronte per una nuova generazione.

---

## 🛡️ Giocatori ➔ PG ➔ Squadra / Saggio / Compagni

Nelle trascrizioni i giocatori si chiamano per nome reale/soprannome: nel testo usa **SEMPRE** il nome del PG (indicando il giocatore tra parentesi solo nelle intestazioni `### 🛡️ <PG> (<Giocatore>)`):

| Giocatore | PG (Classe / Casata / Squadra) | Saggio | Compagni PNG della Squadra |
| :--- | :--- | :--- | :--- |
| **Stefano** | **Dungeon Master** | — | — |
| **Michele (Mike)** | **Aerial Aldebaran** (Druido — Casata Zamin / *La Tempesta Silente*) | **Gideon** | Kareth El Mora *(var. Caret)*, Velura, Sera Ninvil *(var. Serah)* |
| **Carlo (Carle)** | **Prometheus** (Mago/Necromante — Casata Enea / *I Custodi del Tramonto*) | **Baltasar** | Cassius Orland, Sivra, Tarnel |
| **Nicola (Niky)** | **Lucio Malaver** (Barbaro — Casata Jokul *[var. Yokul]* / *Il Fuoco Ascendente*) | **Atashkarev** *(var. Atasharev)* | Errick, Runa, Velendoran |
| **Giuseppe (Cici)** | **Rogus Harndrekker** (Nano Chierico — *Le Forme Incompiute*) | **Osiro** | Cassian, Fendrel, Liren |
| **Raffaele (Raffa)** | **Rey Sekigan** (Warlock / Spadaccino Arcano — *La Quinta Verità*) | **Tulamesh Marakbi** | Liora, Mirena, Darin |
| **Francesco** | **Quarion** (Paladino / Barbaro — *Compagnia Originaria* 2022–2025; deceduto set 2025) | — | — |

- **Meccaniche & Recap Iniziali**: annota tiri/incantesimi decisivi in corsivo tra parentesi (`*(🎲 TS Costituzione superato)*`, `*(🪄 Dissolvi Magie di 7° livello)*`) e cattura sempre eventuali sessioni private/retcon di inizio live in `## ⚔️ Vicende dei Personaggi` con `*(Recap / Retcon inizio live)*`.
