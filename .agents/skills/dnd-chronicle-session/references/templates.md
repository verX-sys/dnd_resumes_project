# Riferimenti, Schemi e Template Ufficiali del Cronista

Questo file raccoglie gli schemi JSON, i template Markdown e le regole redazionali di dettaglio per il flusso `dnd-chronicle-session`.

---

## 1. Schema `processed_videos.json` (9 chiavi)

Leggi `processed_videos.json` (o crealo se non esiste) e aggiungi/aggiorna la chiave `<video_id>`:

```json
"<video_id>": {
  "id": "<video_id>",
  "title": "<Titolo Episodio>",
  "url": "https://www.youtube.com/watch?v=<video_id>",
  "upload_date": "<YYYYMMDD>",
  "month": "<YYYY-MM>",
  "summarized_at": "<ISO_TIMESTAMP>",
  "summary_file": "docs\\riassunti\\<YYYY-MM>\\<YYYY-MM-DD>_<video_id>_<Titolo_Episodio_Sanitizzato>.md",
  "posted_to_discord": false,
  "posted_at": null
}
```

---

## 2. Formati e Regole dei Glossari (`glossario_<YYYY>.md` e `glossario.md`)

### A. `docs/glossari/glossario_<YYYY>.md` (Diario Cronologico Annuale)

Contiene la cronologia dettagliata sessione per sessione dell'anno in esame, inclusi eventi specifici, indizi e tutti gli elementi scoperti.

- **Ordine cronologico obbligatorio**: le sessioni devono essere **sempre** ordinate dalla data più vecchia alla più recente, raggruppate per mese (`### ❄️ Gennaio <YYYY>`, `### 🌨️ Febbraio <YYYY>`, ecc.). Se riassumi una puntata meno recente dopo una più recente, inseriscila nella posizione cronologica corretta (oppure lancia `py dnd_summarizer.py --rebuild-glossary --year <YYYY>`) con il link relativo `../riassunti/<YYYY-MM>/<nome_file>.md`:

```markdown
#### 📌 Sessione del <YYYY-MM-DD> — <Titolo Episodio> ([Riassunto](../riassunti/<YYYY-MM>/<YYYY-MM-DD>_<video_id>_<Titolo_Episodio_Sanitizzato>.md))
* **<Nome>** (`<Categoria>`): <Descrizione> *(varianti fonetiche: <v1, v2>)*
```

- **Gestione Puntate Senza Sottotitoli YouTube**: se una puntata censita in `channel_videos_cache.json` non ha sottotitoli disponibili (trascrizione non estraibile), **non ignorarla** — inseriscila sempre nella sua esatta collocazione cronologica:

```markdown
#### ⚠️ Sessione del <YYYY-MM-DD> — [Live YouTube](https://www.youtube.com/watch?v=<VIDEO_ID>) *(Priva di sottotitoli YouTube)*
* *(Trascrizione non disponibile: la registrazione su YouTube non presenta sottotitoli automatici o manuali; nessun riassunto testuale disponibile).*
```

- Allinea inoltre il paragrafo discorsivo `🏆 Quadro Riepilogativo delle Squadre` in `docs/glossari/glossario_<YYYY>.md` fino all'ultima sessione riassunta.

### B. `docs/glossari/glossario.md` (Enciclopedia Tematica della Campagna)

Documento enciclopedico organizzato in **5 sezioni principali** e relative **sotto-sezioni geografiche/tematiche**:

1. `🛡️ Membri del Party`
2. `👥 PNG Rilevanti` (sotto-sezioni regionali/tematiche tra cui: `Hillsfar`, `Simbar`, `Caderish`, `Foresta di Cormanthor e Myth Drannor`, `Zhentil Keep, Moonsea e Cormyr`, `Underdark (Sottosuolo) e Tilverton`, `La Via del Sapiente, Sentinelle e Prove`, `Entità Sovrannaturali, Piani e Antagonisti Maggiori`, `Westgate e Altre Terre`)
3. `🗺️ Luoghi Rilevanti` (sotto-sezioni regionali tra cui: `Hillsfar`, `Simbar`, `Caderish`, `Foreste e Rovine Antiche`, `Mare della Luna, Fortezze e Città Esterne`, `Underdark (Sottosuolo)`, `Piani Esteriori, Semipiani e Terre Remote`)
4. `💎 Reliquie`
5. `⚔️ Fazioni, Dottrine e Terminologia Chiave` (sotto-sezioni: `Grandi Organizzazioni e Casate`, `Fenomeni Magici, Dottrine e Bestiario`)

