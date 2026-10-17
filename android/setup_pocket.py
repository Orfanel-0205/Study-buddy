"""Set up Jarvis to run on the phone itself (inside Termux), from this computer over USB.

    python android/setup_pocket.py

Needs: the phone connected with USB debugging on, the Termux app installed (the GitHub
build, which allows setup over USB), Jarvis running on this computer with phone access on
(for pairing the two copies), and internet on the phone once (Termux downloads Python, Ollama,
Node.js and PHP, about 700 MB). The models are copied from this computer, not downloaded.

Each step can safely be run again. What it does:
 1. starts Termux once so it unpacks itself
 2. lets the Jarvis app start commands in Termux (allow-external-apps)
 3. installs Python, Ollama, Node.js, PHP (for coding practice) and Jarvis's Python packages in Termux
 4. copies Jarvis's code and the models (qwen3:1.7b, qwen3-vl:2b)
 5. writes the start/pair scripts the Jarvis app uses
 6. pairs the phone's Jarvis with this computer's Jarvis for syncing
 7. only with --allow-background: turns off Android's "phantom process" limit (a system setting),
    which can otherwise stop Ollama while the phone runs many background processes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TERMUX = "com.termux"
FILES = "/data/data/com.termux/files"
PREFIX = f"{FILES}/usr"
HOME = f"{FILES}/home"
POCKET = f"{HOME}/jarvis-pocket"
TMP = "/data/local/tmp"
MODELS = [("qwen3", "1.7b"), ("qwen3-vl", "2b")]
ENV = f"""export PREFIX={PREFIX} HOME={HOME} TMPDIR={PREFIX}/tmp LANG=en_US.UTF-8
export PATH={PREFIX}/bin LD_PRELOAD={PREFIX}/lib/libtermux-exec.so
export DEBIAN_FRONTEND=noninteractive
# Under run-as, termux-exec would start programs through Android's linker, which makes Ollama look for
# its runner next to the linker instead of in $PREFIX/lib/ollama. The Termux app itself runs them directly.
export TERMUX_EXEC__SYSTEM_LINKER_EXEC__MODE=disable
cd {HOME}
"""


def find_adb() -> str:
    found = shutil.which("adb")
    if found:
        return found
    for c in Path(os.environ.get("LOCALAPPDATA", "")).glob("Microsoft/WinGet/Packages/Google.PlatformTools*/platform-tools/adb.exe"):
        return str(c)
    raise SystemExit("adb not found. Install Android platform-tools.")


ADB = find_adb()


def adb(*args: str, check: bool = True, timeout: int = 600) -> str:
    r = subprocess.run([ADB, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    if check and r.returncode != 0:
        raise SystemExit(f"adb {' '.join(args[:3])} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def termux(script: str, timeout: int = 1800, check: bool = True) -> str:
    """Run a bash script inside Termux (as the Termux app) and return its output."""
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, newline="\n", encoding="utf-8") as f:
        f.write(ENV + script)
    adb("push", f.name, f"{TMP}/jarvis-step.sh")
    os.unlink(f.name)
    adb("shell", "chmod", "644", f"{TMP}/jarvis-step.sh")
    r = subprocess.run([ADB, "shell", "run-as", TERMUX, f"{PREFIX}/bin/bash", f"{TMP}/jarvis-step.sh"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    out = (r.stdout + r.stderr).strip()
    if check and r.returncode != 0:
        raise SystemExit(f"Step failed inside Termux:\n{out[-3000:]}")
    return out


def copy_code() -> None:
    """Copy the jarvis package from this computer into Termux (replacing the old copy)."""
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "jarvis"
        shutil.copytree(ROOT / "jarvis", bundle, ignore=shutil.ignore_patterns("__pycache__"))
        adb("shell", "rm", "-rf", f"{TMP}/jarvis-app")
        adb("push", str(bundle), f"{TMP}/jarvis-app/jarvis")
    adb("shell", "chmod", "-R", "a+rX", f"{TMP}/jarvis-app")
    termux(f"""set -e
