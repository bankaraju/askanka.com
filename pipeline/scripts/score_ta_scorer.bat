@echo off
REM ANKA TA Coincidence Scorer — daily score, 16:00 IST after EOD bars locked
REM Applies cached RELIANCE model to today's close, emits ta_attractiveness_scores.json.
cd /d "C:\Users\Claude_Anka\askanka.com"
python -X utf8 -m pipeline.ta_scorer.score_universe >> pipeline\logs\score_ta_scorer.log 2>&1
