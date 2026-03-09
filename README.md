# ◈ NovaPulse 2.0 — PC Performance Suite

Python backend + React frontend. No tkinter. No build tools.

## Setup

```
pip install flask psutil groq
python server.py
```

Browser opens automatically at http://localhost:7842

## AI Optimizer

Get a free Groq API key at https://console.groq.com  
Enter it in the **AI Optimizer** tab → Save → Analyze

## Architecture

```
server.py     ← Python Flask backend (stats, groq proxy, config)
index.html    ← React 18 frontend (loaded by browser, no build step)
```

All communication is via `http://localhost:7842/api/*`
