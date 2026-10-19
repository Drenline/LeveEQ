"""LeveEQ - equalizador paramétrico leve para fone e microfone.

Usa o Equalizer APO como motor de áudio (processa o som no Windows com custo
mínimo de CPU). Este app só edita os filtros e grava um arquivo de configuração
que o Equalizer APO recarrega na hora.

Mesmo modelo de filtros do equalizador do SteelSeries Sonar: 10 filtros por
dispositivo, cada um com tipo, frequência, ganho e Q. Projeto independente,
sem ligação com a SteelSeries.

Código aberto sob a licença MIT (veja o arquivo LICENSE).
"""
import json
import math
import os
import queue
import shutil
import sqlite3
import sys
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

try:
    import winreg
except ImportError:  # permite abrir a interface fora do Windows
    winreg = None

try:  # ícone na bandeja (perto do relógio); sem ele o app funciona só com a janela
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None

APP_NAME = "LeveEQ"
STATE_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
STATE_FILE = os.path.join(STATE_DIR, "estado.json")
PRESETS_FILE = os.path.join(STATE_DIR, "presets.json")
APO_INCLUDE_NAME = "leveeq.txt"
SONAR_DB = r"C:\ProgramData\SteelSeries\GG\apps\sonar\db\database.db"

FS = 48000.0
# Limites compatíveis com os presets do SteelSeries Sonar (faixas vistas nos presets do GG)
F_MIN, F_MAX = 20.0, 20000.0
G_MIN, G_MAX = -12.0, 12.0
Q_MIN, Q_MAX = 0.5, 10.0
N_FILTERS = 10

# ---------------------------------------------------------------- idiomas
# Para adicionar um idioma: copie o bloco "en", traduza os textos e adicione o
# nome dele em LANG_NAMES. Textos que faltarem aparecem em inglês.
LANG_NAMES = {"pt": "Português", "en": "English"}
STRINGS = {
    "pt": {
        "tab_out": "🎧  Fone", "tab_mic": "🎙  Microfone",
        "power": "EQ ligado (geral)", "language": "🌐",
        "device": "Dispositivo", "active": "Ativo", "preset": "Preset",
        "save": "Salvar", "delete": "Excluir", "import_sonar": "Importar do Sonar",
        "graph_hint": "Arraste os pontos • roda do mouse = Q • duplo clique = liga/desliga o filtro",
        "filter_on": "Filtro ligado", "type": "Tipo", "freq": "Frequência (Hz)", "gain": "Ganho (dB)", "q": "Q",
        "reset_filter": "Zerar filtro", "reset_all": "Zerar tudo",
        "preamp": "Ganho geral", "bass": "Graves", "clarity": "Voz (clareza)", "treble": "Agudos",
        "headroom": "Evitar distorção (reduz o volume)",
        "mic_hint": "Dica: um passa-alta em ~80 Hz no filtro 1 corta ruído de mesa e respiração.",
        "disconnected": "(dispositivo desconectado)",
        "confirm_reset_all": "Zerar todos os filtros deste dispositivo?",
        "preset_name": "Nome do preset:", "preset_saved": "Preset “{name}” salvo",
        "confirm_delete": "Excluir o preset “{name}”?",
        "sonar_read_error": "Não consegui ler o banco do Sonar:\n{err}",
        "sonar_none": "Nenhuma configuração do Sonar encontrada para este canal.",
        "apo_missing": "Equalizer APO não encontrado", "applied": "● aplicado", "write_error": "erro ao gravar: {err}",
        "warn_no_apo": "O Equalizer APO não está instalado.\n\n"
                       "Ele é o motor de áudio leve que este app controla (gratuito e open source).\n"
                       "Instale em https://sourceforge.net/projects/equalizerapo/ e, no Configurator, "
                       "marque o seu fone e o seu microfone. Depois reinicie o PC e abra o LeveEQ de novo.\n\n"
                       "Você já pode montar e salvar presets enquanto isso.",
        "tray_open": "Abrir LeveEQ", "tray_power": "EQ ligado", "tray_quit": "Sair (desliga o EQ)",
        "tray_on": "EQ ligado", "tray_off": "EQ desligado",
        "tray_hint": "O LeveEQ continua ligado aqui na bandeja. "
                     "Clique com o botão direito no ícone para desligar ou sair.",
        "picker_title": "Importar do SteelSeries Sonar", "picker_choose": "Escolha uma configuração do Sonar:",
        "search": "🔍 Buscar", "only_mine": "Só as minhas (esconder presets de fábrica)",
        "import": "Importar", "cancel": "Cancelar", "imported": "Importado: {name}",
        "already_open": "O LeveEQ já está aberto.\n\nProcure o ícone laranja perto do relógio "
                        "(talvez dentro da setinha ^) e clique nele.",
        "vad_1": "Jogo", "vad_2": "Chat (saída)", "vad_3": "Microfone", "vad_4": "Mídia", "vad_5": "Aux",
        "ft_peakingEQ": "Pico (Bell)", "ft_lowShelving": "Shelf grave", "ft_highShelving": "Shelf agudo",
        "ft_lowPass": "Passa-baixa", "ft_highPass": "Passa-alta", "ft_notchFilter": "Notch",
        "ft_bandPassPeak0dB": "Passa-banda (0 dB)", "ft_bandPassPeakQ": "Passa-banda (pico Q)",
        "ft_allPass": "Passa-tudo",
    },
    "en": {
        "tab_out": "🎧  Headphones", "tab_mic": "🎙  Microphone",
        "power": "EQ on (global)", "language": "🌐",
        "device": "Device", "active": "Active", "preset": "Preset",
        "save": "Save", "delete": "Delete", "import_sonar": "Import from Sonar",
        "graph_hint": "Drag the points • mouse wheel = Q • double-click = turn the filter on/off",
        "filter_on": "Filter on", "type": "Type", "freq": "Frequency (Hz)", "gain": "Gain (dB)", "q": "Q",
        "reset_filter": "Reset filter", "reset_all": "Reset all",
        "preamp": "Overall gain", "bass": "Bass", "clarity": "Voice (clarity)", "treble": "Treble",
        "headroom": "Avoid distortion (lowers volume)",
        "mic_hint": "Tip: a high-pass at ~80 Hz on filter 1 cuts desk rumble and breathing noise.",
        "disconnected": "(device disconnected)",
        "confirm_reset_all": "Reset all filters for this device?",
        "preset_name": "Preset name:", "preset_saved": "Preset “{name}” saved",
        "confirm_delete": "Delete preset “{name}”?",
        "sonar_read_error": "Could not read the Sonar database:\n{err}",
        "sonar_none": "No Sonar settings found for this channel.",
        "apo_missing": "Equalizer APO not found", "applied": "● applied", "write_error": "could not save: {err}",
        "warn_no_apo": "Equalizer APO is not installed.\n\n"
                       "It is the lightweight audio engine this app controls (free and open source).\n"
                       "Install it from https://sourceforge.net/projects/equalizerapo/ and, in the Configurator, "
                       "select your headphones and microphone. Then restart your PC and open LeveEQ again.\n\n"
                       "You can already build and save presets in the meantime.",
        "tray_open": "Open LeveEQ", "tray_power": "EQ on", "tray_quit": "Quit (turns EQ off)",
        "tray_on": "EQ on", "tray_off": "EQ off",
        "tray_hint": "LeveEQ is still running here in the tray. "
                     "Right-click the icon to turn it off or quit.",
        "picker_title": "Import from SteelSeries Sonar", "picker_choose": "Choose a Sonar setting:",
        "search": "🔍 Search", "only_mine": "Mine only (hide factory presets)",
        "import": "Import", "cancel": "Cancel", "imported": "Imported: {name}",
        "already_open": "LeveEQ is already open.\n\nLook for the orange icon next to the clock "
                        "(maybe inside the ^ arrow) and click it.",
        "vad_1": "Game", "vad_2": "Chat (output)", "vad_3": "Microphone", "vad_4": "Media", "vad_5": "Aux",
        "ft_peakingEQ": "Peak (Bell)", "ft_lowShelving": "Low shelf", "ft_highShelving": "High shelf",
        "ft_lowPass": "Low-pass", "ft_highPass": "High-pass", "ft_notchFilter": "Notch",
        "ft_bandPassPeak0dB": "Band-pass (0 dB)", "ft_bandPassPeakQ": "Band-pass (Q peak)",
        "ft_allPass": "All-pass",
    },
}
LANG = "en"


