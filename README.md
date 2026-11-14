# Timer From Video

Piccola app Windows (un solo `.exe`). Trascina un video o un audio nella finestra
e genera un video con un timer countdown `hh:mm:ss:ff` che parte dalla durata del
sorgente e arriva a `00:00:00:00`.

- Larghezza impostabile (default 1920); XX
  sorgente (16:9 se è un audio).
- FPS impostabili (default 25).
- Codec: MP4 (H.264, default) o HAP (`.mov`).
- Output `<nome>_timer.mp4/.mov` accanto al sorgente, oppure in una cartella a scelta.
- Le impostazioni sono salvate in `%APPDATA%\TimerFromVideo\settings.json`.

L'exe include ffmpeg: non serve installare nulla.

## Build

L'exe viene compilato da GitHub Actions (artifact di ogni push; con un tag `v*`
viene allegato anche a una Release). In locale:

```
pip install -r requirements.txt
pyinstaller --onefile --windowed --name TimerFromVideo --collect-all tkinterdnd2 --collect-all imageio_ffmpeg timer_from_video.py
```
