"""Resource limits for executing LLM-generated code.

Every runner in this project imports a module the LLM wrote and calls it on
inputs the LLM also chose. That is untrusted code by any reasonable definition,
and until 2026-09-05 it ran with no limits at all.

What that cost: ladder rung R5 is the unbounded-recursion target, generated code
for it ran away on a pathological input, and the kernel OOM-killed a 7.4 GB
Python process on a 7.6 GB machine -- taking the whole dev box down mid-run,
twice, which looked like the machine crashing rather than the harness misbehaving.

The limits below are deliberately tight. Every target in this project is a
string -> string function over short inputs; none has any honest reason to want
half a gigabyte or ten seconds of CPU. A generated implementation that hits one
of these limits has a bug, and recording that as a failed case is the correct
outcome -- far better than letting it take the host with it.

This matters MORE on the shared GPU server, not less: a runaway there costs other
users their machine, not just us.
"""
import os
import resource
import signal
import sys

# Sized so they never bind on legitimate work: every target here is a
# string -> string function over short inputs, so 4 GB and 30 CPU-seconds is
# orders of magnitude more than any correct implementation needs. These exist to
# catch a runaway, not to ration the run. Override per-host if ever needed.
MEM_BYTES = int(os.environ.get("BTP_SANDBOX_MEM_MB", "4096")) * 1024 * 1024
CPU_SECONDS = int(os.environ.get("BTP_SANDBOX_CPU_S", "30"))
RECURSION_LIMIT = int(os.environ.get("BTP_SANDBOX_RECURSION", "20000"))
PER_CALL_SECONDS = int(os.environ.get("BTP_SANDBOX_CALL_S", "15"))


class CallTimeout(Exception):
    pass


def apply_limits(mem_bytes=MEM_BYTES, cpu_seconds=CPU_SECONDS,
                 recursion_limit=RECURSION_LIMIT):
    """Cap this process. Call once, in the child, before importing generated code."""
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    # No core dumps: a 512MB core per runaway would fill the disk instead.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    sys.setrecursionlimit(recursion_limit)


def _raise_timeout(signum, frame):
    raise CallTimeout(f"call exceeded {PER_CALL_SECONDS}s")


def call_guarded(fn, arg, seconds=PER_CALL_SECONDS):
    """Call fn(arg) under a wall-clock alarm.

    Returns (ok, value, error). A timeout, a memory error, a recursion error and
    an ordinary exception all come back the same way: as a failed case, not as a
    dead harness. MemoryError is caught explicitly because that is what
    RLIMIT_AS surfaces as, and it is easy to mistake for a crash.
    """
    old = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(seconds)
    try:
        return True, fn(arg), None
    except CallTimeout as e:
        return False, None, f"Timeout: {e}"
    except RecursionError:
        return False, None, "RecursionError: generated code recursed without terminating"
    except MemoryError:
        return False, None, "MemoryError: generated code exceeded the memory limit"
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
