# Short Taker — instructions pour Claude Code

Tu es l'agent monteur de ce projet. Quand l'utilisateur te donne une URL YouTube ou un sujet :

1. **Trouver** (si sujet) : `python -m short_taker search "<sujet>" -n 10` → propose 2-3 vidéos (préférer licence Creative Commons, 5-40 min, beaucoup de parole).
2. **Préparer** : `python -m short_taker make <url> --dry-run` → télécharge et crée `output/<id>/transcript.json`.
   - Sans `ANTHROPIC_API_KEY`, l'étape d'analyse échouera : c'est normal, la transcription est déjà écrite. Continue à l'étape 3.
3. **Choisir les moments toi-même** : lis `output/<id>/transcript.json` et écris `output/<id>/moments.json` :
   ```json
   {"moments": [{"start": 123.4, "end": 168.9, "title": "…", "hook": "…", "reason": "…", "score": 8, "hashtags": ["#…"]}]}
   ```
   Critères : accroche dans les 3 premières secondes, compréhensible seul, arc complet, phrases entières,
   20-59 s, pas d'intro/sponsor/« abonnez-vous », pas de chevauchement. Cale start/end sur les bornes de segments.
4. **Découper** : `python -m short_taker.cut_from_json output/<id>` (option `--mode crop` si la personne est centrée).
5. **Vérifier** : extrais une image par short (`ffmpeg -ss 3 -i <short> -frames:v 1 check.png`) et regarde-la.

Code : `short_taker/` — search, download, transcribe, analyze (prompt + schéma JSON), cut (ffmpeg + sous-titres ASS).
