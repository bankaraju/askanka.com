@echo off
cd /d "C:\Users\Claude_Anka\Documents\askanka.com\pipeline"
python -X utf8 -c "import sys,io;sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace');sys.path.insert(0,'.');from signal_tracker import run_eod_review;from telegram_bot import send_dashboard,send_followup;d=run_eod_review();send_dashboard(d)" >> logs\eod.log 2>&1
