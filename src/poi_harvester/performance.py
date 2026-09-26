"""Optional portable process and host measurements; no official hardware claim."""

from __future__ import annotations

import os
import platform


def host_metrics() -> dict:
    report = {"platform": platform.platform(), "cpu": platform.processor() or platform.machine(),
              "logical_cpu_count": os.cpu_count(), "physical_memory_bytes": None,
              "process_peak_rss_bytes": None, "official_hardware_verified": False}
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD),
                        *[(name, ctypes.c_ulonglong) for name in
                          ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended")]]
        class ProcessMemory(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in
                          ("peak_rss", "rss", "peak_pool_paged", "pool_paged", "peak_pool_nonpaged", "pool_nonpaged", "pagefile", "peak_pagefile")]]
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            report["physical_memory_bytes"] = memory.total_phys
        counters = ProcessMemory()
        counters.cb = ctypes.sizeof(counters)
        ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        ctypes.windll.psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            report["process_peak_rss_bytes"] = counters.peak_rss
    else:
        try:
            import resource
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            report["process_peak_rss_bytes"] = peak if platform.system() == "Darwin" else peak * 1024
            report["physical_memory_bytes"] = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ImportError, ValueError, OSError, AttributeError):
            pass
    return report
