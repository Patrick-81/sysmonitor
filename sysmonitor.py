#!/usr/bin/env python3
"""
SysMonitor v3 — Widget de bureau semi-transparent pour Linux Mint
• Sparklines CPU / GPU (60 secondes d'historique)
• RAM physique : decode-dimms (CL exact) + fallback dmidecode
• Disques : type NVMe/SSD/HDD + température via smartctl
• 4 thèmes couleur configurables (~/.config/sysmonitor/config.ini)
• Menu clic droit : Réduire / Redémarrer / Thème / À propos / Quitter
• Icône zone de notification (AppIndicator3)
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
try:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3
    HAS_INDICATOR = True
except Exception:
    HAS_INDICATOR = False

from gi.repository import Gtk, Gdk, GLib, Pango
import psutil
import subprocess
import os
import sys
import re
import configparser
from collections import deque

# ═══════════════════════════════════════════════════════════════════════════════
#  THÈMES
# ═══════════════════════════════════════════════════════════════════════════════

THEMES = {
    "green": {
        "name":    "Vert menthe (défaut)",
        "accent":  (0.0,  0.85, 0.60),
        "accent2": (0.0,  0.65, 1.0),
        "accent3": (0.80, 0.45, 1.0),
        "spark":   (0.0,  0.85, 0.60),
    },
    "blue": {
        "name":    "Bleu azur",
        "accent":  (0.15, 0.65, 1.0),
        "accent2": (0.0,  0.90, 0.85),
        "accent3": (0.55, 0.35, 1.0),
        "spark":   (0.15, 0.65, 1.0),
    },
    "amber": {
        "name":    "Ambre doré",
        "accent":  (1.0,  0.75, 0.0),
        "accent2": (1.0,  0.45, 0.1),
        "accent3": (0.90, 0.30, 0.70),
        "spark":   (1.0,  0.75, 0.0),
    },
    "purple": {
        "name":    "Violet néon",
        "accent":  (0.75, 0.30, 1.0),
        "accent2": (0.20, 0.70, 1.0),
        "accent3": (1.0,  0.30, 0.65),
        "spark":   (0.75, 0.30, 1.0),
    },
}

WARN      = (1.0, 0.65, 0.0)
CRIT      = (1.0, 0.25, 0.25)
TEXT_MAIN = (0.92, 0.95, 0.92)
TEXT_DIM  = (0.45, 0.55, 0.50)
BG_DARK   = (0.06, 0.09, 0.08)
BG_ALPHA  = 0.75

# Thème courant (remplacé par apply_theme)
ACCENT  = THEMES["green"]["accent"]
ACCENT2 = THEMES["green"]["accent2"]
ACCENT3 = THEMES["green"]["accent3"]
SPARK   = THEMES["green"]["spark"]


# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG_DIR  = os.path.expanduser("~/.config/sysmonitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.ini")

def load_config():
    cfg = configparser.ConfigParser()
    cfg["sysmonitor"] = {"theme": "green", "x": "-1", "y": "-1"}
    if os.path.exists(CONFIG_FILE):
        cfg.read(CONFIG_FILE)
    return cfg

def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        cfg.write(f)

def apply_theme(theme_key):
    global ACCENT, ACCENT2, ACCENT3, SPARK
    t = THEMES.get(theme_key, THEMES["green"])
    ACCENT  = t["accent"]
    ACCENT2 = t["accent2"]
    ACCENT3 = t["accent3"]
    SPARK   = t["spark"]


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS COULEUR / FORMAT
# ═══════════════════════════════════════════════════════════════════════════════

def hx(c):
    return "#{:02x}{:02x}{:02x}".format(int(c[0]*255), int(c[1]*255), int(c[2]*255))

def fmt_bytes(b):
    for u in ("B","KB","MB","GB","TB"):
        if b < 1024: return "{:.1f} {}".format(b, u)
        b /= 1024
    return "{:.1f} TB".format(b)

def human_gb(mb):
    return "{:.1f} GB".format(mb/1024) if mb >= 1024 else "{:.0f} MB".format(mb)

def temp_color(t):
    if t is None: return TEXT_DIM
    if t < 60:    return ACCENT
    if t < 80:    return WARN
    return CRIT

def load_color(p):
    if p < 60:  return ACCENT
    if p < 85:  return WARN
    return CRIT

def _run(cmd, timeout=4):
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=timeout
        ).decode("utf-8", errors="replace")
    except Exception:
        return ""

def fmt_speed(bps):
    """Formate un débit octets/s → unité lisible."""
    if bps < 1000:    return "{:.0f} B/s".format(bps)
    elif bps < 1e6:   return "{:.1f} KB/s".format(bps / 1e3)
    elif bps < 1e9:   return "{:.2f} MB/s".format(bps / 1e6)
    else:             return "{:.2f} GB/s".format(bps / 1e9)

def fmt_vol(b):
    """Formate un volume octets → unité lisible."""
    if b < 1024:       return "{:.0f} B".format(b)
    elif b < 1024**2:  return "{:.1f} KB".format(b / 1024)
    elif b < 1024**3:  return "{:.2f} MB".format(b / 1024**2)
    elif b < 1024**4:  return "{:.2f} GB".format(b / 1024**3)
    else:              return "{:.2f} TB".format(b / 1024**4)

def get_net_info(prev_counters=None, interval=1.0):
    """
    Retourne compteurs réseau par interface + débits instantanés (delta/s).
    prev_counters : psutil.net_io_counters(pernic=True) de la seconde précédente.
    """
    current = psutil.net_io_counters(pernic=True)
    interfaces = []
    total_rx = total_tx = 0.0

    for iface, c in current.items():
        if iface == "lo": continue
        if c.bytes_recv == 0 and c.bytes_sent == 0: continue
        rx_bps = tx_bps = 0.0
        if prev_counters and iface in prev_counters:
            p = prev_counters[iface]
            rx_bps = max(0.0, (c.bytes_recv - p.bytes_recv) / interval)
            tx_bps = max(0.0, (c.bytes_sent - p.bytes_sent) / interval)
        total_rx += rx_bps
        total_tx += tx_bps
        interfaces.append({
            "name": iface, "rx_bps": rx_bps, "tx_bps": tx_bps,
            "rx_total": c.bytes_recv, "tx_total": c.bytes_sent,
            "rx_packets": c.packets_recv, "tx_packets": c.packets_sent,
            "rx_errors": c.errin,  "tx_errors": c.errout,
            "rx_drop":   c.dropin, "tx_drop":   c.dropout,
        })

    # Interface la plus active en tête
    interfaces.sort(key=lambda x: x["rx_bps"] + x["tx_bps"], reverse=True)
    return {"interfaces": interfaces, "total_rx_bps": total_rx,
            "total_tx_bps": total_tx, "counters": current}


# ═══════════════════════════════════════════════════════════════════════════════
#  COLLECTEURS SYSTÈME
# ═══════════════════════════════════════════════════════════════════════════════

# ── CPU ───────────────────────────────────────────────────────────────────────

def get_cpu_info():
    info = {}
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    info["model"] = line.split(":", 1)[1].strip(); break
    except Exception:
        info["model"] = "CPU inconnu"
    info["cores_physical"] = psutil.cpu_count(logical=False) or 1
    info["cores_logical"]  = psutil.cpu_count(logical=True)  or 1
    info["freq"]     = psutil.cpu_freq()
    info["percent"]  = psutil.cpu_percent(interval=None)
    info["per_core"] = psutil.cpu_percent(percpu=True, interval=None)
    info["temps"]    = {}
    try:
        temps = psutil.sensors_temperatures()
        for key in ("coretemp","k10temp","zenpower","cpu_thermal","acpitz"):
            if key in temps:
                info["temps"] = {(e.label or "Core {}".format(i)): e.current
                                 for i, e in enumerate(temps[key])}
                break
    except Exception:
        pass
    info["temp_avg"] = (sum(info["temps"].values()) / len(info["temps"])
                        if info["temps"] else None)
    return info


# ── GPU ───────────────────────────────────────────────────────────────────────

def get_gpu_info():
    out = _run(["nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,"
                "memory.used,memory.total,driver_version,clocks.current.graphics",
                "--format=csv,noheader,nounits"])
    if out.strip():
        p = [x.strip() for x in out.strip().split(",")]
        try:
            return {"vendor":"NVIDIA","model":p[0],
                    "temp":float(p[1]),"util":float(p[2]),
                    "vram_used":float(p[3]),"vram_total":float(p[4]),
                    "driver":p[5],"clock":(p[6]+" MHz" if len(p)>6 else "N/A")}
        except Exception:
            pass
    out = _run(["rocm-smi","--showtemp","--showuse",
                "--showmemuse","--showproductname","--csv"])
    if out.strip():
        lines = [l for l in out.splitlines() if l.strip()]
        if len(lines) >= 2:
            d = dict(zip(lines[0].split(","), lines[1].split(",")))
            def _n(k): return float(re.sub(r"[^\d.]","",d.get(k,"0")) or 0)
            return {"vendor":"AMD","model":d.get("Card series","AMD GPU"),
                    "temp":_n("Temperature (Sensor edge) (C)"),
                    "util":_n("GPU use (%)"),"vram_used":_n("GTT Memory Use (%)"),
                    "vram_total":0,"driver":"AMDGPU","clock":"N/A"}
    return None


def get_vram_detail(vendor="NVIDIA"):
    d = {}
    if vendor == "NVIDIA":
        out = _run(["nvidia-smi","-q"], timeout=5)
        if not out: return d
        def _f(key):
            m = re.search(r"" + re.escape(key) + r"\s*:\s*(.+)", out)
            return m.group(1).strip() if m else "N/A"
        d["type"] = _f("Memory Type")
        fb = re.search(r"FB Memory Usage\s*\n(.*?)(?=\n\s*\n|\Z)", out, re.DOTALL)
        if fb:
            for pat, k in ((r"Total\s*:\s*(\d+\s*MiB)","fb_total"),
                           (r"Used\s*:\s*(\d+\s*MiB)","fb_used"),
                           (r"Free\s*:\s*(\d+\s*MiB)","fb_free")):
                m = re.search(pat, fb.group(1))
                d[k] = m.group(1) if m else "N/A"
        bar = re.search(r"BAR1 Memory Usage\s*\n(.*?)(?=\n\s*\n|\Z)", out, re.DOTALL)
        if bar:
            for pat, k in ((r"Total\s*:\s*(\d+\s*MiB)","bar1_total"),
                           (r"Used\s*:\s*(\d+\s*MiB)","bar1_used")):
                m = re.search(pat, bar.group(1))
                d[k] = m.group(1) if m else "N/A"
        d["mem_clock"]   = _f("Memory Clock")
        d["bus_width"]   = _f("Memory Bus Width")
        d["ecc_current"] = _f("Current")
        d["ecc_pending"] = _f("Pending")
        d["cuda"]        = _f("CUDA Version")
        d["pcie_gen"]    = _f("PCIe Generation")
        d["pcie_width"]  = _f("Link Width")
    elif vendor == "AMD":
        out = _run(["rocm-smi","--showmeminfo","vram","--showclocks","--csv"])
        for line in out.splitlines():
            if "VRAM Total Memory" in line:
                m = re.search(r":\s*(\d+)", line)
                if m: d["fb_total"] = "{} MiB".format(int(m.group(1))//1024)
            if "VRAM Total Used Memory" in line:
                m = re.search(r":\s*(\d+)", line)
                if m: d["fb_used"] = "{} MiB".format(int(m.group(1))//1024)
        drm = "/sys/class/drm"
        if os.path.exists(drm):
            for card in sorted(os.listdir(drm)):
                p = "{}/{}/device/mem_info_vram_type".format(drm, card)
                if os.path.exists(p):
                    d["type"] = open(p).read().strip(); break
        d["driver"] = "AMDGPU"
    return d


# ── RAM physique ──────────────────────────────────────────────────────────────

def get_ram_detail():
    result = {"slots":[], "need_sudo":False, "error":None, "source":None}

    # 1. Essai decode-dimms (CL exact depuis SPD)
    raw_dd = _run(["sudo","-n","decode-dimms"], timeout=8)
    if raw_dd and "Fundamental Memory type" in raw_dd:
        result["source"] = "decode-dimms"
        _parse_decode_dimms(raw_dd, result)
        return result

    # 2. Fallback dmidecode
    raw = _run(["sudo","-n","dmidecode","-t","memory"], timeout=5)
    if not raw:
        raw = _run(["pkexec","dmidecode","-t","memory"], timeout=6)
    if not raw:
        result["need_sudo"] = True
        result["error"]     = "Accès refusé (voir README)"
        return result

    result["source"] = "dmidecode"
    _parse_dmidecode(raw, result)
    return result


def _parse_decode_dimms(raw, result):
    """Parse la sortie de decode-dimms pour extraire CL, fréquence, type."""
    blocks = re.split(r"\n\s*Decoding EEPROM", raw)
    for block in blocks[1:]:
        s = {}
        def _f(key):
            m = re.search(r"^\s*" + re.escape(key) + r"\s*:\s*(.+)$", block, re.M)
            return m.group(1).strip() if m else ""

        s["source"]       = "SPD"
        s["type"]         = _f("Fundamental Memory type")
        s["size"]         = _f("Module Size")
        s["speed"]        = _f("Maximum module speed")
        s["manufacturer"] = _f("Manufacturer")
        s["part"]         = _f("Part Number").strip()
        s["voltage"]      = _f("Module voltage")
        s["rank"]         = _f("Ranks")

        # CL exact depuis SPD
        cl_line = _f("tCL")
        if cl_line:
            m = re.search(r"(\d+)\s*(?:ns|clk|T)", cl_line)
            if m:
                s["cl"] = "CL{}".format(m.group(1))
                s["cl_estimated"] = False
            else:
                s["cl"] = cl_line
                s["cl_estimated"] = False
        else:
            # Cherche CAS Supported
            m_cas = re.search(r"CAS Latencies Supported.*\n(.*)", block)
            if m_cas:
                # Prend la valeur min
                nums = re.findall(r"\d+", m_cas.group(1))
                if nums:
                    s["cl"] = "CL{}".format(min(int(n) for n in nums))
                    s["cl_estimated"] = False
                else:
                    s["cl"] = "N/A"; s["cl_estimated"] = False
            else:
                s["cl"] = "N/A"; s["cl_estimated"] = False

        # Locator depuis le titre du bloc
        m_loc = re.search(r"at\s+/dev/\S+\s+(.+)", block)
        s["locator"] = m_loc.group(1).strip() if m_loc else "Slot {}".format(len(result["slots"])+1)

        if s.get("type") or s.get("size"):
            result["slots"].append(s)


def _parse_dmidecode(raw, result):
    """Parse dmidecode -t memory."""
    blocks = re.split(r"\n\s*Memory Device\s*\n", raw)
    for block in blocks[1:]:
        def _f(key):
            m = re.search(r"^\s*" + re.escape(key) + r"\s*:\s*(.+)$", block, re.M)
            return m.group(1).strip() if m else ""
        size_str = _f("Size")
        if not size_str or "No Module" in size_str or size_str in ("0","Not Installed"):
            continue
        s = {
            "source":       "dmidecode",
            "size":         size_str,
            "locator":      _f("Locator"),
            "bank":         _f("Bank Locator"),
            "type":         _f("Type"),
            "form":         _f("Form Factor"),
            "speed":        _f("Speed"),
            "configured":   _f("Configured Memory Speed"),
            "voltage":      _f("Configured Voltage"),
            "manufacturer": _f("Manufacturer"),
            "serial":       _f("Serial Number"),
            "part":         _f("Part Number").strip(),
            "rank":         _f("Rank"),
        }
        cl_raw = _f("CAS Latency")
        if cl_raw and re.search(r"\d+", cl_raw):
            s["cl"] = "CL" + re.search(r"\d+", cl_raw).group()
            s["cl_estimated"] = False
        else:
            freq_str = s.get("configured") or s.get("speed","")
            m = re.search(r"(\d+)", freq_str)
            if m:
                mts = int(m.group(1))
                if   "DDR5" in s["type"]: cl_est = max(34, mts // 180)
                elif "DDR4" in s["type"]: cl_est = max(14, mts // 200)
                elif "DDR3" in s["type"]: cl_est = max(9,  mts // 266)
                else:                     cl_est = None
                if cl_est:
                    s["cl"] = "~CL{}".format(cl_est)
                    s["cl_estimated"] = True
                else:
                    s["cl"] = "N/A"; s["cl_estimated"] = False
            else:
                s["cl"] = "N/A"; s["cl_estimated"] = False
        result["slots"].append(s)


# ── Disques (lsblk + smartctl) ───────────────────────────────────────────────

# Systèmes de fichiers à ignorer complètement
_IGNORE_FS = {
    "squashfs","tmpfs","devtmpfs","sysfs","proc","cgroup","cgroup2",
    "pstore","debugfs","tracefs","securityfs","configfs","fusectl",
    "hugetlbfs","mqueue","overlay","aufs","nsfs","binfmt_misc",
    "efivarfs","ramfs","iso9660","udf",
}
# Préfixes de points de montage à ignorer
_IGNORE_MNT = ("/snap/", "/sys/", "/proc/", "/dev/", "/run/user/",
               "/run/lock", "/run/snapd")

def _base_dev(device):
    """
    Remonte au disque physique depuis une partition.
    /dev/sda1   → /dev/sda
    /dev/sdb2   → /dev/sdb
    /dev/nvme0n1p3 → /dev/nvme0n1
    /dev/mmcblk0p1 → /dev/mmcblk0
    """
    b = os.path.basename(device)
    # NVMe : nvme0n1p2 → nvme0n1
    m = re.match(r"(nvme\d+n\d+)p\d+$", b)
    if m: return "/dev/" + m.group(1)
    # MMC : mmcblk0p1 → mmcblk0
    m = re.match(r"(mmcblk\d+)p\d+$", b)
    if m: return "/dev/" + m.group(1)
    # SATA/SCSI : sda1 → sda, vda2 → vda
    m = re.match(r"([a-z]+[a-z])\d+$", b)
    if m: return "/dev/" + m.group(1)
    return device  # déjà un disque de base

def _disk_type(base_dev):
    """NVMe / SSD / HDD depuis /sys/block."""
    b = os.path.basename(base_dev)
    if "nvme"   in b: return "NVMe"
    if "mmcblk" in b: return "eMMC"
    rot = "/sys/block/{}/queue/rotational".format(b)
    try:
        return "HDD" if open(rot).read().strip() == "1" else "SSD"
    except Exception:
        return "?"

def _disk_temp(base_dev):
    """
    Température via smartctl sans réveiller le disque.
    --nocheck=standby : smartctl abandonne si le disque est en veille.
    -n standby        : alias équivalent sur les versions plus anciennes.
    """
    out = _run(["sudo", "-n", "smartctl", "-A", "--nocheck=standby", base_dev], timeout=3)
    # Si le disque est en veille, smartctl renvoie un code non-nul et un message
    # "Device is in STANDBY mode" — on retourne None proprement.
    if not out or "STANDBY" in out.upper() or "SLEEP" in out.upper():
        return None
    m = re.search(
        r"Temperature[_\s]Celsius\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)", out)
    if m: return float(m.group(1))
    m = re.search(r"Temperature:\s+(\d+)\s+Celsius", out)
    if m: return float(m.group(1))
    return None

def get_disk_info():
    """
    Retourne une liste de dicts, un par disque physique unique.
    Taille réelle du disque via lsblk (pas les partitions).
    Filtre tous les pseudo-systèmes (snap, tmpfs, squashfs, loop…).
    """
    # ── 1. lsblk : taille et modèle des disques physiques ────────────────────
    lsblk_sizes  = {}   # /dev/sda → octets
    lsblk_models = {}   # /dev/sda → "Samsung SSD 870"
    out_lsblk = _run(["lsblk", "-b", "-d", "-o", "NAME,SIZE,MODEL", "--noheadings"])
    for line in out_lsblk.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2:
            dev_path = "/dev/" + parts[0].strip()
            try:
                lsblk_sizes[dev_path]  = int(parts[1])
                lsblk_models[dev_path] = parts[2].strip() if len(parts) > 2 else ""
            except Exception:
                pass

    # ── 2. Partitions montées (filtrées) ──────────────────────────────────────
    real = []
    for p in psutil.disk_partitions(all=False):
        if re.match(r"/dev/loop", p.device):                             continue
        if p.fstype.lower() in _IGNORE_FS:                               continue
        if any(p.mountpoint.startswith(pfx) for pfx in _IGNORE_MNT):    continue
        if not p.device.startswith("/dev/"):                             continue
        try:
            u = psutil.disk_usage(p.mountpoint)
            if u.total == 0: continue
            base = _base_dev(p.device)
            real.append({
                "mountpoint": p.mountpoint,
                "device":     p.device,
                "base_dev":   base,
                "fstype":     p.fstype,
                "usage":      u,
            })
        except Exception:
            continue

    # ── 3. Regrouper par disque physique ──────────────────────────────────────
    disks = {}

    # Initialiser d'abord TOUS les disques physiques détectés par lsblk
    for dev_path, size in lsblk_sizes.items():
        b = os.path.basename(dev_path)
        # Exclure les loop devices et les partitions
        if b.startswith("loop"): continue
        if size == 0: continue
        disks[dev_path] = {
            "base_dev":    dev_path,
            "disk_name":   b,
            "disk_model":  lsblk_models.get(dev_path, ""),
            "disk_type":   _disk_type(dev_path),
            "total_bytes": size,
            "temp":        None,
            "partitions":  [],
        }

    # Associer ensuite les partitions montées
    for part in real:
        bd = part["base_dev"]
        if bd not in disks:
            disks[bd] = {
                "base_dev":    bd,
                "disk_name":   os.path.basename(bd),
                "disk_model":  lsblk_models.get(bd, ""),
                "disk_type":   _disk_type(bd),
                "total_bytes": lsblk_sizes.get(bd, 0),   # ← taille disque réelle
                "temp":        None,
                "partitions":  [],
            }
        disks[bd]["partitions"].append(part)

    # ── 4. Calcul used + percent ──────────────────────────────────────────────
    result = []
    for bd, disk in sorted(disks.items()):
        parts = disk["partitions"]
        # used = somme de toutes les partitions montées
        used = sum(p["usage"].used for p in parts)
        total = disk["total_bytes"]
        # Fallback si lsblk n'a pas renvoyé la taille (VM, device mapper…)
        if total == 0:
            total = max(p["usage"].total for p in parts)
        disk["used_bytes"] = used
        disk["total_bytes"] = total
        disk["percent"] = 100.0 * used / total if total else 0
        result.append(disk)

    return result

def enrich_disk_temps(disks):
    """Ajoute les températures par disque physique (appel bloquant)."""
    import threading
    def _fetch(d):
        d["temp"] = _disk_temp(d["base_dev"])
    threads = [threading.Thread(target=_fetch, args=(d,), daemon=True) for d in disks]
    for t in threads: t.start()
    for t in threads: t.join(timeout=5)


# ═══════════════════════════════════════════════════════════════════════════════
#  WIDGETS GTK
# ═══════════════════════════════════════════════════════════════════════════════

CSS = b"* { background-color: transparent; color: rgba(220,240,230,0.95); }"


# ── Barre ─────────────────────────────────────────────────────────────────────

class BarWidget(Gtk.DrawingArea):
    def __init__(self, color=None, height=6):
        super().__init__()
        self._value = 0.0
        self._color = color or ACCENT
        self.set_size_request(-1, height)
        self.connect("draw", self._draw)

    def set_value(self, v):
        self._value = max(0.0, min(1.0, v)); self.queue_draw()

    def set_color(self, c):
        self._color = c; self.queue_draw()

    def _draw(self, widget, cr):
        w = widget.get_allocated_width(); h = widget.get_allocated_height(); r = h/2
        cr.set_source_rgba(*BG_DARK, 0.8); _rr(cr,0,0,w,h,r); cr.fill()
        fw = max(r*2, w*self._value)
        cr.set_source_rgba(*self._color, 0.9); _rr(cr,0,0,fw,h,r); cr.fill()
        cr.set_source_rgba(1,1,1,0.12);        _rr(cr,0,0,fw,h/2,r); cr.fill()


# ── Sparkline ─────────────────────────────────────────────────────────────────

class SparklineWidget(Gtk.DrawingArea):
    """
    Mini graphe de type 'area chart' sur les 60 dernières valeurs (0-100).
    Couleur = SPARK du thème courant.
    """
    HEIGHT = 28

    def __init__(self, history):
        super().__init__()
        self._history = history   # deque partagée
        self.set_size_request(-1, self.HEIGHT)
        self.connect("draw", self._draw)

    def refresh(self):
        self.queue_draw()

    def _draw(self, widget, cr):
        w  = widget.get_allocated_width()
        h  = widget.get_allocated_height()
        n  = len(self._history)
        if n < 2: return

        vals = list(self._history)
        step = w / (len(vals) - 1)

        # Fond de la zone
        cr.set_source_rgba(*BG_DARK, 0.5)
        _rr(cr, 0, 0, w, h, 3); cr.fill()

        # Aire remplie
        cr.new_path()
        cr.move_to(0, h)
        for i, v in enumerate(vals):
            x = i * step
            y = h - (v / 100.0) * h
            cr.line_to(x, y)
        cr.line_to((len(vals)-1)*step, h)
        cr.close_path()
        cr.set_source_rgba(*SPARK, 0.18)
        cr.fill()

        # Ligne du dessus
        cr.new_path()
        for i, v in enumerate(vals):
            x = i * step
            y = h - (v / 100.0) * h
            if i == 0: cr.move_to(x, y)
            else:       cr.line_to(x, y)
        cr.set_source_rgba(*SPARK, 0.85)
        cr.set_line_width(1.5)
        cr.stroke()

        # Valeur courante (dernier point)
        last = vals[-1]
        cr.set_source_rgba(*load_color(last), 1.0)
        cr.arc((len(vals)-1)*step, h - (last/100.0)*h, 2.5, 0, 6.283)
        cr.fill()

        # Ligne de référence à 80%
        y80 = h - 0.8 * h
        cr.set_source_rgba(1,1,1,0.06)
        cr.set_line_width(0.5)
        cr.move_to(0, y80); cr.line_to(w, y80)
        cr.stroke()


# ── DualSparkline (réseau ↓RX / ↑TX) ─────────────────────────────────────────

class DualSparkline(Gtk.DrawingArea):
    """
    Double sparkline superposée :
      RX (download) en ACCENT  — courbe pleine
      TX (upload)   en ACCENT2 — courbe derrière, plus transparente
    Normalisation commune sur le pic glissant des deux séries.
    """
    HEIGHT = 34

    def __init__(self, hist_rx, hist_tx):
        super().__init__()
        self._rx = hist_rx
        self._tx = hist_tx
        self.set_size_request(-1, self.HEIGHT)
        self.connect("draw", self._draw)

    def refresh(self):
        self.queue_draw()

    def _draw(self, widget, cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        # Fond
        cr.set_source_rgba(*BG_DARK, 0.5)
        _rr(cr, 0, 0, w, h, 3); cr.fill()

        rx_vals = list(self._rx)
        tx_vals = list(self._tx)
        n = min(len(rx_vals), len(tx_vals))
        if n < 2:
            return

        peak = max(max(rx_vals[:n]), max(tx_vals[:n]), 1.0)
        step = w / (n - 1)
        PAD  = 0.90   # laisser 10% en haut

        def _curve(vals, color, alpha_fill, alpha_line):
            cr.new_path()
            cr.move_to(0, h)
            for i, v in enumerate(vals[:n]):
                cr.line_to(i * step, h - (v / peak) * h * PAD)
            cr.line_to((n-1) * step, h)
            cr.close_path()
            cr.set_source_rgba(*color, alpha_fill); cr.fill()
            cr.new_path()
            for i, v in enumerate(vals[:n]):
                x = i * step; y = h - (v / peak) * h * PAD
                if i == 0: cr.move_to(x, y)
                else:       cr.line_to(x, y)
            cr.set_source_rgba(*color, alpha_line)
            cr.set_line_width(1.4); cr.stroke()

        # TX derrière, RX devant
        _curve(tx_vals, ACCENT2, 0.10, 0.60)
        _curve(rx_vals, ACCENT,  0.18, 0.90)

        # Points terminaux
        for val, col in ((tx_vals[n-1], ACCENT2), (rx_vals[n-1], ACCENT)):
            cr.set_source_rgba(*col, 1.0)
            cr.arc((n-1)*step, h - (val/peak)*h*PAD, 2.5, 0, 6.283)
            cr.fill()

        # Légende ↓ ↑ en haut à droite
        cr.select_font_face("Monospace", 0, 0)
        cr.set_font_size(7)
        cr.set_source_rgba(*ACCENT, 0.85)
        cr.move_to(w - 44, 9); cr.show_text("↓DL")
        cr.set_source_rgba(*ACCENT2, 0.85)
        cr.move_to(w - 22, 9); cr.show_text("↑UL")


# ── Section cliquable ─────────────────────────────────────────────────────────

class Section(Gtk.EventBox):
    def __init__(self, icon, title, on_click=None, sparkline_history=None):
        super().__init__()
        self._on_click = on_click

        if on_click:
            self.connect("button-press-event", self._handle_press)
            self.set_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                            Gdk.EventMask.ENTER_NOTIFY_MASK |
                            Gdk.EventMask.LEAVE_NOTIFY_MASK)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.set_margin_top(7); box.set_margin_bottom(7)
        box.set_margin_start(14); box.set_margin_end(14)

        # En-tête
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        li = Gtk.Label()
        li.set_markup('<span font_desc="Monospace 10" foreground="{}">{}</span>'.format(hx(ACCENT), icon))
        lt = Gtk.Label()
        lt.set_markup('<span font_desc="Monospace Bold 9" foreground="{}" '
                      'letter_spacing="2000">{}</span>'.format(hx(TEXT_DIM), title))
        lt.set_halign(Gtk.Align.START)
        hbox.pack_start(li, False, False, 0)
        hbox.pack_start(lt, False, False, 0)
        if on_click:
            hint = Gtk.Label()
            hint.set_markup('<span font_desc="Monospace 7" foreground="#446655">▸ détails</span>')
            hint.set_halign(Gtk.Align.END)
            hbox.pack_end(hint, False, False, 0)

        self._lbl_main = Gtk.Label()
        self._lbl_main.set_halign(Gtk.Align.START)
        self._lbl_main.set_ellipsize(Pango.EllipsizeMode.END)

        self._bar = BarWidget()

        self._lbl_sub = Gtk.Label()
        self._lbl_sub.set_halign(Gtk.Align.START)
        self._lbl_sub.set_ellipsize(Pango.EllipsizeMode.END)

        box.pack_start(hbox,           False, False, 0)
        box.pack_start(self._lbl_main, False, False, 0)
        box.pack_start(self._bar,      False, False, 0)
        box.pack_start(self._lbl_sub,  False, False, 0)

        # Sparkline simple (CPU/GPU)
        self._spark_widget = None
        if sparkline_history is not None:
            self._spark_widget = SparklineWidget(sparkline_history)
            box.pack_start(self._spark_widget, False, False, 0)

        # Dual sparkline (réseau) — injectée après construction via attach_dual_spark()
        self._dual_spark = None

        self._extra = []; self._box = box
        self.add(box)

    def attach_dual_spark(self, dual_widget):
        """Attache un DualSparkline sous le lbl_sub."""
        self._dual_spark = dual_widget
        self._box.pack_start(dual_widget, False, False, 0)
        dual_widget.show_all()

    def _handle_press(self, widget, event):
        # Ne propager le clic au callback que si c'est le bouton gauche
        # Le bouton droit est géré au niveau fenêtre
        if event.button == 1 and self._on_click:
            self._on_click()

    def set_main(self, m): self._lbl_main.set_markup(m)
    def set_sub(self,  m): self._lbl_sub.set_markup(m)

    def set_bar(self, v, color=None):
        if color: self._bar.set_color(color)
        self._bar.set_value(v)

    def refresh_spark(self):
        if self._spark_widget:
            self._spark_widget.refresh()
        if self._dual_spark:
            self._dual_spark.refresh()

    def add_row(self, label_markup, value, color):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl = Gtk.Label(); lbl.set_halign(Gtk.Align.START)
        lbl.set_markup(label_markup)
        bar = BarWidget(color=color, height=5); bar.set_value(value)
        row.pack_start(lbl, False, False, 0)
        row.pack_start(bar, False, False, 0)
        self._box.pack_start(row, False, False, 0)
        self._extra.append(row); row.show_all()

    def clear_rows(self):
        for r in self._extra: self._box.remove(r)
        self._extra.clear()


# ── Popup détail ──────────────────────────────────────────────────────────────

class DetailPopup(Gtk.Window):
    def __init__(self, title, content_markup, parent):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_decorated(False); self.set_keep_above(True)
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual: self.set_visual(visual)
        self.connect("draw", self._draw_bg)
        self.connect("button-press-event", lambda *a: self.destroy())
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16); box.set_margin_bottom(16)
        box.set_margin_start(20); box.set_margin_end(20)

        lt = Gtk.Label()
        lt.set_markup('<span font_desc="Monospace Bold 11" foreground="{}">{}</span>'.format(
            hx(ACCENT), title))
        lt.set_halign(Gtk.Align.START)

        lc = Gtk.Label(); lc.set_markup(content_markup)
        lc.set_halign(Gtk.Align.START); lc.set_justify(Gtk.Justification.LEFT)

        lh = Gtk.Label()
        lh.set_markup('<span font_desc="Monospace 7" foreground="#336644">'
                      '[ clic pour fermer — auto 15 s ]</span>')

        box.pack_start(lt,              False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 0)
        box.pack_start(lc,              False, False, 0)
        box.pack_start(lh,              False, False, 0)
        self.add(box); self.show_all()

        px, py = parent.get_window().get_origin()[1:]
        sw = Gdk.Screen.get_default().get_width()
        w, _h = self.get_size()
        self.move(px + 320 if px + 320 + w < sw else px - w - 10, py)
        GLib.timeout_add_seconds(15, lambda: self.destroy() or False)

    def _draw_bg(self, widget, cr):
        w = widget.get_allocated_width(); h = widget.get_allocated_height(); r = 10
        cr.set_source_rgba(0.05, 0.10, 0.08, 0.95)
        _rr(cr, 0, 0, w, h, r); cr.fill()
        cr.set_source_rgba(*ACCENT, 0.35); cr.set_line_width(1)
        _rr(cr, 0, 0, w, h, r); cr.stroke()


# ── Rounded rect helper (module-level) ───────────────────────────────────────

def _rr(cr, x, y, w, h, r):
    if w < 2*r: r = w/2
    if h < 2*r: r = h/2
    cr.new_path()
    cr.arc(x+r,   y+r,   r, 3.14159, 4.712)
    cr.arc(x+w-r, y+r,   r, 4.712,   6.283)
    cr.arc(x+w-r, y+h-r, r, 0,       1.571)
    cr.arc(x+r,   y+h-r, r, 1.571,   3.14159)
    cr.close_path()


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAY ICON
# ═══════════════════════════════════════════════════════════════════════════════

class TrayIcon:
    def __init__(self, on_show, on_quit):
        self._on_show = on_show
        self._on_quit = on_quit
        self._indicator = None
        self._status_icon = None
        self._build()

    def _build(self):
        if HAS_INDICATOR:
            self._indicator = AppIndicator3.Indicator.new(
                "sysmonitor",
                "utilities-system-monitor",
                AppIndicator3.IndicatorCategory.HARDWARE
            )
            self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self._indicator.set_title("SysMonitor")
            menu = Gtk.Menu()
            item_show = Gtk.MenuItem(label="Afficher / Masquer")
            item_show.connect("activate", lambda *a: self._on_show())
            item_quit = Gtk.MenuItem(label="Quitter")
            item_quit.connect("activate", lambda *a: self._on_quit())
            menu.append(item_show); menu.append(Gtk.SeparatorMenuItem()); menu.append(item_quit)
            menu.show_all()
            self._indicator.set_menu(menu)
        else:
            # Fallback StatusIcon (deprecated mais fonctionnel sous Mint)
            self._status_icon = Gtk.StatusIcon.new_from_icon_name("utilities-system-monitor")
            self._status_icon.set_tooltip_text("SysMonitor")
            self._status_icon.connect("activate", lambda *a: self._on_show())


# ═══════════════════════════════════════════════════════════════════════════════
#  FENÊTRE PRINCIPALE
# ═══════════════════════════════════════════════════════════════════════════════

class SysMonitor(Gtk.Window):

    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self._popup    = None
        self._visible  = True

        # Config & thème
        self._cfg = load_config()
        self._theme_key = self._cfg.get("sysmonitor", "theme", fallback="green")
        apply_theme(self._theme_key)

        # Transparence
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual: self.set_visual(visual)

        self.set_decorated(False); self.set_keep_above(True)
        self.set_skip_taskbar_hint(True); self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP); self.stick()

        # Drag
        self._drag = False; self._dx = self._dy = 0
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("button-press-event",   self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event",  self._on_motion)
        self.connect("draw",                 self._draw_bg)

        provider = Gtk.CssProvider(); provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Historiques (60 s)
        self._hist_cpu = deque([0.0]*60, maxlen=60)
        self._hist_gpu = deque([0.0]*60, maxlen=60)
        self._hist_rx  = deque([0.0]*60, maxlen=60)   # réseau download (bps)
        self._hist_tx  = deque([0.0]*60, maxlen=60)   # réseau upload   (bps)

        # Layout
        self._outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._outer.set_margin_top(10); self._outer.set_margin_bottom(10)
        self._outer.set_margin_start(6); self._outer.set_margin_end(6)

        # Barre de titre personnalisée
        titlebar = self._build_titlebar()
        self._outer.pack_start(titlebar, False, False, 0)

        def sep():
            s = Gtk.Separator(); s.set_margin_start(14); s.set_margin_end(14)
            return s

        self._cpu_sec  = Section("▣", "PROCESSEUR", self._show_cpu_detail,
                                 sparkline_history=self._hist_cpu)
        self._gpu_sec  = Section("◈", "GPU",         self._show_gpu_detail,
                                 sparkline_history=self._hist_gpu)
        self._vram_sec = Section("▦", "VRAM",         self._show_vram_detail)
        self._ram_sec  = Section("▤", "RAM",           self._show_ram_detail)
        self._disk_sec = Section("▧", "STOCKAGE",     None)
        self._net_sec  = Section("⇅", "RÉSEAU",        self._show_net_detail)

        # DualSparkline réseau — attachée après construction
        self._dual_spark_widget = DualSparkline(self._hist_rx, self._hist_tx)
        self._net_sec.attach_dual_spark(self._dual_spark_widget)

        for w in (self._cpu_sec,  sep(),
                  self._gpu_sec,  sep(),
                  self._vram_sec, sep(),
                  self._ram_sec,  sep(),
                  self._disk_sec, sep(),
                  self._net_sec):
            self._outer.pack_start(w, False, False, 0)

        self.add(self._outer)

        # Position initiale
        monitor = screen.get_monitor_geometry(0)
        saved_x = self._cfg.getint("sysmonitor", "x", fallback=-1)
        saved_y = self._cfg.getint("sysmonitor", "y", fallback=-1)
        if saved_x >= 0 and saved_y >= 0:
            self.move(saved_x, saved_y)
        else:
            self.move(monitor.width - 330, 40)
        self.set_default_size(310, -1)
        self.show_all()

        # Tray icon
        self._tray = TrayIcon(self._toggle_visibility, Gtk.main_quit)

        # Caches
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(percpu=True, interval=None)
        self._gpu_cache  = None
        self._gpu_tick   = 0
        self._disk_cache = []
        self._disk_tick  = 0

        # Réseau — compteurs de référence
        _boot = psutil.net_io_counters(pernic=True)
        self._net_prev_counters  = _boot      # delta 1 s
        self._net_boot_counters  = _boot      # total depuis boot (déjà là au lancement)
        self._net_session_rx     = 0          # cumul session (octets)
        self._net_session_tx     = 0
        self._net_info_cache     = None       # dernier résultat get_net_info

        # Températures disques en arrière-plan (toutes les 30 s)
        GLib.timeout_add(1000,  self._update)
        GLib.timeout_add(120000, self._update_disk_temps)
        self._update()
        # Premier appel au démarrage (one-shot, non bloquant)
        import threading
        threading.Thread(target=lambda: (
            enrich_disk_temps(self._disk_cache) if self._disk_cache else None
        ), daemon=True).start()

    # ── Barre de titre ────────────────────────────────────────────────────────

    def _build_titlebar(self):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        hbox.set_margin_start(14); hbox.set_margin_end(8)
        hbox.set_margin_top(4); hbox.set_margin_bottom(6)

        lbl = Gtk.Label()
        lbl.set_markup('<span font_desc="Monospace Bold 9" foreground="{}" '
                       'letter_spacing="4000">◈ SYSMONITOR</span>'.format(hx(ACCENT)))
        lbl.set_halign(Gtk.Align.START)

        # Bouton réduire
        btn_min = Gtk.Button(label="—")
        btn_min.set_relief(Gtk.ReliefStyle.NONE)
        btn_min.set_size_request(22, 18)
        btn_min.get_style_context().add_class("flat")
        btn_min.connect("clicked", lambda *a: self._toggle_visibility())

        hbox.pack_start(lbl,     True,  True,  0)
        hbox.pack_end(btn_min,   False, False, 2)
        return hbox

    # ── Fond ──────────────────────────────────────────────────────────────────

    def _draw_bg(self, widget, cr):
        w = widget.get_allocated_width(); h = widget.get_allocated_height(); r = 14
        cr.set_source_rgba(*BG_DARK, BG_ALPHA)
        _rr(cr, 0, 0, w, h, r); cr.fill()
        cr.set_source_rgba(*ACCENT, 0.22); cr.set_line_width(1)
        _rr(cr, 0, 0, w, h, r); cr.stroke()

    # ── Drag / boutons souris ─────────────────────────────────────────────────

    def _on_press(self, w, e):
        if e.button == 3:
            self._show_context_menu(e)
            return
        if e.button == 1:
            self._drag = True
            self._dx   = e.x_root - self.get_position()[0]
            self._dy   = e.y_root - self.get_position()[1]

    def _on_release(self, w, e):
        self._drag = False
        if e.button == 1:
            # Sauvegarde position
            x, y = self.get_position()
            self._cfg["sysmonitor"]["x"] = str(x)
            self._cfg["sysmonitor"]["y"] = str(y)
            save_config(self._cfg)

    def _on_motion(self, w, e):
        if self._drag:
            self.move(int(e.x_root - self._dx), int(e.y_root - self._dy))

    # ── Visibilité / icône ────────────────────────────────────────────────────

    def _toggle_visibility(self):
        if self._visible:
            self.hide()
            self._visible = False
        else:
            self.show_all()
            self.present()
            self._visible = True

    # ── Menu contextuel (clic droit) ──────────────────────────────────────────

    def _show_context_menu(self, event):
        menu = Gtk.Menu()

        # Réduire
        item_hide = Gtk.MenuItem(label="⊟  Réduire dans la barre")
        item_hide.connect("activate", lambda *a: self._toggle_visibility())
        menu.append(item_hide)
        menu.append(Gtk.SeparatorMenuItem())

        # Sous-menu Thème
        item_theme = Gtk.MenuItem(label="🎨  Thème couleur")
        sub = Gtk.Menu()
        for key, t in THEMES.items():
            item = Gtk.CheckMenuItem(label=t["name"])
            item.set_active(key == self._theme_key)
            item.connect("activate", self._on_theme_select, key)
            sub.append(item)
        item_theme.set_submenu(sub)
        menu.append(item_theme)
        menu.append(Gtk.SeparatorMenuItem())

        # Redémarrer
        item_restart = Gtk.MenuItem(label="↺  Redémarrer")
        item_restart.connect("activate", self._on_restart)
        menu.append(item_restart)
        menu.append(Gtk.SeparatorMenuItem())

        # À propos
        item_about = Gtk.MenuItem(label="ℹ  À propos")
        item_about.connect("activate", self._show_about)
        menu.append(item_about)
        menu.append(Gtk.SeparatorMenuItem())

        # Quitter
        item_quit = Gtk.MenuItem(label="✕  Quitter")
        item_quit.connect("activate", lambda *a: Gtk.main_quit())
        menu.append(item_quit)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_theme_select(self, item, key):
        if not item.get_active(): return
        self._theme_key = key
        apply_theme(key)
        self._cfg["sysmonitor"]["theme"] = key
        save_config(self._cfg)
        self.queue_draw()
        # Redessiner toutes les barres au prochain tick
        self._update()

    def _on_restart(self, *args):
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _show_about(self, *args):
        lines = [
            '<span font_desc="Monospace 8.5">',
            self._v("SysMonitor v3", ACCENT) + "  widget de bureau Linux Mint",
            "",
            self._k("Mise à jour")  + self._v("toutes les secondes"),
            self._k("Sparklines")   + self._v("60 secondes d'historique"),
            self._k("RAM")          + self._v("decode-dimms (SPD) ou dmidecode"),
            self._k("Disques")      + self._v("NVMe/SSD/HDD + températures"),
            self._k("VRAM")         + self._v("nvidia-smi -q"),
            self._k("Config")       + self._v("~/.config/sysmonitor/config.ini", TEXT_DIM),
            "",
            self._v("Clic droit    → menu contextuel", TEXT_DIM),
            self._v("—  (bouton)   → réduire en icône", TEXT_DIM),
            self._v("Drag          → déplacer", TEXT_DIM),
            "</span>",
        ]
        if self._popup: self._popup.destroy()
        self._popup = DetailPopup("◈ À PROPOS", "\n".join(lines), self)

    # ── Markup helpers ────────────────────────────────────────────────────────

    def _mk(self, text, color=None, size=9, bold=False):
        c = color or TEXT_MAIN
        b = "Bold " if bold else ""
        return '<span font_desc="Monospace {}{}" foreground="{}">{}</span>'.format(b, size, hx(c), text)

    def _v(self, val, col=None):
        return '<span foreground="{}">{}</span>'.format(hx(col or ACCENT), val)

    def _k(self, s, w=22):
        return '<span foreground="{}">{:<{}}</span>'.format(hx(TEXT_DIM), s, w)

    # ── Mise à jour principale ────────────────────────────────────────────────

    def _update(self):
        self._update_cpu()
        self._update_gpu()
        self._update_ram()
        self._update_disks()
        self._update_net()
        return True

    def _update_disk_temps(self):
        """Lance la récupération des températures en arrière-plan (non bloquant)."""
        if self._disk_cache:
            import threading
            def _bg():
                enrich_disk_temps(self._disk_cache)
                GLib.idle_add(self._update_disks)
            threading.Thread(target=_bg, daemon=True).start()
        return True

    # ── CPU ───────────────────────────────────────────────────────────────────

    def _update_cpu(self):
        info = get_cpu_info()
        pct  = info["percent"]
        temp = info.get("temp_avg")
        freq = info.get("freq")
        self._hist_cpu.append(pct)

        t_str = "{:.0f}°C".format(temp) if temp is not None else "—"
        f_str = "{:.2f} GHz".format(freq.current/1000) if freq else ""
        main  = self._mk("{:.0f}%".format(pct), load_color(pct), 14, True)
        main += "  " + self._mk(t_str, temp_color(temp), 10)
        if f_str: main += "  " + self._mk(f_str, TEXT_DIM, 8)
        self._cpu_sec.set_main(main)
        self._cpu_sec.set_bar(pct/100, load_color(pct))
        s = info.get("model","")
        self._cpu_sec.set_sub(self._mk((s[:36]+"…" if len(s)>36 else s), TEXT_DIM, 7))
        self._cpu_sec.refresh_spark()

    def _show_cpu_detail(self):
        if self._popup: self._popup.destroy()
        info = get_cpu_info()
        freq = info.get("freq")
        f_cur = "{:.2f} GHz".format(freq.current/1000) if freq else "N/A"
        f_max = "{:.2f} GHz".format(freq.max/1000)     if freq and freq.max else "N/A"
        f_min = "{:.2f} GHz".format(freq.min/1000)     if freq and freq.min else "N/A"
        v = self._v; k = self._k
        cores_str = "{} physiques / {} logiques".format(
            info["cores_physical"], info["cores_logical"])
        lines = ['<span font_desc="Monospace 8.5">',
                 k("Modèle")        + v(info.get("model","?"), TEXT_MAIN),
                 k("Cœurs")         + v(cores_str),
                 k("Fréq. courante")+ v(f_cur),
                 k("Fréq. min/max") + v("{} / {}".format(f_min, f_max), TEXT_DIM),
                 k("Charge globale")+ v("{:.1f}%".format(info["percent"]),
                                        load_color(info["percent"]))]
        for i, p in enumerate(info.get("per_core", [])):
            lines.append(k("  Core {}".format(i)) + v("{:.0f}%".format(p), load_color(p)))
        if info.get("temps"):
            lines.append(k("Températures"))
            for nm, t in info["temps"].items():
                lines.append(k("  {}".format(nm)) + v("{:.1f}°C".format(t), temp_color(t)))
        lines.append("</span>")
        self._popup = DetailPopup("▣ PROCESSEUR", "\n".join(lines), self)

    # ── GPU ───────────────────────────────────────────────────────────────────

    def _update_gpu(self):
        self._gpu_tick += 1
        if self._gpu_tick % 2 == 0 or self._gpu_cache is None:
            self._gpu_cache = get_gpu_info()
        g = self._gpu_cache

        if g is None:
            self._hist_gpu.append(0.0)
            self._gpu_sec.set_main(self._mk("Non détecté", TEXT_DIM))
            self._gpu_sec.set_bar(0)
            self._gpu_sec.set_sub(self._mk("nvidia-smi / rocm-smi introuvable", TEXT_DIM, 7))
            self._vram_sec.set_main(self._mk("—", TEXT_DIM))
            self._vram_sec.set_bar(0); self._vram_sec.set_sub("")
            return

        pct = g["util"]; temp = g["temp"]
        self._hist_gpu.append(pct)
        vram_u = g["vram_used"]; vram_t = g["vram_total"]

        main  = self._mk("{:.0f}%".format(pct), load_color(pct), 14, True)
        main += "  " + self._mk("{:.0f}°C".format(temp), temp_color(temp), 10)
        self._gpu_sec.set_main(main)
        self._gpu_sec.set_bar(pct/100, load_color(pct))
        s = g["model"]
        self._gpu_sec.set_sub(self._mk((s[:36]+"…" if len(s)>36 else s), TEXT_DIM, 7))
        self._gpu_sec.refresh_spark()

        if vram_t > 0:
            ratio    = vram_u / vram_t
            vram_str = "{} / {}".format(human_gb(vram_u), human_gb(vram_t))
        else:
            ratio = 0; vram_str = "{:.0f}%".format(vram_u)
        vmain  = self._mk("{:.0f}%".format(ratio*100), load_color(ratio*100), 14, True)
        vmain += "  " + self._mk(vram_str, ACCENT3, 9)
        self._vram_sec.set_main(vmain)
        self._vram_sec.set_bar(ratio, ACCENT3)
        self._vram_sec.set_sub(self._mk(
            "{}  Pilote {}  GPU {}".format(g["vendor"], g["driver"], g["clock"]),
            TEXT_DIM, 7))

    def _show_gpu_detail(self):
        if self._popup: self._popup.destroy()
        g = self._gpu_cache
        if g is None: return
        v = self._v; k = self._k
        vt = g["vram_total"]; vu = g["vram_used"]
        vs = "{} / {}".format(human_gb(vu), human_gb(vt)) if vt > 0 else "{:.0f}%".format(vu)
        lines = ['<span font_desc="Monospace 8.5">',
                 k("Modèle")      + v(g["model"], TEXT_MAIN),
                 k("Vendor")      + v(g["vendor"]),
                 k("Pilote")      + v(g["driver"], TEXT_DIM),
                 k("Horloge GPU") + v(g["clock"]),
                 k("Utilisation") + v("{:.1f}%".format(g["util"]), load_color(g["util"])),
                 k("Température") + v("{:.1f}°C".format(g["temp"]), temp_color(g["temp"])),
                 k("VRAM")        + v(vs, ACCENT3),
                 '</span>']
        self._popup = DetailPopup("◈ GPU", "\n".join(lines), self)

    def _show_vram_detail(self):
        if self._popup: self._popup.destroy()
        g = self._gpu_cache
        if g is None: return
        d = get_vram_detail(g.get("vendor","NVIDIA"))
        v = self._v; k = self._k
        lines = ['<span font_desc="Monospace 8.5">']
        if d.get("type") and d["type"] != "N/A":
            lines.append(k("Type mémoire") + v(d["type"], TEXT_MAIN))
        if d.get("fb_total"):
            lines.append(k("Taille VRAM")  + v(d["fb_total"], TEXT_MAIN))
        if d.get("fb_used"):
            lines.append(k("Utilisée")     + v(d["fb_used"], ACCENT3))
        if d.get("fb_free"):
            lines.append(k("Libre")        + v(d["fb_free"]))
        if g.get("vendor") == "NVIDIA":
            if d.get("bar1_total") and d["bar1_total"] != "N/A":
                lines += ["", k("BAR1 (aperture)") + v(d["bar1_total"], TEXT_DIM)]
            if d.get("bar1_used") and d["bar1_used"] != "N/A":
                lines.append(k("BAR1 utilisé") + v(d["bar1_used"], TEXT_DIM))
            if d.get("mem_clock") and d["mem_clock"] != "N/A":
                lines += ["", k("Horloge mémoire") + v(d["mem_clock"])]
            if d.get("bus_width") and d["bus_width"] != "N/A":
                lines.append(k("Bus") + v(d["bus_width"] + " bits"))
            if d.get("ecc_current") and d["ecc_current"] != "N/A":
                ecc_col = ACCENT if "Disabled" in d["ecc_current"] else WARN
                lines += ["",
                          k("ECC actuel")  + v(d["ecc_current"], ecc_col),
                          k("ECC pending") + v(d.get("ecc_pending","N/A"), TEXT_DIM)]
            if d.get("cuda") and d["cuda"] != "N/A":
                lines += ["", k("CUDA version") + v(d["cuda"])]
            if d.get("pcie_gen") and d["pcie_gen"] != "N/A":
                lines.append(k("PCIe Gen / Width") + v(
                    "{} / {}".format(d["pcie_gen"], d.get("pcie_width","?"))))
        if not d or (not d.get("type") and not d.get("fb_total")):
            lines += [v("Données non disponibles", WARN),
                      v("(nvidia-smi -q requis)", TEXT_DIM)]
        lines.append("</span>")
        self._popup = DetailPopup("▦ VRAM — DÉTAILS", "\n".join(lines), self)

    # ── RAM ───────────────────────────────────────────────────────────────────

    def _update_ram(self):
        ram  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        ratio = ram.used / ram.total
        main  = self._mk("{:.0f}%".format(ratio*100), load_color(ratio*100), 14, True)
        main += "  " + self._mk("{} / {}".format(
            fmt_bytes(ram.used), fmt_bytes(ram.total)), ACCENT, 9)
        self._ram_sec.set_main(main)
        self._ram_sec.set_bar(ratio, ACCENT)
        self._ram_sec.set_sub(self._mk(
            "Swap {:.0f}%  ({}/{})".format(
                swap.percent, fmt_bytes(swap.used), fmt_bytes(swap.total)),
            TEXT_DIM, 7))

    def _show_ram_detail(self):
        if self._popup: self._popup.destroy()
        ram  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        d    = get_ram_detail()
        v = self._v; k = self._k

        lines = ['<span font_desc="Monospace 8.5">',
                 v("── Utilisation en temps réel ──────────────", TEXT_DIM),
                 k("RAM totale")    + v(fmt_bytes(ram.total), TEXT_MAIN),
                 k("Utilisée")      + v(fmt_bytes(ram.used), load_color(ram.percent)),
                 k("Disponible")    + v(fmt_bytes(ram.available)),
                 k("Buffers+cache") + v(fmt_bytes(
                     ram.buffers + getattr(ram,"cached",0)), TEXT_DIM),
                 "",
                 k("Swap total")    + v(fmt_bytes(swap.total), TEXT_DIM),
                 k("Swap utilisé")  + v(fmt_bytes(swap.used), load_color(swap.percent)),
                 ""]

        if d.get("need_sudo"):
            lines += [
                v("── Physique : accès refusé ────────────────", WARN),
                v("Ajoutez dans /etc/sudoers (visudo) :", TEXT_DIM),
                v("  USER ALL=(ALL) NOPASSWD: /usr/sbin/dmidecode", ACCENT),
                v("  USER ALL=(ALL) NOPASSWD: /usr/sbin/decode-dimms", ACCENT),
                v("(remplacez USER par votre nom d'utilisateur)", TEXT_DIM),
                v("Le script install.sh configure cela automatiquement.", TEXT_DIM),
            ]
        elif d.get("slots"):
            src = d.get("source","?")
            nb  = len(d["slots"])
            lines.append(v("── {} barrette(s) — source: {} ─".format(nb, src), TEXT_DIM))
            for i, s in enumerate(d["slots"]):
                loc = s.get("locator","Slot {}".format(i+1))
                lines += ["", v("  {} — {}".format(i+1, loc), ACCENT3)]
                type_str = (s.get("type","?") + "  " + s.get("form","")).strip()
                lines.append("  " + k("Type")        + v(type_str, TEXT_MAIN))
                lines.append("  " + k("Capacité")    + v(s.get("size","?"), TEXT_MAIN))
                freq = s.get("configured") or s.get("speed","N/A")
                lines.append("  " + k("Fréquence")   + v(freq))
                cl     = s.get("cl","N/A")
                cl_col = WARN if s.get("cl_estimated") else ACCENT
                cl_sfx = "  (estimé)" if s.get("cl_estimated") else \
                         ("  ✓ SPD" if s.get("source") == "SPD" else "")
                lines.append("  " + k("Latence CAS") + v(cl + cl_sfx, cl_col))
                if s.get("rank"):
                    lines.append("  " + k("Rang") + v(s["rank"], TEXT_DIM))
                mfr = s.get("manufacturer","")
                if mfr and mfr not in ("Unknown","Not Specified",""):
                    lines.append("  " + k("Fabricant") + v(mfr, TEXT_DIM))
                part = s.get("part","")
                if part and part not in ("Unknown","Not Specified",""):
                    lines.append("  " + k("Référence") + v(part, TEXT_DIM))
                if s.get("voltage"):
                    lines.append("  " + k("Tension") + v(s["voltage"], TEXT_DIM))
        else:
            lines.append(v("Aucun slot détecté par dmidecode.", WARN))

        lines.append("</span>")
        self._popup = DetailPopup("▤ RAM — DÉTAILS PHYSIQUES", "\n".join(lines), self)

    # ── Disques ───────────────────────────────────────────────────────────────

    def _update_disks(self):
        self._disk_sec.clear_rows()
        self._disk_tick += 1

        # Refresh liste disques toutes les 60 s, en arrière-plan
        if self._disk_tick % 60 == 1 or not self._disk_cache:
            if not getattr(self, '_disk_refresh_running', False):
                self._disk_refresh_running = True
                import threading
                def _bg():
                    new_cache = get_disk_info()
                    # Réinjecter les températures déjà connues pour éviter un flash à None
                    old = {d["base_dev"]: d.get("temp") for d in self._disk_cache}
                    for d in new_cache:
                        if d["temp"] is None:
                            d["temp"] = old.get(d["base_dev"])
                    self._disk_cache = new_cache
                    self._disk_refresh_running = False
                threading.Thread(target=_bg, daemon=True).start()

        disks = self._disk_cache
        if not disks:
            self._disk_sec.set_main(self._mk("Aucun disque détecté", TEXT_DIM))
            self._disk_sec.set_bar(0)
            self._disk_sec.set_sub("")
            return

        # ── Résumé global ─────────────────────────────────────────────────────
        # Total = somme des tailles physiques des disques (pas des partitions)
        tot_t = sum(d["total_bytes"] for d in disks)
        tot_u = sum(d["used_bytes"]  for d in disks)
        ratio = tot_u / tot_t if tot_t else 0
        main  = self._mk("{:.0f}%".format(ratio * 100), load_color(ratio*100), 14, True)
        main += "  " + self._mk(
            "{} / {}".format(fmt_bytes(tot_u), fmt_bytes(tot_t)), ACCENT, 9)
        self._disk_sec.set_main(main)
        self._disk_sec.set_bar(ratio, load_color(ratio*100))
        self._disk_sec.set_sub("")

        # ── Une ligne par disque physique ─────────────────────────────────────
        COLORS = [ACCENT, ACCENT2, WARN, ACCENT3, (0.6, 0.9, 0.4)]
        for i, d in enumerate(disks):
            col    = COLORS[i % len(COLORS)]
            dtype  = d.get("disk_type", "?")
            temp   = d.get("temp")
            t_str  = "  {:.0f}\u00b0C".format(temp) if temp is not None else ""
            name   = d["disk_name"]          # sda / nvme0n1 / sdb
            model  = d.get("disk_model","")
            pct    = d["percent"]

            # Ligne 1 : nom (10)  type (4)
            # Ligne 2 : utilisé / total  %  température
            # Ligne 3 : modèle  |  points de montage (tronqué à 38 car.)
            MAX = 38
            line1 = "{:<10}  {:<4}".format(name, dtype)
            line2 = "  {} / {}  {:.0f}%{}".format(
                fmt_bytes(d["used_bytes"]), fmt_bytes(d["total_bytes"]),
                pct, t_str)

            mnts = sorted(p["mountpoint"] for p in d["partitions"])
            mnts_str = "  ".join(mnts[:4]) + ("\u2026" if len(mnts) > 4 else "")
            model_short = (model[:24] + "\u2026" if len(model) > 24 else model)
            line3_parts = []
            if model_short: line3_parts.append(model_short)
            if mnts_str:    line3_parts.append(mnts_str)
            line3_raw = "  |  ".join(line3_parts)
            if len(line3_raw) > MAX:
                line3_raw = line3_raw[:MAX - 1] + "\u2026"
            line3 = "  " + line3_raw if line3_raw else ""

            body = line1 + "\n" + line2 + ("\n" + line3 if line3 else "")
            mu = '<span font_desc="Monospace 7" foreground="{}">{}</span>'.format(
                hx(TEXT_DIM), body)
            self._disk_sec.add_row(mu, pct / 100, col)



    # ── Réseau ────────────────────────────────────────────────────────────────

    def _update_net(self):
        info = get_net_info(self._net_prev_counters, interval=1.0)
        self._net_prev_counters = info["counters"]
        self._net_info_cache    = info

        rx_bps = info["total_rx_bps"]
        tx_bps = info["total_tx_bps"]

        # Accumulation session
        self._net_session_rx += rx_bps   # octets/s × 1 s = octets
        self._net_session_tx += tx_bps

        # Historiques pour sparkline
        self._hist_rx.append(rx_bps)
        self._hist_tx.append(tx_bps)
        self._dual_spark_widget.refresh()

        # ── Ligne principale ──────────────────────────────────────────────────
        # Débit actuel dominant (DL si supérieur, sinon UL)
        if rx_bps >= tx_bps:
            main = self._mk("↓ " + fmt_speed(rx_bps), ACCENT,  13, True)
            main += "  " + self._mk("↑ " + fmt_speed(tx_bps), ACCENT2, 10)
        else:
            main = self._mk("↑ " + fmt_speed(tx_bps), ACCENT2, 13, True)
            main += "  " + self._mk("↓ " + fmt_speed(rx_bps), ACCENT,  10)
        self._net_sec.set_main(main)

        # Barre : activité relative sur le pic de la session
        peak = max(max(self._hist_rx), max(self._hist_tx), 1.0)
        self._net_sec.set_bar((rx_bps + tx_bps) / 2 / peak, ACCENT)

        # ── Ligne secondaire : cumuls ─────────────────────────────────────────
        # Cumul système (depuis boot) = compteur psutil global
        try:
            boot_c = psutil.net_io_counters()
            sys_rx = boot_c.bytes_recv
            sys_tx = boot_c.bytes_sent
        except Exception:
            sys_rx = sys_tx = 0

        sub = "session ↓{} ↑{}   boot ↓{} ↑{}".format(
            fmt_vol(self._net_session_rx), fmt_vol(self._net_session_tx),
            fmt_vol(sys_rx), fmt_vol(sys_tx))
        self._net_sec.set_sub(self._mk(sub, TEXT_DIM, 7))

    def _show_net_detail(self):
        if self._popup: self._popup.destroy()
        info = self._net_info_cache
        if not info:
            return
        v = self._v; k = self._k

        try:
            boot_c = psutil.net_io_counters()
            sys_rx = boot_c.bytes_recv
            sys_tx = boot_c.bytes_sent
        except Exception:
            sys_rx = sys_tx = 0

        lines = ['<span font_desc="Monospace 8.5">',
                 v("── Cumuls ─────────────────────────────────", TEXT_DIM),
                 k("Session  ↓ reçu")  + v(fmt_vol(self._net_session_rx), ACCENT),
                 k("Session  ↑ envoyé")+ v(fmt_vol(self._net_session_tx), ACCENT2),
                 k("Boot     ↓ reçu")  + v(fmt_vol(sys_rx), TEXT_MAIN),
                 k("Boot     ↑ envoyé")+ v(fmt_vol(sys_tx), TEXT_DIM),
                 ""]

        ifaces = info.get("interfaces", [])
        if ifaces:
            lines.append(v("── Interfaces ─────────────────────────────", TEXT_DIM))
        for ifc in ifaces:
            lines += [
                "",
                v("  {}".format(ifc["name"]), ACCENT3),
                "  " + k("↓ débit")   + v(fmt_speed(ifc["rx_bps"]), ACCENT),
                "  " + k("↑ débit")   + v(fmt_speed(ifc["tx_bps"]), ACCENT2),
                "  " + k("↓ total")   + v(fmt_vol(ifc["rx_total"]), TEXT_MAIN),
                "  " + k("↑ total")   + v(fmt_vol(ifc["tx_total"]), TEXT_DIM),
                "  " + k("paquets ↓↑")+ v("{} / {}".format(
                    ifc["rx_packets"], ifc["tx_packets"]), TEXT_DIM),
            ]
            if ifc["rx_errors"] or ifc["tx_errors"] or ifc["rx_drop"] or ifc["tx_drop"]:
                lines.append("  " + k("erreurs/drops") + v(
                    "err {}/{} drop {}/{}".format(
                        ifc["rx_errors"], ifc["tx_errors"],
                        ifc["rx_drop"],   ifc["tx_drop"]), WARN))

        lines.append("</span>")
        self._popup = DetailPopup("⇅ RÉSEAU — DÉTAILS", "\n".join(lines), self)


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = SysMonitor()
    app.connect("destroy", Gtk.main_quit)
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
