"""Parse HU dump logs and produce a human-readable verdict."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CAMERA_ID_LINE_RE = re.compile(
    r"(?:Camera\s*ID|cameraId)\s*[:=]\s*['\"]?([0-9A-Za-z_\-:]+)['\"]?",
    re.IGNORECASE,
)
CAMERA_DEVICE_RE = re.compile(
    r"CameraDevice\s*(?:info\s*)?(?:for\s+id\s+)?['\"]?([0-9A-Za-z_\-:]+)['\"]?",
    re.IGNORECASE,
)
CAMERA_COUNT_RE = re.compile(r"Number of camera devices:\s*(\d+)", re.IGNORECASE)
CLIENT_RE = re.compile(
    r"(?:Client|package|pkg|callingUid|mClientName)\s*[:=]\s*([A-Za-z0-9._]+)",
    re.IGNORECASE,
)
PACKAGE_LINE_RE = re.compile(r"^package:(?:(.+)=)?([A-Za-z0-9._]+)\s*$")
EXCLUSIVE_HINTS = (
    "already in use",
    "camera in use",
    "device is in use",
    "error_camera_in_use",
    "camera_disconnected",
    "camera_in_use",
)
PROP_KEYS = (
    "ro.build.version.release",
    "ro.build.version.sdk",
    "ro.product.model",
    "ro.product.device",
    "ro.product.manufacturer",
    "ro.build.fingerprint",
    "ro.hardware",
    "ro.board.platform",
    "ro.build.display.id",
    "persist.sys.usb.config",
    "sys.usb.config",
    "ro.bootmode",
)


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (not lines[i] or lines[i].startswith("# ")):
        i += 1
    return "\n".join(lines[i:]).strip()


def _parse_getprop(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"\[([^\]]+)\]:\s*\[(.*)\]\s*$", line)
        if m:
            props[m.group(1)] = m.group(2)
    return props


def _camera_ids(text: str) -> list[str]:
    count_match = CAMERA_COUNT_RE.search(text)
    if count_match and int(count_match.group(1)) == 0:
        return []
    found: list[str] = []
    for rx in (CAMERA_ID_LINE_RE, CAMERA_DEVICE_RE):
        for m in rx.finditer(text):
            val = m.group(1)
            if val.lower() in {"id", "for", "info", "device", "devices", "camera"}:
                continue
            if val not in found and 0 < len(val) < 40:
                found.append(val)
    if count_match and not found:
        found = [str(i) for i in range(int(count_match.group(1)))]
    return found


def _clients(text: str) -> list[str]:
    pkgs: list[str] = []
    for m in CLIENT_RE.finditer(text):
        val = m.group(1)
        if "." in val and val not in pkgs and not val.startswith("android.hardware"):
            pkgs.append(val)
    # dumpsys media.camera: "Client: com.foo (PID 123)"
    for m in re.finditer(r"Client:\s*([A-Za-z0-9._]+)", text):
        if m.group(1) not in pkgs:
            pkgs.append(m.group(1))
    return pkgs


def _resumed_activity(text: str) -> str | None:
    m = re.search(r"mResumedActivity:.*? ([A-Za-z0-9._]+)/([A-Za-z0-9._$]+)", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"topResumedActivity=.*? ([A-Za-z0-9._]+)/([A-Za-z0-9._$]+)", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def _packages_of_interest(text: str) -> list[str]:
    keys = re.compile(
        r"camera|avm|around|surround|panoram|360|540|dvr|record|dashcam|"
        r"bird|park|evs|vision|reverse|rearview|chery|jetour|desaysv|"
        r"autochips|ivi",
        re.I,
    )
    out: list[str] = []
    for line in text.splitlines():
        m = re.search(r"package:(?:.+=)?([A-Za-z0-9._]+)\s*$", line)
        if not m:
            continue
        pkg = m.group(1)
        if keys.search(pkg) and pkg not in out:
            out.append(pkg)
    return out


def _usb_volumes(text: str) -> list[str]:
    vols: list[str] = []
    for line in text.splitlines():
        if re.search(r"usb|udisk|otg|public:\d+|vold", line, re.I):
            stripped = line.strip()
            if stripped and stripped not in vols:
                vols.append(stripped[:240])
    return vols[:80]


def analyze_snapshot(folder: Path) -> dict[str, Any]:
    cam = _read(folder / "dumpsys_media_camera.txt")
    act = _read(folder / "dumpsys_activity_activities.txt")
    top = _read(folder / "dumpsys_activity_top.txt")
    logcat = _read(folder / "logcat_camera.txt")
    ids = _camera_ids(cam)
    clients = _clients(cam)
    exclusive = any(h.lower() in (cam + logcat).lower() for h in EXCLUSIVE_HINTS)
    return {
        "stage": folder.name.split("_", 1)[-1] if "_" in folder.name else folder.name,
        "camera_ids": ids,
        "camera_count": len(ids),
        "clients": clients,
        "resumed_activity": _resumed_activity(act) or _resumed_activity(top),
        "exclusive_hints": exclusive,
        "camera_dump_bytes": len(cam.encode("utf-8")),
        "camera_dump_empty": (
            not cam.strip()
            or "Can't find service: media.camera" in cam
            or "Can't find service: media.camera.provider" in cam
        ),
    }


def analyze_session(session_dir: Path) -> dict[str, Any]:
    baseline = session_dir / "01_baseline"
    props = _parse_getprop(_read(baseline / "getprop.txt"))
    identity = {k: props.get(k, "") for k in PROP_KEYS}
    identity["adb_id"] = _read(baseline / "id.txt").strip()
    identity["kernel"] = _read(baseline / "uname.txt").strip()
    identity["selinux"] = _read(baseline / "getenforce.txt").strip()

    pkgs = _packages_of_interest(_read(baseline / "pm_list_packages.txt"))
    usb = _usb_volumes(
        "\n".join(
            [
                _read(baseline / "dumpsys_usb.txt"),
                _read(baseline / "sm_volumes.txt"),
                _read(baseline / "proc_mounts.txt"),
                _read(baseline / "ls_storage.txt"),
                _read(baseline / "df.txt"),
            ]
        )
    )
    video_nodes = [
        line.strip()
        for line in _read(baseline / "ls_dev_video.txt").splitlines()
        if line.strip() and not line.startswith("---")
    ]

    snapshots: list[dict[str, Any]] = []
    for child in sorted(session_dir.iterdir()):
        if child.is_dir() and child.name[:2].isdigit() and child.name != "01_baseline":
            if (child / "dumpsys_media_camera.txt").exists() or child.name.startswith("0"):
                if any(child.iterdir()):
                    snapshots.append(analyze_snapshot(child))

    idle = next((s for s in snapshots if "idle" in s["stage"]), None)
    others = [s for s in snapshots if idle is None or s["stage"] != idle["stage"]]

    camera_count_idle = idle["camera_count"] if idle else 0
    clients_shift = False
    for s in others:
        if idle and s["clients"] != idle["clients"]:
            clients_shift = True
        if s["exclusive_hints"]:
            clients_shift = True

    if not snapshots:
        verdict = "NO_SNAPSHOTS"
        summary = "Снимки камер не найдены. Запустите collect.py и пройдите этапы IDLE/360/реверс/поворотники."
    elif camera_count_idle == 0 and all(s["camera_count"] == 0 for s in snapshots):
        verdict = "NO_CAMERA2"
        summary = (
            "Camera2 не отдаёт камеры (0 cameraId во всех снимках). "
            "Штатный 360, скорее всего, идёт мимо Android Camera API "
            "(отдельный AVM/оверлей). APK-регистратор через Camera2 сделать нельзя "
            "без вмешательства в прошивку/HAL — этот сборщик такое не делает."
        )
    elif clients_shift:
        verdict = "EXCLUSIVE_LOCK"
        summary = (
            "Камеры видны в Camera2, но клиент/блокировка меняется при 360/реверсе/поворотнике. "
            "Системное приложение, вероятно, забирает exclusive lock. "
            "Параллельная запись из стороннего APK будет рваться в манёврах."
        )
    else:
        verdict = "CAMERA2_SHARED_OR_IDLE_ONLY"
        summary = (
            "Камеры видны в Camera2. На снятых этапах явного exclusive-конфликта не видно "
            "(или 360 не открыл Camera2-клиент). Это ещё не разрешение писать регистратор: "
            "нужно отдельно проверить, можно ли открыть те же cameraId из своего APK "
            "одновременно со штатным 360."
        )

    report = {
        "verdict": verdict,
        "summary_ru": summary,
        "identity": identity,
        "packages_of_interest": pkgs,
        "usb_storage_hints": usb,
        "video_device_nodes": video_nodes[:80],
        "snapshots": snapshots,
        "apk_dvr_feasible": verdict == "CAMERA2_SHARED_OR_IDLE_ONLY",
        "hidden_dvr_still_recommended": True,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    idn = report["identity"]
    lines = [
        "# Jetour Dashing HU — отчёт инвентаризации",
        "",
        f"**Вердикт:** `{report['verdict']}`",
        "",
        report["summary_ru"],
        "",
        "## Аппарат",
        "",
        f"- Android: `{idn.get('ro.build.version.release')}` (SDK {idn.get('ro.build.version.sdk')})",
        f"- Model: `{idn.get('ro.product.model')}` / `{idn.get('ro.product.device')}`",
        f"- Platform: `{idn.get('ro.board.platform')}` hardware `{idn.get('ro.hardware')}`",
        f"- Fingerprint: `{idn.get('ro.build.fingerprint')}`",
        f"- ADB: `{idn.get('adb_id')}`",
        f"- SELinux: `{idn.get('selinux')}`",
        f"- Kernel: `{idn.get('kernel')}`",
        "",
        "## Пакеты, связанные с камерами / 360 / DVR",
        "",
    ]
    if report["packages_of_interest"]:
        for pkg in report["packages_of_interest"]:
            lines.append(f"- `{pkg}`")
    else:
        lines.append("_не найдено по имени_")
    lines += ["", "## Снимки Camera2", ""]
    if not report["snapshots"]:
        lines.append("_нет_")
    for s in report["snapshots"]:
        lines += [
            f"### {s['stage']}",
            "",
            f"- cameraId: `{s['camera_ids']}` (count={s['camera_count']})",
            f"- clients: `{s['clients']}`",
            f"- resumed: `{s['resumed_activity']}`",
            f"- exclusive hints: `{s['exclusive_hints']}`",
            f"- dump empty: `{s['camera_dump_empty']}` ({s['camera_dump_bytes']} bytes)",
            "",
        ]
    lines += [
        "## USB / накопители",
        "",
    ]
    if report["usb_storage_hints"]:
        for row in report["usb_storage_hints"][:40]:
            lines.append(f"- `{row}`")
    else:
        lines.append("_явных USB-томов не видно; вставьте флешку в порт регистратора и переснимите baseline_")
    lines += ["", "## /dev video nodes", ""]
    if report["video_device_nodes"]:
        for row in report["video_device_nodes"]:
            lines.append(f"- `{row}`")
    else:
        lines.append("_нет /dev/video* — камеры могут сидеть на отдельном AVM SoC_")
    lines += [
        "",
        "## Что это значит для APK-регистратора",
        "",
        "- `NO_CAMERA2` — штатные камеры недоступны обычному приложению.",
        "- `EXCLUSIVE_LOCK` — 360/поворотник и запись будут драться за один поток.",
        "- `CAMERA2_SHARED_OR_IDLE_ONLY` — можно пробовать тестовый APK на открытие тех же cameraId.",
        "- Скрытый DVR в штатное место у датчика света по-прежнему самый надёжный путь.",
        "",
        "Этот отчёт — инвентаризация. Прошивка не модифицировалась.",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_report(session_dir: Path) -> dict[str, Any]:
    report = analyze_session(session_dir)
    (session_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (session_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    return report
