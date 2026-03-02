#!/bin/bash
# ─── SysMonitor v3 — Script d'installation ───────────────────────────────────
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/sysmonitor"
AUTOSTART="$HOME/.config/autostart"
SERVICE_DIR="$HOME/.config/systemd/user"

echo ""
echo "  ◈ SysMonitor v3 — Installation"
echo "  ─────────────────────────────────────────────"

# ── 1. Dépendances APT ────────────────────────────────────────────────────────
echo ""
echo "  [1/6] Paquets système..."
PKGS_NEEDED=""
for pkg in python3-gi python3-gi-cairo gir1.2-gtk-3.0 dmidecode smartmontools i2c-tools; do
    if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        PKGS_NEEDED="$PKGS_NEEDED $pkg"
    fi
done
# AppIndicator3
if ! dpkg -l gir1.2-ayatanaappindicator3-0.1 2>/dev/null | grep -q "^ii"; then
    if ! dpkg -l gir1.2-appindicator3-0.1 2>/dev/null | grep -q "^ii"; then
        PKGS_NEEDED="$PKGS_NEEDED gir1.2-ayatanaappindicator3-0.1"
    fi
fi

if [ -n "$PKGS_NEEDED" ]; then
    echo "       Installation :$PKGS_NEEDED"
    sudo apt-get install -y $PKGS_NEEDED
else
    echo "       Tous les paquets présents ✓"
fi

# ── 2. psutil ─────────────────────────────────────────────────────────────────
echo ""
echo "  [2/6] psutil..."
if ! python3 -c "import psutil" 2>/dev/null; then
    pip3 install psutil --break-system-packages 2>/dev/null || \
    sudo apt-get install -y python3-psutil
    echo "       psutil installé ✓"
else
    echo "       psutil ✓"
fi

# ── 3. decode-dimms (i2c-tools) ───────────────────────────────────────────────
echo ""
echo "  [3/6] decode-dimms (SPD pour CAS Latency exact)..."
if command -v decode-dimms &>/dev/null; then
    echo "       decode-dimms ✓"
elif [ -f /usr/share/doc/i2c-tools/examples/decode-dimms ]; then
    sudo cp /usr/share/doc/i2c-tools/examples/decode-dimms /usr/local/bin/decode-dimms
    sudo chmod +x /usr/local/bin/decode-dimms
    echo "       decode-dimms installé depuis i2c-tools ✓"
else
    # Chercher dans les archives .gz
    if [ -f /usr/share/doc/i2c-tools/examples/decode-dimms.gz ]; then
        gunzip -c /usr/share/doc/i2c-tools/examples/decode-dimms.gz | \
            sudo tee /usr/local/bin/decode-dimms > /dev/null
        sudo chmod +x /usr/local/bin/decode-dimms
        echo "       decode-dimms extrait et installé ✓"
    else
        echo "       ⚠ decode-dimms non trouvé (CL sera estimé depuis dmidecode)"
    fi
fi

# Charger le module eeprom pour SPD
if lsmod | grep -q eeprom; then
    echo "       Module eeprom déjà chargé ✓"
else
    sudo modprobe eeprom 2>/dev/null && echo "       Module eeprom chargé ✓" || \
        echo "       ⚠ Module eeprom non disponible (normal sur DDR4/5)"
fi

# ── 4. Règles sudoers ─────────────────────────────────────────────────────────
echo ""
echo "  [4/6] Règles sudoers (sans mot de passe)..."
SUDOERS_FILE="/etc/sudoers.d/sysmonitor"
DMIDECODE_PATH="$(which dmidecode 2>/dev/null || echo /usr/sbin/dmidecode)"
SMARTCTL_PATH="$(which smartctl   2>/dev/null || echo /usr/sbin/smartctl)"
DECODE_DIMMS_PATH="$(which decode-dimms 2>/dev/null || echo /usr/local/bin/decode-dimms)"

SUDOERS_CONTENT="$USER ALL=(ALL) NOPASSWD: $DMIDECODE_PATH
$USER ALL=(ALL) NOPASSWD: $SMARTCTL_PATH
$USER ALL=(ALL) NOPASSWD: $DECODE_DIMMS_PATH"

if sudo bash -c "printf '%s\n' '$SUDOERS_CONTENT' > '$SUDOERS_FILE' && \
    chmod 440 '$SUDOERS_FILE' && visudo -c -f '$SUDOERS_FILE'" 2>/dev/null; then
    echo "       sudoers configuré ✓ ($SUDOERS_FILE)"
else
    echo "       ⚠ Impossible d'écrire dans /etc/sudoers.d"
    echo "       Ajoutez manuellement via visudo :"
    echo "$SUDOERS_CONTENT" | sed 's/^/         /'
fi

# ── 5. Copie & service ────────────────────────────────────────────────────────
echo ""
echo "  [5/6] Installation des fichiers..."
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/sysmonitor.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/sysmonitor.py"
echo "       Fichiers copiés → $INSTALL_DIR ✓"

mkdir -p "$SERVICE_DIR"
cat > "$SERVICE_DIR/sysmonitor.service" <<EOF
[Unit]
Description=SysMonitor v3 Desktop Widget
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=python3 $INSTALL_DIR/sysmonitor.py
Restart=on-failure
RestartSec=3
Environment=DISPLAY=:0
Environment=XAUTHORITY=%h/.Xauthority

[Install]
WantedBy=graphical-session.target
EOF
systemctl --user daemon-reload
systemctl --user enable sysmonitor.service 2>/dev/null || true
echo "       Service systemd activé ✓"

# ── 6. Autostart desktop ──────────────────────────────────────────────────────
echo ""
echo "  [6/6] Autostart..."
mkdir -p "$AUTOSTART"
cat > "$AUTOSTART/sysmonitor.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SysMonitor
Comment=Widget système v3
Exec=python3 $INSTALL_DIR/sysmonitor.py
Icon=utilities-system-monitor
X-GNOME-Autostart-enabled=true
EOF
echo "       Autostart créé ✓"

echo ""
echo "  ─────────────────────────────────────────────"
echo "  ✓ SysMonitor v3 installé !"
echo ""
echo "  DÉMARRAGE"
echo "    systemctl --user start sysmonitor"
echo "    # ou immédiatement :"
echo "    python3 $INSTALL_DIR/sysmonitor.py &"
echo ""
echo "  CONTRÔLES"
echo "    — (bouton titre)     → réduire en icône"
echo "    Clic droit           → menu (thèmes, redémarrer, à propos, quitter)"
echo "    Clic gauche drag     → déplacer (position sauvegardée)"
echo "    Clic CPU / GPU       → sparkline + détails"
echo "    Clic VRAM / RAM      → détails physiques complets"
echo ""
echo "  CONFIG   ~/.config/sysmonitor/config.ini"
echo "  LOGS     journalctl --user -u sysmonitor -f"
echo "  ─────────────────────────────────────────────"
echo ""
