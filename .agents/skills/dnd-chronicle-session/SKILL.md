---
name: dnd-chronicle-session
description: Step-by-step Chronicler workflow for fetching YouTube transcripts, writing D&D session summaries, updating annual and thematic glossaries, rebuilding web indices, and posting to Discord.
---

# D&D Chronicle Session Workflow

Follow this workflow to process new D&D live sessions or local transcripts. **Never** invoke the script's internal Gemini summarization (`503` / `429` free-tier limits); you (the agent) read transcripts and author all Markdown summaries and glossary updates, using `dnd_summarizer.py` only for YouTube fetching, glossary chronological rebuilds, web index generation, and Discord posting.

> **Templates & Schemas**: Always consult [`references/templates.md`](references/templates.md) for the exact 9-key `processed_videos.json` schema, verbatim summary Markdown template (and 5 glossary categories), `glossario_<YYYY>.md` / `glossario.md` formats (including missing-subtitle entries), editorial rules, local transcript flow, and phonetic distortion examples.

## 1. Python Invocation & Sandbox Rules

- Use `.\.venv\Scripts\python.exe dnd_summarizer.py <args>` when `.venv` exists; otherwise use `py dnd_summarizer.py <args>`.
- On Windows, run commands that access **YouTube** (`--refresh-cache`, `--fetch-only`) or **Discord Webhook** (`--post-pending`, `--post-file`, `--discord`) with `BypassSandbox: true`.
- Keep commands single-purpose without `&&` or `;` chaining so command prefixes stay consistent.

## 2. Clean-Clone / Fresh-Worktree Runtime State Warning

- `.gitignore` excludes `.env`, `processed_videos.json`, `channel_videos_cache.json`, and `trascrizioni/`.
- On a clean clone or fresh worktree, those runtime files are absent. **Before** running `--fetch-only`, `--list-months`, `--rebuild-glossary`, or `--reset`, bootstrap the cache (with `BypassSandbox: true`):

```powershell
py dnd_summarizer.py --refresh-cache
```

- Verify `.env` (Discord webhook credentials) exists before attempting any Discord publish command.

## 3. Chronological Processing & Summary Formatting

1. **Fetch transcripts without calling Gemini** (use `BypassSandbox: true`):
   ```powershell
   py dnd_summarizer.py --month <YYYY-MM> --fetch-only
   # or --year <YYYY> --fetch-only | --video <URL_O_ID> --fetch-only
   ```
   - **Local transcript input (`trascrizioni/<nome_file>.txt`)**: skip `--fetch-only`, read the local transcript plus `docs/glossari/glossario.md` and `docs/glossari/glossario_<YYYY>.md`, derive the session date from `channel_videos_cache.json` (or the filename), and continue with steps 2–5 (see `references/templates.md`).
2. **Process episodes in strict oldest-to-newest order**:
   - Read `docs/glossari/glossario.md`, `docs/glossari/glossario_<YYYY>.md`, and `trascrizioni/<video_id>.txt` completely.
   - Follow the verbatim Markdown template and editorial rules in `references/templates.md`: convert player names to canonical PCs (`Aerial Aldebaran`, `Lucio Malaver`, `Rey Sekigan`, `Rogus Harndrekker`, `Prometheus`, plus `Quarion` for 2022–2025), fix phonetic subtitle distortions, capture early-live private-play/retcon recaps under `## ⚔️ Vicende dei Personaggi` (`*(Recap / Retcon inizio live)*`), and classify `## 📖 Nuove Voci Rilevate per il Glossario` into the 5 allowed categories.
3. **Triage `detect_transcript_anomalies` output (`🔇 Monitoraggio Audio / Buchi Trascrizione`)**:
   - The script flags internal timestamp gaps `>= 45s` (`gap_threshold_sec=45`), initial cuts `>= 60s`, and tail truncations (`>= 90s` missing vs video duration, or transcript ending `< 1800s`).
   - Use surrounding transcript context to distinguish **YouTube copyright mutes / audio cuts** from **table pauses / private-chat actions**, and record the outcome on the summary's `🔇 **Monitoraggio Audio:** ...` line.
