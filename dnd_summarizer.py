"""
Script per il recupero automatico delle live D&D da YouTube (ultima puntata o storico a blocchi mensili),
generazione e salvataggio dei riassunti in Markdown in locale tramite Gemini API (con supporto al glossario),
e pubblicazione separata/su richiesta su Discord tramite Webhook.
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    import requests
except ImportError:
    requests = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
except ImportError:
    genai = None

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:  # type: ignore
        pass

    def Field(*args, **kwargs):  # type: ignore
        return None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).parent.resolve()
DOCS_DIR = BASE_DIR / "docs"
DOCS_DATA_DIR = DOCS_DIR / "data"
GLOSSARIES_DIR = DOCS_DIR / "glossari"
GLOSSARY_PATH = GLOSSARIES_DIR / "glossario.md"
PROCESSED_PATH = BASE_DIR / "processed_videos.json"
SUMMARIES_DIR = DOCS_DIR / "riassunti"
TRANSCRIPTS_DIR = BASE_DIR / "trascrizioni"


def get_yearly_glossary_path(date_or_year: str = "") -> Path:
    """Restituisce il percorso del glossario annuale (es. `glossari/glossario_2026.md`)."""
    clean = (date_or_year or "").replace("-", "").strip()
    if len(clean) >= 4 and clean[:4].isdigit():
        year = clean[:4]
    else:
        year = datetime.now().strftime("%Y")
    return GLOSSARIES_DIR / f"glossario_{year}.md"


def load_glossary_context(upload_date: str = "") -> str:
    """Legge sia il glossario generale (`glossari/glossario.md`) sia quello dell'anno in esame (`glossari/glossario_<YYYY>.md`)."""
    parts = []
    if GLOSSARY_PATH.exists():
        parts.append(GLOSSARY_PATH.read_text(encoding="utf-8"))
    yearly_path = get_yearly_glossary_path(upload_date)
    if yearly_path.exists() and yearly_path != GLOSSARY_PATH:
        parts.append(yearly_path.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)

DEFAULT_CHANNEL_URL = os.getenv(
    "YOUTUBE_CHANNEL_URL", "https://www.youtube.com/@stefanoleone4578/streams"
)


# =====================================================================
# Modelli Pydantic per lo Structured Output di Gemini
# =====================================================================

class GlossaryEntry(BaseModel):
    nome: str = Field(
        description="Il nome corretto (o presunto tale) del nuovo PNG, luogo, oggetto, reliquia o fazione."
    )
    categoria: str = Field(
        description="Categoria: 'PNG', 'Luogo', 'Oggetto/Reliquia', 'Fazione/Terminologia', o 'Aggiornamento Squadra'."
    )
    descrizione: str = Field(
        description="Breve descrizione di chi/cosa è e del suo ruolo emerso nella sessione."
    )
    varianti_trascrizione: List[str] = Field(
        default_factory=list,
        description="Eventuali storpiature fonetiche trovate nella trascrizione automatica di YouTube (es. 'Cici', 'Carle', nomi storpiati).",
    )


class CharacterEvent(BaseModel):
    personaggio: str = Field(
        description="Nome del PG e tra parentesi il giocatore (es. 'Aerial Aldebaran (Mike)')."
    )
    squadra_saggio: str = Field(
        description="Nome del Saggio e/o compagni di squadra PNG coinvolti."
    )
    eventi: str = Field(
        description="Riassunto dettagliato di cosa ha fatto questo PG/squadra durante la puntata."
    )


class SessionSummaryOutput(BaseModel):
    titolo_episodio: str = Field(
        description="Un titolo evocativo per la sessione (o il titolo della puntata)."
    )
    nota_audio_copyright: str = Field(
        default="Nessun taglio o segmento mutato rilevato.",
        description="Breve appunto su eventuali segmenti mutati da YouTube (per copyright o problemi tecnici) o buchi di trascrizione rilevati, indicando i minutaggi [HH:MM:SS - HH:MM:SS]. Se l'audio è integro, indica 'Nessun taglio rilevato'.",
    )
    sinossi_breve: str = Field(
        description="Un'introduzione narrativa di 3-5 righe che riassume il cuore della sessione."
    )
    vicende_per_personaggio: List[CharacterEvent] = Field(
        description="Le vicende accadute nella sessione, suddivise per ciascuno dei PG presenti (visto che sono divisi nelle squadre del Torneo dell'Ambizione) o per scene principali."
    )
    eventi_chiave_e_rivelazioni: List[str] = Field(
        description="Elenco puntato dei colpi di scena, indizi risolti, scoperte sulla Mano Nera, il Custode o il Torneo dell'Ambizione."
    )
    loot_e_reliquie: List[str] = Field(
        description="Oggetti, reliquie, ricompense, oro o contratti ottenuti/persi nella sessione."
    )
    prossimi_obiettivi: List[str] = Field(
        description="Cosa devono fare i personaggi nella prossima sessione (cliffhanger o appuntamenti fissati)."
    )
    nuove_voci_glossario: List[GlossaryEntry] = Field(
        default_factory=list,
        description="Nuovi PNG, luoghi, oggetti o aggiornamenti importanti di stato non ancora presenti nel glossario fornito.",
    )


# =====================================================================
# Gestione Registro Locale (processed_videos.json)
# =====================================================================