def system_lang():
    """Idioma inicial: o do Windows, se tivermos tradução; senão, inglês."""
    try:
        import ctypes
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x16: "pt"}.get(primary, "en")
    except (AttributeError, OSError):
        return "en"


def t(key, **kw):
    s = STRINGS.get(LANG, {}).get(key) or STRINGS["en"][key]
    return s.format(**kw) if kw else s


# tipo interno (mesmos nomes do FilterType do Sonar) -> usa ganho?
FILTER_TYPES = {
    "peakingEQ": True,
    "lowShelving": True,
    "highShelving": True,
    "lowPass": False,
    "highPass": False,
    "notchFilter": False,
    "bandPassPeak0dB": False,
    "bandPassPeakQ": False,
    "allPass": False,
}


def type_label(tp):
    return t("ft_" + tp)


def type_from_label(label, default):
    return next((tp for tp in FILTER_TYPES if type_label(tp) == label), default)
# "bandPass" era o nome usado pelas versões antigas do LeveEQ
SONAR_TYPE_ALIASES = {"bandPass": "bandPassPeak0dB", "byPass": None}

# Graves / Voz / Agudos (como Bass Boost, Voice Clarity e Treble Boost do Sonar): picos com largura em oitavas.
# Frequência central e largura aproximadas; o valor salvo nos presets do Sonar é o ganho em dB (±12).
TONE_BANDS = {
    "bass": (80.0, 0.707),
    "clarity": (2000.0, 0.5),
    "treble": (8000.0, 0.707),
}


def bw_to_q(f0, bw_oct, fs=FS):
    """Largura em oitavas -> Q, pela fórmula digital do RBJ Audio EQ Cookbook."""
    w0 = 2 * math.pi * f0 / fs
    return 1 / (2 * math.sinh(math.log(2) / 2 * bw_oct * w0 / math.sin(w0)))

DEFAULT_FREQS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

COLORS = {
    "bg": "#15171c", "panel": "#1d2027", "panel2": "#252932", "fg": "#e6e8ee",
    "muted": "#8a90a0", "grid": "#2b303a", "grid0": "#444b58", "accent": "#ff6b1a",
    "curve": "#ff8a3d", "fill": "#3a2618", "off": "#555b68",
}
POINT_COLORS = ["#ff6b1a", "#ffb020", "#e8e04a", "#7ad35a", "#3cc7a0",
                "#38b6ff", "#5b7cff", "#a46bff", "#ff5bc8", "#ff5b6b"]


# ---------------------------------------------------------------- modelo

def default_filter(i):
    return {"enabled": True, "type": "peakingEQ", "frequency": float(DEFAULT_FREQS[i]),
            "gain": 0.0, "qFactor": 0.7071}


def default_channel(kind):
    ch = {"enabled": True, "kind": kind, "device": "", "preset": "", "preamp": 0.0,
          "headroom": kind == "out", "filters": [default_filter(i) for i in range(N_FILTERS)]}
    if kind == "out":
        ch.update(bass=0.0, clarity=0.0, treble=0.0)
    return ch


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def biquad_coeffs(f):
    """Coeficientes do RBJ Audio EQ Cookbook (Robert Bristow-Johnson), com Q direto.
    São as mesmas fórmulas que o Equalizer APO usa, então o gráfico mostra o que você ouve."""
    t = f["type"]
    f0 = clamp(f["frequency"], F_MIN, F_MAX)
    q = clamp(f["qFactor"], Q_MIN, Q_MAX)
    g = f["gain"]
    A = 10 ** (g / 40)
    w0 = 2 * math.pi * f0 / FS
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2 * q)
    if t == "peakingEQ":
        b = (1 + alpha * A, -2 * cw, 1 - alpha * A)
        a = (1 + alpha / A, -2 * cw, 1 - alpha / A)
    elif t in ("lowShelving", "highShelving"):
        sA = 2 * math.sqrt(A) * alpha
        if t == "lowShelving":
            b = (A * ((A + 1) - (A - 1) * cw + sA), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sA))
            a = ((A + 1) + (A - 1) * cw + sA, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sA)
        else:
            b = (A * ((A + 1) + (A - 1) * cw + sA), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sA))
            a = ((A + 1) - (A - 1) * cw + sA, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sA)
    elif t == "lowPass":
        b = ((1 - cw) / 2, 1 - cw, (1 - cw) / 2)
        a = (1 + alpha, -2 * cw, 1 - alpha)
    elif t == "highPass":
        b = ((1 + cw) / 2, -(1 + cw), (1 + cw) / 2)
        a = (1 + alpha, -2 * cw, 1 - alpha)
    elif t == "notchFilter":
        b = (1, -2 * cw, 1)
        a = (1 + alpha, -2 * cw, 1 - alpha)
    elif t == "bandPassPeak0dB":
        b = (alpha, 0, -alpha)
        a = (1 + alpha, -2 * cw, 1 - alpha)
    elif t == "bandPassPeakQ":
        b = (sw / 2, 0, -sw / 2)
        a = (1 + alpha, -2 * cw, 1 - alpha)
    elif t == "allPass":
        b = (1 - alpha, -2 * cw, 1 + alpha)
        a = (1 + alpha, -2 * cw, 1 - alpha)
    else:
        return None
    return b, a


def magnitude_db(coeffs, freq):
    b, a = coeffs
    w = 2 * math.pi * freq / FS
    z1 = complex(math.cos(-w), math.sin(-w))
    z2 = z1 * z1
    h = (b[0] + b[1] * z1 + b[2] * z2) / (a[0] + a[1] * z1 + a[2] * z2)
    return 20 * math.log10(max(abs(h), 1e-9))