4. **Enforce blockquote & generic-title rules**:
   - **Dialogue blockquotes**: always put the clickable timestamp heading first, followed by a **blank `>` line**, then bulleted lines so Markdown does not collapse the title and first line:
     ```markdown
     > 💬 **[[HH:MM:SS - HH:MM:SS]](https://www.youtube.com/watch?v=<VIDEO_ID>&t=<X>h<Y>m<Z>s) — <Titolo della scena>**
     >
     > - **<Nome>:** *"<Battuta>"*
     ```
   - **Generic YouTube titles (`"Mia trasmissione"` / `"Live streaming di Stefano Leone"`)**: never save `_Mia_trasmissione.md`; use a sanitized evocative title (`docs/riassunti/<YYYY-MM>/<YYYY-MM-DD>_<video_id>_<Titolo_Sanitizzato>.md`, max 45 chars `[A-Za-z0-9_]`), and write `[Guarda la Live (<YYYY-MM-DD>)](<URL Video>)` in the header `📺 **YouTube:**` link.
5. **Update `processed_videos.json`**:
   - Add/update `<video_id>` using the exact 9-key schema in `references/templates.md` (`id`, `title`, `url`, `upload_date`, `month`, `summarized_at`, `summary_file`, `posted_to_discord`, `posted_at`).

## 4. Glossaries (`glossario_<YYYY>.md` vs `glossario.md`)

- **Annual chronological diary (`docs/glossari/glossario_<YYYY>.md`)**:
  - Update after **each** episode in strict chronological order using the format in `references/templates.md`, or rebuild chronologically from `docs/riassunti/` + `channel_videos_cache.json` via:
    ```powershell
    py dnd_summarizer.py --rebuild-glossary --year <YYYY>
    ```
  - Never skip sessions lacking YouTube subtitles in `channel_videos_cache.json`; record them chronologically using the 2-line missing-subtitle entry template in `references/templates.md`.
  - `--rebuild-glossary` does **not** blindly append to `docs/glossari/glossario.md`.
- **Campaign encyclopedia (`docs/glossari/glossario.md`) — Semantic Upsert / Merge**:
  - Consolidate **once at the end of a month** (or after `--rebuild-glossary`) by reading summaries oldest-to-newest.
  - Apply the **Encyclopedic Relevance Filter**: include only permanent/recurring NPCs, locations, relics, factions, or persistent mechanics (no single-session tactical micro-events).
  - **Upsert > Create**: search for existing entries (including nicknames/phonetic variants) and enrich them in place within the exact regional/thematic subsection (`Hillsfar`, `Simbar`, `Caderish`, etc. — see `references/templates.md`) instead of creating duplicate bullets; align `🛡️ Membri del Party` and `🏆 Quadro Riepilogativo delle Squadre`.
- **Character chronological diaries (`docs/diari/<slug>.md`) — Semantic Narrative Upsert**:
  - Maintain one chronological diary per PC slug (`aerial`, `lucio`, `rey`, `rogus`, `prometheus`, `quarion`) following the format in `references/templates.md`.
  - After processing new sessions (or reconciling arcs), read each involved PC's diary and insert/update their arc in **strict chronological order** (using `##` / `###` headings so the SPA TOC stays navigable, preserving `(🎲 ...)` / `(🪄 ...)` badges and `> 💬` timestamped quotes), never duplicating existing session entries.

## 5. Build Web Index & Post to Discord

1. Regenerate the frontend indices (`docs/data/manifest.json`, `docs/data/search_index.json`), which scan `docs/riassunti/`, `docs/glossari/`, and `docs/diari/*.md` (`diaries` in manifest, `type: "diario"` in search index):
   ```powershell
   py dnd_summarizer.py --build-web
   ```
2. Publish pending local summaries chronologically to Discord (with `BypassSandbox: true`):
   ```powershell
   py dnd_summarizer.py --post-pending
   # or scoped: py dnd_summarizer.py --post-pending --month <YYYY-MM>
   # or single file: py dnd_summarizer.py --post-file "docs/riassunti/<YYYY-MM>/<file>.md"
   ```
