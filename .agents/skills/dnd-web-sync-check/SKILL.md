---
name: dnd-web-sync-check
description: Checklist and verification commands to keep dnd_summarizer.py, docs/index.html, and generated docs/data/ artifacts in sync after parser, character, or frontend edits.
---

# D&D Web & Parser Sync Check

Run this checklist whenever editing `dnd_summarizer.py`, `docs/index.html`, or files under `docs/riassunti/` and `docs/glossari/`.

## 1. 3-Way Character Sync

Every playable character must stay aligned across three places (or sidebar/card filtering breaks silently):

1. **`dnd_summarizer.py` (`CANONICAL_CHARACTERS`)**:
   - Maps lowercase match keys (`aerial`, `lucio`, `rey`, `rogus`, `prometheus`, `quarion`) to canonical names (`Aerial Aldebaran`, `Lucio Malaver`, `Rey Sekigan`, `Rogus Harndrekker`, `Prometheus`, `Quarion`).
   - `--build-web` matches `### 🛡️ <PG>` headings (via `r"###\s*🛡️\s*([^\n]+)"`) case-insensitively against `CANONICAL_CHARACTERS` so combined headings credit all mentioned PCs when populating `session_entry["characters"]` (`data-chars` on `.session-card-item`).
2. **`docs/index.html` (`CHARACTERS_INFO`, `slug`, & `filterByCharacterAndJump`)**:
   - Each `CHARACTERS_INFO` entry carries a `slug` (`aerial`, `lucio`, `rey`, `rogus`, `prometheus`, `quarion`) matching `docs/diari/<slug>.md` and `#character/<slug>`.
   - Character cards open `#character/<slug>` (`navigateTo('character', slug)`), while `#character-diary-view` preserves `"Filtra sessioni con <PG>"` via `filterByCharacterAndJump(...)` -> `setCharFilter(charKeyword)`.
3. **`docs/index.html` (`.char-pill` buttons & `setCharFilter`)**:
   - Sidebar filter pills (`<button onclick="setCharFilter('...')" data-char="..." class="char-pill ...">`) must use the same first-name token (`all`, `Aerial`, `Lucio`, `Rey`, `Rogus`, `Prometheus`, `Quarion`).
   - `setCharFilter(charName)` activates `pill.dataset.char === charName` and `applySidebarFilters` checks `chars.includes(currentCharacterFilter.toLowerCase())` against `data-chars`.

Verification grep:
```powershell
Select-String -Path "dnd_summarizer.py" -Pattern "CANONICAL_CHARACTERS" -Context 0,8
Select-String -Path "docs/index.html" -Pattern "data-char=|CHARACTERS_INFO|function setCharFilter"
```

## 2. Parser & SPA Rendering Invariants

Preserve the Markdown contract shared between Python generators/parsers and the browser renderer:

- **`format_summary_as_markdown` (`dnd_summarizer.py`)**:
  - Emits `# 🐉 <Title>`, `📅 **Data Live:** <YYYY-MM-DD> | 📺 **YouTube:** [<label>](<url>)`, `🔇 **Monitoraggio Audio:** <note>`, `## 📜 Sinossi della Puntata`, `## ⚔️ Vicende dei Personaggi`, `### 🛡️ <PG> — *<Squad>*`, `## 🔍 ...`, `## 💎 ...`, `## 🧭 ...`, and `## 📖 Nuove Voci Rilevate per il Glossario`.
- **`parse_summary_markdown` & `rebuild_glossaries_from_summaries` (`dnd_summarizer.py`)**:
  - Skips files containing `_CON_DIALOGHI` in the filename.
  - Extracts `video_id` from `YYYY-MM-DD_<11-char-id>_...` filename or `watch?v=<11-char-id>` URL, then requires a cached `startTimestamp`/`upload_date` in `channel_videos_cache.json` via `get_video_info_from_cache` (hard-fails if missing).
  - Parses `# 🐉 ...` and bullet entries under `## 📖 Nuove Voci Rilevate per il Glossario`.
  - `rebuild_glossaries_from_summaries` rewrites chronological `docs/glossari/glossario_<YYYY>.md` (including missing-subtitle sessions from `channel_videos_cache.json`) and never blindly appends to `docs/glossari/glossario.md`.
- **`renderEnhancedMarkdown` (`docs/index.html`)**:
  - Strips the top `# ...` heading plus `📅 **Data Live:**` and `🔇 **Monitoraggio Audio:**` lines before `marked.parse(...)`.
  - Converts inline `(🎲 ...)` to `<span class="dnd-dice-badge">` and `(🪄 ...)` to `<span class="dnd-spell-badge">`.
  - Converts any `<blockquote>` containing `href="https://www.youtube.com` or `💬` into `<div class="dnd-quote-card">`.
- **`buildTableOfContents(container)` (`docs/index.html`)**:
  - Builds `#toc-nav` strictly from `container.querySelectorAll('h2, h3')`; keep section headings at `##` / `###` so session, glossary, and character diary TOCs stay navigable.
- **`loadCharacterDiary(slug)` & `#character-diary-view` (`docs/index.html`)**:
  - Renders `./diari/${slug}.md` with `renderEnhancedMarkdown()` + `buildTableOfContents()`, shows `#toc-sidebar` when `#character-diary-view` is open, and resets to `#characters-grid-view` (hiding `#toc-sidebar`) when switching back to `#characters`.

## 3. Web Data Regeneration & Static Fallback Counts

Whenever summaries, glossaries, or character diaries (`docs/diari/*.md`) change, regenerate the JSON indices:

```powershell
.\.venv\Scripts\python.exe dnd_summarizer.py --build-web
# or if no .venv:
py dnd_summarizer.py --build-web
```

- Verify `docs/data/manifest.json` and `docs/data/search_index.json` were updated (`total_sessions`, `total_glossaries`, `years`, `diaries` entries with `id`, `title`, `path`, `word_count`, `line_count`, and search docs with `type: "diario"`, `date: "Diario PG"`).
- Check hardcoded fallback counters in `docs/index.html` (`#sidebar-stats`, `#search-subtitle-sessions`, `#search-subtitle-glossaries`, `#stat-total-sessions`, `#stat-total-years`, `#stat-total-glossaries`, `onManifestLoaded` fallback literals, and the search intro fallback) if updating the baseline numbers shown before `manifest.json` loads.

```powershell
Select-String -Path "docs/index.html" -Pattern "stat-total-|sidebar-stats|search-subtitle-"
```

## 4. Local Preview

Browsers block `fetch('./data/manifest.json')` and `fetch('./data/search_index.json')` over `file:///`. Always preview via an HTTP server rooted at `docs/`:

```powershell
py -m http.server -d docs 8000
```