**3 Regole Anti-Duplicazione per `glossario.md`:**
1. **Filtro di Rilevanza Enciclopedica**: inserisci **SOLO entità permanenti e ricorrenti della campagna** (PNG importanti, Luoghi stabili, Reliquie/Artefatti chiave, Grandi Fazioni o meccaniche persistenti). **NON inserire mai** micro-eventi tattici di una singola sessione, cibi/oggetti di scena minori o fasi di un combattimento (che restano solo in `glossario_<YYYY>.md`).
2. **Upsert / Merge Semantico (Aggiorna > Crea)**: prima di inserire una voce, controlla se l'entità esiste già (anche con nome parziale, soprannome o variante fonetica). Se esiste già, **modifica e arricchisci la voce esistente** (aggiungendo nuove varianti fonetiche e integrando sviluppi di trama) senza **mai** creare un secondo bullet point duplicato.
3. **Collocazione nella Sotto-Sezione Esatta**: non appendere mai voci alla cieca in fondo al file; inseriscile sempre nella sotto-sezione geografica o tematica pertinente (`Hillsfar`, `Simbar`, `Caderish`, ecc.) e mantieni allineata la sezione `🛡️ Membri del Party`.

**Strategia Batch Mensili / Annuali:**
- **Dopo *ogni* singola puntata**: aggiorna **solo** `docs/glossari/glossario_<YYYY>.md`.
- **Alla fine dell'intero mese (Consolidamento Unico)**: aggiorna `docs/glossari/glossario.md` **una sola volta** a fine mese (o dopo `--rebuild-glossary`) leggendo i riassunti dal più vecchio al più recente.

---

## 3. Template Obbligatorio del Riassunto Markdown & Regole Redazionali

- **Percorso e naming file**: `docs/riassunti/<YYYY-MM>/<YYYY-MM-DD>_<video_id>_<Titolo_Episodio_Sanitizzato>.md` (solo lettere, numeri e underscore `[A-Za-z0-9_]`, max 45 caratteri).
- **Titolo YouTube generico**: se il titolo originale è `"Mia trasmissione"` (o `"Live streaming di Stefano Leone"`), **non** salvare `_Mia_trasmissione.md`, usa un titolo evocativo sanitizzato dell'episodio e nell'intestazione scrivi `[Guarda la Live (<YYYY-MM-DD>)](<URL Video>)`.

### Template Verbatim (`docs/riassunti/<YYYY-MM>/<YYYY-MM-DD>_<video_id>_<Titolo_Episodio>.md`)

```markdown
# 🐉 <Titolo Evocativo dell'Episodio>
📅 **Data Live:** <YYYY-MM-DD> | 📺 **YouTube:** [Guarda la Live (<YYYY-MM-DD>)](<URL Video>)
🔇 **Monitoraggio Audio:** <Nessun taglio rilevato | ⚠️ Possibili segmenti mutati/assenza audio: [HH:MM:SS - HH:MM:SS] (~X min, <breve contesto>)>

## 📜 Sinossi della Puntata
<Introduzione narrativa di 3-5 righe che riassume il cuore della sessione>

## ⚔️ Vicende dei Personaggi
### 🛡️ <Nome PG> (<Nome Giocatore>) — *<Compagni di Squadra PNG>*
<Riassunto dettagliato e narrativo di cosa ha fatto questo PG/squadra durante la puntata, includendo eventuali callout meccanici come *(🎲 TS Saggezza superato)* o *(🪄 Incantesimo)*>

> 💬 **[[HH:MM:SS - HH:MM:SS]](https://www.youtube.com/watch?v=<VIDEO_ID>&t=<X>h<Y>m<Z>s) — <Titolo breve della scena>**
>
> - **<Nome PG/PNG>:** *"<Battuta fedele ma ripulita dagli intercalari off-game>"*
> - **<Nome PG/PNG>:** *"<Risposta del personaggio o del PNG>"*

## 🔍 Eventi Chiave, Indizi e Rivelazioni
- <Colpo di scena, indizio risolto, scoperta sulla Mano Nera>

## 💎 Reliquie, Oggetti e Ricompense
- <Oggetti, reliquie, oro, contratti o punteggi delle lezioni ottenuti/persi>

## 🧭 Prossimi Obiettivi / In Sospeso
- <Cosa devono fare i personaggi nella prossima sessione, cliffhanger o appuntamenti fissati>

## 📖 Nuove Voci Rilevate per il Glossario
- **<Nome>** [<Categoria>]: <Descrizione> *(trascritto anche come: <varianti fonetiche>)*
```