def effective_filters(ch, kind):
    """Filtros na ordem do Sonar: EQ paramétrico, depois graves, voz e agudos."""
    out = [f for f in ch["filters"] if f["enabled"]]
    if kind == "out":
        for key, (f0, bw) in TONE_BANDS.items():
            g = ch.get(key, 0.0)
            if abs(g) > 1e-6:
                out.append({"enabled": True, "type": "peakingEQ", "frequency": f0, "gain": g,
                            "qFactor": bw_to_q(f0, bw), "bw_oct": bw})
    return out


def total_response_db(filters, freqs):
    coeffs = [c for c in (biquad_coeffs(f) for f in filters) if c]
    return [sum(magnitude_db(c, fr) for c in coeffs) for fr in freqs]


def peak_boost_db(filters):
    """Pico real da curva somada (não só o maior ganho de um filtro isolado):
    filtros vizinhos somam e o pico pode passar do ganho de cada um."""
    freqs = [F_MIN * (F_MAX / F_MIN) ** (i / 599) for i in range(600)]
    return max([0.0] + total_response_db(filters, freqs))


# ---------------------------------------------------------------- Equalizer APO

def apo_config_dir():
    if winreg is None:
        return None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EqualizerAPO", 0, winreg.KEY_READ | view) as k:
                path = winreg.QueryValueEx(k, "ConfigPath")[0]
                if os.path.isdir(path):
                    return path
        except OSError:
            pass
    p = r"C:\Program Files\EqualizerAPO\config"
    return p if os.path.isdir(p) else None


def list_devices(flow):
    """Lista dispositivos de áudio ativos. flow = 'Render' (saída) ou 'Capture' (entrada)."""
    devices = []
    if winreg is None:
        return devices
    base = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\{flow}"
    name_key = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
    iface_key = "{b3f8fa53-0004-438e-9003-51a46e139bfc},6"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except OSError:
        return devices
    with root:
        i = 0
        while True:
            try:
                guid = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, guid) as dk:
                    state = winreg.QueryValueEx(dk, "DeviceState")[0]
                if state != 1:
                    continue
                with winreg.OpenKey(root, guid + r"\Properties") as pk:
                    name = winreg.QueryValueEx(pk, name_key)[0]
                    try:
                        iface = winreg.QueryValueEx(pk, iface_key)[0]
                    except OSError:
                        iface = ""
                devices.append({"guid": guid, "label": f"{name} ({iface})" if iface else name})
            except OSError:
                continue
    return sorted(devices, key=lambda d: d["label"].lower())


def num(x):
    """Número com precisão total (antes era arredondado: Q 0.7071 virava 0.707)."""
    return f"{x:.9g}"


def apo_filter_line(f):
    """Comandos do Equalizer APO (conferidos com o Benchmark.exe que vem com ele).
    LSC/HSC = shelf RBJ com Fc no meio da rampa (o LS/HS sem C desloca a frequência)."""
    fc = f"Fc {num(f['frequency'])} Hz"
    q = f"BW Oct {num(f['bw_oct'])}" if "bw_oct" in f else f"Q {num(f['qFactor'])}"
    g = f"Gain {num(f['gain'])} dB"
    t = f["type"]
    return {
        "peakingEQ": f"ON PK {fc} {g} {q}",
        "lowShelving": f"ON LSC {fc} {g} {q}",
        "highShelving": f"ON HSC {fc} {g} {q}",
        "lowPass": f"ON LPQ {fc} {q}",
        "highPass": f"ON HPQ {fc} {q}",
        "notchFilter": f"ON NO {fc} {q}",
        "bandPassPeak0dB": f"ON BP {fc} {q}",
        # o APO só tem o passa-banda de 0 dB; o de "pico Q" é o mesmo filtro x Q,
        # então a diferença (20·log10 Q) entra no Preamp — exato, pois tudo está em série
        "bandPassPeakQ": f"ON BP {fc} {q}",
        "allPass": f"ON AP {fc} {q}",
    }[t]


def build_apo_config(state, names=None):
    """Um bloco por dispositivo configurado: cada fone/mic tem o próprio EQ, todos ativos juntos."""
    names = names or {}
    lines = ["# Gerado pelo LeveEQ - edições manuais serão sobrescritas", ""]
    for guid, ch in sorted(state["profiles"].items(), key=lambda kv: (kv[1]["kind"] != "out", kv[0])):
        kind = ch["kind"]
        title = "SAIDA" if kind == "out" else "ENTRADA"
        lines.append(f"# ---- {title}: {names.get(guid, 'dispositivo desconectado')}")
        lines.append(f"Device: {guid}")
        if not (state["power"] and ch["enabled"]):
            lines.append("# desativado")
            lines.append("")
            continue
        filters = effective_filters(ch, kind)
        pre = ch["preamp"] + sum(20 * math.log10(f["qFactor"]) for f in filters if f["type"] == "bandPassPeakQ")
        # O Sonar tem um limitador depois do ganho geral; o Equalizer APO não tem.
        # Sem ele, reduzimos o volume pelo pico real da curva para o som não distorcer.
        if ch.get("headroom", True):
            pre -= peak_boost_db(filters) + max(0.0, ch["preamp"])
        lines.append(f"Preamp: {num(pre)} dB")
        for n, f in enumerate(filters, 1):
            lines.append(f"Filter {n}: {apo_filter_line(f)}")
        lines.append("")
    lines.append("Device: all")
    return "\n".join(lines) + "\n"


def write_apo_file(path, text):
    """Grava por cima do arquivo existente. Não dá pra trocar o arquivo por rename
    (os.replace) porque o processo de áudio do Windows o mantém aberto e o rename
    falha com 'Acesso negado'."""
    import time
    for attempt in range(5):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)
    stale = path + ".tmp"  # sobra de versões antigas do LeveEQ
    if os.path.exists(stale):
        try:
            os.remove(stale)
        except OSError:
            pass


def ensure_apo_include(cfg_dir):
    main = os.path.join(cfg_dir, "config.txt")
    inc = f"Include: {APO_INCLUDE_NAME}"
    try:
        content = open(main, encoding="utf-8-sig").read() if os.path.exists(main) else ""
    except OSError:
        content = ""
    if content.strip().lower() == inc.lower():
        return
    # guarda o original e assume o config.txt: o padrão do APO inclui um exemplo
    # (Preamp -6 dB + example.txt) que mexeria no som de todos os dispositivos
    if content and not os.path.exists(main + ".antes-leveeq"):
        shutil.copy2(main, main + ".antes-leveeq")
    with open(main, "w", encoding="utf-8") as fh:
        fh.write(inc + "\n")


# ---------------------------------------------------------------- Sonar import



def read_sonar_configs():
    if not os.path.exists(SONAR_DB):
        return []
    tmp = os.path.join(tempfile.gettempdir(), "leveeq_sonar.db")
    shutil.copy2(SONAR_DB, tmp)  # cópia: o GG pode estar com o arquivo aberto
    con = sqlite3.connect(tmp)
    try:
        rows = con.execute("select name, vad, data, is_preset from configs order by is_preset, vad, name").fetchall()
    finally:
        con.close()
    out = []
    for name, vad, data, is_preset in rows:
        try:
            d = json.loads(data)
        except ValueError:
            continue
        if "parametricEQ" in d:
            out.append({"name": name, "vad": vad, "data": d, "is_preset": bool(is_preset)})
    return out


