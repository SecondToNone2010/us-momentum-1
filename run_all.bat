@echo off
cd /d C:\Users\anhtu\Downloads\us-momentum-1
call .venv\Scripts\activate
set APCA_API_KEY_ID=PASTE_YOUR_PAPER_KEY_HERE
set APCA_API_SECRET_KEY=PASTE_YOUR_PAPER_SECRET_HERE
python main.py
python paper_trade.py
