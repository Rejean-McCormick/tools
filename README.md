# Tools

Collection locale de petits outils et de ressources techniques.

Ce dépôt sert de racine commune pour plusieurs apps/scripts utilitaires, principalement orientés vers la manipulation de fichiers, la génération de dumps de code et la documentation d’architecture logicielle.

## Contenu du dépôt

```text
.
├── file_puller_v2.pyw
├── GitSink.bat
├── SmartDump.lnk
├── smart_dumper/
└── The-Senior-Architect_s-Codex/
```

## Apps et outils

### `smart_dumper/`

Application Python avec interface Tkinter pour générer des dumps de repositories.

Elle permet de sélectionner un dossier de code source, choisir un dossier de sortie, appliquer des règles d’exclusion, puis produire des volumes structurés destinés à être lus facilement par un humain ou par un assistant IA.

Fonctionnalités principales :

- sélection d’un repository source et d’un dossier de sortie ;
- génération de dumps en volumes texte, XML ou archive ZIP ;
- création optionnelle d’un document unique de type `Code_snapshot_<repo>` ;
- génération d’un index global et d’un fichier d’instructions ;
- support des exclusions standards, de `.gitignore` et de `.smartignore` ;
- métadonnées de navigation IA : index de fichiers, symboles, imports, chunks et résumés ;
- interface graphique avec lancement/arrêt du traitement et ouverture du dossier de destination.

Lancement :

```bash
python -m smart_dumper.main
```

### `file_puller_v2.pyw`

Petite application Tkinter pour agréger le contenu de plusieurs fichiers.

Elle permet de coller une liste de chemins, éventuellement relatifs à un dossier de base, puis de :

- lire les fichiers et afficher leur contenu dans une zone de sortie ;
- exporter le résultat vers un fichier `.txt` ;
- copier le résultat dans le presse-papiers ;
- ouvrir les fichiers valides dans Notepad++ ;
- créer les fichiers manquants avant ouverture, si l’option est activée.

Lancement :

```bash
python file_puller_v2.pyw
```

### `GitSink.bat`

Script Windows simple pour automatiser le cycle Git courant :

```bash
git add .
git commit -m "<message>"
git push
```

Utilisation :

```bat
GitSink.bat "Message de commit"
```

Sans argument, le script demande le message de commit dans le terminal.

### `SmartDump.lnk`

Raccourci Windows destiné à lancer Smart Dumper depuis l’environnement local.

### `The-Senior-Architect_s-Codex/`

Base documentaire sur les patterns d’architecture senior.

Le contenu est organisé par thèmes :

- stabilité et résilience ;
- découplage et architecture structurelle ;
- gestion des données et cohérence ;
- scalabilité et performance ;
- messaging et communication ;
- opérations et déploiement ;
- observabilité et maintenance ;
- patterns spécialisés ou émergents.

Cette partie du dépôt sert de référence pédagogique et opérationnelle pour la conception de systèmes robustes.

## Prérequis

Ce dépôt est pensé pour un environnement local Windows, mais une partie du code Python reste portable.

Prérequis recommandés :

- Python 3.10 ou plus récent ;
- Tkinter, normalement inclus avec Python ;
- Git, pour `GitSink.bat` ;
- Notepad++, optionnel, pour l’ouverture directe depuis `file_puller_v2.pyw`.

Aucune dépendance Python tierce n’est requise d’après les fichiers actuellement présents dans le dépôt.

## Démarrage rapide

Cloner le dépôt :

```bash
git clone <url-du-repo>
cd tools
```

Lancer Smart Dumper :

```bash
python -m smart_dumper.main
```

Lancer l’agrégateur de fichiers :

```bash
python file_puller_v2.pyw
```

Pousser les changements Git :

```bat
GitSink.bat "Update tools"
```

## Structure recommandée d’utilisation

### Pour générer un dump de repository

1. Lancer Smart Dumper.
2. Choisir le dossier du repository à analyser.
3. Choisir un dossier de sortie.
4. Configurer les exclusions et le format de sortie.
5. Lancer le traitement.
6. Récupérer les volumes générés, l’index et les instructions dans le dossier de sortie.

### Pour regrouper rapidement quelques fichiers

1. Lancer `file_puller_v2.pyw`.
2. Renseigner un dossier de base, si nécessaire.
3. Coller une liste de fichiers.
4. Cliquer sur `Process Paths`, `Export to .txt` ou `Open in Notepad++`.

### Pour consulter le Codex

Ouvrir :

```text
The-Senior-Architect_s-Codex/senior-architecture-patterns/00-introduction/README.md
```

Puis naviguer dans les dossiers thématiques.

## Notes de maintenance

- Les outils racine sont volontairement simples et orientés usage local.
- `smart_dumper/` est l’app la plus structurée du dépôt : elle contient une interface, un worker, des modules d’écriture, de navigation IA, d’indexation et de gestion des exclusions.
- Le Codex est une ressource documentaire indépendante du code applicatif.
- Les scripts Windows (`.bat`, `.lnk`, `.pyw`) supposent un usage desktop plutôt qu’un déploiement serveur.

## Roadmap possible

Améliorations utiles à considérer :

- ajouter un `requirements.txt` ou un `pyproject.toml` même si le projet utilise surtout la bibliothèque standard ;
- ajouter un script de lancement clair pour Smart Dumper ;
- documenter les formats de sortie générés par Smart Dumper ;
- ajouter quelques captures d’écran des interfaces ;
- ajouter des tests pour la logique de parsing `.gitignore` / `.smartignore` ;
- remplacer ou compléter les raccourcis locaux par des commandes reproductibles.

## Licence

Licence non spécifiée pour le moment.