def sonar_to_channel(d, kind):
    ch = default_channel(kind)
    peq = d.get("parametricEQ", {})
    for i in range(N_FILTERS):
        sf = peq.get(f"filter{i + 1}")
        if not sf:
            continue
        t = SONAR_TYPE_ALIASES.get(sf.get("type"), sf.get("type"))
        ch["filters"][i] = {
            "enabled": bool(sf.get("enabled", True)) and t in FILTER_TYPES,
            "type": t if t in FILTER_TYPES else "peakingEQ",
            "frequency": clamp(float(sf.get("frequency", DEFAULT_FREQS[i])), F_MIN, F_MAX),
            "gain": clamp(float(sf.get("gain", 0)), G_MIN, G_MAX),
            "qFactor": clamp(float(sf.get("qFactor", 0.7071)), Q_MIN, Q_MAX),
        }
    if not peq.get("enabled", True):
        for f in ch["filters"]:
            f["enabled"] = False
    if kind == "out":
        for key, sonar_key in (("bass", "bassBoostState"), ("clarity", "voiceClarityState"),
                               ("treble", "trebleBoostState")):
            st = d.get(sonar_key, {})
            ch[key] = clamp(float(st.get("value", 0)), G_MIN, G_MAX) if st.get("enabled") else 0.0
    ch["preamp"] = clamp(float(d.get("generalGain", 0)), G_MIN, G_MAX)
    return ch


# ---------------------------------------------------------------- persistência

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------- interface

