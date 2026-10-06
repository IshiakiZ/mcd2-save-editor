"""A probe for the Mac, where Tk never finishes drawing the editor's window: open the editor the way the window
tests do, count what Tk calls back into Python while it draws, and after a few seconds say what was busiest.
Not a test (unittest's discovery only takes test_*.py); it goes once the cause is found.

    python -m tests.mac_probe            Simple mode
    python -m tests.mac_probe advanced
"""

import collections
import os
import sys
import threading
import time
import tkinter

from tests import test_gui

counts: collections.Counter = collections.Counter()
original = tkinter.CallWrapper.__call__


def counted(self, *args):
    func = self.func
    code = getattr(func, "__code__", None)
    where = f"{os.path.basename(code.co_filename)}:{code.co_firstlineno} " if code is not None else ""
    counts[where + (getattr(func, "__qualname__", None) or repr(func))] += 1
    return original(self, *args)


tkinter.CallWrapper.__call__ = counted


def report(seconds: float) -> None:
    time.sleep(seconds)
    print(f"--- still drawing after {seconds:.0f} s; callbacks so far: {sum(counts.values())}", flush=True)
    for name, count in counts.most_common(15):
        print(f"{count:8}  {name}", flush=True)
    os._exit(3)


class Probe(test_gui.EffectsWindowTests):
    advanced = "advanced" in sys.argv

    def runTest(self):
        pass


threading.Thread(target=report, args=(20,), daemon=True).start()
probe = Probe()
started = time.time()
probe.setUp()
print(f"the window was drawn in {time.time() - started:.1f} s; callbacks: {sum(counts.values())}", flush=True)
for name, count in counts.most_common(8):
    print(f"{count:8}  {name}", flush=True)
probe.doCleanups()
os._exit(0)
