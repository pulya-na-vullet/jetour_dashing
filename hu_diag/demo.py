"""Synthetic dumps so the collector/parser can be tested without a car."""

from __future__ import annotations

from pathlib import Path

from hu_diag.commands import BASELINE_COMMANDS, SNAPSHOT_COMMANDS, SNAPSHOT_STAGES


GETPROP = """\
[ro.build.version.release]: [9]
[ro.build.version.sdk]: [28]
[ro.product.model]: [Dashing]
[ro.product.device]: [JX65]
[ro.product.manufacturer]: [CHERY]
[ro.build.fingerprint]: [CHERY/JX65/JX65:9/PPR1.180610.011/276:user/release-keys]
[ro.hardware]: [qcom]
[ro.board.platform]: [msm8953]
[ro.build.display.id]: [JX65-user 9 276]
[persist.sys.usb.config]: [adb]
[sys.usb.config]: [adb]
[ro.bootmode]: [unknown]
"""

PACKAGES = """\
package:/system/priv-app/AVM/AVM.apk=com.autochips.avm
package:/system/app/CheryCamera/CheryCamera.apk=com.chery.camera
package:/system/priv-app/EvsApp/EvsApp.apk=com.android.car.evs
package:/system/priv-app/Launcher/Launcher.apk=com.android.launcher3
package:/system/app/DVR/DVR.apk=com.jetour.dvr
package:/system/framework/framework-res.apk=android
"""

CAMERA_IDLE = """\
Number of camera devices: 0
No cameras available
"""

CAMERA_360 = """\
Number of camera devices: 0
Can't dump android.hardware.camera.provider
Client: com.autochips.avm
"""

ACTIVITY_IDLE = """\
mResumedActivity: ActivityRecord{abc com.android.launcher3/.Launcher t1}
"""

ACTIVITY_360 = """\
mResumedActivity: ActivityRecord{def com.autochips.avm/.AvmActivity t2}
"""

MOUNTS = """\
/dev/block/sda1 /storage/XXXX-XXXX vfat rw,relatime 0 0
tmpfs /mnt/usb none rw 0 0
"""


def _header(cmd: str) -> str:
    return f"# cmd: adb shell {cmd}\n# rc: 0\n\n"


def write_demo_session(session: Path) -> None:
    session.mkdir(parents=True, exist_ok=True)
    (session / "00_session.json").write_text('{"demo": true, "read_only": true}\n', encoding="utf-8")
    base = session / "01_baseline"
    base.mkdir(parents=True, exist_ok=True)
    mapping = {
        "id.txt": "uid=2000(shell) gid=2000(shell)\n",
        "uname.txt": "Linux localhost 4.9.112 #1 SMP PREEMPT aarch64\n",
        "getenforce.txt": "Enforcing\n",
        "getprop.txt": GETPROP,
        "getprop_build.txt": GETPROP,
        "pm_list_packages.txt": PACKAGES,
        "proc_mounts.txt": MOUNTS,
        "ls_storage.txt": "total 0\ndrwxr-xr-x usb0\n",
        "ls_dev_video.txt": "ls: /dev/video*: No such file or directory\n",
        "sm_volumes.txt": "public:8,1 mounted XXXX-XXXX\n",
        "dumpsys_usb.txt": "USB Host\n",
        "df.txt": "/storage/XXXX-XXXX 15G 12M 14G 1%\n",
    }
    for spec in BASELINE_COMMANDS:
        body = mapping.get(spec.filename, f"(demo empty) {spec.filename}\n")
        (base / spec.filename).write_text(_header(spec.shell) + body, encoding="utf-8")

    contents = {
        "idle": (CAMERA_IDLE, ACTIVITY_IDLE),
        "avm360": (CAMERA_360, ACTIVITY_360),
        "reverse": (CAMERA_360, ACTIVITY_360),
        "turn_left": (CAMERA_IDLE, ACTIVITY_IDLE),
        "turn_right": (CAMERA_IDLE, ACTIVITY_IDLE),
    }
    for idx, (stage, _title, _how) in enumerate(SNAPSHOT_STAGES, start=2):
        folder = session / f"{idx:02d}_{stage}"
        folder.mkdir(parents=True, exist_ok=True)
        cam, act = contents[stage]
        for spec in SNAPSHOT_COMMANDS:
            if spec.filename == "dumpsys_media_camera.txt":
                body = cam
            elif spec.filename.startswith("dumpsys_activity"):
                body = act
            else:
                body = "(demo)\n"
            (folder / spec.filename).write_text(_header(spec.shell) + body, encoding="utf-8")
