# ◈ SysMonitor

> Widget de bureau semi-transparent pour **Linux Mint** (et distributions Debian/Ubuntu).  
> Affichage temps réel de CPU, GPU, VRAM, RAM, stockage, réseau, santé disques et processus — mis à jour toutes les secondes.

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![GTK](https://img.shields.io/badge/GTK-3.0-4A86CF?logo=gnome&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-Mint%20%2F%20Ubuntu%20%2F%20Debian-87CF3E?logo=linux&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Fonctionnalités

| Section | Informations affichées | Clic |
|---------|------------------------|------|
| **CPU** | Charge %, température, fréquence, cœurs actifs / total | Modèle, cœurs physiques/logiques, cœurs actifs, charge par cœur, températures par capteur |
| **GPU** | Charge %, température | Modèle, vendor, pilote, horloge |
| **VRAM** | % utilisé, Mo utilisé / total | Type GDDR, taille, BAR1, horloge mémoire, bus, ECC, PCIe, CUDA |
| **RAM** | % utilisé, Mo utilisé / total, swap | Barrettes physiques : type DDR, capacité, fréquence, **CAS Latency**, fabricant, référence, tension |
| **Stockage** | Total utilisé / total physique | Disques physiques : NVMe/SSD/HDD, modèle, partitions, température |
| **Réseau** | ↓ DL / ↑ UL en temps réel, cumuls session + boot | Débit par interface, totaux, paquets, erreurs |
| **SMART** | Santé globale ✔ OK / ⚠ WARN / ✖ CRIT par disque | Statut PASSED/FAILED, valeurs RAW des attributs critiques (reallocated, pending…) |
| **Processus Top CPU** | Processus le plus gourmand (nom + %) | Top 5 avec PID, nom et % CPU coloré |

### Autres fonctionnalités

- **Sections repliables** — chaque section se plie/déplie individuellement via `▾/▸`, état persisté entre les sessions
- **Sparklines** — graphes d'historique 60 secondes pour CPU, GPU et réseau (double courbe ↓/↑)
- **4 thèmes couleur** — Vert menthe, Bleu azur, Ambre doré, Violet néon
- **Semi-transparent** — fond sombre avec alpha configurable, bordure lumineuse
- **Icône système** — AppIndicator3, masquer/afficher d'un clic
- **Bouton `—`** — réduire dans la barre de notification
- **Bouton `▐`** — replier en barre verticale compacte (voir ci-dessous)
- **Alertes automatiques** — popup non intrusive en cas d'anomalie SMART ou de pic CPU
- **Menu clic droit** — Réduire / Thème / Redémarrer / À propos / Quitter
- **Position mémorisée** — sauvegardée dans `~/.config/sysmonitor/config.ini`
- **Service systemd** — démarrage automatique avec la session, redémarrage en cas de crash

---

## Mode replié (barre compacte)

Le bouton `▐` dans la barre de titre replie le panneau en une fine barre verticale de 70 px qui reste toujours visible sans encombrer l'écran. Elle affiche :

- **CPU %** et **RAM %** avec mini-barres de progression colorées
- **Débits réseau ↓/↑** instantanés
- **Sparkline CPU** sur les 60 dernières secondes

Un clic n'importe où sur la barre restitue le panneau complet.

---

## Alertes automatiques

SysMonitor peut afficher des notifications discrètes (coin inférieur droit, 8 secondes) sans intervention de l'utilisateur :

| Condition | Alerte |
|-----------|--------|
| Attribut SMART critique détecté (ex. Reallocated Sectors > 0) | ⚠ SMART — ALERTE |
| Attribut SMART très dégradé (valeur RAW > 10) | ✖ SMART — ALERTE CRITIQUE |
| Processus consommant ≥ 90 % CPU | ⚡ PROCESSUS — ALERTE CPU |

Chaque alerte ne s'affiche **qu'une seule fois par session** (anti-spam).

---

## Prérequis

### Système
- Linux Mint 20+ / Ubuntu 20.04+ / Debian 11+
- Python 3.8+
- Environnement de bureau avec session graphique (Cinnamon, MATE, XFCE…)

### Support GPU

| Vendor | Statut | Outil requis |
|--------|--------|--------------|
| **NVIDIA** | ✅ Complet — charge, température, VRAM, ECC, PCIe, CUDA… | `nvidia-smi` |
| **AMD** | ⚠️ Basique — charge et température uniquement | `rocm-smi` |
| **Intel Arc** | ❌ Non supporté | — |

> **Note AMD** : le code détecte `rocm-smi` mais le popup de détail VRAM
> n'a pas pu être validé faute de matériel. Les contributions sont les bienvenues !

### Paquets (installés automatiquement par `install.sh`)
```
python3-gi python3-gi-cairo gir1.2-gtk-3.0
gir1.2-ayatanaappindicator3-0.1
python3-psutil
dmidecode
i2c-tools
smartmontools
```

### Optionnel
- `nvidia-smi` — pour les GPU NVIDIA
- `rocm-smi` — pour les GPU AMD
- `decode-dimms` — pour le CAS Latency exact depuis le SPD des barrettes RAM

---

## Installation

### Installation automatique (recommandée)

```bash
git clone https://github.com/VOTRE_USERNAME/sysmonitor.git
cd sysmonitor
bash install.sh
systemctl --user start sysmonitor
```

Le script `install.sh` prend en charge automatiquement :
1. Installation des dépendances APT
2. Installation de `psutil` via pip
3. Installation et configuration de `decode-dimms`
4. Création des règles **sudoers** (sans mot de passe) pour `dmidecode`, `smartctl` et `decode-dimms`
5. Création et activation du **service systemd** utilisateur
6. Entrée **Autostart** pour le gestionnaire de session

### Installation manuelle

```bash
# 1. Dépendances
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    gir1.2-ayatanaappindicator3-0.1 dmidecode smartmontools i2c-tools
pip3 install psutil --break-system-packages

# 2. decode-dimms (CAS Latency exact)
sudo cp /usr/share/doc/i2c-tools/examples/decode-dimms /usr/local/bin/
sudo chmod +x /usr/local/bin/decode-dimms

# 3. Sudoers (pour dmidecode, smartctl, decode-dimms sans mot de passe)
sudo visudo -f /etc/sudoers.d/sysmonitor
# Ajoutez :
# votreuser ALL=(ALL) NOPASSWD: /usr/sbin/dmidecode
# votreuser ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
# votreuser ALL=(ALL) NOPASSWD: /usr/local/bin/decode-dimms

# 4. Lancement
python3 sysmonitor.py &
```

---

## Utilisation

### Contrôles

| Action | Effet |
|--------|-------|
| **Bouton `▾/▸`** (en-tête de section) | Replier / déplier le contenu de la section (état mémorisé) |
| **Bouton `▐`** (barre de titre) | Replier le widget en barre compacte verticale |
| **Clic sur la barre compacte** | Déplier le panneau complet |
| **Bouton `—`** (barre de titre) | Réduire le widget dans la barre de notification |
| **Icône dans la barre de notification** | Afficher / Masquer le widget |
| **Clic gauche + glisser** | Déplacer le widget (position sauvegardée automatiquement) |
| **Clic droit** | Ouvrir le menu contextuel |
| **Clic sur CPU** | Popup : détails processeur, cœurs actifs, charge par cœur, températures |
| **Clic sur GPU** | Popup : détails GPU, pilote |
| **Clic sur VRAM** | Popup : type mémoire, bus, ECC, PCIe, CUDA |
| **Clic sur RAM** | Popup : barrettes physiques, CAS Latency, fréquence, fabricant |
| **Clic sur RÉSEAU** | Popup : détails par interface, cumuls |
| **Clic sur SMART** | Popup : statut PASSED/FAILED et attributs critiques par disque |
| **Clic sur PROCESSUS** | Popup : top 5 consommateurs CPU avec PID |

### Menu clic droit

- **Réduire** — masque le widget (récupérable via l'icône système)
- **Thème couleur** — 4 thèmes disponibles, changement immédiat et sauvegardé
- **Redémarrer** — relance le processus (utile après une mise à jour)
- **À propos** — version et raccourcis
- **Quitter** — ferme le widget

---

## Configuration

Fichier : `~/.config/sysmonitor/config.ini`

```ini
[sysmonitor]
theme = green    # green | blue | amber | purple
x = 1580         # position horizontale (px)
y = 40           # position verticale (px)

[collapsed]
processeur = 0   # 1 = replié, 0 = déplié
gpu        = 0
vram       = 1
ram        = 0
stockage   = 0
réseau     = 0
smart      = 0
processus top cpu = 0
```

La position est mise à jour automatiquement après chaque déplacement. L'état replié de chaque section est mis à jour à chaque clic sur `▾/▸`.

---

## Gestion du service

```bash
# Démarrer
systemctl --user start sysmonitor

# Arrêter
systemctl --user stop sysmonitor

# Redémarrer
systemctl --user restart sysmonitor

# État
systemctl --user status sysmonitor

# Logs en direct
journalctl --user -u sysmonitor -f

# Désactiver le démarrage automatique
systemctl --user disable sysmonitor
```

---

## Notes techniques

### CAS Latency (RAM)

`decode-dimms` lit les puces **SPD (Serial Presence Detect)** des barrettes via le bus i²C :

- **DDR3** — CL exact généralement disponible ✓
- **DDR4 / DDR5** — l'accès i²C est souvent bloqué par le firmware UEFI pour des raisons de sécurité. Dans ce cas, le CL est **estimé** à partir de la fréquence (dmidecode) et affiché en orange avec la mention *(estimé)*.

### Santé disques (SMART)

`smartctl` interroge les attributs S.M.A.R.T. de chaque disque physique toutes les **60 secondes** en arrière-plan. Les attributs surveillés sont :

| ID | Attribut | Seuil d'alerte |
|----|----------|----------------|
| 5 | Reallocated Sectors Count | > 0 → WARN, > 10 → CRIT |
| 187 | Reported Uncorrectable Errors | > 0 → WARN |
| 188 | Command Timeout | > 0 → WARN |
| 196 | Reallocation Event Count | > 0 → WARN |
| 197 | Current Pending Sector Count | > 0 → WARN |
| 198 | Offline Uncorrectable | > 0 → WARN |

### Températures disques

Les températures S.M.A.R.T. sont rafraîchies toutes les **30 secondes** en arrière-plan pour ne pas bloquer l'interface.

### Cœurs CPU actifs

Un cœur est considéré **actif** dès que son utilisation instantanée est supérieure à 0 %. Le comptage est effectué via `psutil.cpu_percent(percpu=True)` à chaque tick d'une seconde.

### Réseau

- **Débit instantané** — delta des compteurs `psutil.net_io_counters()` sur 1 seconde
- **Cumul session** — accumulé depuis le lancement du widget
- **Cumul boot** — total système depuis le démarrage via les compteurs `psutil`
- Loopback (`lo`) et interfaces sans trafic ignorées automatiquement

### Thèmes

Les couleurs du thème actif (ACCENT, ACCENT2, ACCENT3) sont des variables globales réaffectées à la volée. Toutes les barres et sparklines se mettent à jour au prochain tick (1 s).

---

## Structure du projet

```
sysmonitor/
├── sysmonitor.py      # Application principale (GTK3, ~2300 lignes)
├── install.sh         # Script d'installation automatique
├── CHANGELOG.md       # Historique des versions
└── README.md          # Cette documentation
```

---

## Dépannage

**Le widget n'apparaît pas**
```bash
python3 sysmonitor.py   # lancer en console pour voir les erreurs
```

**AppIndicator3 non disponible**
```bash
sudo apt-get install gir1.2-ayatanaappindicator3-0.1
# ou pour les anciens systèmes :
sudo apt-get install gir1.2-appindicator3-0.1
```

**Températures CPU absentes**
```bash
sudo apt-get install lm-sensors
sudo sensors-detect --auto
```

**SMART indisponible**
```bash
sudo apt-get install smartmontools
# Vérifier la règle sudoers
sudo -n smartctl -H /dev/sda
```

**dmidecode ne retourne rien (RAM)**
```bash
# Vérifier que la règle sudoers est correcte
sudo -n dmidecode -t memory | head -20
```

**Le service ne démarre pas avec la session**
```bash
# Vérifier que systemd user est actif
systemctl --user status
# Vérifier la variable DISPLAY
echo $DISPLAY   # doit retourner :0 ou :1
```

---

## Licence

MIT — libre d'utilisation, modification et redistribution.

---

## Contributions

Les PR sont les bienvenues ! En particulier :
- Support des GPU Intel Arc (`intel_gpu_top`)
- Support `sensors` pour températures supplémentaires
- Portage Wayland (actuellement X11 uniquement via GTK3)
- Tests sur d'autres distributions (Fedora, Arch…)
