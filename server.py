#!/usr/bin/env python3
"""NovaPulse 2.0 — Python backend. Run: python server.py"""

import os, sys, json, time, platform, subprocess, re, threading, webbrowser, traceback, collections, shutil, signal
from datetime import datetime

# Keep window open on any uncaught error
def _excepthook(exc_type, exc_value, exc_tb):
    print("\n" + "="*52)
    print("  NOVAPULSE ERROR — please report this:")
    print("="*52)
    traceback.print_exception(exc_type, exc_value, exc_tb)
    print("\nPress Enter to close...")
    try: input()
    except: pass
sys.excepthook = _excepthook

from flask import Flask, jsonify, request, send_from_directory, Response

try:
    import psutil
except ImportError:
    print("ERROR: pip install psutil"); sys.exit(1)

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

def try_import_groq():
    """Re-attempt groq import at request time in case of env issues."""
    global GROQ_AVAILABLE
    if not GROQ_AVAILABLE:
        try:
            from groq import Groq as _G
            GROQ_AVAILABLE = True
            return _G
        except ImportError:
            return None
    try:
        from groq import Groq as _G
        return _G
    except ImportError:
        GROQ_AVAILABLE = False
        return None

# ── Vendor JS auto-download ───────────────────────────────────────────────────
VENDOR_SCRIPTS = {
    "react.js":     "https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js",
    "react-dom.js": "https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js",
    "babel.js":     "https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.2/babel.min.js",
}

def ensure_vendor_scripts():
    base = os.path.dirname(os.path.abspath(__file__))
    vendor_dir = os.path.join(base, "vendor")
    os.makedirs(vendor_dir, exist_ok=True)
    missing = [name for name in VENDOR_SCRIPTS if not os.path.exists(os.path.join(vendor_dir, name))]
    if not missing:
        return
    print(f"  Downloading {len(missing)} vendor script(s)...")
    try:
        import urllib.request
        for name in missing:
            url = VENDOR_SCRIPTS[name]
            dest = os.path.join(vendor_dir, name)
            print(f"    {name}...")
            urllib.request.urlretrieve(url, dest)
        print("  Vendor scripts ready.")
    except Exception as e:
        print(f"  WARNING: Could not download vendor scripts: {e}")
        print("  The app requires an internet connection on first run.")
        print("  Or manually place React/ReactDOM/Babel in the ./vendor/ folder.")

ensure_vendor_scripts()

GPU_TIER_KW = {
    5:["4090","4080","7900 xtx","7900 xt","rtx 4080","rtx 4090"],
    4:["4070 ti","4070","3090","3080","6900","6800 xt","rtx 3080","rtx 3090"],
    3:["3070","3060 ti","3060","2080","2070","6600 xt","rx 5700","rtx 3060","rtx 3070"],
    2:["3050","2060","1070","1660","rx 580","rx 570","gtx 1660"],
    1:["1060","1650","1050","rx 480","rx 470","rx 460","gtx 1060"],
    0:["integrated","intel uhd","intel hd","iris xe","vega 8","vega 11"],
}

