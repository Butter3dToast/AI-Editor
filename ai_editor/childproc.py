"""FFmpeg and TwitchDownloader stop when AI-Editor stops.

Closing the window AI-Editor runs in ends it on the spot, with no chance to
tidy up. The programs it started would carry on without it: an FFmpeg encode
could keep the GPU and drive busy for an hour, unseen, while the creator
streams. Windows can tie them together: AI-Editor's own child programs join a
"job" that Windows ends when AI-Editor ends, however it ends.

Only programs AI-Editor itself started are ever put in it.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import threading
from ctypes import wintypes

from .logging_setup import get_logger

log = get_logger(__name__)

_KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMITS = 9  # JobObjectExtendedLimitInformation


class _Basic(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _Extended(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


_lock = threading.Lock()
_job: int | None = None
_failed = False


def _make_job() -> int | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                 wintypes.DWORD]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = _Extended()
    limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, _EXTENDED_LIMITS, ctypes.byref(limits),
                                            ctypes.sizeof(limits)):
        return None
    return job


def keep_with_us(process: subprocess.Popen) -> None:
    """Have Windows end ``process`` (and what it starts) when AI-Editor ends.

    Best effort: if Windows refuses, the program simply runs as before.
    """
    global _job, _failed
    if sys.platform != "win32" or _failed:
        return
    with _lock:
        if _job is None:
            _job = _make_job()
            if _job is None:
                _failed = True
                log.warning("Couldn't tie child programs to AI-Editor (error %s)",
                            ctypes.get_last_error())
                return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    if not kernel32.AssignProcessToJobObject(_job, int(process._handle)):  # noqa: SLF001
        # It may simply have finished already.
        log.debug("Couldn't tie %s to AI-Editor (error %s)", process.args, ctypes.get_last_error())
