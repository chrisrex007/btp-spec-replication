"""Standalone trusted Python line collector; never imported by the candidate."""
from __future__ import annotations

import atexit
import builtins
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import sys
import threading
import types
import _thread


def main() -> None:
    source = Path(sys.argv[1]).resolve()
    fd = int(os.environ.pop("BTP_TRACE_FD"))
    os.set_inheritable(fd, False)
    write = os.write
    encode = json.dumps
    terminate = os._exit
    active = False
    termination = {"kind": "exit", "exit_code": 0}

    def emit(record):
        data = (encode(record, ensure_ascii=True) + "\n").encode("ascii")
        while data:
            data = data[write(fd, data):]

    def unsupported(message):
        emit({"type": "error", "reason": "unsupported_execution", "message": message})
        terminate(125)

    def audit(event, _args):
        if event in {"_thread.start_new_thread", "os.fork", "os.forkpty", "os.posix_spawn",
                     "os.exec", "os.spawn", "os.system", "subprocess.Popen", "cpython.PyInterpreterState_New"}:
            unsupported("Candidate requested " + event)
        if event == "sys.settrace" and active:
            unsupported("Candidate attempted to replace the trace hook")

    def new_thread(*_args, **_kwargs):
        unsupported("Candidate requested another Python thread")

    owner = threading.get_ident()
    source_name = str(source)

    def trace(frame, event, _arg):
        if threading.get_ident() != owner:
            unsupported("Candidate created another Python thread")
        if frame.f_code.co_filename == source_name:
            if event == "line":
                emit({"type": "line", "line": frame.f_lineno})
            return trace
        return None

    def finish():
        nonlocal active
        active = False
        sys.settrace(None)
        emit({"type": "end", "termination": termination})

    try:
        code = compile(source.read_bytes(), source_name, "exec")
        # Match ordinary script execution, without exposing wrapper argv/globals.
        sys.argv = [source_name]
        if hasattr(sys, "orig_argv"):
            sys.orig_argv = [sys.executable, source_name]
        sys.path[0] = str(source.parent)
        module = types.ModuleType("__main__")
        module.__file__ = source_name
        module.__package__ = None
        module.__spec__ = None
        module.__cached__ = None
        module.__loader__ = SourceFileLoader("__main__", source_name)
        module.__dict__["__builtins__"] = builtins
        sys.modules["__main__"] = module
        # Register first: candidate atexit callbacks execute before this final
        # record, with tracing still enabled. Do not lose their source events.
        atexit.register(finish)
        _thread.start_new_thread = new_thread
        threading._start_new_thread = new_thread
        sys.addaudithook(audit)
        threading.settrace(trace)
        emit({"type": "ready"})
        sys.settrace(trace)
        active = True
    except BaseException as exc:
        emit({"type": "error", "reason": "collector_failed", "message": type(exc).__name__})
        terminate(125)
    try:
        exec(code, module.__dict__)
    except SystemExit as exc:
        status = int(exc.code) if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        termination = {"kind": "exit", "exit_code": status}
        raise
    except BaseException:
        termination = {"kind": "exception", "exit_code": 1}
        raise


if __name__ == "__main__":
    main()
