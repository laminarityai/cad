import json
import os
import resource
import sys
from collections.abc import Callable, Iterable, Sequence
from typing import NoReturn

CPU_KILL_AFTER_SECONDS = 5


def serve(answer: Callable[[Sequence[str], bytes], Iterable[object]]) -> NoReturn:
    """Calls `answer` with the arguments after the CPU seconds and with stdin, and writes each
    message it yields to the report channel as one line of JSON as soon as it is yielded."""
    # OCCT prints transfer statistics to fd 1 from C++, so fd 1 is moved aside before OCP loads.
    report_channel = os.dup(1)
    os.dup2(2, 1)
    cpu_seconds = int(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + CPU_KILL_AFTER_SECONDS))
    with os.fdopen(report_channel, "wb") as channel:
        for message in answer(sys.argv[2:], sys.stdin.buffer.read()):
            sys.stdout.flush()
            sys.stderr.flush()
            channel.write(json.dumps(message).encode() + b"\n")
            channel.flush()
    os._exit(0)