### Le 5 Categorie per `## 📖 Nuove Voci Rilevate per il Glossario`

Classifica ogni nuova scoperta esattamente in una di queste 5 categorie:
1. `PNG`
2. `Luogo`
3. `Oggetto/Reliquia`
4. `Fazione/Terminologia`
5. `Aggiornamento Squadra`

### Regole Redazionali di Dettaglio

- **Filtro Off-Game vs Recap Iniziale / Retcon / Giocate in Privato**: ignora chiacchiere fuori gioco, problemi tecnici o battute off-game. Nei primi 10-15 minuti della live, giocatori e DM raccontano spesso **sessioni in privato, retcon o azioni off-screen** tra una sessione e l'altra (anche per PG il cui giocatore è assente o non gioca il resto della live): **includi sempre** una sotto-sezione dedicata a quel PG in `## ⚔️ Vicende dei Personaggi` specificando `*(Recap / Retcon inizio live)*`.
- **Dialoghi Salienti e Formattazione Blockquote**: inserisci 1-3 riquadri `>` per sezione PG dopo le scene chiave. Ripulisci le battute reali dagli intercalari off-game (*"allora"*, *"diciamo"*, *"tiro dado"*); se il DM o il giocatore narra in terza persona (*"Lui ti dice che..."*), converti in discorso diretto teatrale fedele al tono del personaggio. Usa sempre il timestamp cliccabile (`&t=<X>h<Y>m<Z>s`) seguito obbligatoriamente da **una riga `>` vuota** prima dei bullet `> - **Nome:** *"..."*` per evitare che Markdown fondi titolo e prima battuta.
- **Tiri di Dado e Incantesimi (`🎲` / `🪄`)**: quando un tiro o un incantesimo/abilità decisivo cambia l'esito della scena, annotalo in corsivo tra parentesi: es. `*(🎲 TS Costituzione superato)*`, `*(🎲 Intuizione: 18)*`, `*(🪄 Dissolvi Magie di 7° livello)*`.
- **Monitoraggio Audio (`🔇 Monitoraggio Audio`)**: confronta il report `🔇 Monitoraggio Audio / Buchi Trascrizione` dello script e i salti `[HH:MM:SS]` (>= 45-60s o troncamenti finali) con il contesto per distinguere **Segmento mutato da YouTube (Copyright) / Taglio Audio** (parlato interrotto di netto o finale mancante) da **Silenzio di gioco / Chat privata** (azioni segrete su WhatsApp/Telegram/Discord dichiarate al tavolo o pausa), riportando l'esito nella riga `🔇 **Monitoraggio Audio:**`.

---

## 4. Flusso Trascrizione Locale & Storpiature Fonetiche

### Flusso per File di Trascrizione Locale (`trascrizioni/<nome_file>.txt`)

1. Leggi `docs/glossari/glossario.md`, `docs/glossari/glossario_<YYYY>.md` (se esistente) e `trascrizioni/<nome_file>.txt` (a blocchi di righe se supera il limite di singola lettura).
2. Ricava la data della sessione da `channel_videos_cache.json` (o dal nome del file).
3. Esegui la generazione/salvataggio del riassunto Markdown (Sezione 3), l'aggiornamento dei glossari (Sezione 2) e l'aggiornamento di `processed_videos.json` (Sezione 1).

### Correzione Storpiature Fonetiche (Esempi Comuni)

I sottotitoli automatici di YouTube storpiano frequentemente i nomi fantasy. Verifica sempre su `docs/glossari/glossario.md`, `docs/glossari/glossario_<YYYY>.md` e dal contesto per scrivere i nomi canonici e annotare eventuali nuove storpiature tra le varianti fonetiche:
- `"Caret"` ➔ **Kareth El Mora**
- `"Serah"` ➔ **Sera Ninvil**
- `"Yokul"` ➔ **Casata Jokul**
- `"Atasharev"` ➔ **Saggio Atashkarev**
- Altre trascrizioni fonetiche frequenti da controllare: *"Velendoran"*, *"Osiro"*, *"Baltasar"*, *"Gideon"*.
