"""Score the 31 missing F&O stocks for Monday morning trust gate coverage."""
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

MISSING = [
    "BAJAJHLDNG", "BDL", "CIPLA", "FORCEMOT",
    "IREDA", "OFSS", "PAGEIND", "WAAREEENER",
]

OPUS_DIR = Path(__file__).parent
LOG_FILE = OPUS_DIR / "logs" / "missing_31_batch.log"


def log(msg):
    ts = datetime.now(IST).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    done = []
    failed = []
    log(f"Starting batch: {len(MISSING)} stocks")

    for i, sym in enumerate(MISSING, 1):
        ts_file = OPUS_DIR / "artifacts" / sym / "trust_score.json"
        if ts_file.exists():
            try:
                existing = json.loads(ts_file.read_text(encoding="utf-8"))
                g = existing.get("trust_grade")
                if g and g != "?":
                    log(f"[{i}/{len(MISSING)}] SKIP {sym}: already scored grade={g}")
                    done.append(sym)
                    continue
            except Exception:
                pass
        log(f"[{i}/{len(MISSING)}] Scoring {sym}...")
        try:
            result = subprocess.run(
                [sys.executable, "run_trust_score.py", sym],
                cwd=str(OPUS_DIR),
                capture_output=True,
                text=True,
                timeout=600,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                ts_file = OPUS_DIR / "artifacts" / sym / "trust_score.json"
                if ts_file.exists():
                    score = json.loads(ts_file.read_text(encoding="utf-8"))
                    grade = score.get("trust_grade", "?")
                    log(f"  OK {sym}: grade={grade}")
                    done.append(sym)
                else:
                    log(f"  FAIL{sym}: completed but no trust_score.json")
                    failed.append(sym)
            else:
                err = result.stderr[-200:] if result.stderr else "no stderr"
                log(f"  FAIL{sym}: exit {result.returncode} — {err}")
                failed.append(sym)
        except subprocess.TimeoutExpired:
            log(f"  FAIL{sym}: TIMEOUT (600s)")
            failed.append(sym)
        except Exception as e:
            log(f"  FAIL{sym}: {e}")
            failed.append(sym)

    log(f"\nBatch complete: {len(done)} scored, {len(failed)} failed")
    if failed:
        log(f"Failed: {failed}")

    # Export updated trust scores to data/trust_scores.json
    log("Exporting trust scores to data/trust_scores.json...")
    try:
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'C:/Users/Claude_Anka/askanka.com/pipeline'); "
             "from website_exporter import export_trust_scores; "
             "import json; from pathlib import Path; "
             "ts = export_trust_scores(); "
             "Path('C:/Users/Claude_Anka/askanka.com/data/trust_scores.json').write_text("
             "json.dumps(ts, indent=2), encoding='utf-8'); "
             "print(f'Exported {ts.get(\"total_scored\", 0)} stocks')"],
            cwd="C:/Users/Claude_Anka/askanka.com",
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        log(f"  Export: {result.stdout.strip()}")
    except Exception as e:
        log(f"  Export failed: {e}")


if __name__ == "__main__":
    main()
