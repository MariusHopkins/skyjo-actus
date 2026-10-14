"""
Ce qui complete la nuit d'Albigny-sur-Saone, au-dela de la meteo du site :

- la stabilite de l'air (seeing) et la transparence, d'apres le service
  gratuit 7Timer! (produit ASTRO), pour les trois jours qui viennent ;
- les cometes a portee, calculees a partir des elements d'orbite publies
  par le Minor Planet Center (le meme calcul que pour les planetes : Skyfield
  et les ephemerides du JPL), avec la magnitude que le MPC fournit pour
  chacune (formule g + 5 log delta + 2,5 k log r) ;
- l'activite aurorale prevue (indice Kp planetaire), d'apres le centre de
  prevision meteo spatiale de la NOAA (SWPC).

Rien n'est invente : chaque valeur vient d'une de ces sources, ou d'un calcul
fait a partir d'elles. Les seuils de selection sont des choix de SkyJo,
nommes en tete de fichier.
"""
import json
import math
import urllib.request
from datetime import datetime, timedelta, timezone

from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
from skyfield.data import mpc

from evenements import LAT, LON, PARIS, ts, eph, TERRE, SOLEIL, ICI, CONST, NOMS_CONST

URL_7TIMER = ('https://www.7timer.info/bin/astro.php?lon=%.1f&lat=%.1f'
              '&ac=0&unit=metric&output=json&tzshift=0' % (LON, LAT))
URL_COMETES = 'https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt'
URL_KP = 'https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json'

COMETE_MAG_MAX = 12.0      # au-dela, trop faible pour valoir la sortie
COMETE_HAUTEUR_MIN = 15.0  # degres, au-dessus de l'horizon pendant la nuit noire
COMETES_MAX = 8


def lire(url, delai=40):
    req = urllib.request.Request(url, headers={'User-Agent': 'skyjo-actus (robot personnel)'})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return r.read()


# ---------------------------------------------------------------- 7Timer!
def seeing():
    """Seeing et transparence, de 3 h en 3 h (classes 1 a 8 de 7Timer!).
    Seeing : 1 = moins de 0,5", 8 = plus de 2,5" (plus c'est bas, plus l'air
    est stable). Transparence : 1 = moins de 0,3 mag d'extinction, 8 = plus
    de 1 mag (plus c'est bas, plus le ciel est transparent)."""
    try:
        brut = lire(URL_7TIMER)
    except Exception:
        brut = lire(URL_7TIMER.replace('https://', 'http://'))
    d = json.loads(brut.decode('utf-8'))
    init = datetime.strptime(str(d['init']), '%Y%m%d%H').replace(tzinfo=timezone.utc)
    serie = []
    for p in d.get('dataseries', []):
        s, tr = p.get('seeing'), p.get('transparency')
        if not (isinstance(s, int) and 1 <= s <= 8 and isinstance(tr, int) and 1 <= tr <= 8):
            continue
        t = init + timedelta(hours=int(p['timepoint']))
        serie.append({'t': t.strftime('%Y-%m-%dT%H:%MZ'), 'seeing': s, 'transp': tr})
    if not serie:
        raise ValueError('7Timer : aucune valeur exploitable')
    return {'source': '7Timer! (produit ASTRO)', 'init': init.strftime('%Y-%m-%dT%H:%MZ'),
            'lieu': 'Albigny-sur-Saône', 'serie': serie[:24]}


# ---------------------------------------------------------------- cometes
class Ligne(dict):
    """Une ligne du fichier du MPC, lisible comme un objet (pour Skyfield)."""
    __getattr__ = dict.__getitem__


def elements_cometes(texte):
    lignes = []
    for brute in texte.splitlines():
        if len(brute) < 103:
            continue
        r = Ligne()
        try:
            for nom, (a, b) in mpc._COMET_COLUMNS:
                v = brute[a:b].strip()
                if nom in ('perihelion_year', 'perihelion_month', 'perturbed_epoch_year',
                           'perturbed_epoch_month', 'perturbed_epoch_day'):
                    v = int(v) if v else None
                elif nom in ('perihelion_day', 'perihelion_distance_au', 'eccentricity',
                             'argument_of_perihelion_degrees', 'longitude_of_ascending_node_degrees',
                             'inclination_degrees', 'magnitude_g', 'magnitude_k'):
                    v = float(v) if v else None
                r[nom] = v
        except ValueError:
            continue
        if r['magnitude_g'] is None or r['magnitude_k'] is None or r['perihelion_year'] is None:
            continue
        lignes.append(r)
    return lignes


