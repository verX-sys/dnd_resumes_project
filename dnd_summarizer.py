"""
Script per il recupero automatico delle live D&D da YouTube (ultima puntata o storico a blocchi mensili),
generazione e salvataggio dei riassunti in Markdown in locale tramite Gemini API (con supporto al glossario),
e pubblicazione separata/su richiesta su Discord tramite Webhook.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
import yt_dlp
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field
from youtube_transcript_api import YouTubeTranscriptApi

# Carica le variabili d'ambiente da .env
load_dotenv()

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).parent.resolve()
GLOSSARY_PATH = BASE_DIR / "glossario.md"
PROCESSED_PATH = BASE_DIR / "processed_videos.json"
SUMMARIES_DIR = BASE_DIR / "riassunti"
TRANSCRIPTS_DIR = BASE_DIR / "trascrizioni"

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


def get_video_metadata(video_id: str) -> dict:
    """Recupera titolo, data di pubblicazione (YYYYMMDD) e URL di un singolo video tramite yt-dlp (o cache)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    channel_cache = load_channel_cache()
    if video_id in channel_cache and channel_cache[video_id].get("upload_date"):
        return {
            "id": video_id,
            "title": channel_cache[video_id].get("title", f"Sessione D&D ({video_id})"),
            "url": url,
            "upload_date": channel_cache[video_id].get("upload_date", ""),
            "duration": None,
            "live_status": None,
        }

    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            upload_date = info.get("upload_date") or info.get("release_date") or ""
            if not upload_date and info.get("timestamp"):
                upload_date = datetime.fromtimestamp(info["timestamp"]).strftime("%Y%m%d")
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

        upload_date = entry.get("upload_date") or entry.get("release_date") or ""
        if not upload_date and entry.get("timestamp"):
            upload_date = datetime.fromtimestamp(entry["timestamp"]).strftime("%Y%m%d")

        # 1. Controlla se è già nella cache del canale o dei video processati
        if not upload_date and vid_id in channel_cache:
            upload_date = channel_cache[vid_id].get("upload_date", "")
            title = channel_cache[vid_id].get("title", title)
        if not upload_date and vid_id in processed_cache:
            upload_date = processed_cache[vid_id].get("upload_date", "").replace("-", "")

        # 2. Prova a estrarre la data dal titolo se presente
        if not upload_date:
            upload_date = parse_date_from_title(title)

        # 3. Se ancora non abbiamo la data, interroga YouTube per il singolo video (solo la prima volta!)
        if not upload_date:
            print(f"   ⏳ [{idx}/{total}] Recupero data pubblicazione per: {title[:55]}...")
            meta = get_video_metadata(vid_id)
            upload_date = meta.get("upload_date", "")
            title = meta.get("title") or title

        if vid_id not in channel_cache or channel_cache[vid_id].get("upload_date") != upload_date:
            channel_cache[vid_id] = {
                "id": vid_id,
                "title": title,
                "upload_date": upload_date,
            }
            save_channel_cache(channel_cache)
            cache_updated = True

        results.append(
            {
                "id": vid_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "upload_date": upload_date,
                "month": format_month_from_upload_date(upload_date),
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
    lines = [
        f"# 🐉 {summary.titolo_episodio}",
        f"📅 **Data Live:** {date_formatted} | 📺 **YouTube:** [{video_info['title']}]({video_info['url']})",
        f"🔇 **Monitoraggio Audio:** {audio_note}",
        "",
        "## 📜 Sinossi della Puntata",
        summary.sinossi_breve,
        "",
        "## ⚔️ Vicende delle Squadre e dei Personaggi",
    ]

    for char_ev in summary.vicende_per_personaggio:
        lines.append(f"### 🛡️ {char_ev.personaggio} — *{char_ev.squadra_saggio}*")
        lines.append(char_ev.eventi)
        lines.append("")

    if summary.eventi_chiave_e_rivelazioni:
        lines.append("## 🔍 Eventi Chiave, Indizi e Rivelazioni")
        for ev in summary.eventi_chiave_e_rivelazioni:
            lines.append(f"- {ev}")
        lines.append("")

    if summary.loot_e_reliquie:
        lines.append("## 💎 Reliquie, Oggetti e Ricompense")
        for item in summary.loot_e_reliquie:
            lines.append(f"- {item}")
        lines.append("")

    if summary.prossimi_obiettivi:
        lines.append("## 🧭 Prossimi Obiettivi / In Sospeso")
        for obj in summary.prossimi_obiettivi:
            lines.append(f"- {obj}")
        lines.append("")

    if summary.nuove_voci_glossario:
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
    spezzando in modo intelligente sulle righe senza troncare le frasi.
    """
    chunks = []
    current_chunk = ""

    for line in text.split("\n"):
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
        current_chunk += line + "\n"

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


def update_glossary_file(
    new_entries: List[GlossaryEntry], video_title: str, video_date: str = ""
) -> None:
    """Aggiunge in coda a glossario.md una sezione con le nuove voci scoperte nella puntata."""
    if not new_entries:
        return

    date_str = format_date_from_yyyymmdd(video_date) if video_date else datetime.now().strftime("%Y-%m-%d")
    lines = [
        "\n\n",
        f"## Note e Nuove Voci Emerse ({video_title} - {date_str})",
        "",
    ]
    for entry in new_entries:
        varianti = (
            f" *(varianti fonetiche: {', '.join(entry.varianti_trascrizione)})*"
            if entry.varianti_trascrizione
            else ""
        )
        lines.append(
            f"* **{entry.nome}** ({entry.categoria}): {entry.descrizione}{varianti}"
        )

    with open(GLOSSARY_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"📝 Glossario aggiornato con {len(new_entries)} nuove voci in {GLOSSARY_PATH.name}!")


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
    5. Opzionalmente aggiorna il glossario e/o invia a Discord.
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

    if fetch_only:
        print("🤖 Modalità --fetch-only (per elaborazione tramite Agente):")
        print(f"   - Video ID:        {video_id}")
        print(f"   - Titolo:          {video_title}")
        print(f"   - URL:             {video_info.get('url', f'https://www.youtube.com/watch?v={video_id}')}")
        print(f"   - Upload Date:     {upload_date} ({date_prefix})")
        print(f"   - Mese:            {month_folder}")
        print(f"   - Trascrizione:    {transcript_file.relative_to(BASE_DIR)}")
        print(f"   - Target Riassunto:{expected_summary_path.relative_to(BASE_DIR)}")
        return transcript_file

    # Rilegge il glossario a ogni puntata (così se processiamo un mese in ordine cronologico,
    # ogni puntata beneficia delle voci aggiunte dalla puntata precedente!)
    if GLOSSARY_PATH.exists():
        glossary_text = GLOSSARY_PATH.read_text(encoding="utf-8")
    else:
        glossary_text = ""

    # Genera riassunto con Gemini
    summary_output = generate_summary_with_gemini(
        transcript=transcript,
        glossary_text=glossary_text,
        video_title=video_title,
    )

    # Salva il riassunto Markdown organizzato per sottocartella mensile (es. riassunti/2026-10/...)
    markdown_summary = format_summary_as_markdown(summary_output, video_info)
    target_dir.mkdir(parents=True, exist_ok=True)

    summary_path = expected_summary_path
    summary_path.write_text(markdown_summary, encoding="utf-8")
    print(f"✅ Riassunto Markdown salvato in locale: {summary_path.relative_to(BASE_DIR)}")

    # Aggiornamento glossario
    if update_glossary and summary_output.nuove_voci_glossario:
        update_glossary_file(summary_output.nuove_voci_glossario, video_title, upload_date)
    elif summary_output.nuove_voci_glossario:
        print(
            f"💡 Trovate {len(summary_output.nuove_voci_glossario)} nuove voci per il glossario "
            "(incluse in fondo al file Markdown; usa --update-glossary per aggiungerle a glossario.md)."
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

def list_channel_history(channel_url: str, max_videos: int) -> None:
    """Mostra tutte le puntate sul canale raggruppate per mese (YYYY-MM) e il loro stato locale/Discord."""
    videos = fetch_channel_videos(channel_url, max_videos=max_videos)
    processed = load_processed_videos()

    by_month = {}
    for v in videos:
        m = v["month"]
        by_month.setdefault(m, []).append(v)

    print("\n📚 STORICO PUNTATE SUL CANALE YOUTUBE (divise per mese):")
    for month in sorted(by_month.keys(), reverse=True):
        month_vids = sorted(by_month[month], key=lambda x: x.get("upload_date", ""))
        print(f"\n🗓️  Mese: {month} ({len(month_vids)} puntate)")
        for v in month_vids:
            vid_id = v["id"]
            date_str = format_date_from_yyyymmdd(v.get("upload_date", ""))
            if vid_id in processed:
                is_posted = processed[vid_id].get("posted_to_discord", False)
                status = "✅ Riassunto + Inviato Discord" if is_posted else "📝 Solo Riassunto Locale (da inviare)"
            else:
                status = "⏳ Da riassumere"
            print(f"   - [{date_str}] {v['title']} ({vid_id}) -> {status}")


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
        "--month",
        type=str,
        default=None,
        help="Elabora tutte le puntate di uno specifico mese (formato YYYY-MM, es. '2026-09') in ordine cronologico.",
    )
    parser.add_argument(
        "--video",
        type=str,
        default=None,
        help="URL o ID di uno specifico video YouTube (se omesso e non usi --month, prende l'ultima live).",
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
        help="Scarica solo la trascrizione e mostra i metadati senza chiamare le API Gemini (ideale quando il riassunto viene generato dall'Agente).",
    )
    parser.add_argument(
        "--update-glossary",
        action="store_true",
        help="Aggiorna automaticamente glossario.md con le nuove voci scoperte.",
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

    # Caso A: Mostra il catalogo storico diviso per mesi
    if args.list_months:
        list_channel_history(args.channel, max_videos=args.max_videos)
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

        glossary_text = GLOSSARY_PATH.read_text(encoding="utf-8") if GLOSSARY_PATH.exists() else ""
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
            update_glossary_file(summary_output.nuove_voci_glossario, session_title, date_From_title)

        posted = False
        if args.discord:
            posted = send_to_discord(markdown_summary)

        record_video_summary(video_info, summary_path, posted_to_discord=posted)
        return

    # Caso D: Elaborazione storico di un intero mese (--month YYYY-MM)
    if args.month:
        videos = fetch_channel_videos(args.channel, max_videos=args.max_videos)
        month_videos = [v for v in videos if v["month"] == args.month]
        if not month_videos:
            print(
                f"⚠️ Nessuna puntata trovata per il mese '{args.month}'. "
                "Usa `python dnd_summarizer.py --list-months` per vedere i mesi disponibili."
            )
            return

        # Ordina dal più vecchio al più recente così la storia e il glossario progrediscono in ordine!
        month_videos.sort(key=lambda x: x.get("upload_date", ""))
        print(
            f"🗓️ Trovate {len(month_videos)} puntate per il mese {args.month}. "
            "Avvio elaborazione in ordine cronologico..."
        )
        for v in month_videos:
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
            print(f"\n📥 Scaricamento trascrizioni del mese {args.month} completato! Ora l'Agente può generare i riassunti.")
        else:
            print(f"\n🎉 Elaborazione del mese {args.month} completata! Trovi i file in riassunti/{args.month}/")
        return

    # Caso E: Elaborazione di un singolo video specifico (--video) o dell'ultima live sul canale
    if args.video:
        vid_id = extract_video_id(args.video)
        video_info = get_video_metadata(vid_id)
    else:
        videos = fetch_channel_videos(args.channel, max_videos=5)
        video_info = videos[0]

    process_single_video(
        video_info=video_info,
        force=args.force,
        update_glossary=args.update_glossary,
        post_discord=args.discord,
        fetch_only=args.fetch_only,
    )


if __name__ == "__main__":
    main()