mkdir -p {POCKET}/app
rm -rf {POCKET}/app/jarvis
cp -r {TMP}/jarvis-app/jarvis {POCKET}/app/
""")
    adb("shell", "rm", "-rf", f"{TMP}/jarvis-app")
    print("  Code copied.", flush=True)


def step(n: int, text: str) -> None:
    print(f"\n[{n}/7] {text}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--laptop", default="http://127.0.0.1:8765", help="this computer's Jarvis (for pairing)")
    parser.add_argument("--skip-models", action="store_true")
    parser.add_argument("--repair", action="store_true", help="pair with the laptop again even if already paired")
    parser.add_argument("--code-only", action="store_true",
                        help="only copy this computer's Jarvis code to the phone (after an update)")
    parser.add_argument("--allow-background", action="store_true",
                        help="also turn off Android's phantom-process limit (a system setting; undo command is printed)")
    args = parser.parse_args()

    if TERMUX not in adb("shell", "pm", "list", "packages", TERMUX):
        raise SystemExit("Termux is not installed on the phone yet.")

    if args.code_only:
        print("Updating Jarvis's code on the phone (no downloads)…", flush=True)
        copy_code()
        # A running Jarvis keeps the old code in memory: stop it; the Jarvis app starts it again when needed.
        print("  " + (termux("pkill -f 'python -m jarvis --pocket' && echo 'Stopped the running Jarvis; it restarts "
                             "with the new code next time the app needs it.' || echo 'Jarvis was not running.'",
                             check=False).splitlines() or ["done"])[-1])
        return

    step(1, "Starting Termux once so it unpacks itself")
    if "bash" not in adb("shell", "run-as", TERMUX, "ls", f"{PREFIX}/bin/", check=False):
        adb("shell", "am", "start", "-n", f"{TERMUX}/.app.TermuxActivity")
        for _ in range(90):
            time.sleep(2)
            if "bash" in adb("shell", "run-as", TERMUX, "ls", f"{PREFIX}/bin/", check=False):
                break
        else:
            raise SystemExit("Termux didn't finish setting itself up. Open it once on the phone and try again.")
        time.sleep(3)
    print("  Termux is ready.")

    step(2, "Allowing the Jarvis app to start Jarvis inside Termux")
    termux("""mkdir -p ~/.termux
grep -q '^allow-external-apps' ~/.termux/termux.properties 2>/dev/null || echo 'allow-external-apps = true' >> ~/.termux/termux.properties
""")

    step(3, "Installing Python, Ollama and Jarvis's packages inside Termux (downloads ~600 MB once; the first time,\n"
            "      pydantic-core is compiled on the phone, which takes a while). Progress: ~/jarvis-setup.log in Termux")
    print(termux(f"""set -eo pipefail
LOG={HOME}/jarvis-setup.log
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confnew upgrade 2>&1 | tee $LOG
apt-get -y -q -o Dpkg::Options::=--force-confnew install python python-pip ollama python-cryptography \\
  curl procps termux-tools nodejs-lts php 2>&1 | tee -a $LOG   # node + php: coding practice in JS/TS/PHP
if ! python -c "import pydantic_core" 2>/dev/null; then
  # Termux has no ready-made pydantic-core, so build it here with Termux's own Rust compiler.
  apt-get -y -q -o Dpkg::Options::=--force-confnew install rust 2>&1 | tee -a $LOG
  export ANDROID_API_LEVEL=$(getprop ro.build.version.sdk) CARGO_BUILD_JOBS=$(nproc)
fi
python -m pip install --disable-pip-version-check --progress-bar off fastapi uvicorn httpx pydantic 2>&1 | tee -a $LOG
python -c "import fastapi, uvicorn, httpx, pydantic, cryptography; print('python packages ok')"
ollama --version
""", timeout=7200)[-400:])

    step(4, "Copying Jarvis and the models")
    copy_code()
    if not args.skip_models:
        models_src = Path.home() / ".ollama" / "models"
        for name, tag in MODELS:
            manifest = json.loads((models_src / "manifests" / "registry.ollama.ai" / "library" / name / tag).read_text())
            for layer in [manifest["config"], *manifest["layers"]]:
                blob = layer["digest"].replace(":", "-")
                remote = f"{TMP}/jarvis-models/blobs/{blob}"
                if adb("shell", "ls", remote, check=False).strip() != remote:
                    adb("push", str(models_src / "blobs" / blob), remote, timeout=1800)
            adb("shell", "mkdir", "-p", f"{TMP}/jarvis-models/manifests/registry.ollama.ai/library/{name}")
            adb("push", str(models_src / "manifests" / "registry.ollama.ai" / "library" / name / tag),
                f"{TMP}/jarvis-models/manifests/registry.ollama.ai/library/{name}/{tag}")
        adb("shell", "chmod", "-R", "a+rX", f"{TMP}/jarvis-models")
        termux(f"""set -e
mkdir -p ~/.ollama/models
cp -r {TMP}/jarvis-models/blobs {TMP}/jarvis-models/manifests ~/.ollama/models/
""", timeout=3600)
        adb("shell", "rm", "-rf", f"{TMP}/jarvis-models")
    print("  Code and models copied.")

    step(5, "Writing the scripts the Jarvis app uses")
    termux(f"""set -e
