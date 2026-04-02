"""Bootstrap for schtasks: injects local lib packages then runs target script."""
import sys
import os

# Local lib directory (always accessible, even from schtasks)
_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_pipeline = os.path.dirname(os.path.abspath(__file__))
if _pipeline not in sys.path:
    sys.path.insert(0, _pipeline)
os.chdir(_pipeline)

if __name__ == "__main__":
    script = sys.argv[1]
    sys.argv = sys.argv[1:]
    import runpy
    runpy.run_path(script, run_name="__main__")
