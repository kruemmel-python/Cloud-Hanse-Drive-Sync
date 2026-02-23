#!/usr/bin/env python3
"""
ATHERIA DEMO: Program Forge

Creates a new runnable offspring program from profile templates and emits:
- Python source (`<name>.py`)
- Zipapp executable (`<name>.pyz`)
- launchers (`run_<name>.bat`, `run_<name>.sh`)
- optional native exe via PyInstaller (if available)
- integrity bundle with SHA-256 hashes and HMAC signatures
- optional harness validation report
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import zipapp
from dataclasses import asdict, dataclass
from pathlib import Path
from string import Template
from typing import Any, Dict, Optional, Tuple


PROFILE_CHOICES = ("survival", "diagnostic", "stress-test")


PROFILE_SPECS: Dict[str, Dict[str, float]] = {
    "survival": {
        "resilience_gain": 0.94,
        "jitter": 0.012,
        "target": 0.65,
    },
    "diagnostic": {
        "diag_level": 0.91,
        "jitter": 0.02,
        "target": 0.62,
    },
    "stress-test": {
        "stress_level": 0.93,
        "jitter": 0.045,
        "target": 0.7,
    },
}


@dataclass
class ArtifactMetadata:
    path: str
    relative_path: str
    size_bytes: int
    sha256: str
    signature_hmac_sha256: Optional[str]
    signature_file: Optional[str]


@dataclass
class HarnessResult:
    enabled: bool
    passed: bool
    checks: Dict[str, bool]
    details: Dict[str, Any]


@dataclass
class ForgeResult:
    name: str
    profile: str
    output_dir: str
    script_path: str
    pyz_path: str
    launcher_bat: str
    launcher_sh: str
    exe_path: Optional[str]
    hash_algorithm: str
    signature_algorithm: Optional[str]
    signing_key_path: Optional[str]
    signing_key_fingerprint: Optional[str]
    integrity_path: str
    artifacts: Dict[str, ArtifactMetadata]
    harness: Optional[HarnessResult]
    note: str
    created_at: float


def _sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "atheria_offspring"


def _make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _profile_spec(profile: str) -> Dict[str, float]:
    if profile not in PROFILE_SPECS:
        raise ValueError(f"Unknown profile: {profile}")
    return dict(PROFILE_SPECS[profile])


def _render_program(name: str, profile: str, message: str, default_interval: float, default_iterations: int) -> str:
    spec = _profile_spec(profile)
    template = Template(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import argparse
            import hashlib
            import json
            import math
            import os
            import platform
            import random
            import sys
            import time
            from pathlib import Path

            APP_NAME = $APP_NAME
            PROFILE = $PROFILE
            PROFILE_SPEC = $PROFILE_SPEC
            DEFAULT_MESSAGE = $MESSAGE
            DEFAULT_INTERVAL = $INTERVAL
            DEFAULT_ITERATIONS = $ITERATIONS

            def _bounded(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
                if isinstance(value, float) and math.isnan(value):
                    return lo
                return max(lo, min(hi, float(value)))

            def _load_json(path: Path, default):
                if not path.exists():
                    return default
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    return default

            def _append_jsonl(path: Path, payload: dict) -> None:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\\n")

            def _stress_burst(stress_level: float) -> dict:
                loops = int(2500 + 24000 * max(0.0, min(1.0, stress_level)))
                seed = b"ATHERIA_STRESS_BURST"
                checksum = 0
                started = time.perf_counter()
                for idx in range(loops):
                    seed = hashlib.sha256(seed + idx.to_bytes(4, "little", signed=False)).digest()
                    checksum ^= seed[0]
                elapsed = max(1e-9, time.perf_counter() - started)
                return {
                    "ops": loops,
                    "ops_per_sec": round(loops / elapsed, 2),
                    "checksum": checksum,
                    "elapsed": round(elapsed, 6),
                }

            def _next_pulse(pulse: float) -> float:
                jitter = float(PROFILE_SPEC.get("jitter", 0.02))
                target = float(PROFILE_SPEC.get("target", 0.65))
                drift = random.uniform(-jitter, jitter)
                if PROFILE == "survival":
                    resilience = float(PROFILE_SPEC.get("resilience_gain", 0.9))
                    pulse = pulse * (0.95 + 0.02 * resilience) + (target - pulse) * 0.05 + drift
                elif PROFILE == "diagnostic":
                    pulse = pulse * 0.94 + 0.06 + drift
                else:
                    pulse = pulse * 0.90 + 0.09 + drift
                return _bounded(pulse)

            def run(iterations: int, interval: float, out_dir: Path) -> int:
                out_dir.mkdir(parents=True, exist_ok=True)
                state_path = out_dir / f"{APP_NAME}_state.json"
                checkpoint_path = out_dir / f"{APP_NAME}_checkpoint.json"
                diagnostic_path = out_dir / f"{APP_NAME}_diagnostic.jsonl"
                stress_path = out_dir / f"{APP_NAME}_stress_metrics.jsonl"

                runtime = _load_json(checkpoint_path, {"pulse": 0.61, "health": 1.0, "recoveries": 0})
                pulse = _bounded(float(runtime.get("pulse", 0.61)))
                health = _bounded(float(runtime.get("health", 1.0)))
                recoveries = int(runtime.get("recoveries", 0))

                for step in range(max(1, iterations)):
                    pulse = _next_pulse(pulse)
                    metrics = {}

                    if PROFILE == "survival":
                        if pulse < 0.08 or pulse > 0.98:
                            recoveries += 1
                            fallback = _load_json(checkpoint_path, {"pulse": 0.61}).get("pulse", 0.61)
                            pulse = _bounded(float(fallback) * 0.9 + 0.05)
                        target = float(PROFILE_SPEC.get("target", 0.65))
                        health = _bounded(0.985 * health + 0.015 * (1.0 - abs(pulse - target)))
                        metrics = {
                            "health": round(health, 6),
                            "recoveries": recoveries,
                            "resilience_gain": float(PROFILE_SPEC.get("resilience_gain", 0.9)),
                        }
                    elif PROFILE == "diagnostic":
                        started = time.perf_counter()
                        probe_payload = {
                            "step": step + 1,
                            "cwd": str(Path.cwd()),
                            "pid": os.getpid(),
                            "python": sys.version.split()[0],
                            "platform": platform.platform(),
                            "pulse": round(pulse, 6),
                            "timestamp": time.time(),
                        }
                        _append_jsonl(diagnostic_path, probe_payload)
                        write_latency = max(0.0, time.perf_counter() - started)
                        metrics = {
                            "diag_level": float(PROFILE_SPEC.get("diag_level", 0.9)),
                            "diag_log": diagnostic_path.name,
                            "write_latency_ms": round(write_latency * 1000.0, 4),
                        }
                    else:
                        burst = _stress_burst(float(PROFILE_SPEC.get("stress_level", 0.9)))
                        burst["step"] = step + 1
                        burst["timestamp"] = time.time()
                        _append_jsonl(stress_path, burst)
                        metrics = {
                            "stress_level": float(PROFILE_SPEC.get("stress_level", 0.9)),
                            "ops": burst["ops"],
                            "ops_per_sec": burst["ops_per_sec"],
                            "checksum": burst["checksum"],
                        }

                    payload = {
                        "app": APP_NAME,
                        "profile": PROFILE,
                        "step": step + 1,
                        "pulse": round(pulse, 6),
                        "message": DEFAULT_MESSAGE,
                        "metrics": metrics,
                        "timestamp": time.time(),
                    }
                    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    checkpoint_path.write_text(
                        json.dumps(
                            {"pulse": pulse, "health": health, "recoveries": recoveries, "step": step + 1},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    print(
                        "[{}] profile={} step={} pulse={} | {}".format(
                            APP_NAME,
                            PROFILE,
                            payload["step"],
                            payload["pulse"],
                            DEFAULT_MESSAGE,
                        )
                    )
                    time.sleep(max(0.0, interval))
                return 0

            def main() -> int:
                parser = argparse.ArgumentParser(
                    prog=APP_NAME,
                    description="Generated offspring executable from ATHERIA DEMO forge.",
                )
                parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
                parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
                parser.add_argument("--out-dir", default=".")
                args = parser.parse_args()
                return run(
                    iterations=max(1, int(args.iterations)),
                    interval=max(0.0, float(args.interval)),
                    out_dir=Path(args.out_dir),
                )

            if __name__ == "__main__":
                raise SystemExit(main())
            """
        )
    )
    return template.substitute(
        APP_NAME=json.dumps(name),
        PROFILE=json.dumps(profile),
        PROFILE_SPEC=repr(spec),
        MESSAGE=json.dumps(message),
        INTERVAL=repr(float(default_interval)),
        ITERATIONS=repr(int(default_iterations)),
    )


