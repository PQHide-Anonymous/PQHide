# Simulation sur votre Drive (simulate_on_drive.py + analyze_sim.py)

BUT : tester le pipeline de bout en bout (vraies ecritures Drive, vraie API Activity, vraies horloges) avec un comportement SIMULE a etiquette connue.
Ce n'est PAS de l'activite d'utilisateur reel : le papier doit l'appeler « simulated behaviour on a real cloud API ».

1. Essai sans reseau :  python simulate_on_drive.py --dry-run --files 300 --windows-per-class 6 --window-s 0.3 --out t
2. Petit essai reel (environ 5 min) :  python simulate_on_drive.py --files 300 --windows-per-class 3 --window-s 90 --out sim_essai
   (premiere fois : le navigateur demande l'autorisation « drive.file » ; jeton token_sim.json)
3. Campagne (environ 2 h 40, laissez l'ordinateur allume) :
   python session_notes.py S1
   python simulate_on_drive.py --files 300 --windows-per-class 40 --window-s 120 --hetero 1.0 --out sim_het
   python simulate_on_drive.py --files 300 --windows-per-class 40 --window-s 120 --hetero 0.0 --out sim_hom    (baseline uniforme)
   Chaque lancement affiche l'ID du dossier de test et ne le supprime pas.
4. Exporter l'activite de chaque dossier de test (script du kit real_trace_kit) :
   python ../real_trace_kit/collect_activity.py collect --folder-id <ID_DU_DOSSIER> --out sim_het_trace.csv
   (attendre au moins 1 minute apres la fin pour que l'API Activity ait tout publie)
5. Analyser :  python analyze_sim.py sim_het_trace.csv sim_het_manifest.csv --out sim_het_report
              python analyze_sim.py sim_hom_trace.csv sim_hom_manifest.csv --out sim_hom_report
6. Envoyez-moi : *_report.json, *_report.md, *_manifest.csv, notes_sessionS1.txt  (pas les traces .csv, pas salt.txt, pas credentials.json, pas token_*.json).

Lecture attendue : baseline uniforme -> detecteurs a ~0,5 (indistinguable) ; baseline heterogene (fichiers « chauds ») -> la fraction de fichiers chauds separe tres bien le schema (c'est la limite deja decrite dans le papier : le pool doit etre construit pour ressembler a l'activite).
Reserves : « advantage » est un maximum sur les seuils, donc biaise vers le haut avec peu de fenetres ; l'AUC avec IC95 % est la mesure principale. Les fenetres de 2 min ne sont pas des jours : la conclusion porte sur la forme de la selection, pas sur le rythme quotidien.
Statut : les trois scripts sont testes sur simulateur local ; simulate_on_drive.py n'a pas ete execute sur l'API reelle.
