#!/usr/bin/env python3
"""
Vignettes du ciel pour SkyJo, fabriquees une fois pour toutes.

Le service hips2fits du CDS de Strasbourg decoupe a la demande, dans le
releve photographique DSS2 couleur, le morceau de ciel d'un objet. C'est
juste, mais lent : chaque image est calculee au moment ou on la demande,
plusieurs secondes parfois, et une liste de trente cibles fait la queue.

Ce robot demande chaque vignette une seule fois et la range dans le dossier
vignettes/ du depot. Le site les lit ensuite comme de simples fichiers,
servis instantanement. Il ne refait que les manquantes et celles dont le
cadrage a change, a un rythme raisonnable pour le service (une a la fois).

Le cadrage est exactement celui du site : champ = 1,6 fois le grand axe de
l'objet, entre 0,15 et 3 degres (0,25 degre quand le grand axe est inconnu).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(ICI, 'vignettes')
INDEX = os.path.join(DOSSIER, 'index.json')
TAILLE = 160            # pixels de cote : 52 a 62 px a l'ecran, ecrans retina compris
BUDGET = float(os.environ.get('BUDGET_MINUTES', '150')) * 60
PAUSE = 0.4             # secondes entre deux demandes, par egard pour le service
AGENT = 'SkyJo-vignettes/1.0 (site personnel, une image a la fois)'


def champ(taille):
    return max(0.15, min(3.0, (taille / 60.0 if taille else 0.25) * 1.6))


def adresse(ra, dec, fov):
    q = urllib.parse.urlencode({
        'hips': 'CDS/P/DSS2/color', 'ra': '%.4f' % ra, 'dec': '%.4f' % dec,
        'fov': '%.3f' % fov, 'width': TAILLE, 'height': TAILLE, 'projection': 'TAN',
        'coordsys': 'icrs', 'format': 'jpg', 'stretch': 'asinh'})
    return 'https://alasky.cds.unistra.fr/hips-image-services/hips2fits?' + q


def main():
    os.makedirs(DOSSIER, exist_ok=True)
    objets = json.load(open(os.path.join(ICI, 'vignettes.json'), encoding='utf-8'))['objets']
    try:
        fait = json.load(open(INDEX, encoding='utf-8'))
    except (OSError, ValueError):
        fait = {}
    debut = time.time()
    neufs = echecs = 0
    for nom, ra, dec, taille in objets:
        fov = round(champ(taille), 3)
        fichier = os.path.join(DOSSIER, nom + '.jpg')
        if fait.get(nom) == fov and os.path.exists(fichier):
            continue
        if time.time() - debut > BUDGET:
            print('Temps imparti ecoule : la suite au prochain passage.')
            break
        try:
            req = urllib.request.Request(adresse(ra, dec, fov), headers={'User-Agent': AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                image = r.read()
            if image[:2] != b'\xff\xd8' or len(image) < 500:
                raise ValueError('reponse qui n est pas une image')
            with open(fichier, 'wb') as f:
                f.write(image)
            fait[nom] = fov
            neufs += 1
        except Exception as e:
            echecs += 1
            print('%-14s echec : %s' % (nom, str(e)[:100]))
        time.sleep(PAUSE)
        if neufs and neufs % 100 == 0:
            print('%d vignettes faites...' % neufs)
            with open(INDEX, 'w', encoding='utf-8') as f:
                json.dump(fait, f, separators=(',', ':'), sort_keys=True)
    with open(INDEX, 'w', encoding='utf-8') as f:
        json.dump(fait, f, separators=(',', ':'), sort_keys=True)
    reste = sum(1 for o in objets if o[0] not in fait)
    print('%d nouvelles vignettes, %d echecs, %d encore a faire, %d au total.'
          % (neufs, echecs, reste, len(fait)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
