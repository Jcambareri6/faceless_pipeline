# faceless_pipeline

Pipeline de automatización de contenido para canales de YouTube Shorts (y,
como caption secundario, TikTok). Flujo 100% asistido por Telegram: nada se
sube solo a ninguna plataforma. Vos aprobás cada guion y cada video a mano;
el pipeline solo prepara todo listo para copiar/pegar.

Multi-canal desde el día 1:

- 💰 `money_curiosities` — finanzas y economía, formato "por qué pasó esto".
- 🏛️ `history_geopolitics` — historia y geopolítica, mismo formato.

## Instalación

1. Python 3.11+.
2. `pip install -r requirements.txt` (instala, entre otras cosas, `openai-whisper`
   + `torch`; la primera instalación puede tardar varios minutos).
3. **ffmpeg** tiene que estar instalado en el sistema y accesible como comando
   `ffmpeg` en una terminal nueva. Lo usan `generate_subtitles.py` (via Whisper)
   y `generate_video.py` directamente.
   - Windows: `winget install --id Gyan.FFmpeg -e`, después reiniciá la
     terminal (el PATH no se actualiza en una consola ya abierta).
   - macOS: `brew install ffmpeg`.
   - Linux: `apt-get install ffmpeg` (esto ya lo hace `telegram-listener.yml`
     automáticamente en GitHub Actions).
4. Copiá `.env.example` a `.env` y completá las 5 variables (ver abajo) si vas
   a correr algo localmente con `app.py`.

## Variables de entorno / Secrets

Son 5 en total. En local van en `.env` (o exportadas en la shell); en GitHub
van como **Secrets** del repo (Settings → Secrets and variables → Actions).