class EQGraph(tk.Canvas):
    PAD_L, PAD_R, PAD_T, PAD_B = 44, 14, 14, 26

    def __init__(self, master, app, **kw):
        super().__init__(master, bg=COLORS["panel"], highlightthickness=0, height=300, **kw)
        self.app = app
        self.drag = None
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<MouseWheel>", self.on_wheel)
        self.bind("<Double-Button-1>", self.on_double)

    # coordenadas
    def fx(self, f):
        w = self.winfo_width() - self.PAD_L - self.PAD_R
        return self.PAD_L + w * (math.log10(f / F_MIN) / math.log10(F_MAX / F_MIN))

    def xf(self, x):
        w = self.winfo_width() - self.PAD_L - self.PAD_R
        return F_MIN * (F_MAX / F_MIN) ** clamp((x - self.PAD_L) / w, 0, 1)

    def gy(self, g):
        h = self.winfo_height() - self.PAD_T - self.PAD_B
        return self.PAD_T + h * (G_MAX - g) / (G_MAX - G_MIN)

    def yg(self, y):
        h = self.winfo_height() - self.PAD_T - self.PAD_B
        return clamp(G_MAX - (y - self.PAD_T) / h * (G_MAX - G_MIN), G_MIN, G_MAX)

    def point_pos(self, f):
        g = f["gain"] if FILTER_TYPES[f["type"]] else 0.0
        return self.fx(f["frequency"]), self.gy(g)

    def redraw(self):
        self.delete("all")
        W, H = self.winfo_width(), self.winfo_height()
        if W < 50:
            return
        ch, kind = self.app.channel(), self.app.kind
        # grade
        for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
            x = self.fx(f)
            self.create_line(x, self.PAD_T, x, H - self.PAD_B, fill=COLORS["grid"])
            self.create_text(x, H - self.PAD_B + 12, text=f"{f // 1000}k" if f >= 1000 else str(f),
                             fill=COLORS["muted"], font=("Segoe UI", 8))
        for g in range(int(G_MIN), int(G_MAX) + 1, 3):
            y = self.gy(g)
            self.create_line(self.PAD_L, y, W - self.PAD_R, y, fill=COLORS["grid0"] if g == 0 else COLORS["grid"])
            self.create_text(self.PAD_L - 8, y, text=f"{g:+d}" if g else "0", anchor="e",
                             fill=COLORS["muted"], font=("Segoe UI", 8))
        # curva total
        active = self.app.cfg["power"] and ch["enabled"]
        coeffs = [c for c in (biquad_coeffs(f) for f in effective_filters(ch, kind)) if c]
        pts = []
        n = max(200, W - self.PAD_L - self.PAD_R)
        for i in range(n + 1):
            x = self.PAD_L + i * (W - self.PAD_L - self.PAD_R) / n
            f = self.xf(x)
            g = sum(magnitude_db(c, f) for c in coeffs) if active else 0.0
            pts.append((x, self.gy(clamp(g, G_MIN - 6, G_MAX + 6))))
        y0 = self.gy(0)
        poly = [(self.PAD_L, y0)] + pts + [(W - self.PAD_R, y0)]
        if active:
            self.create_polygon(*[c for p in poly for c in p], fill=COLORS["fill"], outline="")
        self.create_line(*[c for p in pts for c in p], fill=COLORS["curve"] if active else COLORS["off"],
                         width=2.5, smooth=True)
        # pontos
        sel = self.app.selected
        for i, f in enumerate(ch["filters"]):
            x, y = self.point_pos(f)
            color = POINT_COLORS[i] if f["enabled"] and active else COLORS["off"]
            r = 10 if i == sel else 8
            if i == sel:
                self.create_oval(x - r - 4, y - r - 4, x + r + 4, y + r + 4, outline=color, width=2)
            self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=COLORS["bg"], width=2)
            self.create_text(x, y, text=str(i + 1), fill="#111", font=("Segoe UI", 8, "bold"))

    def hit(self, x, y):
        best, bd = None, 16 ** 2
        for i, f in enumerate(self.app.channel()["filters"]):
            px, py = self.point_pos(f)
            d = (px - x) ** 2 + (py - y) ** 2
            if d < bd:
                best, bd = i, d
        return best

    def on_press(self, e):
        i = self.hit(e.x, e.y)
        if i is not None:
            self.drag = i
            self.app.select(i)

    def on_drag(self, e):
        if self.drag is None:
            return
        f = self.app.channel()["filters"][self.drag]
        f["frequency"] = round(self.xf(e.x), 1)
        if FILTER_TYPES[f["type"]]:
            f["gain"] = round(self.yg(e.y), 1)
        f["enabled"] = True
        self.app.changed(live=True)

    def on_release(self, e):
        if self.drag is not None:
            self.drag = None
            self.app.changed()

    def on_wheel(self, e):
        i = self.hit(e.x, e.y)
        if i is None:
            i = self.app.selected
        f = self.app.channel()["filters"][i]
        factor = 1.12 if e.delta > 0 else 1 / 1.12
        f["qFactor"] = round(clamp(f["qFactor"] * factor, Q_MIN, Q_MAX), 3)
        self.app.select(i)
        self.app.changed()

    def on_double(self, e):
        i = self.hit(e.x, e.y)
        if i is not None:
            f = self.app.channel()["filters"][i]
            f["enabled"] = not f["enabled"]
            self.app.changed()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leveeq.ico")
        if os.path.exists(ico):
            try:
                self.iconbitmap(default=ico)
            except tk.TclError:
                pass
        self.geometry("1040x720")
        self.minsize(820, 600)
        self.configure(bg=COLORS["bg"])
        self.cfg = self.load_state()
        global LANG
        LANG = self.cfg["lang"]
        self.scratch = {"out": default_channel("out"), "mic": default_channel("mic")}
        self.presets = load_json(PRESETS_FILE, {"out": {}, "mic": {}})
        self.kind = "out"
        self.selected = 0
        self.apo_dir = apo_config_dir()
        self._write_job = None
        self._loading = False
        self.devices = {"out": list_devices("Render"), "mic": list_devices("Capture")}
        self.setup_style()
        self.build()
        self.refresh_all()
        self.tray = None
        self._tray_q = queue.Queue()
        self._tray_hint_shown = False
        self.setup_tray()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray if self.tray else self.quit_app)
        # "Sair" grava o EQ desligado; ao abrir de novo, reaplica o estado salvo
        self._write_job = self.after(100, self.write_config)
        if not self.apo_dir:
            self.after(300, self.warn_no_apo)

    # ---- estado
    def load_state(self):
        s = load_json(STATE_FILE, {})
        lang = s.get("lang") if s.get("lang") in LANG_NAMES else system_lang()
        st = {"power": s.get("power", True), "auto_headroom": s.get("auto_headroom", True),
              "lang": lang, "sel": {"out": "", "mic": ""}, "profiles": {}}
        st["sel"].update(s.get("sel", {}))
        for guid, data in s.get("profiles", {}).items():
            st["profiles"][guid] = self.normalize(data, data.get("kind", "out"), guid)
        # formato antigo: um único canal "out" e um "mic"
        for k in ("out", "mic"):
            old = s.get(k)
            if isinstance(old, dict) and old.get("device"):
                st["profiles"].setdefault(old["device"], self.normalize(old, k, old["device"]))
                st["sel"][k] = st["sel"][k] or old["device"]
        for k in ("out", "mic"):
            if st["sel"][k] and st["sel"][k] not in st["profiles"]:
                st["sel"][k] = ""
        return st

    @staticmethod
    def normalize(data, kind, guid=""):
        ch = default_channel(kind)
        ch.update({kk: vv for kk, vv in data.items() if kk in ch})
        if len(ch["filters"]) != N_FILTERS:
            ch["filters"] = [default_filter(i) for i in range(N_FILTERS)]
        for f in ch["filters"]:  # presets salvos por versões antigas
            f["type"] = SONAR_TYPE_ALIASES.get(f["type"], f["type"]) or "peakingEQ"
            if f["type"] not in FILTER_TYPES:
                f["type"] = "peakingEQ"
            f["qFactor"] = clamp(f["qFactor"], Q_MIN, Q_MAX)
        ch["kind"], ch["device"] = kind, guid
        return ch

    def channel(self):
        """EQ do dispositivo escolhido na aba atual (ou um rascunho, se nenhum foi escolhido)."""
        guid = self.cfg["sel"][self.kind]
        return self.cfg["profiles"][guid] if guid else self.scratch[self.kind]

    def set_channel(self, ch):
        guid = self.cfg["sel"][self.kind]
        ch = self.normalize(ch, self.kind, guid)
        if guid:
            self.cfg["profiles"][guid] = ch
        else:
            self.scratch[self.kind] = ch

    def device_names(self):
        return {d["guid"]: d["label"] for k in ("out", "mic") for d in self.devices[k]}

    # ---- estilo
    def setup_style(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        c = COLORS
        st.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["panel2"],
                     bordercolor=c["grid"], lightcolor=c["panel"], darkcolor=c["panel"], font=("Segoe UI", 10))
        st.configure("TFrame", background=c["bg"])
        st.configure("Panel.TFrame", background=c["panel"])
        st.configure("TLabel", background=c["bg"], foreground=c["fg"])
        st.configure("Panel.TLabel", background=c["panel"])
        st.configure("Muted.TLabel", background=c["panel"], foreground=c["muted"], font=("Segoe UI", 9))
        st.configure("Title.TLabel", font=("Segoe UI Semibold", 15))
        st.configure("TButton", background=c["panel2"], foreground=c["fg"], padding=(10, 5), borderwidth=0)
        st.map("TButton", background=[("active", c["grid0"])])
        st.configure("Accent.TButton", background=c["accent"], foreground="#111")
        st.map("Accent.TButton", background=[("active", "#ff8a3d")])
        st.configure("Tab.TButton", background=c["panel"], foreground=c["muted"], padding=(18, 8), font=("Segoe UI Semibold", 11))
        st.configure("TabOn.TButton", background=c["accent"], foreground="#111", padding=(18, 8), font=("Segoe UI Semibold", 11))
        st.map("Tab.TButton", background=[("active", c["panel2"])])
        st.configure("TCheckbutton", background=c["panel"], foreground=c["fg"])
        st.map("TCheckbutton", background=[("active", c["panel"])])
        st.configure("Bar.TCheckbutton", background=c["bg"])
        st.map("Bar.TCheckbutton", background=[("active", c["bg"])])
        st.configure("TCombobox", arrowcolor=c["fg"], foreground=c["fg"])
        st.map("TCombobox", fieldbackground=[("readonly", c["panel2"])], foreground=[("readonly", c["fg"])])
        self.option_add("*TCombobox*Listbox.background", c["panel2"])
        self.option_add("*TCombobox*Listbox.foreground", c["fg"])
        st.configure("Horizontal.TScale", background=c["panel"], troughcolor=c["panel2"])
        st.configure("TSpinbox", arrowcolor=c["fg"], foreground=c["fg"])

    # ---- layout
    def build(self):
        top = ttk.Frame(self, padding=(14, 10))
        top.pack(fill="x")
        ttk.Label(top, text="LeveEQ", style="Title.TLabel").pack(side="left")
        self.tab_btns = {}
        for k, label in (("out", t("tab_out")), ("mic", t("tab_mic"))):
            b = ttk.Button(top, text=label, style="Tab.TButton", command=lambda k=k: self.switch(k))
            b.pack(side="left", padx=(12 if k == "out" else 4, 0))
            self.tab_btns[k] = b
        # seletor de idioma (canto direito)
        self.lang_var = tk.StringVar(value=LANG_NAMES[LANG])
        lang_cb = ttk.Combobox(top, textvariable=self.lang_var, state="readonly", width=10,
                               values=list(LANG_NAMES.values()))
        lang_cb.pack(side="right")
        lang_cb.bind("<<ComboboxSelected>>", self.on_language)
        ttk.Label(top, text=t("language")).pack(side="right", padx=(14, 4))
        self.power_var = tk.BooleanVar(value=self.cfg["power"])
        ttk.Checkbutton(top, text=t("power"), variable=self.power_var, style="Bar.TCheckbutton",
                        command=self.on_power).pack(side="right")
        self.status = ttk.Label(top, text="", foreground=COLORS["muted"])
        self.status.pack(side="right", padx=14)

        # linha: dispositivo + presets
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        bar.pack(fill="x", padx=14)
        ttk.Label(bar, text=t("device"), style="Panel.TLabel").pack(side="left")
        self.dev_var = tk.StringVar()
        self.dev_combo = ttk.Combobox(bar, textvariable=self.dev_var, state="readonly", width=50)
        self.dev_combo.pack(side="left", padx=(8, 4))
        self.dev_combo.bind("<<ComboboxSelected>>", self.on_device)
        ttk.Button(bar, text="↻", width=3, command=self.reload_devices).pack(side="left")
        self.ch_enabled = tk.BooleanVar()
        ttk.Checkbutton(bar, text=t("active"), variable=self.ch_enabled, command=self.on_ch_enabled).pack(side="left", padx=12)

        ttk.Button(bar, text=t("import_sonar"), command=self.import_sonar).pack(side="right")
        ttk.Button(bar, text=t("delete"), command=self.delete_preset).pack(side="right", padx=4)
        ttk.Button(bar, text=t("save"), style="Accent.TButton", command=self.save_preset).pack(side="right", padx=4)
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(bar, textvariable=self.preset_var, state="readonly", width=22)
        self.preset_combo.pack(side="right", padx=4)
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset)
        ttk.Label(bar, text=t("preset"), style="Panel.TLabel").pack(side="right", padx=(12, 0))

        # gráfico
        gwrap = ttk.Frame(self, style="Panel.TFrame", padding=6)
        gwrap.pack(fill="both", expand=True, padx=14, pady=(8, 0))
        self.graph = EQGraph(gwrap, self)
        self.graph.pack(fill="both", expand=True)
        ttk.Label(gwrap, text=t("graph_hint"),
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

        # editor do filtro selecionado + extras
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=14, pady=8)

        ed = ttk.Frame(bottom, style="Panel.TFrame", padding=12)
        ed.pack(side="left", fill="both", expand=True)
        row0 = ttk.Frame(ed, style="Panel.TFrame")
        row0.pack(fill="x")
        self.sel_btns = []
        for i in range(N_FILTERS):
            b = tk.Label(row0, text=str(i + 1), width=3, bg=COLORS["panel2"], fg=COLORS["fg"],
                         font=("Segoe UI Semibold", 10), cursor="hand2", pady=3)
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, i=i: self.select(i))
            self.sel_btns.append(b)
        self.f_enabled = tk.BooleanVar()
        ttk.Checkbutton(row0, text=t("filter_on"), variable=self.f_enabled, command=self.on_field).pack(side="left", padx=12)

        row1 = ttk.Frame(ed, style="Panel.TFrame")
        row1.pack(fill="x", pady=(10, 0))
        ttk.Label(row1, text=t("type"), style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.f_type = tk.StringVar()
        cb = ttk.Combobox(row1, textvariable=self.f_type, state="readonly", width=19,
                          values=[type_label(tp) for tp in FILTER_TYPES])
        cb.grid(row=1, column=0, sticky="w", padx=(0, 14))
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_field())
        self.f_freq = tk.DoubleVar()
        self.f_gain = tk.DoubleVar()
        self.f_q = tk.DoubleVar()
        self.spin_gain = None
        for col, (label, var, lo, hi, inc, fmt) in enumerate((
                (t("freq"), self.f_freq, F_MIN, F_MAX, 1, "%.1f"),
                (t("gain"), self.f_gain, G_MIN, G_MAX, 0.1, "%.1f"),
                (t("q"), self.f_q, Q_MIN, Q_MAX, 0.01, "%.4f")), start=1):
            ttk.Label(row1, text=label, style="Panel.TLabel").grid(row=0, column=col, sticky="w")
            sp = ttk.Spinbox(row1, textvariable=var, from_=lo, to=hi, increment=inc, format=fmt, width=10,
                             command=self.on_field)
            sp.grid(row=1, column=col, sticky="w", padx=(0, 14))
            sp.bind("<Return>", lambda e: self.on_field())
            sp.bind("<FocusOut>", lambda e: self.on_field())
            if var is self.f_gain:
                self.spin_gain = sp
        ttk.Button(row1, text=t("reset_filter"), command=self.reset_filter).grid(row=1, column=4, padx=(6, 4))
        ttk.Button(row1, text=t("reset_all"), command=self.reset_all).grid(row=1, column=5)

        # painel lateral: ganho geral + Bass Boost / Voice Clarity / Treble Boost do Sonar
        side = ttk.Frame(bottom, style="Panel.TFrame", padding=12)
        side.pack(side="left", fill="y", padx=(8, 0))
        self.sliders = {}
        for key, label, lo, hi in (("preamp", t("preamp"), G_MIN, G_MAX), ("bass", t("bass"), G_MIN, G_MAX),
                                   ("clarity", t("clarity"), G_MIN, G_MAX), ("treble", t("treble"), G_MIN, G_MAX)):
            fr = ttk.Frame(side, style="Panel.TFrame")
            lab = ttk.Label(fr, text=label, style="Panel.TLabel", width=14)
            lab.pack(side="left")
            var = tk.DoubleVar()
            sc = ttk.Scale(fr, from_=lo, to=hi, variable=var, length=130,
                           command=lambda v, k=key: self.on_slider(k))
            sc.pack(side="left")
            val = ttk.Label(fr, text="", style="Muted.TLabel", width=9)
            val.pack(side="left")
            sc.bind("<ButtonRelease-1>", lambda e: self.changed())
            sc.bind("<Double-Button-1>", lambda e, k=key: self.reset_slider(k))
            self.sliders[key] = (fr, var, val)
        self.headroom_var = tk.BooleanVar()
        self.headroom_chk = ttk.Checkbutton(side, text=t("headroom"),
                                            variable=self.headroom_var, command=self.on_headroom)
        self.mic_hint = ttk.Label(side, style="Muted.TLabel", wraplength=300, justify="left",
                                  text=t("mic_hint"))

    # ---- ações
    def switch(self, kind):
        self.kind = kind
        self.selected = min(self.selected, N_FILTERS - 1)
        self.refresh_all()

    def select(self, i):
        self.selected = i
        self.refresh_editor()
        self.graph.redraw()

    def refresh_all(self):
        for k, b in self.tab_btns.items():
            b.configure(style="TabOn.TButton" if k == self.kind else "Tab.TButton")
        # "✓ EQ" marca os dispositivos que já têm EQ ligado
        profiles = self.cfg["profiles"]
        self.dev_choices = []
        for d in self.devices[self.kind]:
            p = profiles.get(d["guid"])
            tag = f"   ✓ EQ: {p['preset']}" if p and p["enabled"] and p.get("preset") else ("   ✓ EQ" if p and p["enabled"] else "")
            self.dev_choices.append((d["label"] + tag, d["guid"]))
        self.dev_combo["values"] = [c[0] for c in self.dev_choices]
        sel = self.cfg["sel"][self.kind]
        cur = next((lab for lab, g in self.dev_choices if g == sel), "")
        if sel and not cur:
            cur = t("disconnected")
        self.dev_var.set(cur)
        self.ch_enabled.set(self.channel()["enabled"])
        self.preset_combo["values"] = sorted(self.presets.get(self.kind, {}))
        self.preset_var.set(self.channel().get("preset", ""))
        for key, (fr, var, val) in self.sliders.items():
            fr.pack_forget()
        self.mic_hint.pack_forget()
        self.headroom_chk.pack_forget()
        keys = ("preamp", "bass", "clarity", "treble") if self.kind == "out" else ("preamp",)
        for key in keys:
            fr, var, val = self.sliders[key]
            fr.pack(fill="x", pady=3)
            var.set(self.channel().get(key, 0.0))
            val.configure(text=f"{var.get():+.1f} dB")
        self.headroom_var.set(self.channel().get("headroom", True))
        self.headroom_chk.pack(fill="x", pady=(6, 0))
        if self.kind == "mic":
            self.mic_hint.pack(fill="x", pady=(8, 0))
        self.refresh_editor()
        self.graph.redraw()

    def refresh_editor(self):
        self._loading = True
        f = self.channel()["filters"][self.selected]
        for i, b in enumerate(self.sel_btns):
            on = self.channel()["filters"][i]["enabled"]
            if i == self.selected:
                b.configure(bg=POINT_COLORS[i], fg="#111")
            else:
                b.configure(bg=COLORS["panel2"], fg=COLORS["fg"] if on else COLORS["off"])
        self.f_enabled.set(f["enabled"])
        self.f_type.set(type_label(f["type"]))
        # o que aparece na tela é arredondado; guardamos o texto exibido para só
        # gravar de volta o campo que a pessoa realmente mudou (antes, ligar/desligar
        # um filtro arredondava a frequência e o Q dos presets importados do Sonar)
        self._shown = {"frequency": round(f["frequency"], 1), "gain": round(f["gain"], 1),
                       "qFactor": round(f["qFactor"], 4)}
        self.f_freq.set(self._shown["frequency"])
        self.f_gain.set(self._shown["gain"])
        self.f_q.set(self._shown["qFactor"])
        self.spin_gain.configure(state="normal" if FILTER_TYPES[f["type"]] else "disabled")
        self._loading = False

    def on_field(self):
        if self._loading:
            return
        f = self.channel()["filters"][self.selected]
        f["enabled"] = self.f_enabled.get()
        f["type"] = type_from_label(self.f_type.get(), f["type"])
        for key, var, lo, hi in (("frequency", self.f_freq, F_MIN, F_MAX), ("gain", self.f_gain, G_MIN, G_MAX),
                                 ("qFactor", self.f_q, Q_MIN, Q_MAX)):
            try:
                v = float(var.get())
            except (tk.TclError, ValueError):
                continue
            if v != self._shown[key]:
                f[key] = clamp(v, lo, hi)
        self.refresh_editor()
        self.changed()

    def on_language(self, _e=None):
        """Troca o idioma e reconstrói a janela na hora (o EQ continua funcionando)."""
        global LANG
        code = next((c for c, name in LANG_NAMES.items() if name == self.lang_var.get()), LANG)
        if code == LANG:
            return
        LANG = self.cfg["lang"] = code
        save_json(STATE_FILE, self.cfg)
        for w in self.winfo_children():
            if not isinstance(w, tk.Toplevel):
                w.destroy()
        self.build()
        self.refresh_all()
        self.update_tray()

    def on_headroom(self):
        self.channel()["headroom"] = self.headroom_var.get()
        self.changed()

    def on_slider(self, key):
        fr, var, val = self.sliders[key]
        v = round(var.get(), 1)
        self.channel()[key] = v
        val.configure(text=f"{v:+.1f} dB")
        self.changed(live=True)

    def reset_slider(self, key):
        self.sliders[key][1].set(0.0)
        self.on_slider(key)
        self.changed()

    def reset_filter(self):
        self.channel()["filters"][self.selected] = default_filter(self.selected)
        self.refresh_editor()
        self.changed()

    def reset_all(self):
        if messagebox.askyesno(APP_NAME, t("confirm_reset_all")):
            self.set_channel(default_channel(self.kind))
            self.refresh_all()
            self.changed()

    def on_power(self):
        self.cfg["power"] = self.power_var.get()
        self.update_tray()
        self.changed()

    def on_ch_enabled(self):
        self.channel()["enabled"] = self.ch_enabled.get()
        self.refresh_all()
        self.changed()

    def on_device(self, _e=None):
        """Troca o dispositivo em edição. Cada dispositivo guarda o próprio EQ;
        um dispositivo novo começa reto (sem efeito) até você escolher um preset."""
        guid = next((g for lab, g in self.dev_choices if lab == self.dev_var.get()), None)
        if not guid:
            return
        self.cfg["sel"][self.kind] = guid
        if guid not in self.cfg["profiles"]:
            self.cfg["profiles"][guid] = self.normalize(default_channel(self.kind), self.kind, guid)
        self.refresh_all()
        self.changed()

    def reload_devices(self):
        self.devices = {"out": list_devices("Render"), "mic": list_devices("Capture")}
        self.refresh_all()

    # ---- presets
    def save_preset(self):
        name = simpledialog.askstring(APP_NAME, t("preset_name"), initialvalue=self.preset_var.get() or "", parent=self)
        if not name:
            return
        data = json.loads(json.dumps(self.channel()))
        for k in ("device", "preset", "enabled"):
            data.pop(k, None)
        self.presets.setdefault(self.kind, {})[name] = data
        save_json(PRESETS_FILE, self.presets)
        self.channel()["preset"] = name
        self.changed()
        self.preset_combo["values"] = sorted(self.presets[self.kind])
        self.preset_var.set(name)
        self.flash(t("preset_saved", name=name))

    def on_preset(self, _e=None):
        p = self.presets.get(self.kind, {}).get(self.preset_var.get())
        if p:
            self.apply_channel(json.loads(json.dumps(p)))
            name = self.preset_var.get()
            self.preset_var.set(name)

    def delete_preset(self):
        name = self.preset_var.get()
        if name and messagebox.askyesno(APP_NAME, t("confirm_delete", name=name)):
            self.presets[self.kind].pop(name, None)
            save_json(PRESETS_FILE, self.presets)
            self.refresh_all()

    def apply_channel(self, data):
        data = dict(data, enabled=True, preset=self.preset_var.get())
        self.set_channel(data)
        self.refresh_all()
        self.changed()

    def import_sonar(self):
        try:
            configs = read_sonar_configs()
        except (OSError, sqlite3.Error) as ex:
            messagebox.showerror(APP_NAME, t("sonar_read_error", err=ex))
            return
        want = (3,) if self.kind == "mic" else (1, 2, 4, 5)
        configs = [c for c in configs if c["vad"] in want]
        if not configs:
            messagebox.showinfo(APP_NAME, t("sonar_none"))
            return
        SonarPicker(self, configs)

    # ---- aplicar
    def changed(self, live=False):
        self.graph.redraw()
        if self._write_job:
            self.after_cancel(self._write_job)
        self._write_job = self.after(60 if live else 10, self.write_config)

    def write_config(self):
        self._write_job = None
        save_json(STATE_FILE, self.cfg)
        if not self.apo_dir:
            self.status.configure(text=t("apo_missing"), foreground="#ff5b6b")
            return
        try:
            ensure_apo_include(self.apo_dir)
            write_apo_file(os.path.join(self.apo_dir, APO_INCLUDE_NAME), build_apo_config(self.cfg, self.device_names()))
            self.status.configure(text=t("applied"), foreground="#7ad35a")
        except OSError as ex:
            self.status.configure(text=t("write_error", err=ex.strerror), foreground="#ff5b6b")
            # o APO pode estar lendo o arquivo neste instante: tenta de novo
            self._write_job = self.after(300, self.write_config)

    def flash(self, msg):
        self.status.configure(text=msg, foreground=COLORS["fg"])
        self.after(2500, lambda: self.status.configure(text=""))

    def warn_no_apo(self):
        messagebox.showwarning(APP_NAME, t("warn_no_apo"))

    # ---- bandeja (área perto do relógio)
    @staticmethod
    def tray_image(on):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=COLORS["accent"] if on else "#5a606c")
        for x, top in ((15, 18), (29, 30), (43, 12)):  # três barrinhas de EQ
            d.rounded_rectangle((x, top, x + 7, 50), radius=3, fill="#ffffff")
        return img

    def setup_tray(self):
        if pystray is None:
            return
        # os cliques no ícone chegam em outra thread: vão para a fila e o Tk executa
        post = lambda fn: (lambda icon, item: self._tray_q.put(fn))
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: t("tray_open"), post(self.show_window), default=True),
            pystray.MenuItem(lambda item: t("tray_power"), post(self.toggle_power), checked=lambda item: self.cfg["power"]),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: t("tray_quit"), post(self.quit_app)),
        )
        self.tray = pystray.Icon(APP_NAME, self.tray_image(self.cfg["power"]), self.tray_title(), menu)
        self.tray.run_detached()
        self.after(100, self.poll_tray)

    def tray_title(self):
        return f"{APP_NAME} — {t('tray_on') if self.cfg['power'] else t('tray_off')}"

    def update_tray(self):
        if self.tray:
            self.tray.icon = self.tray_image(self.cfg["power"])
            self.tray.title = self.tray_title()
            self.tray.update_menu()

    def poll_tray(self):
        try:
            while True:
                self._tray_q.get_nowait()()
        except queue.Empty:
            pass
        if self.tray:
            self.after(100, self.poll_tray)

    def toggle_power(self):
        self.power_var.set(not self.cfg["power"])
        self.on_power()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide_to_tray(self):
        self.withdraw()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            try:
                self.tray.notify(t("tray_hint"), APP_NAME)
            except Exception:
                pass

    def quit_app(self):
        """Fecha o app e desliga o EQ (como sair do Sonar). O estado salvo continua
        com o EQ ligado, então ao abrir o LeveEQ de novo ele volta a funcionar."""
        if self._write_job:
            self.after_cancel(self._write_job)
            self._write_job = None
        save_json(STATE_FILE, self.cfg)
        if self.apo_dir:
            try:
                off = dict(self.cfg, power=False)
                write_apo_file(os.path.join(self.apo_dir, APO_INCLUDE_NAME), build_apo_config(off, self.device_names()))
            except OSError:
                pass
        if self.tray:
            tray, self.tray = self.tray, None
            tray.stop()
        self.destroy()


