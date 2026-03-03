# Changelog

## [4.1.0] — 2025

### Ajouté
- **Sections repliables** — chaque section dispose d'un bouton `▾/▸` dans son en-tête pour masquer/afficher son contenu individuellement
  - L'en-tête (icône + titre) reste toujours visible même replié
  - La popup de détail ne se déclenche pas sur une section repliée
  - L'état replié/déplié de chaque section est **persisté** dans `~/.config/sysmonitor/config.ini` (section `[collapsed]`) et restauré au prochain lancement

### Corrigé
- **Redimensionnement automatique** du panneau après repli ou dépli d'une section — `resize(310, 1)` déclenché via `GLib.idle_add` pour laisser GTK finaliser le hide/show avant recalcul

---

## [4.0.0] — 2025

### Ajouté
- Section **SMART** — indicateur de santé global par disque (OK / WARN / CRIT) via `smartctl`
  - Surveillance des attributs critiques : Reallocated Sectors, Pending Sectors, Uncorrectable Errors, Command Timeout…
  - Rafraîchissement en arrière-plan toutes les 60 secondes (non bloquant)
  - Popup détail : statut PASSED/FAILED + valeurs RAW des attributs critiques par disque
- Section **Processus Top CPU** — affichage en temps réel du processus le plus gourmand
  - Top 5 consultables via popup détail (PID, nom, % CPU)
- **Popup d'alerte automatique** — notification non intrusive en coin inférieur droit
  - Déclenchée si un disque passe en WARN ou CRIT (SMART)
  - Déclenchée si un processus dépasse 90 % de CPU
  - Anti-spam : une seule alerte par type par session, auto-fermeture après 8 secondes
- **Mode replié** — bouton `▐` dans la barre de titre pour réduire le widget en barre verticale compacte (70 px)
  - Affiche CPU %, RAM %, débits réseau ↓/↑ avec mini-barres de progression colorées
  - Sparkline CPU 60 secondes intégrée
  - Clic sur la barre pour déplier le panneau complet
- **Nombre de cœurs actifs** affiché dans la section CPU (cœurs à charge > 0 %)
  - Visible dans le sous-titre du widget principal
  - Détaillé dans le popup CPU avec colorisation selon le ratio

### Corrigé
- Popup d'alerte automatique : anti-spam défaillant corrigé (`_alert_titles` initialisé dans `__init__`)
- Popup réseau : n'apparaît plus automatiquement au démarrage (déclenchement uniquement sur clic)
- `clear_rows()` : ne supprime plus accidentellement la DualSparkline réseau lors du rafraîchissement des disques

---

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

---

## [2.0.0]

### Ajouté
- Popup détails RAM physique via `dmidecode` (type, CL estimé, fréquence, fabricant)
- Popup détails VRAM via `nvidia-smi -q` (type mémoire, bus, ECC)
- Sections RAM et VRAM cliquables
- Règles sudoers configurées automatiquement par `install.sh`

---

## [1.0.0]

### Initial
- Widget GTK3 semi-transparent, mise à jour 1 seconde
- Sections CPU, GPU, VRAM, RAM, Stockage
- Popup détails CPU et GPU au clic
- Service systemd + autostart desktop
- Drag & drop pour repositionner
