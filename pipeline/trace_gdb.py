"""Trusted GDB Python script, loaded explicitly by the candidate-only collector."""
import json
import os

import gdb


def collect():
    fd = int(os.environ.pop("BTP_TRACE_FD"))
    config_path = os.environ.pop("BTP_TRACE_CONFIG")
    os.set_inheritable(fd, False)
    with open(config_path, encoding="utf-8") as stream:
        config = json.load(stream)
    source = os.path.realpath(config["source"])
    ended = False
    initial_thread = None
    unsupported = None
    last_signal = None

    def emit(value):
        data = (json.dumps(value, ensure_ascii=True) + "\n").encode("ascii")
        while data:
            data = data[os.write(fd, data):]

    def fail(message):
        nonlocal unsupported
        unsupported = message

    class Location(gdb.Breakpoint):
        def __init__(self, pc, line):
            super().__init__("*" + hex(pc), internal=True)
            self.line = line
            self.silent = True

        def stop(self):
            emit({"type": "line", "line": self.line})
            return False

    def new_thread(event):
        nonlocal initial_thread
        try:
            if initial_thread is None:
                initial_thread = event.inferior_thread.global_num
                pid = event.inferior_thread.inferior.pid
                with open("/proc/" + str(pid) + "/stat", encoding="ascii") as stream:
                    ticks = stream.read().rsplit(")", 1)[1].split()[19]
                emit({"type": "process", "pid": pid, "start_ticks": ticks})
            elif event.inferior_thread.global_num != initial_thread:
                fail("Candidate created another thread")
                emit({"type": "error", "reason": "unsupported_execution", "message": unsupported})
        except BaseException as exc:
            emit({"type": "error", "reason": "collector_failed", "message": str(exc)[:1000]})

    def exited(event):
        nonlocal ended
        if unsupported is None and not ended:
            exit_code = getattr(event, "exit_code", None)
            termination = ({"kind": "signal", "signal": last_signal}
                           if exit_code is None and last_signal is not None
                           else {"kind": "exit", "exit_code": exit_code})
            emit({"type": "end", "termination": termination})
            ended = True

    try:
        gdb.execute("set pagination off")
        gdb.execute("set confirm off")
        gdb.execute("set startup-with-shell off")
        gdb.execute("set auto-load off")
        gdb.execute("set debuginfod enabled off")
        gdb.execute("set follow-fork-mode parent")
        gdb.execute("set detach-on-fork off")
        gdb.execute("unset environment BTP_TRACE_FD")
        gdb.execute("unset environment BTP_TRACE_CONFIG")
        # The non-PIE executable's line addresses are valid before run, so static
        # initialization is included rather than beginning collection at main.
        location = "'" + source.replace("\\", "\\\\").replace("'", "\\'") + "':1"
        remainder, decoded = gdb.decode_line(location)
        symtabs = [sal.symtab for sal in (decoded or ()) if sal.symtab is not None
                   and os.path.realpath(sal.symtab.fullname()) == source]
        if remainder or not symtabs:
            raise ValueError("Candidate debug source is unavailable")
        symtab = symtabs[0]
        locations = {}
        for entry in symtab.linetable():
            if entry.line <= 0:
                continue
            sal = gdb.find_pc_line(entry.pc)
            if sal.line > 0 and sal.symtab is not None and os.path.realpath(sal.symtab.fullname()) == source:
                locations[entry.pc] = sal.line
        if not locations:
            raise ValueError("Candidate has no executable source mappings")
        breakpoints = [Location(pc, line) for pc, line in sorted(locations.items())]
        # Catchpoints have no Python constructor. Each stops run and is
        # classified below without continuing the unsupported execution.
        for operation in ("fork", "vfork", "exec"):
            gdb.execute("catch " + operation)
        gdb.events.new_thread.connect(new_thread)
        gdb.events.exited.connect(exited)
        emit({"type": "ready"})
        gdb.execute("run")
        while not ended and unsupported is None:
            stop = last_stop[0]
            if isinstance(stop, gdb.SignalEvent):
                # A stop before signal delivery is not program termination: a
                # candidate handler may run. Deliver it and keep collecting.
                last_signal = stop.stop_signal
                gdb.execute("signal " + last_signal)
            elif isinstance(stop, gdb.BreakpointEvent):
                fail("Candidate requested fork, vfork or exec")
                emit({"type": "error", "reason": "unsupported_execution",
                      "message": unsupported})
            else:
                raise ValueError("Debugger stopped without a candidate termination")
    except BaseException as exc:
        emit({"type": "error", "reason": "collector_failed", "message": str(exc)[:1000]})
    finally:
        # Parent also kills the debugger process group, covering timeout and limit.
        for inferior in gdb.inferiors():
            if inferior.pid:
                try:
                    gdb.execute("kill inferiors " + str(inferior.num))
                except gdb.error:
                    pass


last_stop = [None]
gdb.events.stop.connect(lambda event: last_stop.__setitem__(0, event))
collect()