GAMES = [
    # AAA Open World
    {"name":"Cyberpunk 2077","preset":"1080p Ultra","fps":[4,17,34,56,88,125]},
    {"name":"Cyberpunk 2077","preset":"1440p Ultra","fps":[2,11,23,40,65,98]},
    {"name":"Cyberpunk 2077","preset":"2160p High","fps":[1,5,12,24,42,68]},
    {"name":"Cyberpunk 2077 (RT Overdrive)","preset":"1080p","fps":[1,4,10,22,40,65]},
    {"name":"GTA V","preset":"1080p Ultra","fps":[14,44,80,122,152,185]},
    {"name":"GTA VI (Estimated)","preset":"1080p High","fps":[3,14,30,55,85,120]},
    {"name":"Red Dead Redemption 2","preset":"1080p Ultra","fps":[7,24,48,78,108,138]},
    {"name":"Red Dead Redemption 2","preset":"1440p Ultra","fps":[4,17,34,58,83,113]},
    {"name":"The Witcher 3 (Next-Gen)","preset":"1080p Ultra","fps":[9,32,65,108,138,168]},
    {"name":"The Witcher 3 (Next-Gen RT)","preset":"1080p","fps":[4,14,32,58,88,118]},
    {"name":"Elden Ring","preset":"1080p Max","fps":[18,48,78,98,108,118]},
    {"name":"Elden Ring: Shadow of Erdtree","preset":"1080p High","fps":[16,44,72,94,105,115]},
    {"name":"Starfield","preset":"1080p High","fps":[7,24,48,73,98,128]},
    {"name":"Hogwarts Legacy","preset":"1080p Ultra","fps":[7,21,43,68,98,128]},
    {"name":"Horizon Zero Dawn Remastered","preset":"1080p Ultra","fps":[14,42,82,128,162,198]},
    {"name":"Horizon Forbidden West","preset":"1080p High","fps":[10,32,64,100,132,165]},
    # Action / Adventure
    {"name":"Black Myth: Wukong","preset":"1080p High","fps":[5,18,38,65,98,135]},
    {"name":"Black Myth: Wukong (RT)","preset":"1080p","fps":[2,9,22,42,68,98]},
    {"name":"God of War","preset":"1080p Ultra","fps":[14,44,83,128,158,183]},
    {"name":"God of War Ragnarok","preset":"1080p High","fps":[12,38,75,118,150,178]},
    {"name":"Spider-Man Remastered","preset":"1080p High","fps":[9,28,58,93,128,163]},
    {"name":"Spider-Man 2","preset":"1080p High","fps":[7,24,50,85,118,155]},
    {"name":"Hellblade II","preset":"1080p High","fps":[5,18,38,62,92,122]},
    {"name":"Alan Wake 2","preset":"1080p Ultra","fps":[4,14,28,48,78,113]},
    {"name":"Alan Wake 2 (RT)","preset":"1080p","fps":[1,7,17,34,58,88]},
    {"name":"Indiana Jones","preset":"1080p High","fps":[8,26,52,82,115,148]},
    {"name":"Star Wars Outlaws","preset":"1080p High","fps":[6,20,42,68,98,130]},
    {"name":"Assassin's Creed Shadows","preset":"1080p High","fps":[6,22,44,70,100,132]},
    {"name":"Assassin's Creed Mirage","preset":"1080p Ultra","fps":[14,44,85,130,165,200]},
    {"name":"Assassin's Creed Valhalla","preset":"1080p Ultra","fps":[12,38,75,118,152,185]},
    {"name":"Watch Dogs Legion","preset":"1080p Ultra","fps":[8,26,52,82,115,148]},
    {"name":"Just Cause 4","preset":"1080p Ultra","fps":[14,42,82,128,165,202]},
    {"name":"Shadow of the Tomb Raider","preset":"1080p Ultra","fps":[16,48,92,138,178,218]},
    {"name":"Death Stranding 2","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"Returnal","preset":"1080p High","fps":[10,30,60,95,128,162]},
    # Shooters - Competitive
    {"name":"CS2","preset":"1080p High","fps":[28,88,175,275,345,440]},
    {"name":"Valorant","preset":"1080p High","fps":[42,148,248,345,395,490]},
    {"name":"Apex Legends","preset":"1080p High","fps":[18,58,118,188,238,295]},
    {"name":"Fortnite","preset":"1080p Competitive","fps":[18,58,115,175,235,290]},
    {"name":"Fortnite","preset":"1080p Epic","fps":[9,28,62,108,158,215]},
    {"name":"Overwatch 2","preset":"1080p Epic","fps":[23,73,138,208,278,348]},
    {"name":"Rainbow Six Siege","preset":"1080p Ultra","fps":[38,118,228,338,418,498]},
    {"name":"PUBG","preset":"1080p Ultra","fps":[14,42,82,128,165,205]},
    {"name":"Warframe","preset":"1080p Ultra","fps":[32,88,165,248,315,395]},
    # Shooters - AAA
    {"name":"Call of Duty: Warzone","preset":"1080p High","fps":[13,48,98,158,198,238]},
    {"name":"Call of Duty: Black Ops 6","preset":"1080p High","fps":[15,52,105,165,210,255]},
    {"name":"Battlefield 2042","preset":"1080p Ultra","fps":[14,43,83,128,168,208]},
    {"name":"Battlefield 6","preset":"1080p High","fps":[12,40,80,125,162,198]},
    {"name":"Halo Infinite","preset":"1080p Ultra","fps":[18,58,108,158,198,238]},
    {"name":"Doom Eternal","preset":"1080p Ultra","fps":[23,73,148,248,318,395]},
    {"name":"Doom: The Dark Ages","preset":"1080p High","fps":[18,58,120,200,270,345]},
    {"name":"Wolfenstein: Youngblood","preset":"1080p Ultra","fps":[28,82,158,238,305,378]},
    {"name":"Deathloop","preset":"1080p High","fps":[18,55,108,165,212,258]},
    {"name":"Prey (2017)","preset":"1080p Ultra","fps":[22,68,132,198,255,312]},
    # Open World RPG
    {"name":"Baldur's Gate 3","preset":"1080p Ultra","fps":[14,38,73,108,138,168]},
    {"name":"Diablo IV","preset":"1080p Ultra","fps":[14,43,83,128,168,198]},
    {"name":"Path of Exile 2","preset":"1080p Ultra","fps":[20,55,105,158,205,255]},
    {"name":"Torchlight Infinite","preset":"1080p High","fps":[28,75,145,218,278,342]},
    {"name":"Dragon's Dogma 2","preset":"1080p High","fps":[8,25,50,78,108,138]},
    {"name":"Monster Hunter Wilds","preset":"1080p High","fps":[8,25,50,80,112,145]},
    {"name":"Monster Hunter World","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"Kingdom Come: Deliverance 2","preset":"1080p High","fps":[9,28,56,88,120,152]},
    {"name":"Like a Dragon: Infinite Wealth","preset":"1080p High","fps":[12,35,68,105,138,172]},
    {"name":"Avowed","preset":"1080p High","fps":[10,32,65,100,135,168]},
    {"name":"Frostpunk 2","preset":"1080p Ultra","fps":[12,36,70,108,142,175]},
    {"name":"Stalker 2","preset":"1080p High","fps":[7,22,44,70,98,128]},
    {"name":"Warhammer 40K: Space Marine 2","preset":"1080p High","fps":[12,38,75,118,155,192]},
    # Survival / Crafting
    {"name":"Helldivers 2","preset":"1080p High","fps":[14,38,78,118,158,193]},
    {"name":"Palworld","preset":"1080p High","fps":[18,53,98,143,178,218]},
    {"name":"ARK: Survival Ascended","preset":"1080p Medium","fps":[6,18,38,62,88,118]},
    {"name":"Rust","preset":"1080p High","fps":[12,38,75,118,155,192]},
    {"name":"7 Days to Die","preset":"1080p High","fps":[10,32,65,98,128,162]},
    {"name":"Valheim","preset":"1080p High","fps":[22,62,118,178,228,278]},
    {"name":"Enshrouded","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"Satisfactory","preset":"1080p High","fps":[18,48,88,132,168,205]},
    {"name":"Subnautica: Below Zero","preset":"1080p High","fps":[20,58,112,168,215,262]},
    {"name":"No Man's Sky","preset":"1080p Ultra","fps":[16,46,88,132,170,208]},
    {"name":"Green Hell","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"DayZ","preset":"1080p High","fps":[12,36,70,108,142,175]},
    {"name":"The Forest","preset":"1080p High","fps":[24,68,128,192,248,305]},
    {"name":"Sons of the Forest","preset":"1080p High","fps":[14,42,82,125,162,198]},
    # Horror
    {"name":"Resident Evil 4 Remake","preset":"1080p High","fps":[18,55,105,158,205,248]},
    {"name":"Resident Evil Village","preset":"1080p High","fps":[22,65,122,182,228,278]},
    {"name":"Resident Evil 3 Remake","preset":"1080p High","fps":[24,72,135,202,258,315]},
    {"name":"Silent Hill 2 Remake","preset":"1080p High","fps":[9,28,55,88,120,152]},
    {"name":"The Callisto Protocol","preset":"1080p High","fps":[8,25,50,80,112,145]},
    {"name":"Dead Space Remake","preset":"1080p High","fps":[16,48,92,140,182,222]},
    {"name":"Outlast Trials","preset":"1080p High","fps":[20,58,112,168,215,262]},
    # Strategy / Sim
    {"name":"Microsoft Flight Sim 2024","preset":"1080p High","fps":[4,16,32,52,76,105]},
    {"name":"Cities: Skylines 2","preset":"1080p High","fps":[8,22,42,65,88,115]},
    {"name":"Civilization VI","preset":"1080p High","fps":[28,75,145,218,278,342]},
    {"name":"Total War: Warhammer 3","preset":"1080p Ultra","fps":[12,36,70,108,142,175]},
    {"name":"Age of Empires IV","preset":"1080p High","fps":[22,65,125,188,242,295]},
    {"name":"Company of Heroes 3","preset":"1080p High","fps":[16,46,88,132,170,208]},
    {"name":"Planet Zoo","preset":"1080p High","fps":[12,36,70,108,142,175]},
    {"name":"Euro Truck Simulator 2","preset":"1080p Ultra","fps":[22,65,125,188,242,295]},
    {"name":"Farming Simulator 22","preset":"1080p High","fps":[18,52,98,148,192,235]},
    # Racing
    {"name":"Forza Horizon 5","preset":"1080p Ultra","fps":[14,48,93,138,178,218]},
    {"name":"Forza Motorsport","preset":"1080p Ultra","fps":[12,42,85,130,168,205]},
    {"name":"Need for Speed Unbound","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"Grid Legends","preset":"1080p Ultra","fps":[22,65,125,188,242,295]},
    {"name":"Assetto Corsa Competizione","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"BeamNG.drive","preset":"1080p High","fps":[12,36,70,108,142,175]},
    {"name":"WRC Generations","preset":"1080p High","fps":[20,58,112,168,215,262]},
    # Sports & Fighting
    {"name":"Rocket League","preset":"1080p High","fps":[45,128,235,338,398,478]},
    {"name":"Tekken 8","preset":"1080p High","fps":[22,68,128,192,238,288]},
    {"name":"Street Fighter 6","preset":"1080p High","fps":[25,72,138,205,255,305]},
    {"name":"Mortal Kombat 1","preset":"1080p High","fps":[22,68,128,192,238,288]},
    {"name":"EA Sports FC 25","preset":"1080p High","fps":[28,82,158,238,305,378]},
    {"name":"NBA 2K25","preset":"1080p High","fps":[24,72,138,208,265,325]},
    {"name":"WWE 2K24","preset":"1080p High","fps":[22,65,125,188,242,295]},
    # MOBA / Online
    {"name":"League of Legends","preset":"1080p High","fps":[58,148,248,348,398,498]},
    {"name":"Dota 2","preset":"1080p High","fps":[38,98,198,298,378,448]},
    {"name":"Smite 2","preset":"1080p High","fps":[28,78,148,225,288,352]},
    {"name":"Marvel Rivals","preset":"1080p High","fps":[15,45,90,138,178,220]},
    # Minecraft & Block
    {"name":"Minecraft Vanilla","preset":"1080p","fps":[38,98,178,248,295,345]},
    {"name":"Minecraft (Shaders)","preset":"1080p High","fps":[4,14,34,58,98,148]},
    # Narrative / Linear
    {"name":"The Last of Us Part I","preset":"1080p High","fps":[7,21,43,73,103,133]},
    {"name":"The Last of Us Part II Remastered","preset":"1080p High","fps":[8,23,46,76,108,138]},
    {"name":"A Plague Tale: Requiem","preset":"1080p High","fps":[9,28,55,88,120,152]},
    {"name":"Hogwarts Legacy","preset":"1440p High","fps":[4,14,28,45,68,92]},
    # Misc Popular
    {"name":"Sea of Thieves","preset":"1080p Ultra","fps":[18,58,108,158,198,238]},
    {"name":"Deep Rock Galactic","preset":"1080p Ultra","fps":[32,88,165,248,315,395]},
    {"name":"Risk of Rain 2","preset":"1080p High","fps":[38,105,205,305,385,465]},
    {"name":"Hades II","preset":"1080p High","fps":[42,115,225,335,415,495]},
    {"name":"Hollow Knight: Silksong","preset":"1080p","fps":[55,145,255,355,415,495]},
    {"name":"Ori and the Will of the Wisps","preset":"1080p High","fps":[48,132,248,355,415,495]},
    {"name":"Cyberpunk 2077 (DLSS Quality)","preset":"1440p","fps":[4,18,38,68,102,145]},
    {"name":"Forza Horizon 5","preset":"1440p Ultra","fps":[8,28,58,92,120,152]},
    # Co-op / Multiplayer
    {"name":"It Takes Two","preset":"1080p High","fps":[32,88,165,248,315,395]},
    {"name":"A Way Out","preset":"1080p High","fps":[28,80,155,232,298,368]},
    {"name":"Baldur's Gate 3 Co-op","preset":"1080p Ultra","fps":[12,34,68,100,132,165]},
    {"name":"Phasmophobia","preset":"1080p High","fps":[22,62,120,182,232,285]},
    {"name":"Lethal Company","preset":"1080p High","fps":[35,95,185,275,345,425]},
    {"name":"Content Warning","preset":"1080p High","fps":[38,102,200,298,375,455]},
    {"name":"Among Us","preset":"1080p","fps":[55,145,255,355,425,495]},
    {"name":"Pico Park","preset":"1080p","fps":[55,148,255,355,425,495]},
    {"name":"Unravel Two","preset":"1080p High","fps":[38,105,205,308,385,465]},
    {"name":"Sackboy","preset":"1080p High","fps":[18,52,98,148,192,235]},
    # Roguelike / Indie
    {"name":"Hades II","preset":"1080p High","fps":[42,115,225,335,415,495]},
    {"name":"Dead Cells","preset":"1080p High","fps":[55,148,255,355,425,495]},
    {"name":"Vampire Survivors","preset":"1080p","fps":[58,155,265,368,425,495]},
    {"name":"Balatro","preset":"1080p","fps":[62,165,275,378,428,498]},
    {"name":"Slay the Spire","preset":"1080p","fps":[65,175,285,385,438,498]},
    {"name":"Dead Cells","preset":"1080p High","fps":[52,142,248,348,415,495]},
    {"name":"Noita","preset":"1080p","fps":[30,82,162,245,312,385]},
    {"name":"Enter the Gungeon","preset":"1080p","fps":[62,165,278,382,428,498]},
    {"name":"Cuphead","preset":"1080p","fps":[65,178,292,395,438,498]},
    {"name":"Hollow Knight","preset":"1080p","fps":[55,148,262,368,425,495]},
    {"name":"Celeste","preset":"1080p","fps":[65,175,288,392,438,498]},
    {"name":"Stardew Valley","preset":"1080p","fps":[68,182,298,398,445,498]},
    {"name":"Terraria","preset":"1080p","fps":[72,192,312,412,452,498]},
    # MMO
    {"name":"Final Fantasy XIV","preset":"1080p Ultra","fps":[18,55,108,165,212,258]},
    {"name":"World of Warcraft","preset":"1080p Ultra","fps":[16,50,98,152,198,242]},
    {"name":"New World: Aeternum","preset":"1080p High","fps":[10,32,65,100,135,168]},
    {"name":"Lost Ark","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"Throne and Liberty","preset":"1080p High","fps":[12,38,75,118,155,192]},
    {"name":"Guild Wars 2","preset":"1080p High","fps":[16,48,92,140,182,222]},
    # Simulation / Sandbox
    {"name":"Kerbal Space Program 2","preset":"1080p High","fps":[8,22,42,65,88,115]},
    {"name":"Planet Coaster 2","preset":"1080p High","fps":[10,30,58,90,120,152]},
    {"name":"Two Point Campus","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"Jurassic World Evolution 2","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"Tropico 6","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"Manor Lords","preset":"1080p High","fps":[10,30,60,95,128,162]},
    {"name":"Against the Storm","preset":"1080p High","fps":[22,62,120,182,232,282]},
    {"name":"Workers & Resources: Soviet Republic","preset":"1080p High","fps":[10,32,65,100,135,168]},
    {"name":"Transport Fever 2","preset":"1080p High","fps":[12,38,75,118,155,192]},
    {"name":"Space Engineers","preset":"1080p High","fps":[10,32,65,100,135,168]},
    {"name":"Astroneer","preset":"1080p High","fps":[16,46,88,135,172,210]},
    # Horror / Thriller
    {"name":"Outlast 2","preset":"1080p High","fps":[24,68,128,192,248,305]},
    {"name":"Amnesia: The Bunker","preset":"1080p High","fps":[22,65,125,188,242,295]},
    {"name":"Layers of Fear (2023)","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"The Quarry","preset":"1080p High","fps":[12,38,75,118,155,192]},
    {"name":"Little Nightmares II","preset":"1080p High","fps":[24,72,138,208,265,325]},
    {"name":"Soma","preset":"1080p High","fps":[22,65,125,188,242,295]},
    # Action RPG
    {"name":"Nioh 2","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"Sekiro: Shadows Die Twice","preset":"1080p High","fps":[32,88,165,248,315,395]},
    {"name":"Dark Souls III","preset":"1080p High","fps":[28,78,152,228,292,358]},
    {"name":"Bloodborne (PC via PS Now)","preset":"1080p","fps":[8,22,42,65,88,115]},
    {"name":"Code Vein","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"Wo Long: Fallen Dynasty","preset":"1080p High","fps":[16,46,88,135,172,210]},
    {"name":"Lords of the Fallen (2023)","preset":"1080p High","fps":[10,32,65,100,135,168]},
    {"name":"Lies of P","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"Stellar Blade","preset":"1080p High","fps":[12,38,75,118,155,192]},
    {"name":"Rise of the Ronin","preset":"1080p High","fps":[12,38,75,118,155,192]},
    # Platformer
    {"name":"Astro Bot","preset":"1080p High","fps":[28,78,152,228,292,358]},
    {"name":"Crash Bandicoot 4","preset":"1080p High","fps":[32,88,168,252,318,395]},
    {"name":"Ratchet & Clank: Rift Apart","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"Sonic Frontiers","preset":"1080p High","fps":[22,65,125,188,242,295]},
    {"name":"Psychonauts 2","preset":"1080p High","fps":[18,52,98,148,192,235]},
    # Battle Royale
    {"name":"Warzone 2.0","preset":"1080p High","fps":[14,48,98,158,198,238]},
    {"name":"Hyper Scape","preset":"1080p High","fps":[18,55,108,165,212,258]},
    {"name":"Naraka: Bladepoint","preset":"1080p High","fps":[16,48,92,140,182,222]},
    {"name":"Super People","preset":"1080p High","fps":[18,52,98,148,192,235]},
    # Other popular
    {"name":"Nier: Automata","preset":"1080p High","fps":[22,65,125,188,242,295]},
    {"name":"Nier Replicant","preset":"1080p High","fps":[24,70,135,202,258,315]},
    {"name":"Disco Elysium","preset":"1080p High","fps":[32,88,168,252,318,395]},
    {"name":"Cyberpunk 2077 Phantom Liberty","preset":"1080p High","fps":[7,22,44,72,105,142]},
    {"name":"Persona 5 Royal","preset":"1080p High","fps":[35,95,185,275,345,425]},
    {"name":"Persona 3 Reload","preset":"1080p High","fps":[28,80,155,232,298,368]},
    {"name":"Metaphor: ReFantazio","preset":"1080p High","fps":[26,75,148,222,285,352]},
    {"name":"Scarlet Nexus","preset":"1080p High","fps":[22,65,125,188,242,295]},
    {"name":"Tales of Arise","preset":"1080p High","fps":[20,58,112,168,215,262]},
    {"name":"One Piece Odyssey","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"Dragon Ball Sparking! Zero","preset":"1080p High","fps":[22,65,125,188,242,295]},
    {"name":"Ghostwire: Tokyo","preset":"1080p High","fps":[12,38,75,118,155,192]},
    {"name":"Hi-Fi Rush","preset":"1080p High","fps":[32,88,168,252,318,395]},
    {"name":"Cocoon","preset":"1080p High","fps":[42,115,225,335,415,495]},
    {"name":"Dave the Diver","preset":"1080p High","fps":[38,105,205,308,385,465]},
    {"name":"Dredge","preset":"1080p High","fps":[42,115,225,335,415,495]},
    {"name":"Venba","preset":"1080p","fps":[62,168,278,382,432,498]},
    {"name":"Terra Nil","preset":"1080p High","fps":[35,95,188,282,355,435]},
    {"name":"Raft","preset":"1080p High","fps":[18,52,98,148,192,235]},
    {"name":"Icarus","preset":"1080p High","fps":[10,32,65,100,135,168]},
    {"name":"V Rising","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"Going Medieval","preset":"1080p High","fps":[14,42,82,125,162,198]},
    {"name":"RimWorld","preset":"1080p","fps":[38,105,205,308,385,465]},
    {"name":"Dwarf Fortress (Steam)","preset":"1080p","fps":[35,95,185,275,345,425]},
]

def _run(cmd, t=3):
    try: return subprocess.check_output(cmd,stderr=subprocess.DEVNULL,timeout=t).decode(errors="ignore")
    except: return ""

def get_cpu_name():
    s=platform.system()
    if s=="Windows":
        out=_run(["wmic","cpu","get","name"])
        lines=[l.strip() for l in out.splitlines() if l.strip() and l.strip()!="Name"]
        return lines[0] if lines else platform.processor()
    if s=="Linux":
        try:
            for line in open("/proc/cpuinfo"):
                if "model name" in line: return line.split(":")[1].strip()
        except: pass
    if s=="Darwin": return _run(["sysctl","-n","machdep.cpu.brand_string"]).strip()
    return platform.processor() or "Unknown CPU"

def get_gpu_name():
    s=platform.system()
    if s=="Windows":
        out=_run(["wmic","path","win32_VideoController","get","name"])
        lines=[l.strip() for l in out.splitlines() if l.strip() and l.strip()!="Name"]
        return lines[0] if lines else "Unknown GPU"
    if s=="Linux":
        nv=_run(["nvidia-smi","--query-gpu=name","--format=csv,noheader"]).strip()
        if nv: return nv.split("\n")[0]
        out=_run(["lspci"])
        for line in out.splitlines():
            if "VGA" in line or "3D" in line:
                m=re.search(r'\[(.+?)\]',line)
                if m: return m.group(1)
    if s=="Darwin":
        out=_run(["system_profiler","SPDisplaysDataType"])
        for line in out.splitlines():
            if "Chipset Model" in line: return line.split(":")[-1].strip()
    return "Unknown GPU"

def get_temps_windows():
    temps = {}
    # Method 1: MSAcpi thermal zones (works on most laptops/desktops)
    try:
        out = _run(["powershell","-NoProfile","-Command",
            "Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi | "
            "Select-Object -ExpandProperty CurrentTemperature"],t=5)
        vals = [int(x.strip()) for x in out.strip().splitlines() if x.strip().lstrip('-').isdigit()]
        # Convert from tenths of Kelvin to Celsius
        celsius = [round((v / 10.0) - 273.15, 1) for v in vals if v > 2731]
        if celsius:
            temps["CPU Package"] = celsius[0]
            if len(celsius) > 1:
                temps["Thermal Zone 2"] = celsius[1]
    except: pass
    # Method 2: OpenHardwareMonitor WMI (if user has it running)
    try:
        out = _run(["powershell","-NoProfile","-Command",
            "Get-WmiObject -Namespace root/OpenHardwareMonitor -Class Sensor | "
            "Where-Object {$_.SensorType -eq 'Temperature'} | "
            "Select-Object Name,Value | ForEach-Object {$_.Name+':'+$_.Value}"],t=4)
        for line in out.strip().splitlines():
            if ':' in line:
                name, val = line.rsplit(':', 1)
                try: temps[name.strip()] = round(float(val.strip()), 1)
                except: pass
    except: pass
    return temps

def detect_tier(name):
    n=name.lower()
    for t in sorted(GPU_TIER_KW.keys(),reverse=True):
        for kw in GPU_TIER_KW[t]:
            if kw in n: return t
    return 1

def get_gpu_live():
    # Try nvidia-smi first
    try:
        out=_run(["nvidia-smi","--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total","--format=csv,noheader,nounits"])
        p=out.strip().split(",")
        if len(p)==4: return {"usage":int(p[0].strip()),"temp":int(p[1].strip()),"mem_used":int(p[2].strip()),"mem_total":int(p[3].strip())}
    except: pass
    # Windows: query GPU engine counters (works for Intel UHD, AMD integrated, discrete)
    if platform.system()=="Windows":
        try:
            out=_run(["powershell","-NoProfile","-Command",
                "$s=(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples;"
                "if($s){[math]::Round(($s|Measure-Object CookedValue -Sum).Sum)}else{0}"],t=6)
            val=out.strip().split('\n')[-1].strip()
            if val: return {"usage":min(100,int(float(val))),"temp":0,"mem_used":0,"mem_total":0}
        except: pass
        # Fallback: WMI video controller load
        try:
            out=_run(["wmic","path","Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine",
                      "where","Name like '%engtype_3D%'","get","UtilizationPercentage"],t=4)
            vals=[int(l.strip()) for l in out.splitlines() if l.strip().isdigit()]
            if vals: return {"usage":min(100,sum(vals)),"temp":0,"mem_used":0,"mem_total":0}
        except: pass
    # Linux AMD/Intel
    if platform.system()=="Linux":
        try:
            p_out=open("/sys/class/drm/card0/device/gpu_busy_percent").read().strip()
            return {"usage":int(p_out),"temp":0,"mem_used":0,"mem_total":0}
        except: pass
    return {"usage":0,"temp":0,"mem_used":0,"mem_total":0}

def get_ram_type():
    s=platform.system()
    if s=="Windows":
        out=_run(["wmic","memorychip","get","MemoryType"])
        if "34" in out: return "DDR5"
        if "26" in out: return "DDR4"
        if "24" in out: return "DDR3"
    if s=="Linux":
        out=_run(["sudo","dmidecode","--type","memory"])
        for t in ["DDR5","DDR4","DDR3"]:
            if t in out: return t
    return ""

print("NovaPulse 2.0 — gathering system info...")
_cpu   = get_cpu_name()
_gpu   = get_gpu_name()
_tier  = detect_tier(_gpu)
_cores = psutil.cpu_count(logical=False) or 1
_thrs  = psutil.cpu_count(logical=True)  or 1
_fmax  = 0.0
try:
    f=psutil.cpu_freq()
    if f: _fmax=round((f.max or f.current)/1000,2)
except: pass
_mem   = psutil.virtual_memory()
_ramgb = round(_mem.total/(1024**3),1)
_ramt  = get_ram_type()
_os    = platform.system(); _osr=platform.release()
_boot  = datetime.fromtimestamp(psutil.boot_time())
_disks = []
for p in psutil.disk_partitions(all=False):
    try:
        u=psutil.disk_usage(p.mountpoint)
        _disks.append({"device":p.device,"mountpoint":p.mountpoint,"fstype":p.fstype,
            "total_gb":round(u.total/(1024**3),1),"used_gb":round(u.used/(1024**3),1),
            "free_gb":round(u.free/(1024**3),1),"percent":u.percent})
    except: pass
psutil.cpu_percent(interval=None)
psutil.cpu_percent(percpu=True, interval=None)
_pnet=psutil.net_io_counters(); _pnet_t=time.time()
_up_kbs=0.0; _dn_kbs=0.0

# Background sampler — fast loop for CPU, slow loop for GPU/temps
_cpu_pct   = 0.0
_cpu_cores = []
_gpu_pct   = 0
_cached_temps = {}
_sample_lock = threading.Lock()
_history = collections.deque(maxlen=300)   # 5 min of 1s samples

def _fast_sampler():
    """CPU only — runs every 1s, no subprocess calls."""
    global _cpu_pct, _cpu_cores
    while True:
        try:
            c = psutil.cpu_percent(interval=0.8)
            cores = psutil.cpu_percent(percpu=True, interval=None)
            mem = psutil.virtual_memory()
            with _sample_lock:
                _cpu_pct   = c
                _cpu_cores = cores
                _history.append({
                    "t": int(time.time()),
                    "cpu": round(c, 1),
                    "ram": round(mem.percent, 1),
                    "gpu": _gpu_pct,
                })
        except: pass
        time.sleep(0.2)

def _slow_sampler():
    """GPU + temps — runs every 10s to avoid hammering PowerShell/WMI."""
    global _gpu_pct, _cached_temps
    while True:
        try:
            g = get_gpu_live()
            t = {}
            try:
                ps = psutil.sensors_temperatures()
                if ps:
                    for name,entries in ps.items():
                        if entries: t[name]=round(entries[0].current,1)
            except: pass
            if not t and platform.system()=="Windows":
                t = get_temps_windows()
            if g["temp"]>0: t["GPU"]=g["temp"]
            with _sample_lock:
                _gpu_pct = g["usage"]
                if t: _cached_temps = t
        except: pass
        time.sleep(10)

threading.Thread(target=_fast_sampler, daemon=True).start()
threading.Thread(target=_slow_sampler, daemon=True).start()

print(f"  CPU: {_cpu}")
print(f"  GPU: {_gpu} (Tier {_tier}/5)")
print(f"  RAM: {_ramgb}GB {_ramt}")

BASE=os.path.dirname(os.path.abspath(__file__))
app=Flask(__name__,static_folder=BASE)
app.config["SEND_FILE_MAX_AGE_DEFAULT"]=0

@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"]="*"
    r.headers["Access-Control-Allow-Headers"]="Content-Type"
    r.headers["Access-Control-Allow-Methods"]="GET,POST,OPTIONS"
    return r

@app.route("/")
def index(): return send_from_directory(BASE,"index.html")

@app.route("/vendor/<path:filename>")
def vendor(filename): return send_from_directory(os.path.join(BASE,"vendor"),filename)

@app.route("/api/system")
def api_system():
    now=datetime.now(); up=now-_boot
    h,r=divmod(int(up.total_seconds()),3600); m,sc=divmod(r,60)
    return jsonify({"cpu_name":_cpu,"cpu_cores":_cores,"cpu_threads":_thrs,"cpu_freq_max":_fmax,
        "ram_gb":_ramgb,"ram_type":_ramt,"gpu_name":_gpu,"gpu_tier":_tier,
        "os":f"{_os} {_osr}","hostname":platform.node(),"arch":platform.architecture()[0],
        "disks":_disks,"uptime":f"{h}h {m}m {sc}s","boot_time":_boot.strftime("%Y-%m-%d %H:%M"),
        "groq_available":try_import_groq() is not None})

@app.route("/api/stats")
def api_stats():
    global _pnet,_pnet_t,_up_kbs,_dn_kbs
    with _sample_lock:
        cpu      = _cpu_pct
        cores    = list(_cpu_cores)
        gpu_usage= _gpu_pct
        temps    = dict(_cached_temps)
    mem=psutil.virtual_memory(); swap=psutil.swap_memory()
    gpu=get_gpu_live()  # still call for temp/vram info (nvidia only); usage overridden below
    gpu["usage"] = gpu_usage
    if gpu["temp"]>0: temps["GPU"]=gpu["temp"]
    try:
        net=psutil.net_io_counters(); now_t=time.time()
        dt=max(now_t-_pnet_t,0.01)
        _up_kbs=round((net.bytes_sent-_pnet.bytes_sent)/1024/dt,1)
        _dn_kbs=round((net.bytes_recv-_pnet.bytes_recv)/1024/dt,1)
        _pnet=net; _pnet_t=now_t
        nsent=round(net.bytes_sent/1024/1024,1); nrecv=round(net.bytes_recv/1024/1024,1)
    except: nsent=nrecv=0
    if gpu["temp"]>0: temps["GPU"]=gpu["temp"]
    procs=[]
    try:
        for p in sorted(psutil.process_iter(["pid","name","cpu_percent","memory_percent","status"]),
                        key=lambda x:x.info.get("cpu_percent") or 0,reverse=True)[:10]:
            i=p.info
            procs.append({"pid":i.get("pid"),"name":(i.get("name") or "")[:20],
                "cpu":round(i.get("cpu_percent") or 0,1),"mem":round(i.get("memory_percent") or 0,1),
                "status":(i.get("status") or "")[:10]})
    except: pass
    cur_freq=0
    try:
        f=psutil.cpu_freq()
        if f: cur_freq=round(f.current/1000,2)
    except: pass
    return jsonify({"cpu":round(cpu,1),"cpu_cores":[round(c,1) for c in (cores or [])],"cpu_freq":cur_freq,
        "ram":round(mem.percent,1),"ram_used":round(mem.used/(1024**3),2),"ram_total":round(mem.total/(1024**3),2),
        "swap":round(swap.percent,1),"gpu":gpu["usage"],"gpu_temp":gpu["temp"],
        "gpu_mem_used":gpu["mem_used"],"gpu_mem_total":gpu["mem_total"],
        "net_up":max(_up_kbs,0),"net_down":max(_dn_kbs,0),
        "net_sent_mb":nsent,"net_recv_mb":nrecv,"temps":temps,"processes":procs,"timestamp":time.time()})

@app.route("/api/games")
def api_games(): return jsonify({"games":GAMES,"gpu_tier":_tier})

@app.route("/api/groq",methods=["POST","OPTIONS"])
def api_groq():
    if request.method=="OPTIONS": return jsonify({}),200
    GroqClass = try_import_groq()
    if not GroqClass:
        import sys
        return jsonify({"error":f"groq not found in current Python ({sys.executable}). Run: {sys.executable} -m pip install groq"}),400
    data=request.get_json(force=True)
    key=data.get("api_key","").strip()
    ptype=data.get("type","general")
    if not key: return jsonify({"error":"No API key provided"}),400
    try:
        with _sample_lock:
            cpu_now = _cpu_pct
        mem=psutil.virtual_memory(); gpu=get_gpu_live()
        live=f"CPU:{cpu_now}% RAM:{mem.percent}% GPU:{gpu['usage']}% GPUtemp:{gpu['temp']}C"
    except: live="unavailable"
    ctx = (
        "You are an expert PC performance tuner analyzing a SPECIFIC machine. "
        "Always reference the exact hardware by name in every tip. "
        "Never give generic advice; every recommendation must be tailored to this exact CPU, GPU, and RAM.\n\n"
        "SYSTEM SPECS:\n"
        f"- CPU: {_cpu} ({_cores} physical cores / {_thrs} threads, max {_fmax} GHz)\n"
        f"- RAM: {_ramgb} GB {_ramt}\n"
        f"- GPU: {_gpu} (Tier {_tier}/5)\n"
        f"- OS: {_os} {_osr}\n"
        f"- Live readings: {live}\n\n"
        "Rules:\n"
        f"1. Always name the specific component (e.g. 'your {_cpu}' or 'the {_gpu}') in every tip\n"
        "2. Give exact values, registry paths, commands, or settings - not vague suggestions\n"
        "3. Flag any bottlenecks between these specific components\n"
        "4. If the GPU is integrated or low-tier, acknowledge the limitations honestly"
    )

    prompts = {
        "general": (
            f"Analyze this exact system ({_cpu} + {_gpu} + {_ramgb}GB {_ramt}) and give 8-10 specific optimization tips. "
            f"Identify the biggest bottleneck in this config. Include exact commands or settings paths. "
            f"Call out anything that's misconfigured or underperforming for this hardware combo."
        ),
        "gaming": (
            f"Give 8-10 gaming performance tips specifically for the {_gpu} (Tier {_tier}/5) paired with the {_cpu}. "
            f"State the realistic target FPS and resolution for this GPU tier. "
            f"Cover: the right driver settings for this exact GPU, in-game settings to change, "
            f"whether this CPU bottlenecks this GPU in games, and Windows tweaks that help this combo."
        ),
        "thermal": (
            f"Analyze thermals for the {_cpu} and {_gpu}. "
            f"Current live readings: {live}. "
            f"Give 6-8 thermal recommendations: safe temp thresholds for these specific chips, "
            f"whether the current temps are concerning, cooling upgrades that suit this hardware, "
            f"and whether undervolting is viable and safe for this CPU/GPU."
        ),
        "memory": (
            f"Give 6-8 RAM and storage tips for {_ramgb}GB {_ramt} paired with the {_cpu}. "
            f"Does this CPU support XMP/EXPO? What is the ideal RAM speed for it? "
            f"Is {_ramgb}GB enough for this GPU tier ({_gpu})? "
            f"Cover pagefile config, virtual memory, and any RAM-specific bottlenecks with this CPU."
        ),
        "windows": (
            f"Give 8-10 Windows {_osr} tweaks specifically beneficial for the {_cpu} and {_gpu}. "
            f"Include: the correct power plan for this CPU, any driver-level settings for the {_gpu}, "
            f"startup/services to disable, scheduler tweaks for {_cores}-core/{_thrs}-thread CPUs, "
            f"and registry edits with exact paths."
        ),
        "power": (
            f"Give 6-8 power and efficiency tips for the {_cpu} ({_cores}C/{_thrs}T) and {_gpu}. "
            f"What power plan maximizes performance for this CPU? "
            f"Is the {_gpu} TDP a concern? Cover CPU TDP limits, GPU power targets, "
            f"and whether eco-mode or undervolting makes sense for this specific hardware."
        ),
    }
    def stream():
        try:
            client=GroqClass(api_key=key)
            comp=client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role":"system","content":ctx},{"role":"user","content":prompts.get(ptype,prompts["general"])}],
                temperature=0.7,max_tokens=1500,stream=True)
            for chunk in comp:
                delta=chunk.choices[0].delta.content or ""
                if delta:
                    yield f"data: {json.dumps({'text':delta})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error':str(e)})}\n\n"
            yield "data: [DONE]\n\n"
    resp = Response(stream(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp

CFG=os.path.join(BASE,".novapulse_config.json")

@app.route("/api/groq/chat",methods=["POST","OPTIONS"])
def api_groq_chat():
    if request.method=="OPTIONS": return jsonify({}),200
    GroqClass = try_import_groq()
    if not GroqClass:
        import sys as _sys
        return jsonify({"error":f"groq not installed. Run: {_sys.executable} -m pip install groq"}),400
    data=request.get_json(force=True)
    key=data.get("api_key","").strip()
    question=data.get("question","").strip()
    if not key: return jsonify({"error":"No API key provided"}),400
    if not question: return jsonify({"error":"No question provided"}),400
    guard = (
        "You are a PC hardware and software expert assistant embedded in NovaPulse, a PC monitoring app. "
        "You ONLY answer questions about: PC hardware, software, Windows, gaming, performance, benchmarks, "
        "drivers, overclocking, cooling, storage, networking, or anything directly related to computers. "
        "If the user asks about ANYTHING unrelated to PCs or computers, politely refuse and say you can only help with PC topics. "
        f"The user's system: {_cpu} / {_gpu} / {_ramgb}GB {_ramt} / {_os} {_osr}. "
        "Always reference their specific hardware when relevant."
    )
    def stream():
        try:
            client=GroqClass(api_key=key)
            comp=client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role":"system","content":guard},{"role":"user","content":question}],
                temperature=0.6,max_tokens=1000,stream=True)
            for chunk in comp:
                delta=chunk.choices[0].delta.content or ""
                if delta: yield f"data: {json.dumps({'text':delta})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error':str(e)})}\n\n"
            yield "data: [DONE]\n\n"
    resp=Response(stream(),mimetype="text/event-stream")
    resp.headers["Cache-Control"]="no-cache"
    resp.headers["X-Accel-Buffering"]="no"
    resp.headers["Connection"]="keep-alive"
    return resp

@app.route("/api/benchmark")
def api_benchmark():
    # Synthetic scores based on hardware specs
    cpu_score = min(100, int(_cores * 12 + _thrs * 5 + _fmax * 8))
    gpu_score = [5,20,40,60,80,100][min(_tier,5)]
    ram_score = min(100, int(_ramgb * 3.2))
    scores = {
        "cpu": min(100,cpu_score),
        "gpu": gpu_score,
        "ram": ram_score,
        "overall": min(100, int((cpu_score*0.35 + gpu_score*0.45 + ram_score*0.20))),
    }
    bottleneck = "CPU" if cpu_score < gpu_score - 25 else "GPU" if gpu_score < cpu_score - 25 else "Balanced"
    scores["bottleneck"] = bottleneck
    return jsonify(scores)
@app.route("/api/config",methods=["GET"])
def get_cfg():
    try:
        with open(CFG) as f: return jsonify(json.load(f))
    except: return jsonify({})
@app.route("/api/config",methods=["POST"])
def save_cfg():
    try:
        # Merge with existing config so partial updates don't wipe other keys
        existing = {}
        try:
            with open(CFG) as f: existing = json.load(f)
        except: pass
        existing.update(request.get_json(force=True) or {})
        with open(CFG,"w") as f: json.dump(existing, f, indent=2)
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

# ─── HISTORY ────────────────────────────────────────────────────────────────
@app.route("/api/history")
def api_history():
    with _sample_lock:
        data = list(_history)
    return jsonify(data)

# ─── PROCESS MANAGER ────────────────────────────────────────────────────────
@app.route("/api/processes")
def api_processes():
    procs = []
    try:
        attrs = ["pid","name","cpu_percent","memory_percent","status","username","create_time","num_threads"]
        for p in psutil.process_iter(attrs):
            try:
                i = p.info
                # try to get exe and affinity
                exe = ""
                try: exe = p.exe() or ""
                except: pass
                affinity = []
                try: affinity = list(p.cpu_affinity()) if hasattr(p,'cpu_affinity') else []
                except: pass
                nice = None
                try: nice = p.nice()
                except: pass
                procs.append({
                    "pid": i.get("pid"),
                    "name": (i.get("name") or "")[:32],
                    "cpu": round(i.get("cpu_percent") or 0, 1),
                    "mem": round(i.get("memory_percent") or 0, 1),
                    "status": (i.get("status") or "")[:12],
                    "user": (i.get("username") or "")[:20],
                    "threads": i.get("num_threads") or 0,
                    "nice": nice,
                    "affinity_count": len(affinity),
                    "exe": exe[:60],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    except: pass
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    return jsonify(procs[:60])

@app.route("/api/processes/kill", methods=["POST","OPTIONS"])
def api_kill():
    if request.method=="OPTIONS": return "",204
    data = request.get_json(force=True) or {}
    pid = data.get("pid")
    if not pid: return jsonify({"error":"No PID"}), 400
    try:
        p = psutil.Process(int(pid))
        p.kill()
        return jsonify({"ok": True, "name": p.name() if p.is_running() else "?"})
    except psutil.NoSuchProcess: return jsonify({"error": "Process not found"}), 404
    except psutil.AccessDenied: return jsonify({"error": "Access denied — try running as admin"}), 403
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/processes/priority", methods=["POST","OPTIONS"])
def api_priority():
    if request.method=="OPTIONS": return "",204
    data = request.get_json(force=True) or {}
    pid = data.get("pid"); level = data.get("level","normal")
    if not pid: return jsonify({"error":"No PID"}), 400
    pmap = {
        "realtime": psutil.REALTIME_PRIORITY_CLASS if platform.system()=="Windows" else -20,
        "high":     psutil.HIGH_PRIORITY_CLASS     if platform.system()=="Windows" else -10,
        "abovenormal": psutil.ABOVE_NORMAL_PRIORITY_CLASS if platform.system()=="Windows" else -5,
        "normal":   psutil.NORMAL_PRIORITY_CLASS   if platform.system()=="Windows" else 0,
        "belownormal": psutil.BELOW_NORMAL_PRIORITY_CLASS if platform.system()=="Windows" else 10,
        "idle":     psutil.IDLE_PRIORITY_CLASS     if platform.system()=="Windows" else 19,
    }
    if level not in pmap: return jsonify({"error":"Unknown priority"}), 400
    try:
        p = psutil.Process(int(pid))
        p.nice(pmap[level])
        return jsonify({"ok": True})
    except psutil.AccessDenied: return jsonify({"error":"Access denied"}), 403
    except Exception as e: return jsonify({"error": str(e)}), 500

# ─── SYSTEM CLEANER ─────────────────────────────────────────────────────────
def _scan_dir(path):
    total = 0; count = 0
    try:
        for root,dirs,files in os.walk(path):
            for f in files:
                try:
                    fp = os.path.join(root,f)
                    total += os.path.getsize(fp); count += 1
                except: pass
    except: pass
    return count, total

@app.route("/api/cleaner/scan")
def api_cleaner_scan():
    results = []
    if platform.system() == "Windows":
        targets = [
            ("Windows Temp",  os.environ.get("WINDIR","C:\\Windows") + "\\Temp"),
            ("User Temp",     os.environ.get("TEMP", os.path.expanduser("~\\AppData\\Local\\Temp"))),
            ("Prefetch",      os.environ.get("WINDIR","C:\\Windows") + "\\Prefetch"),
            ("Recent Files",  os.path.expanduser("~\\AppData\\Roaming\\Microsoft\\Windows\\Recent")),
            ("Recycle Bin",   "C:\\$Recycle.Bin"),
            ("Crash Dumps",   os.path.expanduser("~\\AppData\\Local\\CrashDumps")),
            ("Chrome Cache",  os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache")),
            ("Edge Cache",    os.path.expanduser("~\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Cache")),
            ("Firefox Cache", os.path.expanduser("~\\AppData\\Local\\Mozilla\\Firefox\\Profiles")),
            ("Steam Shader Cache", os.path.expanduser("~\\AppData\\Local\\Steam\\htmlcache")),
            ("Discord Cache", os.path.expanduser("~\\AppData\\Roaming\\discord\\Cache")),
            ("Thumbnail Cache", os.path.expanduser("~\\AppData\\Local\\Microsoft\\Windows\\Explorer")),
        ]
    else:
        targets = [
            ("Temp /tmp",   "/tmp"),
            ("User Cache",  os.path.expanduser("~/.cache")),
        ]
    for name, path in targets:
        if os.path.exists(path):
            count, size = _scan_dir(path)
            results.append({"name": name, "path": path,
                "count": count, "size_mb": round(size / 1024 / 1024, 2)})
        else:
            results.append({"name": name, "path": path, "count": 0, "size_mb": 0})

    # Startup items (Windows)
    startup_items = []
    if platform.system() == "Windows":
        try:
            import winreg
            for hive, key_path in [
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
            ]:
                try:
                    k = winreg.OpenKey(hive, key_path)
                    i = 0
                    while True:
                        try:
                            name_v, val, _ = winreg.EnumValue(k, i)
                            startup_items.append({"name": name_v, "path": val[:80],
                                "hive": "HKCU" if hive==winreg.HKEY_CURRENT_USER else "HKLM"})
                            i += 1
                        except OSError: break
                    winreg.CloseKey(k)
                except: pass
        except: pass
    return jsonify({"dirs": results, "startup": startup_items})

@app.route("/api/cleaner/clean", methods=["POST","OPTIONS"])
def api_cleaner_clean():
    if request.method=="OPTIONS": return "",204
    data = request.get_json(force=True) or {}
    paths = data.get("paths", [])
    result = {"freed_mb": 0, "errors": [], "done": False}
    result_lock = threading.Lock()

    safe_prefixes = [
        os.environ.get("TEMP",""), os.environ.get("TMP",""),
        os.path.expanduser("~\\AppData\\Local\\Temp"),
        os.path.expanduser("~\\AppData\\Local\\Google\\Chrome"),
        os.path.expanduser("~\\AppData\\Local\\Microsoft\\Edge"),
        os.path.expanduser("~\\AppData\\Roaming\\discord\\Cache"),
        os.path.expanduser("~\\AppData\\Local\\Steam\\htmlcache"),
        os.environ.get("WINDIR","C:\\Windows") + "\\Temp",
        os.path.expanduser("~\\AppData\\Roaming\\Microsoft\\Windows\\Recent"),
        "/tmp", os.path.expanduser("~/.cache"),
    ]

    freed = 0; errors = []
    for path in paths:
        is_safe = any(path.lower().startswith(p.lower()) for p in safe_prefixes if p)
        if not is_safe:
            errors.append(f"Skipped (unsafe): {os.path.basename(path)}")
            continue
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    try:
                        fp = os.path.join(root, f)
                        freed += os.path.getsize(fp)
                        os.remove(fp)
                    except: pass
                for d in dirs:
                    try: shutil.rmtree(os.path.join(root,d), ignore_errors=True)
                    except: pass
        except Exception as e:
            errors.append(f"{os.path.basename(path)}: {str(e)}")
    return jsonify({"freed_mb": round(freed/1024/1024,2), "errors": errors})

@app.route("/api/cleaner/ram", methods=["POST","OPTIONS"])
def api_cleaner_ram():
    if request.method=="OPTIONS": return "",204
    freed_mb = 0
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.psapi.EmptyWorkingSet(-1)  # flush all processes
            before = psutil.virtual_memory().used
            time.sleep(0.5)
            after = psutil.virtual_memory().used
            freed_mb = round(max(0, before - after) / 1024 / 1024, 1)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "freed_mb": freed_mb,
        "ram_free_gb": round(psutil.virtual_memory().available/1024**3, 2)})

# ─── GAME LAUNCHER ──────────────────────────────────────────────────────────
def _find_steam_games():
    games = []
    steam_path = ""
    if platform.system() == "Windows":
        try:
            import winreg
            for key_path in [r"SOFTWARE\Valve\Steam", r"SOFTWARE\WOW6432Node\Valve\Steam"]:
                try:
                    k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    steam_path, _ = winreg.QueryValueEx(k, "InstallPath")
                    winreg.CloseKey(k)
                    break
                except: pass
        except: pass
        if not steam_path:
            for p in [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]:
                if os.path.isdir(p): steam_path = p; break
    else:
        for p in [os.path.expanduser("~/.steam/steam"), "/usr/games/steam", os.path.expanduser("~/.local/share/Steam")]:
            if os.path.isdir(p): steam_path = p; break

    if not steam_path: return games

    # Find all library folders
    lib_folders = [os.path.join(steam_path, "steamapps")]
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for m in re.finditer(r'"path"\s+"([^"]+)"', content):
            p = m.group(1).replace("\\\\","\\")
            if os.path.isdir(p):
                lib_folders.append(os.path.join(p, "steamapps"))
    except: pass

    for lib in lib_folders:
        if not os.path.isdir(lib): continue
        try:
            for fn in os.listdir(lib):
                if fn.startswith("appmanifest_") and fn.endswith(".acf"):
                    acf_path = os.path.join(lib, fn)
                    try:
                        with open(acf_path, encoding="utf-8", errors="ignore") as f:
                            acf = f.read()
                        app_id   = re.search(r'"appid"\s+"(\d+)"', acf)
                        name_m   = re.search(r'"name"\s+"([^"]+)"', acf)
                        size_m   = re.search(r'"SizeOnDisk"\s+"(\d+)"', acf)
                        state_m  = re.search(r'"StateFlags"\s+"(\d+)"', acf)
                        if app_id and name_m:
                            state = int(state_m.group(1)) if state_m else 0
                            installed = (state & 4) != 0
                            if installed:
                                size_gb = round(int(size_m.group(1)) / 1024**3, 1) if size_m else 0
                                games.append({
                                    "id": app_id.group(1),
                                    "name": name_m.group(1),
                                    "source": "Steam",
                                    "size_gb": size_gb,
                                    "launch": f"steam://rungameid/{app_id.group(1)}",
                                    "img": f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id.group(1)}/header.jpg",
                                })
                    except: pass
        except: pass
    return games

def _find_epic_games():
    games = []
    manifests_path = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
    if not os.path.isdir(manifests_path): return games
    try:
        for fn in os.listdir(manifests_path):
            if fn.endswith(".item"):
                try:
                    with open(os.path.join(manifests_path, fn), encoding="utf-8") as f:
                        d = json.load(f)
                    name  = d.get("DisplayName","")
                    app_name = d.get("AppName","")
                    install  = d.get("InstallLocation","")
                    if name and app_name and os.path.isdir(install):
                        games.append({
                            "id": app_name,
                            "name": name,
                            "source": "Epic",
                            "size_gb": 0,
                            "launch": f"com.epicgames.launcher://apps/{app_name}?action=launch",
                            "img": "",
                        })
                except: pass
    except: pass
    return games

_installed_games_cache = None
_installed_games_ts = 0

@app.route("/api/launcher/scan")
def api_launcher_scan():
    global _installed_games_cache, _installed_games_ts
    now = time.time()
    if _installed_games_cache is not None and now - _installed_games_ts < 60:
        return jsonify(_installed_games_cache)
    games = _find_steam_games() + _find_epic_games()
    games.sort(key=lambda g: g["name"].lower())
    _installed_games_cache = games
    _installed_games_ts = now
    return jsonify(games)

@app.route("/api/launcher/launch", methods=["POST","OPTIONS"])
def api_launcher_launch():
    if request.method=="OPTIONS": return "",204
    data = request.get_json(force=True) or {}
    uri = data.get("launch","")
    if not uri: return jsonify({"error":"No launch URI"}), 400
    try:
        webbrowser.open(uri)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── MULTI-MONITOR ──────────────────────────────────────────────────────────
@app.route("/api/monitors")
def api_monitors():
    monitors = []
    if platform.system() == "Windows":
        # Try screeninfo first
        try:
            from screeninfo import get_monitors
            for i, m in enumerate(get_monitors()):
                monitors.append({
                    "index": i, "name": m.name or f"Display {i+1}",
                    "width": m.width, "height": m.height,
                    "x": m.x, "y": m.y,
                    "is_primary": m.is_primary,
                    "width_mm": m.width_mm, "height_mm": m.height_mm,
                    "refresh_hz": None,
                })
        except:
            pass
        # Also get refresh rate via PowerShell
        try:
            out = subprocess.check_output(
                ["powershell","-NoProfile","-Command",
                 "Get-WmiObject -Namespace root/wmi -Class WmiMonitorVideoTimings | "
                 "Select-Object InstanceName,HorizontalActivePixels,VerticalActivePixels,"
                 "HSync,VSync | ConvertTo-Json -Compress"],
                timeout=6, stderr=subprocess.DEVNULL
            ).decode(errors="ignore").strip()
            if out:
                arr = json.loads(out) if out.startswith('[') else [json.loads(out)]
                for i,m in enumerate(arr):
                    vsync = m.get("VSync",0)
                    hz = round(10000000/vsync) if vsync else None
                    if i < len(monitors):
                        monitors[i]["refresh_hz"] = hz
                    else:
                        monitors.append({
                            "index": i, "name": f"Display {i+1}",
                            "width": m.get("HorizontalActivePixels"),
                            "height": m.get("VerticalActivePixels"),
                            "x": 0, "y": 0, "is_primary": i==0,
                            "width_mm": None, "height_mm": None,
                            "refresh_hz": hz,
                        })
        except: pass
        # Fallback: Win32_VideoController
        if not monitors:
            try:
                out = subprocess.check_output(
                    ["powershell","-NoProfile","-Command",
                     "Get-WmiObject Win32_VideoController | "
                     "Select-Object Name,CurrentHorizontalResolution,CurrentVerticalResolution,"
                     "CurrentRefreshRate,AdapterRAM,DriverVersion | ConvertTo-Json -Compress"],
                    timeout=6, stderr=subprocess.DEVNULL
                ).decode(errors="ignore").strip()
                if out:
                    arr = json.loads(out) if out.startswith('[') else [json.loads(out)]
                    for i,m in enumerate(arr):
                        monitors.append({
                            "index": i, "name": m.get("Name","GPU " + str(i+1)),
                            "width": m.get("CurrentHorizontalResolution"),
                            "height": m.get("CurrentVerticalResolution"),
                            "x": 0, "y": 0, "is_primary": i==0,
                            "width_mm": None, "height_mm": None,
                            "refresh_hz": m.get("CurrentRefreshRate"),
                            "vram_mb": round(int(m.get("AdapterRAM") or 0)/1024**2),
                            "driver": m.get("DriverVersion",""),
                        })
            except: pass
    else:
        try:
            from screeninfo import get_monitors
            for i, m in enumerate(get_monitors()):
                monitors.append({"index":i,"name":m.name or f"Display {i+1}",
                    "width":m.width,"height":m.height,"x":m.x,"y":m.y,
                    "is_primary":m.is_primary,"refresh_hz":None})
        except:
            monitors.append({"index":0,"name":"Primary Display","width":None,"height":None,
                "x":0,"y":0,"is_primary":True,"refresh_hz":None})
    return jsonify(monitors)


# ─── AUDIO ──────────────────────────────────────────────────────────────────
# Auto-install pycaw + comtypes if missing (Windows audio API)
def _ensure_pycaw():
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        import comtypes
        return True
    except ImportError:
        print("  Installing pycaw for audio control...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pycaw", "comtypes", "pywin32", "-q"],
                check=True, timeout=30)
            return True
        except Exception as e:
            print(f"  pycaw install failed: {e}")
            return False

PYCAW_OK = False
if platform.system() == "Windows":
    PYCAW_OK = _ensure_pycaw()

def _get_volume_obj():
    """Return (volume_interface, None) or (None, error_string).
    Handles both old pycaw (returns raw IMMDevice) and new pycaw (returns AudioDevice wrapper).
    """
    try:
        import ctypes
        ctypes.windll.ole32.CoInitialize(None)
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER

        speakers = AudioUtilities.GetSpeakers()

        # New pycaw wraps the device — unwrap it
        raw = getattr(speakers, '_dev', speakers)

        interface = raw.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        return vol, None
    except Exception as e:
        return None, str(e)

def _get_audio_devices():
    """Get playback device list via WMI (display only)."""
    devices = []
    try:
        import subprocess
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-WmiObject Win32_SoundDevice | Select-Object Name,Manufacturer,Status | ConvertTo-Json -Compress"],
            stderr=subprocess.DEVNULL, timeout=5
        ).decode(errors="ignore").strip()
        arr = json.loads(raw)
        if isinstance(arr, dict): arr = [arr]
        for i, d in enumerate(arr):
            devices.append({
                "id": str(i),
                "name": (d.get("Name") or f"Device {i+1}")[:48],
                "manufacturer": (d.get("Manufacturer") or "")[:32],
                "status": d.get("Status") or "OK",
                "is_default": i == 0,
                "type": "playback",
            })
    except: pass
    return devices

_audio_cache = {}
_audio_ts = 0.0

@app.route("/api/audio")
def api_audio():
    global _audio_cache, _audio_ts
    now = time.time()
    if now - _audio_ts > 3:
        result = {"devices": [], "master_volume": None, "master_muted": False, "pycaw": PYCAW_OK}
        if platform.system() == "Windows":
            result["devices"] = _get_audio_devices()
            if PYCAW_OK:
                vol_obj, err = _get_volume_obj()
                if vol_obj is not None:
                    try:
                        result["master_volume"] = round(vol_obj.GetMasterVolumeLevelScalar() * 100)
                        result["master_muted"] = bool(vol_obj.GetMute())
                    except: pass
        _audio_cache = result
        _audio_ts = now
    return jsonify(_audio_cache)

@app.route("/api/audio/volume", methods=["POST", "OPTIONS"])
def api_audio_volume():
    if request.method == "OPTIONS": return "", 204
    if platform.system() != "Windows":
        return jsonify({"ok": False, "error": "Windows only"})
    if not PYCAW_OK:
        return jsonify({"ok": False, "error": "pycaw not available — restart server to auto-install"})
    data = request.get_json(force=True) or {}
    vol = max(0, min(100, int(data.get("volume", 50))))
    vol_obj, err = _get_volume_obj()
    if vol_obj is None:
        return jsonify({"ok": False, "error": err or "Could not access audio device"})
    try:
        vol_obj.SetMasterVolumeLevelScalar(vol / 100.0, None)
        global _audio_ts; _audio_ts = 0  # bust cache
        return jsonify({"ok": True, "volume": vol})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/audio/mute", methods=["POST", "OPTIONS"])
def api_audio_mute():
    if request.method == "OPTIONS": return "", 204
    if platform.system() != "Windows":
        return jsonify({"ok": False, "error": "Windows only"})
    if not PYCAW_OK:
        return jsonify({"ok": False, "error": "pycaw not available — restart server to auto-install"})
    data = request.get_json(force=True) or {}
    mute = bool(data.get("mute", True))
    vol_obj, err = _get_volume_obj()
    if vol_obj is None:
        return jsonify({"ok": False, "error": err or "Could not access audio device"})
    try:
        vol_obj.SetMute(mute, None)
        global _audio_ts; _audio_ts = 0
        return jsonify({"ok": True, "muted": mute})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    try:
        PORT=7842
        print(f"\n{'='*52}")
        print(f"  NovaPulse 2.0  →  http://localhost:{PORT}")
        print(f"{'='*52}\n")
        def _open():
            time.sleep(1.4); webbrowser.open(f"http://localhost:{PORT}")
        threading.Thread(target=_open,daemon=True).start()
        app.run(host="0.0.0.0",port=PORT,debug=False,threaded=True)
    except Exception as e:
        import traceback
        print("\n" + "="*52)
        print("  STARTUP ERROR:")
        print("="*52)
        traceback.print_exc()
        print("\nPress Enter to close...")
        input()
