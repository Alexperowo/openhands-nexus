import ctypes
import ctypes.wintypes
import os
import re
import socket
import logging
from typing import Optional, Tuple

logger = logging.getLogger("antigravity-bridge.upstream")

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('ExitStatus', ctypes.c_ulonglong),
        ('PebBaseAddress', ctypes.c_void_p),
        ('AffinityMask', ctypes.c_ulonglong),
        ('BasePriority', ctypes.c_ulonglong),
        ('UniqueProcessId', ctypes.c_ulonglong),
        ('InheritedFromUniqueProcessId', ctypes.c_ulonglong),
    ]

_cached_proxy_url: Optional[str] = None

def _is_proxy_alive(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def _extract_proxy_from_peb(pid: int) -> Optional[str]:
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    ntdll = ctypes.WinDLL('ntdll', use_last_error=True)

    hProcess = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not hProcess:
        return None

    try:
        pbi = PROCESS_BASIC_INFORMATION()
        ret_len = ctypes.c_ulong()
        if ntdll.NtQueryInformationProcess(hProcess, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), ctypes.byref(ret_len)) != 0:
            return None

        peb_addr = pbi.PebBaseAddress
        if not peb_addr:
            return None

        buf = ctypes.c_void_p()
        if not kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(peb_addr + 0x20), ctypes.byref(buf), 8, None):
            return None
        proc_params_addr = buf.value
        if not proc_params_addr:
            return None

        if not kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(proc_params_addr + 0x80), ctypes.byref(buf), 8, None):
            return None
        env_addr = buf.value
        if not env_addr:
            return None

        env_data = bytearray(32768)
        bytes_read = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(env_addr), (ctypes.c_char * len(env_data)).from_buffer(env_data), len(env_data), ctypes.byref(bytes_read)):
            return None

        env_str = env_data[:bytes_read.value].decode('utf-16le', errors='ignore')
        for item in env_str.split('\x00'):
            if item.startswith('HTTPS_PROXY='):
                return item.split('=', 1)[1].strip()
    except Exception as e:
        logger.debug("PEB extraction exception for PID %d: %s", pid, e)
    finally:
        kernel32.CloseHandle(hProcess)

    return None

def _extract_proxy_from_log() -> Optional[str]:
    log_path = os.path.expanduser(r"~\.agy-lswrap.log")
    if not os.path.exists(log_path):
        return None

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-50:]
            for line in reversed(lines):
                # Pattern: [lswrap] start pid=... port=54991
                m = re.search(r'\[lswrap\] start pid=(\d+) port=(\d+)', line)
                if m:
                    pid = int(m.group(1))
                    port = int(m.group(2))
                    # Try to get full auth token from process PEB if alive
                    peb_proxy = _extract_proxy_from_peb(pid)
                    if peb_proxy:
                        return peb_proxy
                    if _is_proxy_alive("127.0.0.1", port):
                        return f"http://127.0.0.1:{port}"
    except Exception as e:
        logger.debug("Failed reading lswrap log: %s", e)

    return None

def find_running_antigravity_pids() -> list[int]:
    """Find PIDs for running language_server.exe or Antigravity processes, prioritizing language_server."""
    import subprocess
    cmd = 'powershell.exe -NoProfile -Command "Get-Process -Name language_server -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id; Get-Process -Name Antigravity -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"'
    try:
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
        return [int(line.strip()) for line in out.splitlines() if line.strip().isdigit()]
    except Exception:
        return []

def get_upstream_proxy(force_refresh: bool = False) -> Optional[str]:
    """
    Lazy detector: retrieves the current active HTTPS_PROXY for agy-unlock.
    1. Checks cached proxy liveness.
    2. Probes running Antigravity processes via PEB.
    3. Falls back to ~/.agy-lswrap.log.
    """
    global _cached_proxy_url

    if not force_refresh and _cached_proxy_url:
        # Quick validation
        m = re.search(r':(\d+)', _cached_proxy_url.split('@')[-1])
        if m and _is_proxy_alive("127.0.0.1", int(m.group(1))):
            return _cached_proxy_url

    # 1. Probe running processes via PEB
    pids = find_running_antigravity_pids()
    for pid in pids:
        proxy = _extract_proxy_from_peb(pid)
        if proxy:
            m = re.search(r':(\d+)', proxy.split('@')[-1])
            if m and _is_proxy_alive("127.0.0.1", int(m.group(1))):
                logger.info("[UPSTREAM] Discovered live proxy from PID %d: %s", pid, re.sub(r':[^@]+@', ':***@', proxy))
                _cached_proxy_url = proxy
                return proxy

    # 2. Fallback to ~/.agy-lswrap.log
    fallback_proxy = _extract_proxy_from_log()
    if fallback_proxy:
        logger.info("[UPSTREAM] Discovered live proxy from lswrap log: %s", fallback_proxy)
        _cached_proxy_url = fallback_proxy
        return fallback_proxy

    logger.warning("[UPSTREAM] No active agy-unlock proxy found; upstream requests will connect direct.")
    _cached_proxy_url = None
    return None

def invalidate_proxy():
    global _cached_proxy_url
    _cached_proxy_url = None
