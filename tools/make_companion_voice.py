"""Record Study Buddy's voice lines once, so she can speak offline afterwards.

Free, on this PC, with VOICEVOX (open the VOICEVOX app first; its engine listens on 127.0.0.1:50021):

    python tools/make_companion_voice.py --list-voicevox                  # the characters and their styles
    python tools/make_companion_voice.py --samples 四国めたん 九州そら     # a page in Downloads to compare them
    python tools/make_companion_voice.py --voicevox 四国めたん             # record every line in her voice
    python tools/make_companion_voice.py --voicevox 四国めたん --speed 1.1 --pitch 0.05 --intonation 1.4

Each line uses the character's style for its mood (MOODS: annoyed for the reminder, whispering late at
night, happy when tests pass). English is read with a Japanese accent. Nothing leaves this PC. VOICEVOX's
terms ask for the credit "VOICEVOX:<character>", which Settings shows; each character has its own terms.

Or with an ElevenLabs voice (the paid API, or the free website with --website / --import):

    python tools/make_companion_voice.py --dry-run     # list the lines and how many characters they use
    python tools/make_companion_voice.py               # record them (needs your ElevenLabs API key)

ElevenLabs is the only part of Jarvis that contacts an outside service, and only when you run it: it sends
the fixed lines below (nothing of yours: no chats, tasks, files or names) to ElevenLabs and saves the
audio in jarvis/static/companion/voice and android/app/assets/companion/voice. After that, playing
them needs no internet and nothing is sent anywhere.

Your API key is read from the ELEVENLABS_API_KEY environment variable or from the file
%APPDATA%\\Jarvis\\elevenlabs.key (one line). It is never printed or saved anywhere else.
Library voices may need "Add to my voices" on the ElevenLabs website first. The recordings are for
your own use; ElevenLabs' terms for your plan apply (the free plan asks for attribution).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "jarvis" / "static" / "companion" / "voice"
ANDROID = ROOT / "android" / "app" / "assets" / "companion" / "voice"
VOICE_ID = "fUjY9K2nAIwlALOwSiwc"  # "Yui" (Japanese female anime voice) in the ElevenLabs voice library
MODEL = "eleven_multilingual_v2"  # speaks English and Japanese with the same voice

# What Study Buddy says, per event. Short and fixed, so they can be recorded once.
LINES = {
    "en": {
        "hello_morning": "Good morning! Ready to learn something new?",
        "hello_afternoon": "Good afternoon! Let's do this together.",
        "hello_evening": "Good evening! One small step at a time.",
        "hello_late": "Still up? Don't forget to rest, okay?",
        "checkin": "Before we start, how are you feeling right now?",
        "start_coding": "Coding session started. Let's go!",
        "start_study": "Study session started. You've got this!",
        "nudge": "Hmph! You've been quiet for a while. Are you still with me?",
        "back": "You're back! Let's keep going.",
        "done_coding": "Coding session done! Great work. Take a short break.",
        "done_study": "Study session done! Great work. Take a short break.",
        "break_start": "Break time! Stand up, drink some water, and rest your eyes.",
        "break_end": "Break's over. Ready for one small step?",
        "passed": "All tests pass! That's real progress!",
        "failed": "Not yet. Read the first error, fix one thing, and try again.",
        "reviews_done": "Reviews done! Your future self says thank you.",
        "long_work": "You've been working for almost an hour. Let's take a short break.",
    },
    "ja": {
        "hello_morning": "おはよう！今日も新しいこと、学ぼうね。",
        "hello_afternoon": "こんにちは！一緒にがんばろう。",
        "hello_evening": "こんばんは！一歩ずつ、いこうね。",
        "hello_late": "まだ起きてるの？ちゃんと休んでね。",
        "checkin": "始める前に、今の調子はどう？",
        "start_coding": "コーディングセッション、スタート！がんばろう！",
        "start_study": "学習セッション、スタート！きっとできるよ！",
        "nudge": "むー！しばらく静かだったよ。まだいる？",
        "back": "おかえり！続けよう。",
        "done_coding": "コーディングセッション完了！よくがんばったね。少し休憩しよう。",
        "done_study": "学習セッション完了！よくがんばったね。少し休憩しよう。",
        "break_start": "休憩タイム！立って、水を飲んで、目を休めてね。",
        "break_end": "休憩おしまい。小さな一歩からいこう。",
        "passed": "テスト全部合格！すごい進歩だよ！",
        "failed": "まだだよ。最初のエラーを読んで、一つ直して、もう一回。",
        "reviews_done": "復習完了！未来の自分がありがとうって。",
        "long_work": "もうすぐ一時間、がんばってるね。少し休憩しよう。",
    },
}


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        f = Path(os.environ.get("APPDATA", Path.home())) / "Jarvis" / "elevenlabs.key"
        if f.exists():
            key = f.read_text(encoding="utf-8-sig").strip()  # -sig: Notepad may add a byte-order mark
    if not key:
        raise SystemExit("No ElevenLabs API key: put it in %APPDATA%\\Jarvis\\elevenlabs.key (one line) "
                         "or the ELEVENLABS_API_KEY environment variable, then run this again.")
    return key


def record(key: str, voice: str, text: str) -> bytes:
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_64",
        data=json.dumps({"text": text, "model_id": MODEL,
                         "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.3}}).encode("utf-8"),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"}, method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            if exc.code in (401, 403) or "api_key" in detail:
                raise SystemExit("ElevenLabs refused the API key. Use the key itself (it starts with sk_ and is shown "
                                 "only once, when you create it), not the key's ID or name.")
            if exc.code in (400, 404) and "voice" in detail.lower():
                raise SystemExit("ElevenLabs can't use that voice with your account yet: open the voice's page and "
                                 f"click 'Add to my voices', then run this again. ({detail})")
            raise SystemExit(f"ElevenLabs said {exc.code}: {detail}")
    raise SystemExit("ElevenLabs kept saying 'too many requests'; try again in a minute.")


# ---------------------------------------------------------------- VOICEVOX: free, runs on this PC (no account, nothing sent)
VOICEVOX = "http://127.0.0.1:50021"
# How she feels in each line; each mood uses the first of these styles the character has.
MOODS = {
    "hello_morning": "happy", "hello_afternoon": "normal", "hello_evening": "sweet", "hello_late": "whisper",
    "checkin": "sweet", "start_coding": "happy", "start_study": "normal", "nudge": "tsun", "back": "sweet",
    "done_coding": "happy", "done_study": "happy", "break_start": "sweet", "break_end": "normal",
    "passed": "happy", "failed": "sad", "reviews_done": "sweet", "long_work": "sweet",
}
STYLES = {
    "happy": ["喜び", "たのしい", "わーい", "元気", "うきうき", "明るい", "あまあま", "甘々"],
    "sweet": ["あまあま", "甘々", "ぶりっ子", "のんびり", "おちつき"],
    "tsun": ["ツンツン", "怒り", "おこ", "ツンギレ", "不機嫌", "呆れ", "つよつよ"],
    "whisper": ["ささやき", "囁き", "ヒソヒソ", "内緒話"],
    "sad": ["なみだめ", "かなしい", "悲しみ", "哀しみ", "かなしみ", "泣き", "よわよわ"],
    "normal": ["ノーマル", "ふつう"],
}
# VOICEVOX reads English as Japanese-accented English; a few words read better spelled out.
SPOKEN_EN = {"That's": "That is", "Let's": "Lets", "tests": "test cases", "Don't": "Do not", "Break's": "Break is",
             "You've": "You have", "You're": "You are"}


def voicevox(path: str, params: dict | None = None, body: dict | None = None) -> bytes:
    from urllib.parse import urlencode
    req = urllib.request.Request(f"{VOICEVOX}{path}?{urlencode(params or {})}", method="POST" if body is not None or path != "/speakers" else "GET",
                                 data=json.dumps(body).encode("utf-8") if body is not None else (b"" if path != "/speakers" else None),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"VOICEVOX isn't running on this PC ({exc}). Open the VOICEVOX app, then run this again.")


def voicevox_styles(character: str) -> dict[str, int]:
    """Style name -> id for one VOICEVOX character (e.g. 九州そら)."""
    for s in json.loads(voicevox("/speakers")):
        if s["name"] == character:
            return {st["name"]: st["id"] for st in s["styles"] if st.get("type", "talk") == "talk"}
    raise SystemExit(f"No VOICEVOX character called {character}. Run with --list-voicevox to see them.")


def record_voicevox(character: str, speed: float, pitch: float, intonation: float, only: str = "") -> None:
    import subprocess
    import tempfile
    styles = voicevox_styles(character)
    normal = next((styles[n] for n in STYLES["normal"] if n in styles), next(iter(styles.values())))
    manifest = {"voice": character, "engine": "VOICEVOX", "credit": f"VOICEVOX:{character}", "lines": {},
                "settings": {"speed": speed, "pitch": pitch, "intonation": intonation}}
    for lang, lines in LINES.items():
        if only and lang != only:
            continue
        (OUT / lang).mkdir(parents=True, exist_ok=True)
        manifest["lines"][lang] = {}
        for key, text in lines.items():
            mood = MOODS.get(key, "normal")
            style = next((styles[n] for n in STYLES[mood] if n in styles), normal)
            spoken = text
            if lang == "en":
                for a, b in SPOKEN_EN.items():
                    spoken = spoken.replace(a, b)
            query = json.loads(voicevox("/audio_query", {"text": spoken, "speaker": style}))
            query.update(speedScale=speed, pitchScale=pitch, intonationScale=intonation,
                         prePhonemeLength=0.05, postPhonemeLength=0.15)
            wav = voicevox("/synthesis", {"speaker": style}, query)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav)
            dest = OUT / lang / f"{key}.mp3"
            subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", f.name, "-c:a", "libmp3lame",
                            "-b:a", "64k", str(dest)], check=True)
            os.unlink(f.name)
            manifest["lines"][lang][key] = {"file": f"voice/{lang}/{key}.mp3", "text": text, "mood": mood}
            print(f"  {lang}/{key} ({mood})", flush=True)
    (OUT / "voice.json").write_bytes(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    if ANDROID.exists():
        shutil.rmtree(ANDROID)
    shutil.copytree(OUT, ANDROID)
    print(f"Done with VOICEVOX:{character}. Credit shown in Settings: VOICEVOX:{character}.")


def voicevox_samples(characters: list[str], dest: Path) -> None:
    """A page to hear several characters say the same lines (normal, annoyed, English), to choose one."""
    import base64
    rows = []
    for character in characters:
        styles = voicevox_styles(character)
        normal = next((styles[n] for n in STYLES["normal"] if n in styles), next(iter(styles.values())))
        tsun = next((styles[n] for n in STYLES["tsun"] if n in styles), normal)
        clips = []
        for label, style, text in (("Japanese", normal, LINES["ja"]["hello_morning"]),
                                   ("Annoyed (the reminder)", tsun, LINES["ja"]["nudge"]),
                                   ("English", normal, "Good morning! Ready to learn something new?")):
            q = json.loads(voicevox("/audio_query", {"text": text, "speaker": style}))
            q.update(speedScale=1.05, pitchScale=0.03, intonationScale=1.25)
            audio = base64.b64encode(voicevox("/synthesis", {"speaker": style}, q)).decode()
            clips.append(f"<div><span>{label}</span><audio controls src='data:audio/wav;base64,{audio}'></audio></div>")
        rows.append(f"<section><h2>{character}</h2>{''.join(clips)}</section>")
        print(f"  sampled {character}", flush=True)
    dest.write_text("<!doctype html><meta charset='utf-8'><title>Study Buddy voices</title>"
                    "<style>body{font-family:system-ui;max-width:760px;margin:24px auto;padding:0 16px}section{border:1px solid #ccc;"
                    "border-radius:12px;padding:8px 14px;margin:10px 0}div{display:flex;gap:12px;align-items:center;margin:6px 0}"
                    "span{width:190px}</style><h1>Study Buddy: pick her voice</h1>"
                    "<p>Made on this PC with VOICEVOX. Tell Claude the name you like.</p>" + "".join(rows), encoding="utf-8")


# ---------------------------------------------------------------- free plan: record on the website, cut here
PAUSE = '<break time="1.5s" />'  # Multilingual v2 pauses here; the cuts go in the longest pauses


def website_texts(path: Path) -> None:
    """The two texts to paste into ElevenLabs' website (free accounts can't use library voices via the API)."""
    parts = ["Study Buddy's voice: paste each text below into ElevenLabs (elevenlabs.io > Text to Speech).",
             "Settings there: voice Yui, model 'Eleven Multilingual v2'. Generate, then download the audio.",
             "Do ENGLISH first, then JAPANESE, and tell Claude when both are downloaded.", ""]
    for lang, title in (("en", "ENGLISH"), ("ja", "JAPANESE")):
        parts += [f"===== {title} (copy everything between the lines) =====", f" {PAUSE} ".join(LINES[lang].values()),
                  "=" * 60, ""]
    path.write_text("\n".join(parts), encoding="utf-8")


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise SystemExit("ffmpeg isn't installed (winget install Gyan.FFmpeg), so the recordings can't be cut.")
    return found


def pauses(path: Path) -> tuple[float, list[tuple[float, float]]]:
    """Length of a recording and its pauses (start, end), from ffmpeg's silence detection."""
    import re
    import subprocess
    out = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path), "-af", "silencedetect=noise=-38dB:d=0.3", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    length = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    total = int(length[1]) * 3600 + int(length[2]) * 60 + float(length[3]) if length else 0.0
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return total, list(zip(starts, ends + [total] * (len(starts) - len(ends))))


