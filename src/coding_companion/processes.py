"""Process lifetime bounds. These do not supply filesystem/network isolation."""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from .common import CompanionError


def launch(argv, cwd: Path, env: dict, config):
    if os.name == "nt":
        return WindowsProcess(argv, cwd, env, config)
    return subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, start_new_session=True)


def terminate(process):
    if isinstance(process, WindowsProcess):
        process.terminate_job()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def close(process):
    # A successful parent exit must not leave its children running.
    terminate(process)
    if isinstance(process, WindowsProcess):
        process.close()


class WindowsProcess:
    """Create suspended, assign a nonbreakaway Job Object, then resume."""

    def __init__(self, argv, cwd, env, config):
        import ctypes as c
        import msvcrt
        from ctypes import wintypes as w

        class BasicLimit(c.Structure):
            _fields_ = [("PerProcessUserTimeLimit", c.c_int64), ("PerJobUserTimeLimit", c.c_int64), ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", c.c_size_t), ("MaximumWorkingSetSize", c.c_size_t), ("ActiveProcessLimit", w.DWORD), ("Affinity", c.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

        class IOCounters(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimit(c.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IOCounters), ("ProcessMemoryLimit", c.c_size_t), ("JobMemoryLimit", c.c_size_t), ("PeakProcessMemoryUsed", c.c_size_t), ("PeakJobMemoryUsed", c.c_size_t)]

        class Startup(c.Structure):
            _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR), ("lpTitle", w.LPWSTR), ("dwX", w.DWORD), ("dwY", w.DWORD), ("dwXSize", w.DWORD), ("dwYSize", w.DWORD), ("dwXCountChars", w.DWORD), ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD), ("dwFlags", w.DWORD), ("wShowWindow", w.WORD), ("cbReserved2", w.WORD), ("lpReserved2", c.POINTER(w.BYTE)), ("hStdInput", w.HANDLE), ("hStdOutput", w.HANDLE), ("hStdError", w.HANDLE)]

        class StartupEx(c.Structure):
            _fields_ = [("StartupInfo", Startup), ("lpAttributeList", c.c_void_p)]

        class ProcessInfo(c.Structure):
            _fields_ = [("hProcess", w.HANDLE), ("hThread", w.HANDLE), ("dwProcessId", w.DWORD), ("dwThreadId", w.DWORD)]

        kernel = c.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([c.c_void_p, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "InitializeProcThreadAttributeList": ([c.c_void_p, w.DWORD, w.DWORD, c.POINTER(c.c_size_t)], w.BOOL),
            "UpdateProcThreadAttribute": ([c.c_void_p, w.DWORD, c.c_size_t, c.c_void_p, c.c_size_t, c.c_void_p, c.c_void_p], w.BOOL),
            "DeleteProcThreadAttributeList": ([c.c_void_p], None),
            "CreateProcessW": ([w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL, w.DWORD, c.c_void_p, w.LPCWSTR, c.c_void_p, c.POINTER(ProcessInfo)], w.BOOL),
            "ResumeThread": ([w.HANDLE], w.DWORD),
            "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
            "TerminateProcess": ([w.HANDLE, w.UINT], w.BOOL),
            "GetExitCodeProcess": ([w.HANDLE, c.POINTER(w.DWORD)], w.BOOL),
            "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
            "CloseHandle": ([w.HANDLE], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(kernel, name)
            function.argtypes, function.restype = args, result
        self.kernel, self.handle, self.job = kernel, None, None
        self.returncode, self.stdout, self.stderr = None, None, None
        descriptors, attribute, info = [], None, ProcessInfo()
        try:
            self.job = kernel.CreateJobObjectW(None, None)
            if not self.job:
                raise c.WinError(c.get_last_error())
            limits = ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x100  # KILL_ON_JOB_CLOSE, PROCESS_MEMORY
            limits.ProcessMemoryLimit = config.max_process_memory_bytes
            if not kernel.SetInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits)):
                raise c.WinError(c.get_last_error())
            out_read, out_write = os.pipe()
            descriptors.extend([out_read, out_write])
            err_read, err_write = os.pipe()
            descriptors.extend([err_read, err_write])
            null_fd = os.open(os.devnull, os.O_RDONLY)
            descriptors.append(null_fd)
            for fd in (out_write, err_write, null_fd):
                os.set_inheritable(fd, True)
            handles = (w.HANDLE * 3)(*[msvcrt.get_osfhandle(fd) for fd in (null_fd, out_write, err_write)])
            size = c.c_size_t()
            kernel.InitializeProcThreadAttributeList(None, 1, 0, c.byref(size))
            attribute = c.create_string_buffer(size.value)
            if not kernel.InitializeProcThreadAttributeList(attribute, 1, 0, c.byref(size)):
                raise c.WinError(c.get_last_error())
            if not kernel.UpdateProcThreadAttribute(attribute, 0, 0x20002, handles, c.sizeof(handles), None, None):
                raise c.WinError(c.get_last_error())
            startup = StartupEx()
            startup.StartupInfo.cb = c.sizeof(startup)
            startup.StartupInfo.dwFlags = 0x100 | 0x1  # Standard handles and hidden window
            startup.StartupInfo.wShowWindow = 0
            startup.StartupInfo.hStdInput, startup.StartupInfo.hStdOutput, startup.StartupInfo.hStdError = handles
            startup.lpAttributeList = c.cast(attribute, c.c_void_p)
            environment = c.create_unicode_buffer("\0".join(f"{key}={value}" for key, value in sorted(env.items(), key=lambda pair: pair[0].upper())) + "\0\0")
            command = c.create_unicode_buffer(subprocess.list2cmdline(argv))
            flags = 0x4 | 0x400 | 0x80000 | 0x08000000  # suspended, Unicode, extended startup, no window
            if not kernel.CreateProcessW(argv[0], command, None, None, True, flags, environment, str(cwd), c.byref(startup), c.byref(info)):
                raise c.WinError(c.get_last_error())
            self.handle, self.pid = info.hProcess, info.dwProcessId
            if not kernel.AssignProcessToJobObject(self.job, self.handle):
                # Never resume uncontained user code, even on an incompatible host.
                kernel.TerminateProcess(self.handle, 1)
                raise CompanionError("Windows host rejected Job Object assignment; command was not resumed")
            self.stdout, self.stderr = os.fdopen(out_read, "rb"), os.fdopen(err_read, "rb")
            descriptors.remove(out_read)
            descriptors.remove(err_read)
            if kernel.ResumeThread(info.hThread) == 0xFFFFFFFF:
                raise c.WinError(c.get_last_error())
        except BaseException:
            if self.handle:
                kernel.TerminateProcess(self.handle, 1)
            self.close()
            for pipe in (self.stdout, self.stderr):
                if pipe:
                    pipe.close()
            raise
        finally:
            if info.hThread:
                kernel.CloseHandle(info.hThread)
            if attribute:
                kernel.DeleteProcThreadAttributeList(attribute)
            for fd in descriptors:
                os.close(fd)

    def poll(self):
        import ctypes as c
        from ctypes import wintypes as w
        if self.returncode is not None:
            return self.returncode
        if self.kernel.WaitForSingleObject(self.handle, 0) == 0:
            code = w.DWORD()
            if not self.kernel.GetExitCodeProcess(self.handle, c.byref(code)):
                raise c.WinError(c.get_last_error())
            self.returncode = code.value
        return self.returncode

    def wait(self, timeout=None):
        milliseconds = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
        if self.kernel.WaitForSingleObject(self.handle, milliseconds) == 0x102:
            raise subprocess.TimeoutExpired("native process", timeout)
        return self.poll()

    def terminate_job(self):
        if self.job:
            self.kernel.TerminateJobObject(self.job, 130)

    def close(self):
        for name in ("job", "handle"):
            handle = getattr(self, name, None)
            if handle:
                self.kernel.CloseHandle(handle)
                setattr(self, name, None)
