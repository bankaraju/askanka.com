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

# Repo root must be on sys.path so `from pipeline.X import Y` resolves.
# Without this, scripts launched via runpy.run_path that touch any
# pipeline.* sub-package fail with ModuleNotFoundError: No module named 'pipeline'.
_repo_root = os.path.dirname(_pipeline)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
os.chdir(_pipeline)

if __name__ == "__main__":
    script = sys.argv[1]
    # runpy.run_path sets __file__ to the path string as given. Pass an
    # absolute path so scripts that derive paths from Path(__file__).parent
    # don't silently compute against CWD.
    if not os.path.isabs(script):
        script = os.path.abspath(script)
    sys.argv = sys.argv[1:]
    import runpy
    runpy.run_path(script, run_name="__main__")