class SonarPicker(tk.Toplevel):
    def __init__(self, app, configs):
        super().__init__(app)
        self.app, self.configs = app, configs
        self.title(t("picker_title"))
        self.configure(bg=COLORS["bg"])
        self.geometry("460x480")
        self.transient(app)
        ttk.Label(self, text=t("picker_choose"), padding=10).pack(anchor="w")
        sf = ttk.Frame(self)
        sf.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(sf, text=t("search")).pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.fill())
        se = tk.Entry(sf, textvariable=self.search, bg=COLORS["panel2"], fg=COLORS["fg"],
                      insertbackground=COLORS["fg"], relief="flat", font=("Segoe UI", 10))
        se.pack(side="left", fill="x", expand=True, padx=(8, 0), ipady=3)
        se.focus_set()
        self.only_mine = tk.BooleanVar(value=True)
        ttk.Checkbutton(self, text=t("only_mine"), variable=self.only_mine,
                        style="Bar.TCheckbutton", command=self.fill).pack(anchor="w", padx=10)
        self.lb = tk.Listbox(self, bg=COLORS["panel"], fg=COLORS["fg"], selectbackground=COLORS["accent"],
                             selectforeground="#111", highlightthickness=0, borderwidth=0, font=("Segoe UI", 10))
        self.lb.pack(fill="both", expand=True, padx=10, pady=8)
        self.lb.bind("<Double-Button-1>", lambda e: self.ok())
        bf = ttk.Frame(self, padding=10)
        bf.pack(fill="x")
        ttk.Button(bf, text=t("import"), style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bf, text=t("cancel"), command=self.destroy).pack(side="right", padx=6)
        self.fill()

    def fill(self):
        self.lb.delete(0, "end")
        q = self.search.get().strip().lower()
        if q:  # a busca procura em tudo, inclusive nos presets de fábrica
            self.shown = [c for c in self.configs if q in c["name"].lower()]
        else:
            self.shown = [c for c in self.configs if not (self.only_mine.get() and c["is_preset"])] or self.configs
        for c in self.shown:
            self.lb.insert("end", f"{c['name']}   —   {t('vad_%s' % c['vad']) if c['vad'] in (1, 2, 3, 4, 5) else c['vad']}")

    def ok(self):
        sel = self.lb.curselection()
        if not sel:
            return
        c = self.shown[sel[0]]
        ch = sonar_to_channel(c["data"], self.app.kind)
        self.app.presets.setdefault(self.app.kind, {})[c["name"]] = {k: v for k, v in ch.items() if k != "device"}
        save_json(PRESETS_FILE, self.app.presets)
        self.app.preset_var.set(c["name"])
        self.app.apply_channel(ch)
        self.app.preset_combo["values"] = sorted(self.app.presets[self.app.kind])
        self.app.flash(t("imported", name=c["name"]))
        self.destroy()


if __name__ == "__main__":
    # usado pelo instalador: gera o ícone do atalho a partir do mesmo desenho da bandeja
    if len(sys.argv) == 3 and sys.argv[1] == "--make-icon":
        App.tray_image(True).save(sys.argv[2], sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])
        sys.exit(0)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
        _saved_lang = load_json(STATE_FILE, {}).get("lang")
        LANG = _saved_lang if _saved_lang in LANG_NAMES else system_lang()
        # só uma cópia aberta por vez (senão aparecem dois ícones na bandeja)
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "LeveEQ_single_instance")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            ctypes.windll.user32.MessageBoxW(None, t("already_open"), APP_NAME, 0x40)
            sys.exit(0)
    App().mainloop()