def import_recordings(files: dict[str, Path], name: str, voice: str) -> None:
    """Cut each language's recording into one clip per line, at its longest pauses."""
    import subprocess
    manifest = {"voice": name, "voice_id": voice, "model": MODEL, "credit": f"Voice: {name} (ElevenLabs)", "lines": {}}
    for lang, src in files.items():
        keys = list(LINES[lang])
        total, gaps = pauses(src)
        inner = [g for g in gaps if g[0] > 0.2 and g[1] < total - 0.2]  # not the silence at the very start or end
        if len(inner) < len(keys) - 1:
            raise SystemExit(f"{src.name}: found {len(inner)} pauses but needs {len(keys) - 1}. Was it made with "
                             "'Eleven Multilingual v2' from the text in the file?")
        cuts = sorted(sorted(inner, key=lambda g: g[1] - g[0], reverse=True)[:len(keys) - 1])
        first = next((g[1] for g in gaps if g[0] <= 0.2), 0.0)  # skip the silence before the first line
        last = next((g[0] for g in gaps if g[1] >= total - 0.2), total)  # and after the last one
        bounds = [(first, cuts[0][0])] + [(cuts[i][1], cuts[i + 1][0]) for i in range(len(cuts) - 1)] + [(cuts[-1][1], last)]
        (OUT / lang).mkdir(parents=True, exist_ok=True)
        manifest["lines"][lang] = {}
        for key, (start, end) in zip(keys, bounds):
            dest = OUT / lang / f"{key}.mp3"
            subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0, start - 0.06):.3f}",
                            "-to", f"{end + 0.15:.3f}", "-i", str(src), "-af", "afade=t=in:d=0.03", "-c:a", "libmp3lame",
                            "-b:a", "64k", str(dest)], check=True)
            manifest["lines"][lang][key] = {"file": f"voice/{lang}/{key}.mp3", "text": LINES[lang][key]}
            print(f"  {lang}/{key}: {end - start:.1f}s", flush=True)
    (OUT / "voice.json").write_bytes(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    if ANDROID.exists():
        shutil.rmtree(ANDROID)
    shutil.copytree(OUT, ANDROID)
    print(f"Done: {sum(len(v) for v in manifest['lines'].values())} clips in {OUT} and {ANDROID}.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", default=VOICE_ID, help="ElevenLabs voice id (default: Yui)")
    ap.add_argument("--name", default="Yui", help="the voice's name, shown in Settings")
    ap.add_argument("--dry-run", action="store_true", help="only list the lines and the characters they use")
    ap.add_argument("--website", metavar="FILE", help="write the texts to paste into ElevenLabs' website (free plan)")
    ap.add_argument("--import", dest="recordings", nargs=2, metavar=("ENGLISH.mp3", "JAPANESE.mp3"),
                    help="cut the two recordings made on the website into one clip per line")
    ap.add_argument("--voicevox", metavar="CHARACTER", help="record with VOICEVOX on this PC instead, e.g. 九州そら")
    ap.add_argument("--speed", type=float, default=1.05, help="VOICEVOX speaking speed (1.0 = normal)")
    ap.add_argument("--pitch", type=float, default=0.03, help="VOICEVOX pitch shift (0 = normal; small steps like 0.03)")
    ap.add_argument("--intonation", type=float, default=1.25, help="VOICEVOX expressiveness (1.0 = normal)")
    ap.add_argument("--samples", nargs="+", metavar="CHARACTER", help="write a page to compare VOICEVOX characters")
    ap.add_argument("--list-voicevox", action="store_true", help="list the VOICEVOX characters and their styles")
    args = ap.parse_args()
    if args.list_voicevox:
        for s in json.loads(voicevox("/speakers")):
            print(f"{s['name']}: " + ", ".join(st["name"] for st in s["styles"] if st.get("type", "talk") == "talk"))
        return
    if args.samples:
        page = Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads" / "Study Buddy voices.html"
        voicevox_samples(args.samples, page)
        print(f"Wrote {page}")
        return
    if args.voicevox:
        record_voicevox(args.voicevox, args.speed, args.pitch, args.intonation)
        return
    if args.website:
        website_texts(Path(args.website))
        print(f"Wrote {args.website}")
        return
    if args.recordings:
        import_recordings({"en": Path(args.recordings[0]), "ja": Path(args.recordings[1])}, args.name, args.voice)
        return
    chars = sum(len(t) for lines in LINES.values() for t in lines.values())
    print(f"{sum(len(v) for v in LINES.values())} lines, {chars} characters (counted against your ElevenLabs quota).")
    if args.dry_run:
        for lang, lines in LINES.items():
            for k, t in lines.items():
                print(f"  {lang}/{k}: {t}")
        return
    key = api_key()
    manifest = {"voice": args.name, "voice_id": args.voice, "model": MODEL, "credit": f"Voice: {args.name} (ElevenLabs)", "lines": {}}
    for lang, lines in LINES.items():
        (OUT / lang).mkdir(parents=True, exist_ok=True)
        manifest["lines"][lang] = {}
        for k, text in lines.items():
            audio = record(key, args.voice, text)
            (OUT / lang / f"{k}.mp3").write_bytes(audio)
            manifest["lines"][lang][k] = {"file": f"voice/{lang}/{k}.mp3", "text": text}
            print(f"  recorded {lang}/{k} ({len(audio) // 1024} KB)", flush=True)
    (OUT / "voice.json").write_bytes(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    if ANDROID.exists():
        shutil.rmtree(ANDROID)
    shutil.copytree(OUT, ANDROID)  # the floating Study Buddy on Android speaks too
    print(f"Done. Saved in {OUT} and {ANDROID}. Rebuild the Android app to include them.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