mkdir -p {POCKET}
cat > {POCKET}/start <<'EOF'
#!{PREFIX}/bin/bash
# Starts Ollama and Jarvis on this phone. The Jarvis app runs this; it's safe to run when already running.
cd {POCKET}/app
if curl -s -m 2 http://127.0.0.1:8766/m/manifest.webmanifest >/dev/null; then exit 0; fi
termux-wake-lock
if ! curl -s -m 2 http://127.0.0.1:11434/api/version >/dev/null; then
  OLLAMA_HOST=127.0.0.1:11434 nohup ollama serve >{POCKET}/ollama.log 2>&1 &
fi
exec python -m jarvis --pocket --port 8766 >>{POCKET}/jarvis.log 2>&1
EOF
cat > {POCKET}/pair <<'EOF'
#!{PREFIX}/bin/bash
# Prints a key for the Jarvis app on this phone (asked for by the app through Termux).
cd {POCKET}/app && exec python -m jarvis --issue-device-token "Jarvis app on this phone"
EOF
chmod 700 {POCKET}/start {POCKET}/pair
cd {POCKET}/app && python -c "
from jarvis.config import ConfigStore
from jarvis.paths import resolve_data_dir
ConfigStore(resolve_data_dir()).update({{'model': 'qwen3:1.7b', 'think': False, 'vision_model': 'qwen3-vl:2b',
    'semantic_search': False, 'context_window': 4096, 'phone_access': False}})
print('settings ok')"
""")

    step(6, "Pairing the phone's Jarvis with this computer's Jarvis for syncing")
    already = termux(f"""cd {POCKET}/app && python -c "
from jarvis.config import ConfigStore
from jarvis.paths import resolve_data_dir
s = ConfigStore(resolve_data_dir()).get()
print('PAIRED ' + s.sync_url if s.sync_url and s.sync_token else 'NOT PAIRED')"
""", check=False).strip().splitlines()[-1:]
    if already and already[0].startswith("PAIRED") and not args.repair:
        print(f"  Already paired ({already[0][7:]}). Use --repair to pair again.")
    else:
        pair_with_laptop(args)

    step(7, "Letting Ollama keep running (Android's phantom process limit)")
    if args.allow_background:
        adb("shell", "settings", "put", "global", "settings_enable_monitor_phantom_procs", "false")
        print("  Done. (Undo with: adb shell settings put global settings_enable_monitor_phantom_procs true)")
    else:
        print("  Skipped: this changes a system setting. Run again with --allow-background if Android stops Jarvis\n"
              "  on the phone while it's working (Termux shows \"[Process completed (signal 9)]\").")

    print("""
All set. On the phone, please also:
  * Settings > Apps > Termux > Battery saver > No restrictions (so Android doesn't stop it)
  * Open the Jarvis app: when the laptop isn't reachable it starts Jarvis on the phone by itself
    (the first time, allow it to "run commands in Termux").""")


def pair_with_laptop(args) -> None:
    page = urllib.request.urlopen(args.laptop + "/", timeout=5).read().decode()
    token = re.search(r'jarvis-token" content="([^"]+)', page).group(1)

    def laptop(path: str, method: str = "GET"):
        req = urllib.request.Request(args.laptop + path, method=method, headers={"X-Jarvis-Token": token})
        return json.loads(urllib.request.urlopen(req, timeout=10).read())

    phone_info = laptop("/api/phone")
    if not phone_info.get("running"):
        raise SystemExit("Turn on phone access on this computer first (Settings -> Phone access).")
    sync_url = phone_info["urls"][0].removesuffix("/m/")
    code = laptop("/api/phone/pairing-code", "POST")["code"]
    ca = Path(os.environ.get("APPDATA", "")) / "Jarvis" / "phone" / "jarvis-ca.crt"
    adb("push", str(ca), f"{TMP}/jarvis-laptop-ca.pem")
    adb("shell", "chmod", "644", f"{TMP}/jarvis-laptop-ca.pem")
    print("  " + termux(f"""cp {TMP}/jarvis-laptop-ca.pem {POCKET}/laptop-ca.pem
cd {POCKET}/app && python -m jarvis --sync-with {sync_url} --sync-code {code} --sync-ca {POCKET}/laptop-ca.pem
""").strip().splitlines()[-1])
    adb("shell", "rm", "-f", f"{TMP}/jarvis-laptop-ca.pem", f"{TMP}/jarvis-step.sh")


if __name__ == "__main__":
    main()