| Variable | Para qué | Dónde conseguirla |
|---|---|---|
| `ANTHROPIC_API_KEY` | Genera guiones, metadata y ajustes de keywords con Claude | [console.anthropic.com](https://console.anthropic.com) → API Keys. Requiere cargar crédito, no tiene free tier. |
| `TELEGRAM_BOT_TOKEN` | Autentica al bot que manda/recibe todos los mensajes | Hablarle a **@BotFather** en Telegram → `/newbot`. Gratis. |
| `TELEGRAM_CHAT_ID` | A qué chat le manda todo el bot | Mandale un mensaje cualquiera a tu bot, después abrí `https://api.telegram.org/bot<TOKEN>/getUpdates` en el navegador y buscá `"chat":{"id": ...}`. |
| `PEXELS_API_KEY` | Busca/descarga el b-roll de cada escena | [pexels.com/api](https://www.pexels.com/api/) → crear cuenta, la key se genera al instante. Gratis, 200 req/hora / 20.000/mes. |
| `YOUTUBE_API_KEY` | Investigación de competencia semanal | Ver paso a paso abajo. |

### Cómo conseguir `YOUTUBE_API_KEY` (Google Cloud Console)

1. Entrá a [console.cloud.google.com](https://console.cloud.google.com).
2. Creá un proyecto nuevo (o usá uno existente).
3. Menú → **APIs & Services → Library** → buscá "YouTube Data API v3" → **Enable**.
4. **APIs & Services → Credentials → Create Credentials → API Key**.
5. (Recomendado) Restringí la key a "YouTube Data API v3" para que no sirva
   para otras APIs si se filtra.

**Cuota**: el proyecto arranca con **10.000 unidades/día**, gratis, sin tarjeta.
`search.list` cuesta 100 unidades por llamada; `videos.list` cuesta 1 unidad.
`search_competitor_videos()` hace exactamente 1 `search.list` + 1 `videos.list`
por corrida = **101 unidades por canal**. Con 2 canales, 1 vez por semana, son
202 unidades semanales — un **2% de la cuota de un solo día**. Sobra cuota de
sobra incluso si algún día lo corrés a mano varias veces seguidas para debug.

### Límite real: la API no filtra "es un Short"

La YouTube Data API v3 no tiene un flag "isShort". El filtro más fino que
ofrece `search.list` es `videoDuration=short`, que significa **"menos de 4
minutos"**, no "es un Short". `competitor_research.py` lo compensa en dos
pasos: primero pide `videoDuration=short`, y después, con los datos de
`videos.list` (que sí trae la duración exacta en `contentDetails.duration`),
descarta todo lo que supere ~183 segundos (el límite real de Shorts, que
YouTube extendió a 3 minutos). No es 100% preciso — puede colarse algún video
corto que no sea técnicamente un Short, o perderse alguno mal categorizado —
pero es la mejor aproximación posible con esta API pública.

## Probar cada módulo standalone

Casi todos los módulos tienen un bloque `if __name__ == "__main__"` para
probarlos sueltos:

```bash
python fetch_topics.py --channel money_curiosities
python rank_topics.py --channel money_curiosities --top 10
python generate_script.py --channel money_curiosities --title "..." --summary "..."
python generate_audio.py --channel money_curiosities --text "..." --output test.mp3
python generate_subtitles.py --audio test.mp3
python fetch_footage.py --channel money_curiosities
python generate_video.py --channel money_curiosities --audio test.mp3 --clips a.mp4 b.mp4 --mode preview
python competitor_research.py --channel money_curiosities
python generate_metadata.py --channel money_curiosities --title "..."
```

`rank_topics.py`, `fetch_topics.py`, `generate_audio.py`, `generate_subtitles.py`
y `fetch_footage.py` no necesitan `ANTHROPIC_API_KEY` (RSS, edge-tts, Whisper y
Pexels no dependen de Claude). `generate_script.py`, `generate_metadata.py` y
`competitor_research.py` sí necesitan sus keys correspondientes.

## Cómo probar el flujo completo en tu máquina antes de subir nada

1. Seteá las 5 variables de entorno (`.env` + tu forma preferida de cargarlo,
   o exportadas a mano en la shell).
2. Corré `python app.py --channel money_curiosities --title "algún tema" --summary "..."`.
   Esto hace guion → audio → subtítulos → footage → preview, te lo deja en
   `manual_runs/<id>/preview.mp4`, y te pregunta por consola si aprobás. Si
   decís que sí, genera la versión final + metadata y te la imprime en la
   terminal — todo sin tocar Telegram ni GitHub.
3. Cuando eso funcione, probá el flujo real: corré `python orchestrator.py
   --channel money_curiosities` a mano (manda guiones candidatos a tu
   Telegram), apretá "✅ Usar este guion", y después corré `python
   telegram_listener.py` a mano para que procese el click (en producción esto
   lo dispara el cron cada 10 min, pero localmente lo corrés cuando quieras).
   Repetí `telegram_listener.py` cada vez que apretes un botón nuevo.
4. Recién cuando todo esto funcione local, pusheá a GitHub, cargá los 5
   Secrets, y dejá que los workflows corran solos.

## El flujo preview → iterar → aprobar → final

1. `orchestrator.py` (2x/día) manda hasta 3 guiones candidatos por canal a
   Telegram, cada uno con estado `pendiente`.
2. Apretás "✅ Usar este guion" → pasa a `guion_aprobado` y enseguida a
   `preview_generado`: se genera audio, subtítulos, footage y un video en
   **baja calidad** (rápido), con 4 botones.
3. Podés iterar cuantas veces quieras:
   - 🔄 **Regenerar video**: vuelve a buscar footage (evitando los clips ya
     usados) y arma un preview nuevo. Si le dejaste una nota de texto (ver
     abajo), Claude ajusta los `visual_keywords` de las escenas según esa
     nota antes de rebuscar.
   - 🎙️ **Regenerar solo voz**: vuelve a sintetizar el audio y los
     subtítulos, reusando el mismo footage.
   - Respondé (reply) al mensaje del preview con texto libre para dejar una
     nota — se guarda y se tiene en cuenta la próxima vez que regenerás el
     video. No dispara nada automático por sí sola.
4. ✅ **Aprobar - versión final**: genera el video en alta calidad (mismo
   footage/audio del último preview) + título/descripción/hashtags/caption de
   TikTok optimizados, y te lo manda todo listo para copiar y pegar a mano.
5. ❌ **Descartar** en cualquier momento del camino.

## La cadena de fallback de footage (Paso 7)

Por cada escena, `fetch_footage_for_scenes` prueba en orden:

1. `visual_keywords[0]` (lo más específico y filmable) → si hay un clip que
   cumple duración mínima y calidad mínima, listo.
2. Si no, `visual_keywords[1]` (más amplio).
3. Si no, `visual_keywords[2]` (genérico pero temático).
4. Si los tres fallan, un clip random de `channel.FALLBACK_KEYWORDS` — nunca
   deja una escena sin clip. Si ni siquiera eso encuentra nada (Pexels caído,
   sin conectividad), recién ahí levanta un error explícito.

Cada resultado queda marcado `match_quality`: `"specific"` (keyword 0),
`"broad"` (keyword 1 o 2), o `"fallback"`.

## Cómo usa la investigación de competencia `generate_metadata.py`

`competitor_research.py` (semanal) guarda en `competitor_insights_{slug}.json`
palabras frecuentes en títulos ganadores, hashtags más usados, y longitud de
título promedio de los shorts con más vistas del nicho. Mientras ese archivo
tenga **menos de 7 días**, `generate_metadata.py` se lo pasa a Claude como
contexto ("estos patrones probaron funcionar, inspirate pero no copies
textual"). Si no existe o está vencido, genera la metadata igual, sin ese
contexto, y avisa por log que conviene correr `competitor_research.py` pronto.

## Cómo agregar un tercer canal

1. Creá `channels/mi_canal_nuevo.py` copiando la forma de los otros dos:
   `CHANNEL_SLUG`, `CHANNEL_EMOJI`, `NICHE_DESCRIPTION` y `TARGET_AUDIENCE`
   **en inglés** (se usan tal cual en los prompts de Claude y en el matching
   de keywords contra artículos en inglés), `RSS_FEEDS` (verificá que las
   URLs respondan y devuelvan XML real antes de usarlas), `TTS_VOICE` (una
   voz de edge-tts distinguible de los otros canales), `AFFILIATE_TAG`, y
   `FALLBACK_KEYWORDS`.
2. Agregá el slug a `AVAILABLE_CHANNELS` en `config.py`.
3. Agregalo al `matrix.channel` de los 3 workflows en `.github/workflows/`.

No hace falta tocar ningún otro módulo: todos reciben `channel` como
parámetro y leen sus datos de ahí.

## Cuándo sumar Amazon Associates

`AFFILIATE_TAG` está en `None` en los dos canales por ahora. Tiene sentido
activarlo cuando: (a) el canal ya tenga tracción real (viste consistente,
no solo los primeros videos), y (b) el contenido se preste naturalmente a
recomendar productos físicos relacionados (ej. libros de historia/finanzas,
no "consejos de inversión" — que además el propio `NICHE_DESCRIPTION` de
`money_curiosities` prohíbe explícitamente). Para activarlo: creá una cuenta
en [Amazon Associates](https://afiliados.amazon.com/), conseguí tu tracking
ID, y seteá `AFFILIATE_TAG = "tu-tag-20"` en el `channels/*.py` que
corresponda — `generate_metadata.py` ya agrega el link automáticamente al
final de la descripción cuando el tag no es `None`.

## Nota sobre el tamaño del repo

`drafts/` termina guardando audio, footage y video de cada draft (necesario:
los runners de GitHub Actions son efímeros, así que el propio repo es la
"base de datos" entre corridas). Con el tiempo esto puede crecer bastante.
Si se vuelve un problema, una opción simple es agregar un paso de limpieza
que borre la carpeta de media (no el `.json`) de los drafts en estado
`final_aprobado` o `descartado` de más de N días.
