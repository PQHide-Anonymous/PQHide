# Kit « latence cloud » PQHide (point 6 du reviewer 1)

Mesure, sur VOTRE Drive, le coût d'une fenêtre = K éditions individuelles (files.update, sans batch), en séparant :
- `t_local` : calcul local (choix des K fichiers avec l'embedder PQHide réel, pool 131 072) ;
- `t_submit` : de l'envoi de la 1re requête au retour OK de la dernière (retries/backoff inclus) ;
- `t_confirm` : délai supplémentaire jusqu'à ce que chaque fichier montre une nouvelle `version` via files.get ;
- latence par appel (p50/p95/p99), nombre de retries, de 403/429 (throttling) et d'échecs, pour chaque concurrence c.

Statut : testé uniquement avec un backend simulé (--dry-run). Jamais exécuté contre l'API Google réelle.

## Procédure
1. Google Cloud : réutilisez le projet du kit « trace réelle » (même credentials.json) ; Google Drive API activée.
   Scope utilisé : `drive.file` (le script ne voit que les fichiers qu'il crée). Ajoutez ce scope à l'écran de consentement si demandé.
2. `pip install -r requirements.txt`  (placer `credentials.json` dans ce dossier)
3. Test à blanc, sans réseau : `python measure_drive_latency.py --dry-run --files 120 --K 50,105 --conc 1,4 --reps 2 --poll 0.05`
4. Petit essai réel : `python measure_drive_latency.py --files 120 --K 20 --conc 1,4 --reps 2 --cleanup`
   (autorisez dans le navigateur ; ~2 min).
5. Mesure complète : `python measure_drive_latency.py --files 300 --K 20,60,105 --conc 1,4,16 --reps 10 --cleanup`
   Durée : de quelques minutes à une heure selon le débit. Faites-la à des heures différentes (matin/soir) et
   avec une connexion stable ; notez le lieu, le type de connexion, la date.
6. Notez : type de compte (gratuit / Workspace), région, version de Python.
7. Envoyez-moi `latency_raw.csv`, `latency_summary.json`, `tab_latency.tex` + les notes de l'étape 6.
   Je remplace alors le modèle paramétrique de la section « cloud cost » par ces mesures et je mets à jour la lettre (R1.6).

## Précautions
- Le script crée un dossier `pqhide_latency_test` et ~300 petits fichiers texte, et les supprime avec `--cleanup`.
  Sans cet indicateur, supprimez le dossier à la main.
- Des 403/429 sont attendus à forte concurrence : ils sont comptés, pas cachés. Si beaucoup d'échecs apparaissent
  à c=16, c'est un résultat à rapporter (limite de débit du fournisseur).
- Gardez privés `credentials.json` et `token_lat.json`.
- Mesure faite depuis votre machine : elle inclut votre réseau. C'est voulu, mais précisez-le (le papier le dira).

## Version du 24/11 (après l'erreur SSLEOFError observée en phase de confirmation)
- La lecture de confirmation (`files.get`) est maintenant relancée (6 essais, backoff) sur les erreurs HTTP et de transport ; les classes d'erreur sont écrites dans la colonne `confirm_error_classes`.
- Le CSV est écrit fenêtre par fenêtre : une coupure réseau ou Ctrl-C ne perd plus les fenêtres terminées. Le dossier de test est supprimé même en cas d'interruption (`--cleanup`).
- Les sorties portent le nom de `--out` : `X.csv` -> `X_summary.json`, `X_table.tex` (plus d'écrasement de `latency_summary.json`).
- Le script indique « RUN INCOMPLETE » si la campagne s'est arrêtée avant la fin.

## Mesure côté destinataire (recipient_latency.py)
Mesure, après l'envoi d'une fenêtre de K éditions, le délai avant que le destinataire VOIE ces K éditions (Drive Activity API, et files.list comme référence) et le coût d'un listing.
Scopes : drive.file + drive.activity.readonly (jeton séparé : token_recv.json ; il faut que l'API Drive Activity soit activée, comme pour le kit « trace réelle »).
1. Essai à blanc : `python recipient_latency.py --dry-run --files 60 --K 20,40 --reps 2 --poll 0.05 --dry-scale 0.02 --gap 0.1 --listings 2 --out dry`
2. Petit essai réel : `python recipient_latency.py --files 60 --K 20 --conc 16 --reps 2 --poll 2 --cleanup --out recv_essai`
3. Campagne : `python recipient_latency.py --files 200 --K 20,60,105 --conc 16 --reps 5 --poll 2 --timeout 300 --cleanup --out recv_session1` (à lancer après `python session_notes.py R1`)
Sorties : `<out>_windows.csv` (une ligne par fenêtre), `<out>_polls.csv` (un appel de listing par ligne), `<out>_listings.csv` (coût d'un listing une fois la fenêtre visible), `<out>_summary.json`.
Un fichier « jamais vu » avant le timeout est un résultat (colonne `n_not_seen`), pas une erreur.
