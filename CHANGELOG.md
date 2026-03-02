# Changelog

## [3.0.0] — 2025

### Ajouté
- Section **Réseau** avec double sparkline ↓DL / ↑UL, cumul session et boot
- **Sparklines** CPU et GPU (historique 60 secondes)
- **decode-dimms** — lecture SPD i²C pour CAS Latency exact (DDR3/4)
- **smartctl** — type NVMe/SSD/HDD et température par disque physique
- `lsblk` — taille physique réelle des disques (plus partitions mal calculées)
- **4 thèmes couleur** — Vert menthe, Bleu azur, Ambre doré, Violet néon
- **AppIndicator3** — icône dans la barre de notification système
- **Bouton `—`** — réduire le widget en icône
- **Menu clic droit** — Réduire / Thème / Redémarrer / À propos / Quitter
- Position du widget sauvegardée dans `~/.config/sysmonitor/config.ini`
- Service **systemd utilisateur** avec redémarrage automatique
- Détail VRAM étendu : type mémoire, BAR1, horloge, bus, ECC, PCIe, CUDA

### Corrigé
- Affichage disques : taille physique réelle via `lsblk` au lieu du max des partitions
- Filtrage correct des pseudo-systèmes (snap, tmpfs, squashfs, loop…)
- Modèle du disque affiché sous chaque ligne

## [2.0.0]

### Ajouté
- Popup détails RAM physique via `dmidecode` (type, CL estimé, fréquence, fabricant)
- Popup détails VRAM via `nvidia-smi -q` (type mémoire, bus, ECC)
- Sections RAM et VRAM cliquables
- Règles sudoers configurées automatiquement par `install.sh`

## [1.0.0]

### Initial
- Widget GTK3 semi-transparent, mise à jour 1 seconde
- Sections CPU, GPU, VRAM, RAM, Stockage
- Popup détails CPU et GPU au clic
- Service systemd + autostart desktop
- Drag & drop pour repositionner
