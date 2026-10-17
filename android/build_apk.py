"""Build (and optionally install) the Jarvis Android app.

    python android/build_apk.py                 # build android/dist/Jarvis-<version>.apk
    python android/build_apk.py --install       # ...and install it on the phone connected by USB
    python android/build_apk.py --address 192.168.1.23:8766

The app is built for *this* computer: it bundles this computer's Jarvis certificate
authority (so the phone trusts only your Jarvis) and its network address as the default.
Run android/setup_toolchain.py once first. No Android Studio or Gradle needed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from jarvis import __version__  # noqa: E402
from jarvis.config import ConfigStore  # noqa: E402
from jarvis.paths import resolve_data_dir  # noqa: E402
from jarvis.phone.certs import ensure_certificates, lan_addresses  # noqa: E402

from setup_toolchain import tools_dir  # noqa: E402

MIN_SDK, TARGET_SDK = "26", "34"


def run(cmd: list[str], **kw) -> None:
    printable = " ".join(str(c) for c in cmd)
    print(f"  $ {printable[:160]}{'...' if len(printable) > 160 else ''}")
    result = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if result.returncode != 0:
        print(result.stdout[-3000:], result.stderr[-3000:], sep="\n")
        raise SystemExit(f"Step failed: {cmd[0]}")


def find_adb() -> str | None:
    found = shutil.which("adb")
    if found:
        return found
    for root in [os.environ.get("LOCALAPPDATA", "")]:
        for candidate in Path(root, "Microsoft", "WinGet", "Packages").glob("Google.PlatformTools*/platform-tools/adb.exe"):
            return str(candidate)
    return None


def signing_key(folder: Path) -> tuple[Path, Path]:
    """A stable signing key, so later builds install as updates of this one."""
    key_path, cert_path = folder / "signing-key.pk8", folder / "signing-cert.pem"
    if key_path.exists() and cert_path.exists():
        return key_path, cert_path
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    folder.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Jarvis app ({socket.gethostname()})")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + dt.timedelta(days=365 * 30)).sign(key, hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, cert_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--address", help="computer address the app opens, host:port (default: this PC's Wi-Fi address)")
    parser.add_argument("--data-dir", help="Jarvis data folder (default: the normal one)")
    parser.add_argument("--debuggable", action="store_true", help="allow inspecting the app over USB (for testing)")
    parser.add_argument("--install", action="store_true", help="install on the phone connected by USB (adb)")
    args = parser.parse_args()

    tools = tools_dir()
    jdk, bt, platform = tools / "jdk", tools / "build-tools", tools / "platform"
    for need in (jdk / "ok", bt / "ok", platform / "ok"):
        if not need.exists():
            raise SystemExit("Android build tools are missing. Run:  python android/setup_toolchain.py")
    exe = ".exe" if os.name == "nt" else ""
    java, javac = jdk / "bin" / f"java{exe}", jdk / "bin" / f"javac{exe}"
    android_jar = platform / "android.jar"

    data_dir = resolve_data_dir(args.data_dir)
    settings = ConfigStore(data_dir).get()
    ips = lan_addresses()
    cert = ensure_certificates(data_dir / "phone", socket.gethostname(), ips)  # same CA the server uses
    address = args.address or f"{(ips or ['127.0.0.1'])[0]}:{settings.phone_port}"

    build, dist = HERE / "build", HERE / "dist"
    shutil.rmtree(build, ignore_errors=True)
    (build / "gen").mkdir(parents=True)
    (build / "classes").mkdir()
    (build / "dex").mkdir()
    dist.mkdir(exist_ok=True)

    print(f"Building Jarvis {__version__} for {address}")
    res = build / "res"
    shutil.copytree(HERE / "app" / "res", res)
    (res / "raw").mkdir(exist_ok=True)
    shutil.copyfile(cert.ca_certfile, res / "raw" / "jarvis_ca.pem")
    (res / "values" / "config.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        f'    <string name="default_address" translatable="false">{address}</string>\n</resources>\n',
        encoding="utf-8")

    major, minor, patch = (int(x) for x in __version__.split(".")[:3])
    version_code = major * 10000 + minor * 100 + patch
    run([bt / f"aapt2{exe}", "compile", "--dir", res, "-o", build / "res.zip"])
    link = [bt / f"aapt2{exe}", "link", "-o", build / "unsigned.apk", "-I", android_jar,
            "--manifest", HERE / "app" / "AndroidManifest.xml", "-A", HERE / "app" / "assets",
            "--java", build / "gen", "--min-sdk-version", MIN_SDK, "--target-sdk-version", TARGET_SDK,
            "--version-code", str(version_code), "--version-name", __version__, build / "res.zip"]
    if args.debuggable:
        link.insert(2, "--debug-mode")
    run(link)

    sources = [str(p) for p in (HERE / "app" / "src").rglob("*.java")] + [str(p) for p in (build / "gen").rglob("*.java")]
    run([javac, "-source", "8", "-target", "8", "-bootclasspath", android_jar, "-encoding", "UTF-8",
         "-Xlint:-options", "-d", build / "classes", *sources])
    classes = [str(p) for p in (build / "classes").rglob("*.class")]
    run([java, "-cp", bt / "lib" / "d8.jar", "com.android.tools.r8.D8", "--release", "--min-api", MIN_SDK,
         "--lib", android_jar, "--output", build / "dex", *classes])

    with zipfile.ZipFile(build / "unsigned.apk", "a", zipfile.ZIP_DEFLATED) as apk:
        apk.write(build / "dex" / "classes.dex", "classes.dex")
    run([bt / f"zipalign{exe}", "-p", "-f", "4", build / "unsigned.apk", build / "aligned.apk"])

    key, signing_cert = signing_key(data_dir / "android")
    out = dist / f"Jarvis-{__version__}{'-debug' if args.debuggable else ''}.apk"
    run([java, "-jar", bt / "lib" / "apksigner.jar", "sign", "--key", key, "--cert", signing_cert,
         "--out", out, build / "aligned.apk"])
    run([java, "-jar", bt / "lib" / "apksigner.jar", "verify", out])
    print(f"\nBuilt {out} ({out.stat().st_size // 1024} KB)")
    print(f"Trusts only the Jarvis certificate authority with fingerprint {cert.ca_fingerprint}")

    if args.install:
        adb = find_adb()
        if not adb:
            raise SystemExit("adb not found. Install Android platform-tools, or copy the APK to the phone and tap it.")
        print("Installing on the connected phone (accept any prompt on the phone)...")
        run([adb, "install", "-r", out])
        run([adb, "shell", "am", "start", "-n", "local.jarvis.assistant/.MainActivity"])
        print("Installed and opened Jarvis on the phone.")


if __name__ == "__main__":
    main()
