"""Read-only ADB command catalog for Dashing HU camera/DVR inventory.

These commands only dump system state. They do not patch firmware,
unlock bootloader, or extract app private data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DumpCmd:
    filename: str
    description: str
    shell: str
    # If True, run even when adb is unprivileged (shell).
    required: bool = True


# Snapshot-sensitive: camera clients, foreground activity, overlay.
SNAPSHOT_COMMANDS: tuple[DumpCmd, ...] = (
    DumpCmd(
        "dumpsys_media_camera.txt",
        "Camera2/HAL clients, cameraId, exclusive lock",
        "dumpsys media.camera",
    ),
    DumpCmd(
        "dumpsys_media_camera_provider.txt",
        "Camera provider HAL",
        "dumpsys media.camera.provider",
        required=False,
    ),
    DumpCmd(
        "dumpsys_activity_activities.txt",
        "Foreground activity (360 app / reverse overlay)",
        "dumpsys activity activities",
    ),
    DumpCmd(
        "dumpsys_activity_top.txt",
        "Resumed activity",
        "dumpsys activity top",
        required=False,
    ),
    DumpCmd(
        "dumpsys_window_windows.txt",
        "Window overlay / Surface for 360",
        "dumpsys window windows",
        required=False,
    ),
    DumpCmd(
        "dumpsys_display.txt",
        "Displays and layers",
        "dumpsys display",
        required=False,
    ),
    DumpCmd(
        "ps_camera.txt",
        "Processes matching camera/AVM/DVR",
        "ps -A",
        required=False,
    ),
    DumpCmd(
        "logcat_camera.txt",
        "Recent camera/AVM logcat",
        "logcat -d -t 400 CameraService:V Camera2Client:V Camera3-*:V "
        "android.hardware.camera*:V CamX:V AVM:V Evs*:V *:S",
        required=False,
    ),
)


# Once per session: identity, packages, USB, device nodes.
BASELINE_COMMANDS: tuple[DumpCmd, ...] = (
    DumpCmd("id.txt", "ADB user (shell vs root)", "id"),
    DumpCmd("uname.txt", "Kernel", "uname -a"),
    DumpCmd("getenforce.txt", "SELinux mode", "getenforce", required=False),
    DumpCmd("getprop.txt", "All system properties", "getprop"),
    DumpCmd(
        "getprop_build.txt",
        "Build/model/android",
        "getprop | grep -E 'ro\\.(build|product|hardware)|ro.system.build'",
    ),
    DumpCmd("pm_list_packages.txt", "All packages", "pm list packages -f"),
    DumpCmd("pm_list_features.txt", "System features", "pm list features", required=False),
    DumpCmd("pm_list_permissions.txt", "Permissions", "pm list permissions -g -d", required=False),
    DumpCmd("service_list.txt", "Binder services", "service list", required=False),
    DumpCmd(
        "lshal.txt",
        "HIDL/AIDL HALs (camera/evs/vehicle)",
        "lshal",
        required=False,
    ),
    DumpCmd(
        "dumpsys_evs.txt",
        "Android EVS (if present)",
        "dumpsys android.hardware.automotive.evs",
        required=False,
    ),
    DumpCmd(
        "dumpsys_car_service.txt",
        "Car service",
        "dumpsys car_service",
        required=False,
    ),
    DumpCmd(
        "dumpsys_usb.txt",
        "USB host/device state",
        "dumpsys usb",
        required=False,
    ),
    DumpCmd(
        "dumpsys_storage.txt",
        "Storage manager",
        "dumpsys mount",
        required=False,
    ),
    DumpCmd("df.txt", "Filesystem free space", "df -h", required=False),
    DumpCmd("proc_mounts.txt", "Mount table", "cat /proc/mounts"),
    DumpCmd("sm_volumes.txt", "sm list-volumes", "sm list-volumes", required=False),
    DumpCmd(
        "ls_storage.txt",
        "Visible storage roots",
        "ls -la /storage /mnt /sdcard /data/media 2>/dev/null; echo '---'; ls -la /storage 2>/dev/null",
        required=False,
    ),
    DumpCmd(
        "ls_dev_video.txt",
        "V4L/camera device nodes",
        "ls -la /dev/video* /dev/v4l* /dev/camera* /dev/cam* 2>/dev/null; "
        "echo '---'; ls /dev | grep -iE 'video|v4l|cam|i2c|spi|drm|gadget|usb'",
        required=False,
    ),
    DumpCmd(
        "dumpsys_media_session.txt",
        "Media session",
        "dumpsys media_session",
        required=False,
    ),
    DumpCmd(
        "cmd_media_camera.txt",
        "cmd media.camera help/state",
        "cmd media.camera",
        required=False,
    ),
)


PACKAGE_DUMP_GREP = (
    r"camera|avm|around|surround|panoram|360|540|dvr|record|dashcam|"
    r"birdview|bird.view|parkassist|park_assist|svs|evs|"
    r"vision|reverse|rearview|chery|jetour|desaysv|autochips|"
    r"megatron|huawei.android.avm|ivi.camera"
)


SNAPSHOT_STAGES: tuple[tuple[str, str, str], ...] = (
    (
        "idle",
        "Снимок IDLE",
        "360 ВЫКЛ, задняя передача НЕ включена, поворотники ВЫКЛ.\n"
        "На экране обычный рабочий стол ГУ.",
    ),
    (
        "avm360",
        "Снимок 360 ОТКРЫТ",
        "Откройте штатный круговой обзор кнопкой на ГУ и оставьте его на экране.",
    ),
    (
        "reverse",
        "Снимок ЗАДНЯЯ ПЕРЕДАЧА",
        "Включите заднюю передачу (камера заднего вида / 360 при реверсе).\n"
        "Держите экран с камерой, пока идёт съём лога.",
    ),
    (
        "turn_left",
        "Снимок ПОВОРОТНИК ВЛЕВО",
        "Заднюю выключите. Включите левый поворотник.\n"
        "Если появляется боковая камера — оставьте её на экране.",
    ),
    (
        "turn_right",
        "Снимок ПОВОРОТНИК ВПРАВО",
        "Включите правый поворотник. Если появляется боковая камера — оставьте её.",
    ),
)