def _build_pyz(pyz_path: Path, program_content: str, interpreter: Optional[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="atheria_demo_forge_") as td:
        app_dir = Path(td) / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        _write_text(app_dir / "__main__.py", program_content)
        zipapp.create_archive(
            source=app_dir,
            target=pyz_path,
            interpreter=interpreter,
            compressed=True,
        )


def _build_optional_exe(script_path: Path, output_dir: Path, name: str) -> Optional[Path]:
    pyinstaller = shutil.which("pyinstaller")
    if not pyinstaller:
        return None

    dist_path = output_dir / "dist"
    build_path = output_dir / "build"
    spec_path = output_dir / "spec"
    dist_path.mkdir(parents=True, exist_ok=True)
    build_path.mkdir(parents=True, exist_ok=True)
    spec_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        pyinstaller,
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        name,
        "--distpath",
        str(dist_path),
        "--workpath",
        str(build_path),
        "--specpath",
        str(spec_path),
        str(script_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        print("WARN: PyInstaller build failed.")
        if completed.stdout.strip():
            print(completed.stdout)
        if completed.stderr.strip():
            print(completed.stderr, file=sys.stderr)
        return None

    exe_name = f"{name}.exe" if os.name == "nt" else name
    exe_path = dist_path / exe_name
    return exe_path if exe_path.exists() else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 64)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _hmac_file(path: Path, key: bytes) -> str:
    signer = hmac.new(key, digestmod=hashlib.sha256)
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 64)
            if not chunk:
                break
            signer.update(chunk)
    return signer.hexdigest()


