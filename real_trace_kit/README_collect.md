# Collecte longue duree (collect_activity.py)

Prerequis : venv actif, `credentials.json` dans ce dossier, API **Drive Activity** et **Google Drive** activees dans votre projet, votre adresse comme utilisateur test.
Nouveau jeton (nouveaux scopes) : le navigateur demandera l'autorisation a la premiere commande ; jeton = `token_collect.json` (prive).

1. Trouver ou il y a de l'activite :
   `python collect_activity.py scan --days 60`
   -> tableau des dossiers : max de fichiers distincts modifies en un jour, nombre de jours actifs, edits. Choisissez un dossier avec des jours >= 60.
2. Premiere collecte (tout l'historique du dossier, ou `--since 2026-01-01`) :
   `python collect_activity.py collect --folder-id <ID> --out trace.csv`
   (`--folder-id ALL` = tout le Drive.)
3. Voir si c'est suffisant :
   `python collect_activity.py report --out trace.csv --kmin 60 --bulk 150 --tz UTC`
   (cible : 200 jours exploitables ; `--only-me` pour ne compter que vos edits.)
4. Collecte quotidienne automatique (Linux), ajoute seulement les nouveaux edits :
   `crontab -e` puis ajouter la ligne (adapter les chemins) :
   `15 3 * * * cd ~/chemin/real_trace_kit && ./venv/bin/python collect_activity.py collect --folder-id <ID> --out trace.csv >> collect.log 2>&1`
   L'ordinateur doit etre allume a cette heure ; sinon la collecte suivante rattrape (le script reprend depuis le dernier edit, avec 1 jour de recouvrement).
5. Quand `report` dit « OBJECTIF ATTEINT » :
   `python analyze_real_trace.py trace.csv --tz UTC --exclude-bulk 150 --all-actors --min-days 30`
   et envoyez-moi `real_report.json`/`.md` (pas `trace.csv` ni `salt.txt`).

Confidentialite : `trace.csv` ne contient que hash de fichier (sel local), heure UTC et indicateur « par moi ». Ne publiez jamais `salt.txt`, `credentials.json`, `token_collect.json`, `collect.log`.
Si d'autres personnes editent dans le dossier, obtenez leur accord avant d'utiliser leurs edits.
Statut : ecrit d'apres la documentation de l'API ; l'analyse et le rapport sont testes sur donnees synthetiques ; scan et collect n'ont pas ete executes sur l'API reelle.
