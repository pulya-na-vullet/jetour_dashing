#!/usr/bin/env python3
"""Collect a read-only diagnostic inventory from a Jetour Dashing head unit.

You enable ADB on the HU yourself (engineering code + USB Device).
This script then dumps Camera2/AVM/USB state into a timestamped log folder
and writes report.md for later analysis.

Usage:
  python collect.py                 # interactive, waits for adb
  python collect.py --serial SERIAL
  python collect.py --print-commands
  python collect.py --analyze logs/hu_diag_...
  python collect.py --demo          # fake dumps, checks parser without a car
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hu_diag import __version__
from hu_diag.analyze import write_report
from hu_diag.commands import BASELINE_COMMANDS, SNAPSHOT_COMMANDS, SNAPSHOT_STAGES, DumpCmd
from hu_diag.console import ask, configure_stdio, say
from hu_diag.demo import write_demo_session

DEFAULT_LOGS = ROOT / "logs"
ADB_TIMEOUT_SEC = 90


def _say(msg: str) -> None:
    say(msg)


def find_adb(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise SystemExit(f"adb не найден: {explicit}")
        return str(path)
    which = shutil.which("adb")
    if which:
        return which
    extras = [
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools" / "adb",
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools" / "adb.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
        Path("C:/platform-tools/adb.exe"),
    ]
    for cand in extras:
        if cand and cand.exists():
            return str(cand)
    raise SystemExit(
        "adb не найден в PATH. Поставьте platform-tools и укажите --adb PATH.\n"
        "Сами команды на ГУ (инженерное меню) этот скрипт не вводит - только dumpsys после подключения."
    )


def adb(adb_bin: str, serial: str | None, args: list[str], timeout: int = ADB_TIMEOUT_SEC) -> subprocess.CompletedProcess[str]:
    cmd = [adb_bin]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def wait_for_device(adb_bin: str, serial: str | None) -> str:
    _say("")
    _say("=== Подключение ADB ===")
    _say("Коды инженерного меню вводите сами на ГУ, скрипт их не набирает.")
    _say("  Android 9:  *#20201030#*   или  *#20220730#*")
    _say("  Другой код: *621317658#")
    _say("Dalshe: USB -> Device -> OK. Kabel USB-A - USB-A v port GU (pod podlokotnikom).")
    _say("Kogda adb devices pokazyvaet device, nazhmite Enter.")
    while True:
        ask("Enter kogda ADB gotov (ili srazu esli uzhe podklyuchen)...")
        try:
            proc = adb(adb_bin, None, ["devices"])
        except FileNotFoundError:
            raise SystemExit("Не удалось запустить adb")
        lines = [ln.strip() for ln in proc.stdout.splitlines()[1:] if ln.strip()]
        devices = []
        for ln in lines:
            parts = ln.split()
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))
        ready = [(d, s) for d, s in devices if s == "device"]
        unauthorized = [(d, s) for d, s in devices if s != "device"]
        if unauthorized:
            _say("Устройства не в состоянии device: " + ", ".join(f"{d}={s}" for d, s in unauthorized))
            _say("На ГУ подтвердите AC Bridge / разрешение отладки.")
        if not ready:
            _say("Пока нет ни одного `device`. Проверьте кабель, USB Device, драйвер.")
            continue
        if serial:
            match = [d for d, _ in ready if d == serial]
            if not match:
                _say(f"Серийник {serial} не найден. Есть: {[d for d, _ in ready]}")
                continue
            return serial
        if len(ready) > 1:
            _say("Несколько устройств: " + ", ".join(d for d, _ in ready))
            _say("Перезапустите с --serial ID")
            continue
        chosen = ready[0][0]
        _say(f"Подключено: {chosen}")
        return chosen


def run_shell(adb_bin: str, serial: str, shell_cmd: str) -> tuple[int, str, str]:
    try:
        proc = adb(adb_bin, serial, ["shell", shell_cmd])
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {ADB_TIMEOUT_SEC}s: {shell_cmd}"
    return proc.returncode, proc.stdout, proc.stderr


def save_cmd(out_dir: Path, adb_bin: str, serial: str, spec: DumpCmd, log) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rc, stdout, stderr = run_shell(adb_bin, serial, spec.shell)
    body = []
    body.append(f"# cmd: adb shell {spec.shell}")
    body.append(f"# desc: {spec.description}")
    body.append(f"# rc: {rc}")
    body.append(f"# utc: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    body.append("")
    body.append(stdout)
    if stderr.strip():
        body.append("\n\n----- STDERR -----\n")
        body.append(stderr)
    path = out_dir / spec.filename
    path.write_text("\n".join(body), encoding="utf-8")
    status = "ok" if rc == 0 else f"rc={rc}"
    line = f"  [{status}] {spec.filename} ({len(stdout)} bytes) - {spec.description}"
    _say(line)
    log.write(line + "\n")


def pause(title: str, how: str) -> None:
    _say("")
    _say("=" * 60)
    _say(title)
    _say(how)
    _say("=" * 60)
    ask("Enter kogda ekran v nuzhnom sostoyanii...")


def collect(adb_bin: str, serial: str, session: Path) -> None:
    session.mkdir(parents=True, exist_ok=True)
    log_path = session / "collect.log"
    meta = {
        "tool": "hu_diag",
        "version": __version__,
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "serial": serial,
        "read_only": True,
    }
    (session / "00_session.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with log_path.open("w", encoding="utf-8") as log:
        log.write(json.dumps(meta, ensure_ascii=False) + "\n")
        _say("")
        _say("=== Baseline (один раз) ===")
        base = session / "01_baseline"
        for spec in BASELINE_COMMANDS:
            save_cmd(base, adb_bin, serial, spec, log)

        for idx, (stage, title, how) in enumerate(SNAPSHOT_STAGES, start=2):
            pause(title, how)
            folder = session / f"{idx:02d}_{stage}"
            _say(f"Снимаю {stage}...")
            t0 = time.time()
            for spec in SNAPSHOT_COMMANDS:
                save_cmd(folder, adb_bin, serial, spec, log)
            log.write(f"stage {stage} took {time.time() - t0:.1f}s\n")

    _say("")
    _say("=== Разбор ===")
    report = write_report(session)
    _say(f"Вердикт: {report['verdict']}")
    _say(report["summary_ru"])
    _say("")
    _say(f"Папка лога: {session}")
    _say(f"Отчёт:      {session / 'report.md'}")
    _say(f"JSON:       {session / 'report.json'}")


def print_commands() -> None:
    _say("# Команды, которые вы можете ввести сами после `adb shell`")
    _say("# Инженерное меню на ГУ этот список не заменяет.")
    _say("")
    _say("## Baseline")
    for spec in BASELINE_COMMANDS:
        _say(f"# {spec.description}")
        _say(spec.shell)
        _say("")
    _say("## Каждый снимок (idle / 360 / reverse / turn)")
    for spec in SNAPSHOT_COMMANDS:
        _say(f"# {spec.description}")
        _say(spec.shell)
        _say("")
    _say("Сложите текстовые файлы в logs/<session>/01_baseline/ и 02_idle/ ...")
    _say("Затем: python collect.py --analyze logs/<session>")


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(
        description="Инвентаризация камер/360/USB на ГУ Jetour Dashing (только чтение)."
    )
    parser.add_argument("--adb", help="Путь к adb")
    parser.add_argument("--serial", help="Серийник adb, если устройств несколько")
    parser.add_argument("--out", type=Path, default=DEFAULT_LOGS, help="Каталог логов")
    parser.add_argument("--print-commands", action="store_true", help="Только распечатать команды")
    parser.add_argument("--analyze", type=Path, help="Разобрать уже снятую папку")
    parser.add_argument("--demo", action="store_true", help="Прогон парсера на синтетических дампах")
    parser.add_argument("--skip-wait", action="store_true", help="Не ждать Enter на подключении")
    args = parser.parse_args(argv)

    if args.print_commands:
        print_commands()
        return 0

    if args.analyze:
        report = write_report(args.analyze)
        _say(render_short(report, args.analyze))
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    session = args.out / f"hu_diag_{stamp}"

    if args.demo:
        write_demo_session(session)
        report = write_report(session)
        _say(f"Demo session: {session}")
        _say(render_short(report, session))
        return 0

    adb_bin = find_adb(args.adb)
    _say(f"adb: {adb_bin}")
    serial = args.serial
    if args.skip_wait:
        proc = adb(adb_bin, None, ["devices"])
        ready = []
        for ln in proc.stdout.splitlines()[1:]:
            parts = ln.split()
            if len(parts) >= 2 and parts[1] == "device":
                ready.append(parts[0])
        if not ready:
            raise SystemExit("Нет adb device. Уберите --skip-wait и подключите ГУ.")
        serial = serial or ready[0]
    else:
        serial = wait_for_device(adb_bin, serial)
    collect(adb_bin, serial, session)
    return 0


def render_short(report: dict, session: Path) -> str:
    return (
        f"Вердикт: {report['verdict']}\n"
        f"{report['summary_ru']}\n"
        f"Отчёт: {session / 'report.md'}"
    )


if __name__ == "__main__":
    sys.exit(main())