def load_processed_videos() -> dict:
    if PROCESSED_PATH.exists():
        try:
            with open(PROCESSED_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_processed_videos(data: dict) -> None:
    with open(PROCESSED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_video_summary(
    video_info: dict, summary_path: Path, posted_to_discord: bool = False
) -> None:
    processed = load_processed_videos()
    vid_id = video_info["id"]
    existing = processed.get(vid_id, {})

    processed[vid_id] = {
        "id": vid_id,
        "title": video_info.get("title", ""),
        "url": video_info.get("url", f"https://www.youtube.com/watch?v={vid_id}"),
        "upload_date": video_info.get("upload_date", existing.get("upload_date", "")),
        "month": format_month_from_upload_date(
            video_info.get("upload_date", existing.get("upload_date", ""))
        ),
        "summarized_at": datetime.now().isoformat(),
        "summary_file": str(summary_path.relative_to(BASE_DIR)),
        "posted_to_discord": posted_to_discord or existing.get("posted_to_discord", False),
        "posted_at": datetime.now().isoformat()
        if posted_to_discord
        else existing.get("posted_at"),
    }
    save_processed_videos(processed)


def mark_video_posted(video_id: str) -> None:
    processed = load_processed_videos()
    if video_id in processed:
        processed[video_id]["posted_to_discord"] = True
        processed[video_id]["posted_at"] = datetime.now().isoformat()
        save_processed_videos(processed)


def format_date_from_yyyymmdd(date_str: str) -> str:
    """Converte '20261027' in '2026-10-27'."""
    if date_str and len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return datetime.now().strftime("%Y-%m-%d")


def format_month_from_upload_date(date_str: str) -> str:
    """Converte '20261027' o '2026-10-27' in '2026-10'."""
    clean = (date_str or "").replace("-", "")
    if len(clean) >= 6 and clean[:6].isdigit():
        return f"{clean[:4]}-{clean[4:6]}"
    return "sconosciuto"


# =====================================================================
# Funzioni YouTube (Catalogo canale, Metadati e Trascrizioni)
# =====================================================================

def extract_video_id(url_or_id: str) -> str:
    """Estrae il video ID da un URL YouTube o restituisce l'ID stesso."""
    patterns = [
        r"(?:v=|\/videos\/|embed\/|youtu\.be\/|\/v\/|\/e\/|watch\?v=|&v=|\/live\/)([^#\&\?\n]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    if len(url_or_id.strip()) == 11:
        return url_or_id.strip()
    raise ValueError(f"Impossibile estrarre un ID video YouTube valido da: {url_or_id}")


def extract_true_stream_date(info: dict) -> str:
    """
    Estrae la vera data di trasmissione della live da un dizionario yt-dlp:
    1. `release_timestamp` (corrispondente a `liveBroadcastDetails.startTimestamp`, convertito in ora locale)
    2. `release_date` (data di inizio della live)
    3. `timestamp` / `upload_date` (solo come fallback per video non-live; attenzione: su YouTube
       `uploadDate`/`publishDate` viene sovrascritto quando un vecchio flusso viene rinominato o reso pubblico!).
    """
    if info.get("release_timestamp"):
        return datetime.fromtimestamp(info["release_timestamp"]).strftime("%Y%m%d")
    if info.get("release_date"):
        return str(info["release_date"]).replace("-", "").strip()
    if info.get("timestamp"):
        return datetime.fromtimestamp(info["timestamp"]).strftime("%Y%m%d")
    return (info.get("upload_date") or "").replace("-", "").strip()


def get_video_metadata(video_id: str, ignore_cache: bool = False) -> dict:
    """Recupera titolo, data reale di trasmissione (YYYYMMDD) e URL di un singolo video tramite yt-dlp (o cache)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    channel_cache = load_channel_cache()
    if not ignore_cache and video_id in channel_cache and channel_cache[video_id].get("upload_date"):
        return {
            "id": video_id,
            "title": channel_cache[video_id].get("title", f"Sessione D&D ({video_id})"),
            "url": url,
            "upload_date": channel_cache[video_id].get("upload_date", ""),
            "duration": None,
            "live_status": None,
        }

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": {"youtube": {"player_client": ["ios", "mweb", "android", "web_creator"]}},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            upload_date = extract_true_stream_date(info)
            return {
                "id": video_id,
                "title": info.get("title", f"Sessione D&D ({video_id})"),
                "url": url,
                "upload_date": upload_date,
                "duration": info.get("duration"),
                "live_status": info.get("live_status"),
            }
    except Exception:
        return {
            "id": video_id,
            "title": f"Sessione D&D ({video_id})",
            "url": url,
            "upload_date": "",
            "duration": None,
            "live_status": None,
        }


CACHE_PATH = BASE_DIR / "channel_videos_cache.json"


def load_channel_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_channel_cache(cache: dict) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def get_video_info_from_cache(video_id: str) -> dict:
    """
    Recupera obbligatoriamente le informazioni dello streaming da `channel_videos_cache.json`.
    Se il file cache non esiste o il video (o la sua upload_date) è assente, blocca l'esecuzione.
    """
    if not CACHE_PATH.exists():
        print(
            f"❌ ERRORE BLOCCANTE: Il file '{CACHE_PATH.name}' non esiste.\n"
            "   Impossibile recuperare le informazioni dello streaming senza la cache del canale."
        )
        sys.exit(1)

    channel_cache = load_channel_cache()
    if video_id not in channel_cache:
        print(
            f"❌ ERRORE BLOCCANTE: Il video '{video_id}' non è presente in '{CACHE_PATH.name}'.\n"
            "   Esegui prima `--list-months` o `--refresh-cache` per censire il video nella cache."
        )
        sys.exit(1)

    entry = channel_cache[video_id]
    upload_date = (entry.get("upload_date") or "").replace("-", "").strip()
    title = (entry.get("title") or "").strip()
    if not upload_date or not title:
        print(
            f"❌ ERRORE BLOCCANTE: Informazioni dello streaming incomplete in '{CACHE_PATH.name}' "
            f"per il video '{video_id}' (title='{title}', upload_date='{upload_date}')."
        )
        sys.exit(1)

    return {
        "id": video_id,
        "title": title,
        "url": entry.get("url", f"https://www.youtube.com/watch?v={video_id}"),
        "upload_date": upload_date,
        "month": format_month_from_upload_date(upload_date),
        "duration": entry.get("duration"),
        "live_status": entry.get("live_status"),
    }


def get_cached_videos(
    year: Optional[str] = None,
    month: Optional[str] = None,
) -> List[dict]:
    """
    Restituisce la lista dei video (ordinati cronologicamente dal più vecchio al più recente)
    leggendo esclusivamente `channel_videos_cache.json`.
    Se la cache è assente, vuota o se una trascrizione locale non ha i metadati in cache, blocca l'esecuzione.
    """
    if not CACHE_PATH.exists():
        print(
            f"❌ ERRORE BLOCCANTE: Il file '{CACHE_PATH.name}' non esiste.\n"
            "   Impossibile procedere senza le informazioni dello streaming in cache."
        )
        sys.exit(1)

    channel_cache = load_channel_cache()
    if not channel_cache:
        print(f"❌ ERRORE BLOCCANTE: '{CACHE_PATH.name}' è vuoto o non valido.")
        sys.exit(1)

    # Verifica bloccante: ogni trascrizione presente in trascrizioni/<id>.txt deve avere info valide in cache
    if TRANSCRIPTS_DIR.exists():
        for t_file in sorted(TRANSCRIPTS_DIR.glob("*.txt")):
            _ = get_video_info_from_cache(t_file.stem)

    results = []
    for vid_id, raw_entry in channel_cache.items():
        raw_date = (raw_entry.get("upload_date") or "").replace("-", "").strip()
        if not raw_date:
            # Se non stiamo filtrando per anno/mese e c'è un video senza data, segnala se rilevante
            continue
        raw_month = format_month_from_upload_date(raw_date)
        if month and raw_month != month:
            continue
        if year and not raw_date.startswith(str(year)):
            continue
        info = get_video_info_from_cache(vid_id)
        results.append(info)

    results.sort(key=lambda x: x.get("upload_date", ""))
    return results


def parse_date_from_title(title: str) -> str:
    """
    Prova a estrarre una data dal titolo del video se presente
    (es. '15/10/2026', '15-10-2026', '2026-10-15', '15.10.26') -> restituisce 'YYYYMMDD' o ''.
    """
    # Formato DD/MM/YYYY o DD-MM-YYYY o DD.MM.YYYY
    m = re.search(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](20\d{2})\b", title)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}{month:02d}{day:02d}"

    # Formato YYYY-MM-DD o YYYY/MM/DD
    m2 = re.search(r"\b(20\d{2})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})\b", title)
    if m2:
        year, month, day = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}{month:02d}{day:02d}"

    return ""


def fetch_channel_videos(channel_url: str, max_videos: int = 150) -> List[dict]:
    """
    Recupera la lista delle live dal canale YouTube (/streams).
    Salva le date e i metadati in `channel_videos_cache.json` così i controlli
    successivi sono istantanei!
    """
    target_url = channel_url
    if not target_url.endswith("/streams") and not target_url.endswith("/videos"):
        target_url = target_url.rstrip("/") + "/streams"

    ydl_opts = {
        "extract_flat": True,
        "playlistend": max_videos,
        "quiet": True,
        "no_warnings": True,
    }

    raw_entries = []
    seen_ids = set()

    print(f"🔍 Lettura catalogo canale YouTube: {target_url} ...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            entries = info.get("entries", []) if info else []
            for entry in entries:
                if not entry:
                    continue
                vid_id = entry.get("id")
                if not vid_id or vid_id in seen_ids:
                    continue
                live_status = entry.get("live_status")
                if live_status in ("is_upcoming", "is_live"):
                    continue
                seen_ids.add(vid_id)
                raw_entries.append(entry)
    except Exception as e:
        raise RuntimeError(f"Errore durante la lettura di {target_url}: {e}")

    if not raw_entries:
        raise RuntimeError(f"Nessun video trovato sul canale: {target_url}")

    processed_cache = load_processed_videos()
    channel_cache = load_channel_cache()
    cache_updated = False
    results = []

    total = len(raw_entries)
    for idx, entry in enumerate(raw_entries, start=1):
        vid_id = entry["id"]
        title = entry.get("title", f"Sessione D&D ({vid_id})")
        duration = entry.get("duration")
        live_status = entry.get("live_status")

        upload_date = extract_true_stream_date(entry)

        # 1. Controlla se è già nella cache del canale o dei video processati
        if vid_id in channel_cache:
            if not upload_date:
                upload_date = channel_cache[vid_id].get("upload_date", "")
                title = channel_cache[vid_id].get("title", title)
            if duration is None:
                duration = channel_cache[vid_id].get("duration")
            if live_status is None:
                live_status = channel_cache[vid_id].get("live_status")
        if not upload_date and vid_id in processed_cache:
            upload_date = processed_cache[vid_id].get("upload_date", "").replace("-", "")

        # 2. Prova a estrarre la data dal titolo se presente
        if not upload_date:
            upload_date = parse_date_from_title(title)

        # 3. Se ancora non abbiamo la data, interroga YouTube per il singolo video (solo la prima volta!)
        if not upload_date:
            print(f"   ⏳ [{idx}/{total}] Recupero data pubblicazione per: {title[:55]}...")
            meta = get_video_metadata(vid_id, ignore_cache=True)
            upload_date = meta.get("upload_date", "")
            title = meta.get("title") or title
            if meta.get("duration") is not None:
                duration = meta.get("duration")
            if meta.get("live_status") is not None:
                live_status = meta.get("live_status")

        needs_cache_update = (
            vid_id not in channel_cache
            or channel_cache[vid_id].get("upload_date") != upload_date
            or "duration" not in channel_cache[vid_id]
            or "live_status" not in channel_cache[vid_id]
            or (duration is not None and channel_cache[vid_id].get("duration") is None)
            or (live_status is not None and channel_cache[vid_id].get("live_status") is None)
        )
        if needs_cache_update:
            channel_cache[vid_id] = {
                "id": vid_id,
                "title": title,
                "upload_date": upload_date,
                "duration": duration,
                "live_status": live_status,
            }
            assert "duration" in channel_cache[vid_id]
            save_channel_cache(channel_cache)
            cache_updated = True

        results.append(
            {
                "id": vid_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "upload_date": upload_date,
                "month": format_month_from_upload_date(upload_date),
                "duration": duration,
                "live_status": live_status,
            }
        )

    if cache_updated:
        save_channel_cache(channel_cache)

    return results


def format_seconds(seconds: float) -> str:
    """Converte secondi in formato [HH:MM:SS]."""
    total_sec = int(seconds)
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"[{hrs:02d}:{mins:02d}:{secs:02d}]"


def detect_transcript_anomalies(
    transcript: str,
    video_duration: Optional[int] = None,
    gap_threshold_sec: int = 45,
) -> List[str]:
    """
    Analizza i timestamp [HH:MM:SS] della trascrizione per individuare:
    - Salti temporali interni >= gap_threshold_sec (possibili mute copyright o silenzi prolungati)
    - Tagli iniziali (se la trascrizione inizia dopo [00:01:00])
    - Troncamenti finali (se la trascrizione termina molto prima della durata del video o dura < 30 min)
    """
    parsed = []
    for line in transcript.splitlines():
        m = re.match(r"^\[(\d+):(\d+):(\d+)\]\s*(.*)", line)
        if m:
            h, mins, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            sec = h * 3600 + mins * 60 + s
            ts_str = f"[{h:02d}:{mins:02d}:{s:02d}]"
            text = m.group(4).strip()
            parsed.append((sec, ts_str, text))

    if not parsed:
        return ["⚠️ Nessun timestamp valido trovato nella trascrizione."]

    anomalies = []
    first_sec, first_ts, _ = parsed[0]
    last_sec, last_ts, last_text = parsed[-1]

    # 1. Controllo taglio iniziale
    if first_sec >= 60:
        anomalies.append(
            f"Taglio/assenza audio iniziale: [00:00:00 ➔ {first_ts}] ({first_sec}s senza parlato)"
        )

    # 2. Controllo buchi interni
    for i in range(len(parsed) - 1):
        curr_sec, curr_ts, curr_text = parsed[i]
        next_sec, next_ts, next_text = parsed[i + 1]
        gap = next_sec - curr_sec
        if gap >= gap_threshold_sec:
            mins_gap = gap / 60.0
            anomalies.append(
                f"Buco di {gap}s (~{mins_gap:.1f} min) da {curr_ts} a {next_ts} "
                f"| Prima: \"{curr_text[:45]}\" ➔ Dopo: \"{next_text[:45]}\""
            )

    # 3. Controllo troncamento finale
    if video_duration and (video_duration - last_sec) >= 90:
        missing = int(video_duration - last_sec)
        anomalies.append(
            f"Possibile mute/troncamento finale da {last_ts} a {format_seconds(video_duration)} "
            f"({missing}s / ~{missing/60:.1f} min mancanti alla fine del video)"
        )
    elif last_sec < 1800:
        anomalies.append(
            f"Trascrizione insolitamente breve/troncata: termina a {last_ts} "
            f"(ultima frase: \"{last_text[:50]}\") — probabile mute copyright esteso o live interrotta."
        )

    return anomalies


def fetch_transcript(video_id: str) -> str:
    """
    Scarica la trascrizione in italiano dal video YouTube.
    Usa come metodo primario `youtube-transcript-api` e come fallback `yt-dlp`.
    """
    print(f"📥 Scaricamento trascrizione per il video ID: {video_id} ...")

    # Metodo 1: youtube-transcript-api
    try:
        if hasattr(YouTubeTranscriptApi, "fetch"):
            ytt_api = YouTubeTranscriptApi()
            fetched = ytt_api.fetch(video_id, languages=["it", "it-IT", "en"])
            lines = []
            for snippet in fetched:
                start = getattr(snippet, "start", 0.0)
                text = getattr(snippet, "text", "")
                lines.append(f"{format_seconds(start)} {text}")
            if lines:
                return "\n".join(lines)
        else:
            transcript_list = YouTubeTranscriptApi.get_transcript(
                video_id, languages=["it", "it-IT", "en"]
            )
            lines = [
                f"{format_seconds(item['start'])} {item['text']}"
                for item in transcript_list
            ]
            if lines:
                return "\n".join(lines)
    except Exception as e:
        print(f"ℹ️ youtube-transcript-api non riuscito ({e}), provo fallback con yt-dlp...")

    # Metodo 2: Fallback con yt-dlp
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["it", "it.*"],
            "subtitlesformat": "json3",
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "extractor_args": {"youtube": {"player_client": ["ios", "mweb", "android", "web_creator"]}},
        }
        url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        for file in os.listdir(tmpdir):
            if file.endswith(".json3"):
                sub_path = os.path.join(tmpdir, file)
                with open(sub_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                events = data.get("events", [])
                lines = []
                for event in events:
                    segs = event.get("segs")
                    if not segs:
                        continue
                    text = "".join(s.get("utf8", "") for s in segs).strip()
                    if not text or text == "\n":
                        continue
                    start_ms = event.get("tStartMs", 0)
                    lines.append(f"{format_seconds(start_ms / 1000.0)} {text}")
                if lines:
                    return "\n".join(lines)

    raise RuntimeError(
        f"Impossibile trovare sottotitoli o trascrizioni per il video {video_id}."
    )


# =====================================================================
# Generazione Riassunto con Gemini API (Interactions API)
# =====================================================================

def generate_summary_with_gemini(
    transcript: str, glossary_text: str, video_title: str
) -> SessionSummaryOutput:
    """
    Invia la trascrizione e il glossario a Gemini (gemini-3.8-flash) usando
    la Interactions API con Structured Output (Pydantic).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "inserisci_qui_la_tua_gemini_api_key":
        raise ValueError(
            "GEMINI_API_KEY mancante! Configura la chiave nel file .env."
        )

    client = genai.Client(api_key=api_key)

    system_instruction = f"""Sei il Cronista Ufficiale di una campagna di Dungeons & Dragons (D&D).
Il tuo compito è analizzare la trascrizione automatica di YouTube di una sessione di gioco (spesso piena di errori fonetici dovuti al riconoscimento vocale automatico) e produrre un riassunto completo, avvincente, ben strutturato e fedele agli eventi accaduti.

REGOLE FONDAMENTALI:
1. USA IL GLOSSARIO: Qui sotto trovi il Glossario ufficiale della campagna. Nella trascrizione sentirai spesso i giocatori chiamarsi per nome reale (Stefano il DM, Mike/Michele, Carle/Carlo, Niky/Nicola, Cici/Giuseppe, Raffa/Raffaele): nel riassunto usa SEMPRE i nomi dei loro Personaggi Giocanti (Aerial Aldebaran, Prometheus, Lucio Malaver, Rogus Harndrekker, Rey Sekigan), indicando il giocatore tra parentesi solo la prima volta o nelle intestazioni.
2. CORREGGI LE STORPIATURE FONETICHE: I sottotitoli automatici di YouTube storpiano i nomi fantasy (es. "Caret", "Velendoran", "Osiro", "Baltasar", "Gideon", "Yokul", "Harndrekker", "Sekigan"). Usa il contesto e il glossario per scrivere sempre i nomi corretti.
3. DISTINGUI GIOCO DA FUORI-GIOCO: Ignora le chiacchiere iniziali/finali fuori gioco, problemi tecnici di audio/streaming o battute off-game, concentrandoti sulla trama, sui dialoghi importanti, sui combattimenti, sulle indagini (Torneo dell'Ambizione, Mano Nera, il Custode) e sulle scelte dei personaggi.
4. AGGIORNAMENTO GLOSSARIO: Individua eventuali nuovi PNG, luoghi, reliquie o importanti cambi di stato delle squadre emersi nella puntata per proporre aggiornamenti al glossario.

--- INIZIO GLOSSARIO DELLA CAMPAGNA ---
{glossary_text}
--- FINE GLOSSARIO DELLA CAMPAGNA ---
"""

    prompt = f"""Analizza la seguente trascrizione della sessione intitolata "{video_title}" e genera il riassunto completo seguendo lo schema richiesto.

--- INIZIO TRASCRIZIONE ---
{transcript}
--- FINE TRASCRIZIONE ---
"""

    models_to_try = [
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-4-argon",
    ]

    last_error = None
    for model_name in models_to_try:
        for attempt in range(1, 3):
            try:
                print(
                    f"🧠 Analisi della trascrizione e generazione del riassunto con Gemini ({model_name}, tentativo {attempt}/2)..."
                )
                interaction = client.interactions.create(
                    model=model_name,
                    system_instruction=system_instruction,
                    input=prompt,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": SessionSummaryOutput.model_json_schema(),
                    },
                )
                return SessionSummaryOutput.model_validate_json(interaction.output_text)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "503" in err_str or "high demand" in err_str or "unavailable" in err_str or "429" in err_str or "overloaded" in err_str:
                    wait_sec = 5 * attempt
                    print(
                        f"⚠️ Il modello {model_name} è temporaneamente sovraccarico (503/429). "
                        f"Attendo {wait_sec}s prima di riprovare o passare al modello successivo..."
                    )
                    time.sleep(wait_sec)
                else:
                    raise e

    raise RuntimeError(f"Tutti i modelli Gemini sono attualmente sovraccarichi. Ultimo errore: {last_error}")


# =====================================================================
# Formattazione Markdown e Invio a Discord
# =====================================================================

def format_summary_as_markdown(
    summary: SessionSummaryOutput, video_info: dict
) -> str:
    """Formatta l'output strutturato di Gemini in un documento Markdown."""
    date_formatted = format_date_from_yyyymmdd(video_info.get("upload_date", ""))
    audio_note = getattr(summary, "nota_audio_copyright", "Nessun taglio rilevato.")
    raw_title = (video_info.get("title") or "").strip()
    if not raw_title or raw_title.lower() in ("mia trasmissione", "live streaming di stefano leone"):
        yt_label = f"Guarda la Live ({date_formatted})"
    else:
        yt_label = raw_title

    lines = [
        f"# 🐉 {summary.titolo_episodio}",
        f"📅 **Data Live:** {date_formatted} | 📺 **YouTube:** [{yt_label}]({video_info['url']})",
        f"🔇 **Monitoraggio Audio:** {audio_note}",
        "",
        "## 📜 Sinossi della Puntata",
        summary.sinossi_breve,
        "",
        "---",
        "",
        "## ⚔️ Vicende dei Personaggi",
        "",
    ]

    for char_ev in summary.vicende_per_personaggio:
        lines.append(f"### 🛡️ {char_ev.personaggio} — *{char_ev.squadra_saggio}*")
        lines.append(char_ev.eventi)
        lines.append("")

    if summary.eventi_chiave_e_rivelazioni:
        lines.append("---")
        lines.append("")
        lines.append("## 🔍 Eventi Chiave, Indizi e Rivelazioni")
        for ev in summary.eventi_chiave_e_rivelazioni:
            lines.append(f"- {ev}")
        lines.append("")

    if summary.loot_e_reliquie:
        lines.append("---")
        lines.append("")
        lines.append("## 💎 Reliquie, Oggetti e Ricompense")
        for item in summary.loot_e_reliquie:
            lines.append(f"- {item}")
        lines.append("")

    if summary.prossimi_obiettivi:
        lines.append("---")
        lines.append("")
        lines.append("## 🧭 Prossimi Obiettivi / In Sospeso")
        for obj in summary.prossimi_obiettivi:
            lines.append(f"- {obj}")
        lines.append("")

    if summary.nuove_voci_glossario:
        lines.append("---")
        lines.append("")
        lines.append("## 📖 Nuove Voci Rilevate per il Glossario")
        for entry in summary.nuove_voci_glossario:
            varianti = (
                f" *(trascritto anche come: {', '.join(entry.varianti_trascrizione)})*"
                if entry.varianti_trascrizione
                else ""
            )
            lines.append(
                f"- **{entry.nome}** [{entry.categoria}]: {entry.descrizione}{varianti}"
            )
        lines.append("")

    return "\n".join(lines)


def split_message_for_discord(text: str, max_length: int = 1950) -> List[str]:
    """
    Divide un testo lungo in blocchi <= 1950 caratteri (il limite di Discord è 2000),
    mantenendo uniti i riquadri di dialogo (`> ...`) e i paragrafi ed evitando di
    lasciare titoli (`## ` / `### `) orfani a fine messaggio.
    """
    # Raggruppa le righe in blocchi logici (tenendo insieme i blocchi citazione `>` e i titoli col blocco successivo)
    raw_blocks: List[str] = []
    current_lines: List[str] = []
    in_quote = False

    for line in text.split("\n"):
        stripped = line.strip()
        is_quote_line = stripped.startswith(">")

        if stripped == "":
            if in_quote:
                in_quote = False
            if current_lines:
                raw_blocks.append("\n".join(current_lines))
                current_lines = []
        else:
            if is_quote_line and not in_quote and current_lines and not current_lines[-1].strip().startswith("#"):
                raw_blocks.append("\n".join(current_lines))
                current_lines = [line]
                in_quote = True
            else:
                if is_quote_line:
                    in_quote = True
                current_lines.append(line)

    if current_lines:
        raw_blocks.append("\n".join(current_lines))

    # Se un blocco è solo un titolo (`##` / `###`) o `---`, uniscilo al blocco successivo
    merged_blocks: List[str] = []
    i = 0
    while i < len(raw_blocks):
        b = raw_blocks[i]
        b_strip = b.strip()
        if (b_strip.startswith("#") or b_strip == "---") and "\n" not in b_strip and i + 1 < len(raw_blocks):
            combined = b + "\n\n" + raw_blocks[i + 1]
            if len(combined) <= max_length:
                merged_blocks.append(combined)
                i += 2
                continue
        merged_blocks.append(b)
        i += 1

    chunks: List[str] = []
    current_chunk = ""

    for block in merged_blocks:
        separator = "\n\n" if current_chunk else ""
        if len(current_chunk) + len(separator) + len(block) <= max_length:
            current_chunk += separator + block
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
                current_chunk = ""

            if len(block) <= max_length:
                current_chunk = block
            else:
                # Fallback riga per riga se un singolo blocco supera max_length
                for line in block.split("\n"):
                    if len(current_chunk) + len(line) + 1 > max_length:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        while len(line) > max_length:
                            chunks.append(line[:max_length])
                            line = line[max_length:]
                    current_chunk += (line + "\n")
                current_chunk = current_chunk.strip()

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def send_to_discord(markdown_text: str, webhook_url: Optional[str] = None) -> bool:
    """Invia il riassunto al canale Discord tramite Webhook. Restituisce True se inviato."""
    webhook = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook or webhook == "inserisci_qui_il_webhook_url_di_discord":
        print(
            "⚠️ DISCORD_WEBHOOK_URL non configurato in .env: impossibile inviare su Discord."
        )
        return False

    chunks = split_message_for_discord(markdown_text)
    print(f"📤 Invio del riassunto su Discord ({len(chunks)} messaggi)...")

    for i, chunk in enumerate(chunks, start=1):
        payload = {
            "username": "Cronista dell'Accademia (D&D)",
            "content": chunk,
        }
        response = requests.post(webhook, json=payload, timeout=15)
        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 2.0)
            time.sleep(float(retry_after) + 0.5)
            response = requests.post(webhook, json=payload, timeout=15)

        if response.status_code not in (200, 204):
            raise RuntimeError(
                f"Errore durante l'invio a Discord (blocco {i}/{len(chunks)}): "
                f"HTTP {response.status_code} - {response.text}"
            )
        time.sleep(0.5)

    print("✅ Riassunto pubblicato con successo su Discord!")
    return True


ITALIAN_MONTH_HEADERS = {
    "01": "❄️ Gennaio",
    "02": "🌨️ Febbraio",
    "03": "🌱 Marzo",
    "04": "🌸 Aprile",
    "05": "🌷 Maggio",
    "06": "☀️ Giugno",
    "07": "🔥 Luglio",
    "08": "🦁 Agosto",
    "09": "🍂 Settembre",
    "10": "🎃 Ottobre",
    "11": "🍁 Novembre",
    "12": "🎄 Dicembre",
}


def parse_summary_markdown(md_path: Path) -> Optional[dict]:
    """
    Analizza un file di riassunto Markdown in `riassunti/`:
    - Estrae il `video_id` e recupera la data certificata (`startTimestamp`) da `channel_videos_cache.json`
    - Estrae il titolo evocativo dell'episodio
    - Estrae le voci della sezione `## 📖 Nuove Voci Rilevate per il Glossario`
    """
    if "_CON_DIALOGHI" in md_path.name:
        return None

    text = md_path.read_text(encoding="utf-8")

    # 1. Estrae video_id dal nome file o dall'URL YouTube nell'intestazione
    vid_id = ""
    m_name = re.match(r"^\d{4}-\d{2}-\d{2}_([A-Za-z0-9_-]{11})_", md_path.name)
    if m_name:
        vid_id = m_name.group(1)
    else:
        m_url = re.search(r"watch\?v=([A-Za-z0-9_-]{11})", text)
        if m_url:
            vid_id = m_url.group(1)

    if not vid_id:
        print(f"⚠️ Impossibile estrarre un video_id valido dal file: {md_path}")
        return None

    # Verifica bloccante su channel_videos_cache.json per avere la data certificata (startTimestamp)
    video_info = get_video_info_from_cache(vid_id)
    upload_date = video_info["upload_date"]
    date_str = format_date_from_yyyymmdd(upload_date)

    # 2. Estrae il titolo dell'episodio dalla prima intestazione #
    ep_title = video_info["title"]
    m_title = re.search(r"^#\s+(?:🐉\s*)?(.+)$", text, flags=re.MULTILINE)
    if m_title:
        ep_title = m_title.group(1).strip()

    # 3. Estrae la sezione "## 📖 Nuove Voci Rilevate per il Glossario"
    glossary_lines: List[str] = []
    parsed_entries: List[dict] = []
    m_sec = re.search(
        r"^##\s+📖\s+Nuove Voci Rilevate per il Glossario\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE,
    )
    if m_sec:
        sec_body = m_sec.group(1).strip()
        for raw_line in sec_body.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("_Nessuna nuova voce") or line == "---":
                continue
            if not (line.startswith("-") or line.startswith("*")):
                continue

            # Normalizza formato "- **Nome** [Categoria]: Descrizione" -> "* **Nome** (`Categoria`): Descrizione"
            m_item = re.match(
                r"^[\-\*]\s+\*\*(.+?)\*\*\s*(?:\[(.+?)\]|\((?:`?)(.+?)(?:`?)\))\s*:\s*(.+)$",
                line,
            )
            if m_item:
                nome = m_item.group(1).strip()
                cat = (m_item.group(2) or m_item.group(3) or "Voce").strip()
                desc = m_item.group(4).strip()
                desc = re.sub(r"\*\(trascritto anche come:\s*", "*(varianti fonetiche: ", desc)
                norm_line = f"* **{nome}** (`{cat}`): {desc}"
                glossary_lines.append(norm_line)
                parsed_entries.append({"nome": nome, "categoria": cat, "descrizione": desc, "line": norm_line})
            else:
                norm_line = "* " + line.lstrip("-* ").strip()
                glossary_lines.append(norm_line)

    rel_from_root = md_path.relative_to(BASE_DIR).as_posix()
    return {
        "id": vid_id,
        "upload_date": upload_date,
        "date_str": date_str,
        "year": upload_date[:4],
        "month_num": upload_date[4:6],
        "episode_title": ep_title,
        "md_path": md_path,
        "rel_link": f"../{rel_from_root}",
        "glossary_lines": glossary_lines,
        "parsed_entries": parsed_entries,
    }


def rebuild_glossaries_from_summaries(year: Optional[str] = None) -> None:
    """
    Ricostruisce/aggiorna i glossari (`glossari/glossario_<YYYY>.md` e `glossari/glossario.md`)
    partendo dai riassunti Markdown presenti in `riassunti/`, ordinati in RIGOROSO ORDINE CRONOLOGICO
    crescente secondo la data certificata (`startTimestamp`) in `channel_videos_cache.json`.
    """
    if not SUMMARIES_DIR.exists():
        print(f"⚠️ La cartella '{SUMMARIES_DIR.relative_to(BASE_DIR)}' non esiste.")
        return

    all_md_files = sorted(SUMMARIES_DIR.rglob("*.md"))
    parsed_summaries = []
    for fpath in all_md_files:
        item = parse_summary_markdown(fpath)
        if not item:
            continue
        if year and item["year"] != str(year).strip():
            continue
        parsed_summaries.append(item)

    # Carica la cache degli streaming per recuperare anche le sessioni prive di sottotitoli/riassunto
    cache_dict = {}
    if CACHE_PATH.exists():
        try:
            cache_dict = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            cache_dict = {}

    known_summary_ids = {item["id"] for item in parsed_summaries}
    for c_id, c_data in cache_dict.items():
        c_date = c_data.get("upload_date", "")
        if not c_date:
            continue
        c_year = c_date[:4]
        if year and c_year != str(year).strip():
            continue
        if c_id not in known_summary_ids:
            d_fmt = f"{c_date[:4]}-{c_date[4:6]}-{c_date[6:8]}" if len(c_date) >= 8 else c_date
            m_num = c_date[4:6] if len(c_date) >= 6 else "00"
            parsed_summaries.append({
                "id": c_id,
                "upload_date": c_date,
                "date_str": d_fmt,
                "year": c_year,
                "month_num": m_num,
                "episode_title": c_data.get("title", ""),
                "rel_link": f"https://www.youtube.com/watch?v={c_id}",
                "is_missing_subtitles": True,
                "glossary_lines": [
                    "* *(Trascrizione non disponibile: la registrazione su YouTube non presenta sottotitoli automatici o manuali; nessun riassunto testuale disponibile).*"
                ],
                "parsed_entries": [],
            })

    if not parsed_summaries:
        scope = f" per l'anno {year}" if year else ""
        print(f"ℹ️ Nessun riassunto o video trovato in cache{scope} da cui ricostruire i glossari.")
        return

    # ORDINAMENTO CRONOLOGICO RIGOROSO (dal più vecchio al più recente)
    parsed_summaries.sort(key=lambda x: (x["upload_date"], x["id"]))

    GLOSSARIES_DIR.mkdir(parents=True, exist_ok=True)

    # Raggruppa per anno
    by_year = {}
    for item in parsed_summaries:
        by_year.setdefault(item["year"], []).append(item)

    for y_str, y_items in sorted(by_year.items()):
        yearly_path = get_yearly_glossary_path(y_str)

        # Preserva eventuale quadro introduttivo presente prima di "## 🗓️ Cronologia delle Scoperte"
        intro_prefix = ""
        if yearly_path.exists():
            existing_content = yearly_path.read_text(encoding="utf-8")
            m_split = re.search(r"^##\s+🗓️\s+Cronologia delle Scoperte.*$", existing_content, flags=re.MULTILINE)
            if m_split:
                intro_prefix = existing_content[: m_split.start()].rstrip() + "\n\n"

        if not intro_prefix:
            intro_prefix = (
                f"# 📖 Glossario Cronologico {y_str} — Campagna D&D\n\n"
                f"Questo file raccoglie in **rigoroso ordine cronologico** tutte le nuove voci, i PNG, i luoghi, "
                f"le reliquie, gli indizi e gli sviluppi emersi durante le sessioni del **{y_str}**.\n"
                f"Per l'inquadramento generale dei Personaggi Giocanti, dei Fondatori e delle regole di conversione fonetica, "
                f"consulta anche il file principale [`glossario.md`](./glossario.md).\n\n---\n\n"
            )

        out_lines = [
            intro_prefix.rstrip(),
            "",
            f"## 🗓️ Cronologia delle Scoperte e Voci del Glossario ({y_str})",
        ]

        current_month = None
        for idx_s, s_item in enumerate(y_items):
            m_num = s_item["month_num"]
            if m_num != current_month:
                if current_month is not None:
                    out_lines.extend(["", "---"])
                month_label = ITALIAN_MONTH_HEADERS.get(m_num, f"🗓️ Mese {m_num}")
                out_lines.extend(["", f"### {month_label} {y_str}"])
                current_month = m_num

            if s_item.get("is_missing_subtitles"):
                out_lines.extend(
                    [
                        "",
                        f"#### ⚠️ Sessione del {s_item['date_str']} — [Live YouTube]({s_item['rel_link']}) *(Priva di sottotitoli YouTube)*",
                    ]
                )
                out_lines.extend(s_item["glossary_lines"])
            else:
                ep_title_part = (
                    f" — {s_item['episode_title']}"
                    if s_item["episode_title"].lower() not in ("mia trasmissione", "live streaming di stefano leone")
                    else ""
                )
                out_lines.extend(
                    [
                        "",
                        f"#### 📌 Sessione del {s_item['date_str']}{ep_title_part} ([Riassunto]({s_item['rel_link']}))",
                    ]
                )
                if s_item["glossary_lines"]:
                    out_lines.extend(s_item["glossary_lines"])
                else:
                    out_lines.append("* *(Nessuna nuova voce specifica registrata in calce al riassunto)*")

        yearly_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        print(
            f"✅ Ricostruito in ordine cronologico '{yearly_path.relative_to(BASE_DIR)}' "
            f"({len(y_items)} sessioni dal {y_items[0]['date_str']} al {y_items[-1]['date_str']})."
        )

    print(
        f"ℹ️ Nota: '{GLOSSARY_PATH.relative_to(BASE_DIR)}' non viene modificato con append automatici dallo script "
        "per evitare duplicazioni o voci fuori sezione; il consolidamento tematico/semantico è affidato all'Agente."
    )


def update_glossary_file(
    new_entries: List[GlossaryEntry],
    video_title: str,
    video_date: str = "",
    summary_path: Optional[Path] = None,
    video_id: str = "",
) -> None:
    """
    Aggiorna sia il glossario generale (`glossari/glossario.md`) sia il glossario
    dell'anno in esame (`glossari/glossario_<YYYY>.md`) mantenendo il rigoroso ordine cronologico.
    """
    if not new_entries:
        return

    date_str = (
        format_date_from_yyyymmdd(video_date)
        if video_date
        else datetime.now().strftime("%Y-%m-%d")
    )
    year_str = date_str[:4]
    rebuild_glossaries_from_summaries(year=year_str)


# =====================================================================
# Flusso di Elaborazione di un Singolo Video
# =====================================================================

def process_single_video(
    video_info: dict,
    force: bool = False,
    update_glossary: bool = False,
    post_discord: bool = False,
    fetch_only: bool = False,
) -> Optional[Path]:
    """
    Elabora una singola puntata:
    1. Scarica trascrizione
    2. (Se fetch_only=True si ferma qui e mostra i metadati per l'Agente)
    3. Genera riassunto con Gemini
    4. Salva il file Markdown in `riassunti/<YYYY-MM>/<YYYY-MM-DD>_<id>_<titolo>.md`
    5. Opzionalmente aggiorna il glossario generale e annuale e/o invia a Discord.
    """
    video_id = video_info["id"]
    video_title = video_info["title"]
    upload_date = video_info.get("upload_date", "")
    month_folder = format_month_from_upload_date(upload_date)
    date_prefix = format_date_from_yyyymmdd(upload_date)
    target_dir = SUMMARIES_DIR / month_folder if month_folder != "sconosciuto" else SUMMARIES_DIR
    safe_title = re.sub(r"[^\w\-_]", "_", video_title)[:50].strip("_")
    expected_summary_path = target_dir / f"{date_prefix}_{video_id}_{safe_title}.md"

    print(f"\n{'='*65}")
    print(f"🎬 Puntata: '{video_title}' ({date_prefix}) - ID: {video_id}")
    print(f"{'='*65}")

    processed = load_processed_videos()
    if video_id in processed and not force:
        existing_file = BASE_DIR / processed[video_id].get("summary_file", "")
        print(
            f"⏭️ Già riassunta in locale: {processed[video_id].get('summary_file')}\n"
            f"   (Usa --force per rigenerarla oppure --post-pending / --post-file per inviarla su Discord)."
        )
        if post_discord and not processed[video_id].get("posted_to_discord") and existing_file.exists():
            md_text = existing_file.read_text(encoding="utf-8")
            if send_to_discord(md_text):
                mark_video_posted(video_id)
        return existing_file

    # Scarica o recupera trascrizione dalla cache
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    transcript_file = TRANSCRIPTS_DIR / f"{video_id}.txt"

    if transcript_file.exists() and not force:
        print(f"📄 Uso trascrizione già salvata in locale: {transcript_file.name}")
        transcript = transcript_file.read_text(encoding="utf-8")
    else:
        transcript = fetch_transcript(video_id)
        transcript_file.write_text(transcript, encoding="utf-8")
        print(f"💾 Trascrizione salvata in: {transcript_file.relative_to(BASE_DIR)}")

    # Analisi automatica buchi di trascrizione / possibili segmenti mutati da YouTube
    anomalies = detect_transcript_anomalies(
        transcript=transcript,
        video_duration=video_info.get("duration"),
    )
    if anomalies:
        print(f"🔇 Monitoraggio Audio / Buchi Trascrizione ({len(anomalies)} rilevati):")
        for a in anomalies[:10]:
            print(f"   ⚠️ {a}")
        if len(anomalies) > 10:
            print(f"   ... e altri {len(anomalies) - 10} buchi rilevati.")
    else:
        print("🔊 Monitoraggio Audio: Nessun buco o taglio significativo rilevato nella trascrizione.")

    yearly_glossary = get_yearly_glossary_path(upload_date)
    if fetch_only:
        print("🤖 Modalità --fetch-only (per elaborazione tramite Agente):")
        print(f"   - Video ID:           {video_id}")
        print(f"   - Titolo YouTube:     {video_title}")
        print(f"   - URL:                {video_info.get('url', f'https://www.youtube.com/watch?v={video_id}')}")
        print(f"   - Upload Date:        {upload_date} ({date_prefix})")
        print(f"   - Mese:               {month_folder}")
        print(f"   - Trascrizione:       {transcript_file.relative_to(BASE_DIR)}")
        print(f"   - Glossario Generale: {GLOSSARY_PATH.relative_to(BASE_DIR)}")
        print(f"   - Glossario Annuale:  {yearly_glossary.relative_to(BASE_DIR)}")
        print(f"   - Target Riassunto:   {(target_dir / f'{date_prefix}_{video_id}_<Titolo_Episodio>.md').relative_to(BASE_DIR)}")
        return transcript_file

    # Rilegge i glossari (generale + annuale) a ogni puntata
    glossary_text = load_glossary_context(upload_date)

    # Genera riassunto con Gemini
    summary_output = generate_summary_with_gemini(
        transcript=transcript,
        glossary_text=glossary_text,
        video_title=video_title,
    )

    # Salva il riassunto Markdown organizzato per sottocartella mensile (es. riassunti/2026-10/...)
    markdown_summary = format_summary_as_markdown(summary_output, video_info)
    target_dir.mkdir(parents=True, exist_ok=True)

    title_for_filename = (
        summary_output.titolo_episodio
        if not video_title or video_title.strip().lower() in ("mia trasmissione", "live streaming di stefano leone")
        else video_title
    )
    safe_ep_title = re.sub(r"[^\w\-_]", "_", title_for_filename)
    safe_ep_title = re.sub(r"_+", "_", safe_ep_title)[:50].strip("_")
    summary_path = target_dir / f"{date_prefix}_{video_id}_{safe_ep_title}.md"
    summary_path.write_text(markdown_summary, encoding="utf-8")
    print(f"✅ Riassunto Markdown salvato in locale: {summary_path.relative_to(BASE_DIR)}")

    # Aggiornamento glossario generale e annuale
    if update_glossary and summary_output.nuove_voci_glossario:
        update_glossary_file(
            summary_output.nuove_voci_glossario,
            summary_output.titolo_episodio or video_title,
            upload_date,
            summary_path=summary_path,
            video_id=video_id,
        )
    elif summary_output.nuove_voci_glossario:
        print(
            f"💡 Trovate {len(summary_output.nuove_voci_glossario)} nuove voci per il glossario "
            "(incluse in fondo al file Markdown; usa --update-glossary per aggiungerle ai glossari in glossari/)."
        )

    # Invio su Discord (SOLO se esplicitamente richiesto)
    posted = False
    if post_discord:
        posted = send_to_discord(markdown_summary)
    else:
        print("📝 Modalità Bozza Locale: riassunto salvato su disco (non ancora inviato su Discord).")

    record_video_summary(video_info, summary_path, posted_to_discord=posted)
    return summary_path


# =====================================================================
# Comandi di Storico e Pubblicazione Differita su Discord
# =====================================================================

def list_channel_history(year: Optional[str] = None, month: Optional[str] = None) -> None:
    """Mostra tutte le puntate in cache raggruppate per mese (YYYY-MM) e il loro stato locale/Discord."""
    videos = get_cached_videos(year=year, month=month)
    processed = load_processed_videos()

    by_month = {}
    for v in videos:
        m = v["month"]
        by_month.setdefault(m, []).append(v)

    print("\n📚 STORICO PUNTATE IN CACHE (divise per mese):")
    for m_key in sorted(by_month.keys(), reverse=True):
        month_vids = sorted(by_month[m_key], key=lambda x: x.get("upload_date", ""))
        print(f"\n🗓️  Mese: {m_key} ({len(month_vids)} puntate)")
        for v in month_vids:
            vid_id = v["id"]
            date_str = format_date_from_yyyymmdd(v.get("upload_date", ""))
            has_transcript = (TRANSCRIPTS_DIR / f"{vid_id}.txt").exists()
            t_badge = "📄 Trascrizione OK" if has_transcript else "☁️ Trascrizione da scaricare"
            has_md_on_disk = bool(SUMMARIES_DIR.exists() and list(SUMMARIES_DIR.rglob(f"*_{vid_id}_*.md")))

            if vid_id in processed:
                is_posted = processed[vid_id].get("posted_to_discord", False)
                status = "✅ Riassunto + Inviato Discord" if is_posted else "📝 Solo Riassunto Locale (da inviare)"
            elif has_md_on_disk:
                status = "📝 Riassunto su disco (non in processed_videos.json)"
            else:
                status = "⏳ Da riassumere"
            print(f"   - [{date_str}] {v['title']} ({vid_id}) -> {status} | {t_badge}")


def post_pending_summaries(target_month: Optional[str] = None) -> None:
    """
    Invia su Discord in ordine cronologico tutti i riassunti già salvati in locale
    (ed eventualmente da te revisionati/modificati a mano) che non sono ancora stati pubblicati.
    """
    processed = load_processed_videos()
    pending = []
    for vid_id, info in processed.items():
        if info.get("posted_to_discord"):
            continue
        if target_month and info.get("month") != target_month:
            continue
        pending.append(info)

    if not pending:
        msg = f" per il mese {target_month}" if target_month else ""
        print(f"ℹ️ Nessun riassunto locale in attesa di pubblicazione su Discord{msg}.")
        return

    # Ordina dal più vecchio al più recente così su Discord compaiono in ordine cronologico!
    pending.sort(key=lambda x: x.get("upload_date", ""))

    print(f"📤 Trovati {len(pending)} riassunti locali pronti per essere pubblicati su Discord...")
    for item in pending:
        file_path = BASE_DIR / item["summary_file"]
        if not file_path.exists():
            print(f"⚠️ File non trovato: {file_path}, salto.")
            continue
        print(f"\n➡️ Pubblicazione: {item['title']} ({file_path.name})")
        md_text = file_path.read_text(encoding="utf-8")
        if send_to_discord(md_text):
            mark_video_posted(item["id"])


def reset_summaries(
    year: Optional[str] = None,
    month: Optional[str] = None,
    video_arg: Optional[str] = None,
) -> None:
    """
    Esegue il reset dei riassunti (per un singolo video, un mese YYYY-MM o un intero anno YYYY):
    1. Verifica obbligatoriamente che le informazioni dello streaming siano presenti in
       `channel_videos_cache.json` (se mancanti o incomplete, si blocca prima di toccare i file).
    2. Elimina il file Markdown del riassunto in `riassunti/...`.
    3. Rimuove il video da `processed_videos.json`.
    4. Conserva intatta la trascrizione in `trascrizioni/<video_id>.txt` per la futura ricostruzione.
    """
    # Se l'utente ha passato un anno a 4 cifre dentro --month (es. --month 2026), trattalo come --year
    if month and re.fullmatch(r"20\d{2}", month.strip()):
        year = month.strip()
        month = None

    if not year and not month and not video_arg:
        print(
            "❌ ERRORE BLOCCANTE: Per usare `--reset` devi specificare almeno uno tra:\n"
            "   - `--year YYYY` (es. `py dnd_summarizer.py --reset --year 2026`)\n"
            "   - `--month YYYY-MM` (es. `py dnd_summarizer.py --reset --month 2026-10`)\n"
            "   - `--video <ID_O_URL>` (es. `py dnd_summarizer.py --reset --video lQ6LK700vBY`)"
        )
        sys.exit(1)

    # 1. Verifica preliminare su channel_videos_cache.json e raccolta video target
    if video_arg:
        vid_id = extract_video_id(video_arg)
        target_videos = [get_video_info_from_cache(vid_id)]
        scope_label = f"video {vid_id}"
    else:
        target_videos = get_cached_videos(year=year, month=month)
        scope_label = f"anno {year}" if year else f"mese {month}"
        if not target_videos:
            print(
                f"❌ ERRORE BLOCCANTE: Nessun video trovato in '{CACHE_PATH.name}' per {scope_label}."
            )
            sys.exit(1)

    # Controlla anche che eventuali file .md già presenti su disco per quel periodo
    # abbiano tutti il rispettivo video_id censito in channel_videos_cache.json
    channel_cache = load_channel_cache()
    if SUMMARIES_DIR.exists() and not video_arg:
        for month_dir in sorted(SUMMARIES_DIR.iterdir()):
            if not month_dir.is_dir():
                continue
            if month and month_dir.name != month:
                continue
            if year and not month_dir.name.startswith(f"{year}-"):
                continue
            for md_file in month_dir.glob("*.md"):
                m = re.match(r"^\d{4}-\d{2}-\d{2}_([A-Za-z0-9_-]{11})_", md_file.name)
                if m:
                    file_vid_id = m.group(1)
                    # Verifica bloccante: se manca in channel_videos_cache.json, si blocca tutto
                    _ = get_video_info_from_cache(file_vid_id)

    processed = load_processed_videos()
    deleted_files: List[Path] = []
    removed_from_processed: List[str] = []
    preserved_transcripts: List[Path] = []
    missing_transcripts: List[str] = []

    print(f"\n🔄 Avvio RESET per {scope_label} ({len(target_videos)} live in cache)...")

    for v in target_videos:
        vid_id = v["id"]
        v_month = v["month"]
        date_str = format_date_from_yyyymmdd(v["upload_date"])

        # A. Cerca ed elimina tutti i file di riassunto associati a questo video_id (anche in altre sottocartelle se la data è stata riallineata)
        candidate_files = set()
        if vid_id in processed and processed[vid_id].get("summary_file"):
            candidate_files.add(BASE_DIR / processed[vid_id]["summary_file"])

        if SUMMARIES_DIR.exists():
            for match_file in SUMMARIES_DIR.rglob(f"*_{vid_id}_*.md"):
                candidate_files.add(match_file)

        for fpath in sorted(candidate_files):
            if fpath.exists() and fpath.is_file():
                fpath.unlink()
                deleted_files.append(fpath)
                print(f"   🗑️ Eliminato riassunto: {fpath.relative_to(BASE_DIR)}")

        # B. Rimuove il video da processed_videos.json
        if vid_id in processed:
            del processed[vid_id]
            removed_from_processed.append(vid_id)
            print(f"   🧹 Rimosso da processed_videos.json: {vid_id} ({date_str})")

        # C. Verifica conservazione trascrizione
        t_file = TRANSCRIPTS_DIR / f"{vid_id}.txt"
        if t_file.exists():
            preserved_transcripts.append(t_file)
        else:
            missing_transcripts.append(f"{vid_id} ({date_str})")

    save_processed_videos(processed)

    print(f"\n{'='*65}")
    print(f"✅ RESET COMPLETATO ({scope_label})")
    print(f"   - Riassunti Markdown eliminati:          {len(deleted_files)}")
    print(f"   - Voci rimosse da processed_videos.json: {len(removed_from_processed)}")
    print(f"   - Trascrizioni conservate in locale:     {len(preserved_transcripts)} / {len(target_videos)}")
    if missing_transcripts:
        print(f"   ℹ️ Video in cache senza trascrizione locale ({len(missing_transcripts)}): {', '.join(missing_transcripts)}")
    print(f"{'='*65}\n")


def clean_search_text(text: str) -> str:
    """Rimuove la sintassi markdown pesante per ottimizzare la ricerca full-text."""
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"^[#>\*\-\+]\s*", "", text, flags=re.M)
    text = re.sub(r"[*_~`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def build_web_data(verbose: bool = True) -> dict:
    """Scansiona direttamente tutti i riassunti in `docs/riassunti/` e i glossari in `docs/glossari/`,
    e genera `docs/data/manifest.json` e `docs/data/search_index.json`
    per il frontend Vanilla SPA su GitHub Pages."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    GLOSSARIES_DIR.mkdir(parents=True, exist_ok=True)

    summary_files = sorted(list(SUMMARIES_DIR.rglob("*.md")))
    sessions_meta = []
    search_docs = []

    CANONICAL_CHARACTERS = {
        "aerial": "Aerial Aldebaran",
        "lucio": "Lucio Malaver",
        "rey": "Rey Sekigan",
        "rogus": "Rogus Harndrekker",
        "prometheus": "Prometheus",
        "quarion": "Quarion",
    }

    for sf in summary_files:
        rel_subpath = sf.relative_to(SUMMARIES_DIR)

        raw_text = sf.read_text(encoding="utf-8")
        title_m = re.search(r"^#\s*🐉?\s*(.+)$", raw_text, re.M)
        title = title_m.group(1).strip() if title_m else sf.stem

        date_m = re.search(r"📅\s*\*\*Data Live:\*\*\s*([\d\-]+)", raw_text)
        date_str = date_m.group(1).strip() if date_m else ""
        if not date_str:
            fn_date = re.match(r"^(\d{4}-\d{2}-\d{2})", sf.name)
            date_str = fn_date.group(1) if fn_date else "Sconosciuta"

        yt_m = re.search(r"📺\s*\*\*YouTube:\*\*\s*\[.*?\]\((https?://[^\)]+)\)", raw_text)
        youtube_url = yt_m.group(1).strip() if yt_m else ""

        audio_m = re.search(r"🔇\s*\*\*Monitoraggio Audio:\*\*\s*(.+)$", raw_text, re.M)
        audio_status = audio_m.group(1).strip() if audio_m else "Nessun taglio rilevato"

        raw_pgs = re.findall(r"###\s*🛡️\s*([^\n\(]+)", raw_text)
        found_chars = set()
        for p in raw_pgs:
            p_clean = p.strip()
            p_lower = p_clean.lower()
            matched = False
            for c_key, c_name in CANONICAL_CHARACTERS.items():
                if c_key in p_lower:
                    found_chars.add(c_name)
                    matched = True
            if not matched and p_clean and "party" not in p_lower and "personaggi" not in p_lower:
                found_chars.add(p_clean)

        syn_m = re.search(r"##\s*📜\s*Sinossi.*?$\n+([\s\S]*?)(?=\n##\s*)", raw_text, re.M)
        synopsis = syn_m.group(1).strip() if syn_m else ""

        dialogues = re.findall(r">\s*💬\s*\*\*\[\[([\d\:]+\s*-\s*[\d\:]+)\]\]\(([^\)]+)\)\s*—\s*([^\*]+)\*\*", raw_text)

        year = date_str[:4] if len(date_str) >= 4 and date_str[:4].isdigit() else "Varie"
        month = date_str[:7] if len(date_str) >= 7 and "-" in date_str else "Varie"

        session_id = sf.stem

        session_entry = {
            "id": session_id,
            "title": title,
            "date": date_str,
            "year": year,
            "month": month,
            "youtube_url": youtube_url,
            "audio_status": audio_status,
            "characters": sorted(list(found_chars)),
            "synopsis": synopsis,
            "dialogue_count": len(dialogues),
            "filename": sf.name,
            "path": f"riassunti/{rel_subpath.as_posix()}",
            "word_count": len(raw_text.split()),
        }
        sessions_meta.append(session_entry)

        clean_content = clean_search_text(raw_text)
        search_docs.append({
            "id": session_id,
            "type": "sessione",
            "title": title,
            "date": date_str,
            "year": year,
            "month": month,
            "characters": sorted(list(found_chars)),
            "path": f"riassunti/{rel_subpath.as_posix()}",
            "content": clean_content,
            "snippet": clean_content[:260] + ("..." if len(clean_content) > 260 else ""),
        })

    sessions_meta.sort(key=lambda s: s["date"], reverse=True)

    glossary_files = sorted(list(GLOSSARIES_DIR.glob("*.md")))
    glossaries_meta = []
    for gf in glossary_files:
        raw_g = gf.read_text(encoding="utf-8")
        clean_g = clean_search_text(raw_g)
        is_general = gf.name == "glossario.md"
        suffix = gf.stem.replace("glossario_", "")
        g_title = "Glossario Generale della Campagna" if is_general else f"Diario Cronologico {suffix}"

        glossaries_meta.append({
            "id": gf.stem,
            "filename": gf.name,
            "title": g_title,
            "is_general": is_general,
            "path": f"glossari/{gf.name}",
            "line_count": len(raw_g.splitlines()),
        })

        search_docs.append({
            "id": gf.stem,
            "type": "glossario",
            "title": g_title,
            "date": "Compendio",
            "year": "Tutti",
            "month": "Tutti",
            "characters": [],
            "path": f"glossari/{gf.name}",
            "content": clean_g,
            "snippet": clean_g[:260] + ("..." if len(clean_g) > 260 else ""),
        })

    years_map = {}
    for s in sessions_meta:
        y = s["year"]
        m = s["month"]
        if y not in years_map:
            years_map[y] = {}
        if m not in years_map[y]:
            years_map[y][m] = []
        years_map[y][m].append(s["id"])

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "total_sessions": len(sessions_meta),
        "total_glossaries": len(glossaries_meta),
        "years": sorted(list(years_map.keys()), reverse=True),
        "tree": years_map,
        "sessions": sessions_meta,
        "glossaries": glossaries_meta,
    }

    manifest_path = DOCS_DATA_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    search_index_path = DOCS_DATA_DIR / "search_index.json"
    search_index_path.write_text(json.dumps(search_docs, ensure_ascii=False), encoding="utf-8")

    if verbose:
        print(f"\n{'='*65}")
        print("✅ BUILD FRONTEND WEB COMPLETATA:")
        print(f"   📁 Cartella di output:              {DOCS_DIR.relative_to(BASE_DIR)}")
        print(f"   📜 Sessioni sincronizzate/indicizzate: {len(sessions_meta)}")
        print(f"   📖 Glossari sincronizzati/indicizzati: {len(glossaries_meta)}")
        print(f"   📄 Manifest generato:               {manifest_path.relative_to(BASE_DIR)} ({round(manifest_path.stat().st_size / 1024, 1)} KB)")
        print(f"   🔍 Search Index generato:           {search_index_path.relative_to(BASE_DIR)} ({round(search_index_path.stat().st_size / 1024, 1)} KB)")
        print(f"{'='*65}\n")

    return manifest


# =====================================================================
# Main CLI
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Cronista D&D: crea riassunti Markdown in locale (singoli o storico mensile) e li pubblica su Discord quando vuoi."
    )

    # Modalità di selezione video / storico
    parser.add_argument(
        "--list-months",
        action="store_true",
        help="Elenca tutte le live presenti sul canale raggruppate per mese (YYYY-MM) e mostra quali sono già riassunte.",
    )
    parser.add_argument(
        "--year",
        type=str,
        default=None,
        help="Seleziona tutte le puntate di uno specifico anno (formato YYYY, es. '2026') leggendo i metadati da channel_videos_cache.json.",
    )
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="Elabora tutte le puntate di uno specifico mese (formato YYYY-MM, es. '2026-09') in ordine cronologico leggendo da channel_videos_cache.json.",
    )
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="URL o ID di uno specifico video YouTube (recupera le info da channel_videos_cache.json).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Elimina i riassunti Markdown e rimuove i video da processed_videos.json (conservando le trascrizioni in trascrizioni/). Richiede --year, --month o --video e recupera i metadati da channel_videos_cache.json.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Aggiorna channel_videos_cache.json interrogando il canale YouTube tramite yt-dlp.",
    )
    parser.add_argument(
        "--transcript-file",
        type=str,
        default=None,
        help="Percorso di un file di trascrizione (.txt o .md) già pronto in locale da riassumere direttamente senza YouTube.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Titolo personalizzato della sessione (usato insieme a --transcript-file).",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=150,
        help="Numero massimo di video da scansionare sul canale per lo storico (default: 150).",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=DEFAULT_CHANNEL_URL,
        help=f"URL del canale YouTube (default: {DEFAULT_CHANNEL_URL}).",
    )

    # Opzioni di elaborazione e Glossario
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Scarica/verifica solo la trascrizione e mostra i metadati senza chiamare le API Gemini (ideale quando il riassunto viene generato dall'Agente).",
    )
    parser.add_argument(
        "--update-glossary",
        action="store_true",
        help="Aggiorna automaticamente i glossari in glossari/ con le nuove voci scoperte.",
    )
    parser.add_argument(
        "--rebuild-glossary",
        action="store_true",
        help="Ricostruisce/aggiorna i glossari (glossario_<YYYY>.md e glossario.md) partendo dai riassunti presenti in riassunti/, in rigoroso ordine cronologico secondo startTimestamp in channel_videos_cache.json (combinabile con --year YYYY).",
    )
    parser.add_argument(
        "--build-web",
        "--export-web",
        action="store_true",
        help="Scansiona direttamente i file Markdown in docs/riassunti/ e docs/glossari/ per generare docs/data/manifest.json e docs/data/search_index.json per il frontend GitHub Pages.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rigenera il riassunto anche se il video risulta già elaborato in locale.",
    )

    # Opzioni di pubblicazione su Discord (di default NON invia su Discord per permettere revisione locale!)
    parser.add_argument(
        "--discord",
        action="store_true",
        help="Invia subito il riassunto su Discord appena generato (di default lo salva solo in locale in Markdown).",
    )
    parser.add_argument(
        "--post-file",
        type=str,
        default=None,
        help="Percorso di un file Markdown (.md) già generato/modificato in locale da pubblicare ora su Discord.",
    )
    parser.add_argument(
        "--post-pending",
        action="store_true",
        help="Pubblica su Discord (in ordine cronologico) tutti i riassunti salvati in locale e non ancora inviati (combinabile con --month YYYY-MM).",
    )

    args = parser.parse_args()

    # Opzionale: aggiornamento esplicito di channel_videos_cache.json da YouTube
    if args.refresh_cache:
        fetch_channel_videos(args.channel, max_videos=args.max_videos)
        if not (args.list_months or args.reset or args.year or args.month or args.video):
            print("✅ Cache del canale (`channel_videos_cache.json`) aggiornata con successo!")
            return

    # Caso 0: Modalità RESET (elimina riassunto e voce in processed_videos.json, conserva trascrizione)
    if args.reset:
        reset_summaries(year=args.year, month=args.month, video_arg=args.video)
        return

    # Caso 0b: Ricostruzione / Refresh dei Glossari a partire dai riassunti in riassunti/ (in ordine cronologico)
    if args.rebuild_glossary:
        rebuild_glossaries_from_summaries(year=args.year)
        return

    # Caso 0c: Esportazione / Build del frontend web per GitHub Pages (manifest.json, search_index.json e sync file)
    if args.build_web:
        build_web_data()
        return

    # Caso A: Mostra il catalogo storico diviso per mesi
    if args.list_months:
        list_channel_history(year=args.year, month=args.month)
        return

    # Caso B: Pubblica su Discord un singolo file Markdown locale
    if args.post_file:
        fpath = Path(args.post_file).resolve()
        if not fpath.exists():
            print(f"❌ File non trovato: {fpath}")
            sys.exit(1)
        md_content = fpath.read_text(encoding="utf-8")
        if send_to_discord(md_content):
            # Se il file corrisponde a un video tracciato, aggiorna lo stato
            processed = load_processed_videos()
            for vid_id, info in processed.items():
                if (BASE_DIR / info.get("summary_file", "")).resolve() == fpath:
                    mark_video_posted(vid_id)
        return

    # Caso C: Pubblica su Discord tutti i riassunti locali in sospeso (o quelli di un mese)
    if args.post_pending:
        post_pending_summaries(target_month=args.month)
        return

    # Caso C2: Riassumi direttamente un file di trascrizione locale (--transcript-file)
    if args.transcript_file:
        t_path = Path(args.transcript_file).resolve()
        if not t_path.exists():
            print(f"❌ File di trascrizione non trovato: {t_path}")
            sys.exit(1)

        transcript_text = t_path.read_text(encoding="utf-8")
        session_title = args.title or t_path.stem
        date_From_title = parse_date_from_title(session_title) or datetime.now().strftime("%Y%m%d")
        video_info = {
            "id": t_path.stem[:15],
            "title": session_title,
            "url": "Trascrizione Locale",
            "upload_date": date_From_title,
            "month": format_month_from_upload_date(date_From_title),
        }

        glossary_text = load_glossary_context(date_From_title)
        summary_output = generate_summary_with_gemini(
            transcript=transcript_text,
            glossary_text=glossary_text,
            video_title=session_title,
        )

        markdown_summary = format_summary_as_markdown(summary_output, video_info)
        target_dir = SUMMARIES_DIR / video_info["month"]
        target_dir.mkdir(parents=True, exist_ok=True)
        date_prefix = format_date_from_yyyymmdd(date_From_title)
        safe_title = re.sub(r"[^\w\-_]", "_", session_title)[:50].strip("_")
        summary_path = target_dir / f"{date_prefix}_{safe_title}.md"
        summary_path.write_text(markdown_summary, encoding="utf-8")
        print(f"✅ Riassunto Markdown salvato in locale: {summary_path.relative_to(BASE_DIR)}")

        if args.update_glossary and summary_output.nuove_voci_glossario:
            update_glossary_file(
                summary_output.nuove_voci_glossario,
                summary_output.titolo_episodio or session_title,
                date_From_title,
                summary_path=summary_path,
            )

        posted = False
        if args.discord:
            posted = send_to_discord(markdown_summary)

        record_video_summary(video_info, summary_path, posted_to_discord=posted)
        return

    # Caso D: Elaborazione storico di un intero anno (--year YYYY) o mese (--month YYYY-MM)
    # Le informazioni dello streaming vengono recuperate da channel_videos_cache.json (e se mancanti si blocca)
    if args.year or args.month:
        target_year = args.year
        target_month = args.month
        if target_month and re.fullmatch(r"20\d{2}", target_month.strip()):
            target_year = target_month.strip()
            target_month = None

        period_videos = get_cached_videos(year=target_year, month=target_month)
        label = f"anno {target_year}" if target_year else f"mese {target_month}"
        if not period_videos:
            print(
                f"❌ ERRORE BLOCCANTE: Nessuna puntata trovata in '{CACHE_PATH.name}' per {label}. "
                "Usa `py dnd_summarizer.py --list-months` o `--refresh-cache` per aggiornare la cache."
            )
            sys.exit(1)

        print(
            f"🗓️ Trovate {len(period_videos)} puntate in cache per {label}. "
            "Avvio elaborazione in ordine cronologico..."
        )
        for v in period_videos:
            try:
                process_single_video(
                    video_info=v,
                    force=args.force,
                    update_glossary=args.update_glossary,
                    post_discord=args.discord,
                    fetch_only=args.fetch_only,
                )
            except Exception as e:
                print(f"❌ Errore durante l'elaborazione di '{v['title']}' ({v['id']}): {e}")
        if args.fetch_only:
            print(f"\n📥 Verifica/scaricamento trascrizioni per {label} completato! Ora l'Agente può generare i riassunti.")
        else:
            print(f"\n🎉 Elaborazione per {label} completata!")
        return

    # Caso E: Elaborazione di un singolo video specifico (--video) o dell'ultima live in cache
    # Recupera obbligatoriamente le informazioni dello streaming da channel_videos_cache.json
    if args.video:
        vid_id = extract_video_id(args.video)
        video_info = get_video_info_from_cache(vid_id)
    else:
        cached_all = get_cached_videos()
        video_info = cached_all[-1]

    process_single_video(
        video_info=video_info,
        force=args.force,
        update_glossary=args.update_glossary,
        post_discord=args.discord,
        fetch_only=args.fetch_only,
    )


if __name__ == "__main__":
    main()