def nuit_noire(jour):
    """Instants (toutes les 30 min) de la nuit du jour donne, Soleil sous -12°."""
    debut = datetime(jour.year, jour.month, jour.day, 17, 0, tzinfo=PARIS)
    instants = [debut + timedelta(minutes=30 * k) for k in range(30)]
    t = ts.from_datetimes(instants)
    h_soleil = ICI.at(t).observe(SOLEIL).apparent().altaz()[0].degrees
    return [ti for ti, h in zip(instants, h_soleil) if h < -12]


def cometes(aujourdhui=None):
    jour = aujourdhui or datetime.now(PARIS).date()
    noir = nuit_noire(jour)
    if not noir:
        return {'source': 'Minor Planet Center (éléments d’orbite)', 'liste': []}
    t_noir = ts.from_datetimes(noir)
    t_milieu = ts.from_datetime(noir[len(noir) // 2])
    soleil = eph['sun']
    texte = lire(URL_COMETES, delai=60).decode('latin-1')
    garde = []
    for r in elements_cometes(texte):
        try:
            orbite = mpc.comet_orbit(r, ts, GM_SUN)
        except Exception:
            continue
        corps = soleil + orbite
        try:
            ra_, dec_, delta = TERRE.at(t_milieu).observe(corps).radec()
            rr = orbite.at(t_milieu).distance().au
        except Exception:
            continue
        d = delta.au
        if not (d > 0 and rr > 0):
            continue
        mag = r['magnitude_g'] + 5 * math.log10(d) + 2.5 * r['magnitude_k'] * math.log10(rr)
        if mag > COMETE_MAG_MAX:
            continue
        alt = ICI.at(t_noir).observe(corps).apparent().altaz()[0].degrees
        k = int(alt.argmax())
        hmax = float(alt[k])
        if hmax < COMETE_HAUTEUR_MIN:
            continue
        pos = ICI.at(t_noir[k]).observe(corps)
        garde.append({
            'nom': r['designation'], 'mag': round(float(mag), 1), 'hmax': int(round(hmax)),
            'heure': '%d h %02d' % (noir[k].hour, noir[k].minute),
            'const': NOMS_CONST.get(CONST(pos), CONST(pos)),
            'ra': round(float(ra_.hours) * 15, 3), 'dec': round(float(dec_.degrees), 3),
            'r': round(float(rr), 2), 'delta': round(float(d), 2)})
    garde.sort(key=lambda x: x['mag'])
    return {'source': 'Minor Planet Center (éléments d’orbite), calcul Skyfield',
            'nuit': jour.isoformat(), 'mag_max': COMETE_MAG_MAX, 'liste': garde[:COMETES_MAX]}


# ---------------------------------------------------------------- aurores
def aurores():
    """Indice Kp planetaire, observe puis prevu, par tranches de 3 h (NOAA SWPC)."""
    d = json.loads(lire(URL_KP).decode('utf-8'))
    lignes = []
    if d and isinstance(d[0], list):
        tete = [str(x) for x in d[0]]
        for l in d[1:]:
            lignes.append(dict(zip(tete, l)))
    else:
        lignes = [x for x in d if isinstance(x, dict)]
    serie = []
    for l in lignes:
        try:
            t = datetime.strptime(str(l['time_tag'])[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
            kp = float(l['kp'])
        except (KeyError, ValueError, TypeError):
            continue
        prevu = str(l.get('observed', '')).lower() in ('predicted', 'estimated')
        serie.append({'t': t.strftime('%Y-%m-%dT%H:%MZ'), 'kp': round(kp, 2), 'prevu': prevu})
    if not serie:
        raise ValueError('Kp : aucune valeur exploitable')
    return {'source': 'NOAA, Space Weather Prediction Center (indice Kp)', 'serie': serie[-32:]}