def _key_fingerprint(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()


def _parse_key_material(raw: str) -> bytes:
    token = raw.strip()
    if not token:
        raise ValueError("Signing key material is empty.")
    if token.startswith("base64:"):
        return base64.b64decode(token.split(":", 1)[1].encode("utf-8"), validate=True)
    if re.fullmatch(r"[0-9a-fA-F]{32,}", token) and len(token) % 2 == 0:
        return bytes.fromhex(token)
    return token.encode("utf-8")


def _resolve_signing_key(
    *,
    output_dir: Path,
    signing_key_path: Optional[Path],
    signing_key_env: Optional[str],
    auto_generate: bool,
) -> Tuple[bytes, Path]:
    if signing_key_path is not None and signing_key_path.exists():
        key = _parse_key_material(signing_key_path.read_text(encoding="utf-8"))
        return key, signing_key_path

    if signing_key_env:
        env_value = os.getenv(signing_key_env, "").strip()
        if env_value:
            key = _parse_key_material(env_value)
            env_path = output_dir / "signing_key_from_env.txt"
            _write_text(env_path, f"env:{signing_key_env}")
            return key, env_path

    if signing_key_path is not None and not signing_key_path.exists() and not auto_generate:
        raise FileNotFoundError(f"Signing key file not found: {signing_key_path}")

    if not auto_generate:
        raise RuntimeError("Signing is enabled but no signing key source was provided.")

    key = os.urandom(32)
    generated_path = signing_key_path or (output_dir / "forge_signing.key")
    _write_text(generated_path, key.hex())
    return key, generated_path


def _collect_artifacts(
    *,
    output_dir: Path,
    artifact_paths: Dict[str, Path],
    signing_key: Optional[bytes],
) -> Tuple[Dict[str, ArtifactMetadata], Path]:
    records: Dict[str, ArtifactMetadata] = {}
    for name, path in artifact_paths.items():
        sha = _sha256_file(path)
        sig = None
        sig_file = None
        if signing_key is not None:
            sig = _hmac_file(path, signing_key)
            sig_path = path.with_suffix(path.suffix + ".sig")
            _write_text(sig_path, sig)
            sig_file = str(sig_path)
        try:
            rel = str(path.relative_to(output_dir))
        except ValueError:
            rel = path.name
        records[name] = ArtifactMetadata(
            path=str(path),
            relative_path=rel,
            size_bytes=int(path.stat().st_size),
            sha256=sha,
            signature_hmac_sha256=sig,
            signature_file=sig_file,
        )

    integrity_path = output_dir / "artifact_integrity.json"
    integrity_payload = {
        "hash_algorithm": "sha256",
        "signature_algorithm": "hmac-sha256" if signing_key is not None else None,
        "created_at": time.time(),
        "artifacts": {key: asdict(value) for key, value in records.items()},
    }
    integrity_path.write_text(json.dumps(integrity_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return records, integrity_path


def _verify_artifacts(records: Dict[str, ArtifactMetadata], signing_key: Optional[bytes]) -> bool:
    for meta in records.values():
        path = Path(meta.path)
        if not path.exists():
            return False
        if _sha256_file(path) != meta.sha256:
            return False
        if signing_key is not None and meta.signature_hmac_sha256 is not None:
            if _hmac_file(path, signing_key) != meta.signature_hmac_sha256:
                return False
    return True


def _run_subprocess(command: list[str], *, timeout_seconds: float, cwd: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=max(1.0, timeout_seconds),
        cwd=str(cwd),
    )
    elapsed = max(0.0, time.perf_counter() - started)
    return {
        "command": command,
        "returncode": int(proc.returncode),
        "duration_seconds": round(elapsed, 6),
        "stdout_tail": proc.stdout.splitlines()[-8:],
        "stderr_tail": proc.stderr.splitlines()[-8:],
    }


def validate_generated_offspring(
    result: ForgeResult,
    *,
    iterations: int = 3,
    interval: float = 0.01,
    timeout_seconds: float = 25.0,
    run_launchers: bool = False,
    signing_key: Optional[bytes] = None,
) -> HarnessResult:
    output_dir = Path(result.output_dir)
    script = Path(result.script_path)
    pyz = Path(result.pyz_path)
    state_path = output_dir / f"{result.name}_state.json"
    checks: Dict[str, bool] = {}
    details: Dict[str, Any] = {}

    if state_path.exists():
        state_path.unlink()

    py_run = _run_subprocess(
        [
            sys.executable,
            str(script),
            "--iterations",
            str(max(1, int(iterations))),
            "--interval",
            str(max(0.0, float(interval))),
            "--out-dir",
            str(output_dir),
        ],
        timeout_seconds=timeout_seconds,
        cwd=output_dir,
    )
    checks["python_run_ok"] = py_run["returncode"] == 0
    details["python_run"] = py_run

    pyz_run = _run_subprocess(
        [
            sys.executable,
            str(pyz),
            "--iterations",
            str(max(1, int(iterations))),
            "--interval",
            str(max(0.0, float(interval))),
            "--out-dir",
            str(output_dir),
        ],
        timeout_seconds=timeout_seconds,
        cwd=output_dir,
    )
    checks["pyz_run_ok"] = pyz_run["returncode"] == 0
    details["pyz_run"] = pyz_run

    state_ok = False
    state_payload: Dict[str, Any] = {}
    if state_path.exists():
        try:
            state_payload = json.loads(state_path.read_text(encoding="utf-8"))
            pulse = float(state_payload.get("pulse", -1.0))
            state_ok = (
                state_payload.get("app") == result.name
                and state_payload.get("profile") == result.profile
                and 0.0 <= pulse <= 1.0
                and int(state_payload.get("step", 0)) >= 1
            )
        except Exception:
            state_ok = False
    checks["state_file_ok"] = state_ok
    details["state_payload"] = state_payload

    checks["integrity_ok"] = _verify_artifacts(result.artifacts, signing_key=signing_key)
    details["integrity_checked_artifacts"] = len(result.artifacts)

    if run_launchers:
        if os.name == "nt":
            bat_path = Path(result.launcher_bat)
            launcher = _run_subprocess(
                [
                    "cmd",
                    "/c",
                    str(bat_path),
                    "--iterations",
                    "1",
                    "--interval",
                    "0.0",
                    "--out-dir",
                    str(output_dir),
                ],
                timeout_seconds=timeout_seconds,
                cwd=output_dir,
            )
            checks["launcher_ok"] = launcher["returncode"] == 0
            details["launcher_run"] = launcher
        else:
            sh_path = Path(result.launcher_sh)
            launcher = _run_subprocess(
                [
                    "sh",
                    str(sh_path),
                    "--iterations",
                    "1",
                    "--interval",
                    "0.0",
                    "--out-dir",
                    str(output_dir),
                ],
                timeout_seconds=timeout_seconds,
                cwd=output_dir,
            )
            checks["launcher_ok"] = launcher["returncode"] == 0
            details["launcher_run"] = launcher
    else:
        checks["launcher_ok"] = True
        details["launcher_run"] = {"skipped": True}

    passed = all(checks.values())
    return HarnessResult(enabled=True, passed=passed, checks=checks, details=details)


def forge(
    *,
    name: str,
    output_dir: Path,
    profile: str = "survival",
    message: str = "Autonomous pulse active.",
    interval: float = 0.35,
    iterations: int = 12,
    build_exe: bool = False,
    sign_artifacts: bool = True,
    signing_key_path: Optional[Path] = None,
    signing_key_env: Optional[str] = "ATHERIA_DEMO_SIGNING_KEY",
    auto_generate_signing_key: bool = True,
    run_harness: bool = False,
    harness_iterations: int = 3,
    harness_interval: float = 0.01,
    harness_timeout_seconds: float = 25.0,
    harness_run_launchers: bool = False,
    strict_harness: bool = False,
) -> ForgeResult:
    safe_name = _sanitize_name(name)
    normalized_profile = profile.strip().lower()
    if normalized_profile not in PROFILE_CHOICES:
        raise ValueError(f"Unsupported profile '{profile}'. Allowed: {PROFILE_CHOICES}")

    out = output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    key_bytes: Optional[bytes] = None
    key_path: Optional[Path] = None
    if sign_artifacts:
        key_bytes, key_path = _resolve_signing_key(
            output_dir=out,
            signing_key_path=signing_key_path,
            signing_key_env=signing_key_env,
            auto_generate=auto_generate_signing_key,
        )

    script_path = out / f"{safe_name}.py"
    pyz_path = out / f"{safe_name}.pyz"
    bat_path = out / f"run_{safe_name}.bat"
    sh_path = out / f"run_{safe_name}.sh"

    program = _render_program(
        name=safe_name,
        profile=normalized_profile,
        message=message,
        default_interval=max(0.0, float(interval)),
        default_iterations=max(1, int(iterations)),
    )

    _write_text(script_path, program)
    _make_executable(script_path)

    interpreter = None if os.name == "nt" else "/usr/bin/env python3"
    _build_pyz(pyz_path, program, interpreter=interpreter)
    _make_executable(pyz_path)

    _write_text(
        bat_path,
        f"@echo off\r\npython \"{script_path.name}\" %*\r\n",
    )
    _write_text(
        sh_path,
        f"#!/usr/bin/env sh\npython3 \"$(dirname \"$0\")/{script_path.name}\" \"$@\"\n",
    )
    _make_executable(sh_path)

    exe_path = _build_optional_exe(script_path, out, safe_name) if build_exe else None

    artifact_paths: Dict[str, Path] = {
        "script": script_path,
        "pyz": pyz_path,
        "launcher_bat": bat_path,
        "launcher_sh": sh_path,
    }
    if exe_path is not None:
        artifact_paths["exe"] = exe_path

    artifacts, integrity_path = _collect_artifacts(output_dir=out, artifact_paths=artifact_paths, signing_key=key_bytes)
    harness: Optional[HarnessResult] = None

    result = ForgeResult(
        name=safe_name,
        profile=normalized_profile,
        output_dir=str(out),
        script_path=str(script_path),
        pyz_path=str(pyz_path),
        launcher_bat=str(bat_path),
        launcher_sh=str(sh_path),
        exe_path=str(exe_path) if exe_path else None,
        hash_algorithm="sha256",
        signature_algorithm="hmac-sha256" if key_bytes is not None else None,
        signing_key_path=str(key_path) if key_path is not None else None,
        signing_key_fingerprint=_key_fingerprint(key_bytes) if key_bytes is not None else None,
        integrity_path=str(integrity_path),
        artifacts=artifacts,
        harness=None,
        note="Executable offspring generated.",
        created_at=time.time(),
    )

    if run_harness:
        harness = validate_generated_offspring(
            result,
            iterations=max(1, int(harness_iterations)),
            interval=max(0.0, float(harness_interval)),
            timeout_seconds=max(2.0, float(harness_timeout_seconds)),
            run_launchers=bool(harness_run_launchers),
            signing_key=key_bytes,
        )
        result.harness = harness
        if strict_harness and not harness.passed:
            raise RuntimeError("Harness validation failed for generated offspring.")

    if exe_path is None and build_exe:
        result.note = "Executable offspring generated; native binary missing (PyInstaller unavailable or build failed)."
    elif harness is not None:
        result.note = "Executable offspring generated and harness executed."

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge_executable.py",
        description="Create a new executable offspring program in DEMO.",
    )
    parser.add_argument("--name", default="aion_offspring")
    parser.add_argument("--output-dir", default="DEMO/generated")
    parser.add_argument("--profile", default="survival", choices=list(PROFILE_CHOICES))
    parser.add_argument(
        "--message",
        default="Autonomous pulse active.",
        help="Status text embedded in the generated offspring.",
    )
    parser.add_argument("--interval", type=float, default=0.35)
    parser.add_argument("--iterations", type=int, default=12)
    parser.add_argument("--build-exe", action="store_true")

    parser.add_argument("--disable-signing", action="store_true")
    parser.add_argument("--signing-key", default=None, help="Path to signing key file (hex, base64:..., or text).")
    parser.add_argument("--signing-key-env", default="ATHERIA_DEMO_SIGNING_KEY")
    parser.add_argument("--no-auto-generate-signing-key", action="store_true")

    parser.add_argument("--run-harness", action="store_true")
    parser.add_argument("--harness-iterations", type=int, default=3)
    parser.add_argument("--harness-interval", type=float, default=0.01)
    parser.add_argument("--harness-timeout", type=float, default=25.0)
    parser.add_argument("--harness-run-launchers", action="store_true")
    parser.add_argument("--strict-harness", action="store_true")

    parser.add_argument(
        "--manifest",
        default="DEMO/generated/forge_manifest.json",
        help="Path to write forge result JSON.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = forge(
            name=args.name,
            output_dir=Path(args.output_dir),
            profile=args.profile,
            message=args.message,
            interval=max(0.0, float(args.interval)),
            iterations=max(1, int(args.iterations)),
            build_exe=bool(args.build_exe),
            sign_artifacts=not bool(args.disable_signing),
            signing_key_path=Path(args.signing_key) if args.signing_key else None,
            signing_key_env=args.signing_key_env,
            auto_generate_signing_key=not bool(args.no_auto_generate_signing_key),
            run_harness=bool(args.run_harness),
            harness_iterations=max(1, int(args.harness_iterations)),
            harness_interval=max(0.0, float(args.harness_interval)),
            harness_timeout_seconds=max(2.0, float(args.harness_timeout)),
            harness_run_launchers=bool(args.harness_run_launchers),
            strict_harness=bool(args.strict_harness),
        )
    except Exception as exc:
        print(f"ERROR: forge failed: {exc}", file=sys.stderr)
        return 1

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

