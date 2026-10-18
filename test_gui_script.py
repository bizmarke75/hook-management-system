import sys, os, re, datetime, threading

# Redirect stdout/stderr if None (for PyInstaller --noconsole)
class DummyStream:
    def write(self, s): pass
    def flush(self): pass

if sys.stdout is None:
    sys.stdout = DummyStream()
if sys.stderr is None:
    sys.stderr = DummyStream()

