# FreshTrack — Advanced Food Waste Reduction System
Python + Flask + SQLite training project.

Features: user registration/login with hashed passwords; personal food inventory;
automatic expiry classification; priority food; consumed/donated/wasted lifecycle;
waste and food-value tracking; analytics; rule-based pantry recipe suggestions;
shopping list; responsive UI; deployment-ready Procfile.

Run:
1. `python -m venv venv`
2. Windows: `venv\Scripts\activate` (macOS/Linux: `source venv/bin/activate`)
3. `pip install -r requirements.txt`
4. `python app.py`
5. Open http://127.0.0.1:5000

Deployment:
Build command: `pip install -r requirements.txt`
Start command: `gunicorn app:app`

Demo: register, add food with expiry and price, mark items consumed/donated/wasted,
then open Analytics, Smart Recipes and Shopping List.
