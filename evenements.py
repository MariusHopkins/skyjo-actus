"""
Les evenements du ciel, calcules et non recopies.

Tout vient des ephemerides du Jet Propulsion Laboratory (DE421, la meme
table que celle des agences spatiales pour cette periode), lues par la
bibliotheque Skyfield. Aucun chiffre n'est saisi a la main, a une exception
pres : la table des pluies d'etoiles filantes, qui fixe pour chacune la
longitude du Soleil au maximum. Ces valeurs sont celles de l'Organisation
internationale des meteores (IMO), stables d'une annee a l'autre ; la date
du maximum en est deduite chaque annee par le calcul.

Le lieu d'observation est Albigny-sur-Saone, au bourg (comme dans le site).
Les heures sont donnees en heure de Paris, ete et hiver compris.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import skyfield_data
from skyfield import almanac, eclipselib
from skyfield.api import Loader, Star, load_constellation_map, wgs84
from skyfield.framelib import ecliptic_J2000_frame, ecliptic_frame
from skyfield.magnitudelib import planetary_magnitude
from skyfield.searchlib import find_discrete, find_maxima, find_minima

LAT, LON = 45.9, 4.8
PARIS = ZoneInfo('Europe/Paris')
JOURS_AVANT = 1
JOURS_APRES = 400

load = Loader(skyfield_data.get_skyfield_data_path(), verbose=False)
ts = load.timescale(builtin=True)
eph = load('de421.bsp')
TERRE, SOLEIL, LUNE = eph['earth'], eph['sun'], eph['moon']
ICI = TERRE + wgs84.latlon(LAT, LON, elevation_m=200)
CONST = load_constellation_map()

PLANETES = [  # nom, cible, article
    ('Mercure', eph['mercury'], 'f'),
    ('Vénus', eph['venus'], 'f'),
    ('Mars', eph['mars'], 'm'),
    ('Jupiter', eph['jupiter barycenter'], 'm'),
    ('Saturne', eph['saturn barycenter'], 'f'),
]
EXTERIEURES = [('Mars', eph['mars']), ('Jupiter', eph['jupiter barycenter']),
               ('Saturne', eph['saturn barycenter']),
               ('Uranus', eph['uranus barycenter']), ('Neptune', eph['neptune barycenter'])]

# Etoiles et amas que la Lune frole : seulement les passages tres serres.
ETOILES = [  # nom, ascension droite (h), declinaison (deg), J2000
    ('les Pléiades', 3.7911, 24.1167),
    ('Aldébaran', 4.5987, 16.5093),
    ('Régulus', 10.1395, 11.9672),
    ('Spica', 13.4199, -11.1613),
    ('Antarès', 16.4901, -26.4320),
]

# Pluies d'etoiles filantes : longitude solaire J2000 du maximum et taux
# horaire zenithal (ZHR, nombre theorique par heure sous un ciel parfait,
# radiant au zenith), d'apres la liste de travail de l'IMO.
PLUIES = [
    ('Quadrantides', 283.15, 80, 'Bouvier', 3),
    ('Lyrides', 32.32, 18, 'Lyre', 2),
    ('Êta Aquarides', 45.5, 50, 'Verseau', 2),
    ('Delta Aquarides du Sud', 128.0, 25, 'Verseau', 1),
    ('Perséides', 140.0, 100, 'Persée', 3),
    ('Orionides', 208.0, 20, 'Orion', 2),
    ('Léonides', 235.27, 15, 'Lion', 2),
    ('Géminides', 262.2, 150, 'Gémeaux', 3),
    ('Ursides', 270.7, 10, 'Petite Ourse', 1),
]

NOMS_CONST = {
    "And": "Andromède", "Ant": "Machine pneumatique", "Aps": "Oiseau de paradis",
    "Aqr": "Verseau", "Aql": "Aigle", "Ara": "Autel", "Ari": "Bélier", "Aur": "Cocher",
    "Boo": "Bouvier", "Cae": "Burin", "Cam": "Girafe", "Cnc": "Cancer",
    "CVn": "Chiens de Chasse", "CMa": "Grand Chien", "CMi": "Petit Chien",
    "Cap": "Capricorne", "Car": "Carène", "Cas": "Cassiopée", "Cen": "Centaure",
    "Cep": "Céphée", "Cet": "Baleine", "Cha": "Caméléon", "Cir": "Compas",
    "Col": "Colombe", "Com": "Chevelure de Bérénice", "CrA": "Couronne australe",
    "CrB": "Couronne boréale", "Crv": "Corbeau", "Crt": "Coupe", "Cru": "Croix du Sud",
    "Cyg": "Cygne", "Del": "Dauphin", "Dor": "Dorade", "Dra": "Dragon",
    "Equ": "Petit Cheval", "Eri": "Éridan", "For": "Fourneau", "Gem": "Gémeaux",
    "Gru": "Grue", "Her": "Hercule", "Hor": "Horloge", "Hya": "Hydre",
    "Hyi": "Hydre mâle", "Ind": "Indien", "Lac": "Lézard", "Leo": "Lion",
    "LMi": "Petit Lion", "Lep": "Lièvre", "Lib": "Balance", "Lup": "Loup", "Lyn": "Lynx",
    "Lyr": "Lyre", "Men": "Table", "Mic": "Microscope", "Mon": "Licorne", "Mus": "Mouche",
    "Nor": "Règle", "Oct": "Octant", "Oph": "Ophiuchus", "Ori": "Orion", "Pav": "Paon",
    "Peg": "Pégase", "Per": "Persée", "Phe": "Phénix", "Pic": "Peintre",
    "Psc": "Poissons", "PsA": "Poisson austral", "Pup": "Poupe", "Pyx": "Boussole",
    "Ret": "Réticule", "Sge": "Flèche", "Sgr": "Sagittaire", "Sco": "Scorpion",
    "Scl": "Sculpteur", "Sct": "Écu de Sobieski", "Ser": "Serpent", "Sex": "Sextant",
    "Tau": "Taureau", "Tel": "Télescope", "Tri": "Triangle", "TrA": "Triangle austral",
    "Tuc": "Toucan", "UMa": "Grande Ourse", "UMi": "Petite Ourse", "Vel": "Voiles",
    "Vir": "Vierge", "Vol": "Poisson volant", "Vul": "Petit Renard",
}
# « dans le Lion », « dans la Vierge », « dans les Gémeaux », « dans Orion »
ARTICLES = {
    'Ari': 'le', 'Tau': 'le', 'Gem': 'les', 'Cnc': 'le', 'Leo': 'le', 'Vir': 'la',
    'Lib': 'la', 'Sco': 'le', 'Oph': '', 'Sgr': 'le', 'Cap': 'le', 'Aqr': 'le',
    'Psc': 'les', 'Cet': 'la', 'Sex': 'le', 'Ori': '', 'Crt': 'la', 'Crv': 'le',
    'Hya': "l'", 'Aur': 'le', 'Per': '', 'Peg': '', 'And': '', 'Ser': 'le',
    'Lup': 'le', 'Eri': "l'", 'Mon': 'la', 'CMi': 'le', 'Lyn': 'le', 'LMi': 'le',
}


def dans(code):
    nom = NOMS_CONST.get(code, code)
    a = ARTICLES.get(code)
    if a is None:
        return 'dans la constellation ' + ('d’' if nom[0] in 'AEÉIOU' else 'de ') + nom
    if a == '':
        return 'dans ' + nom
    return 'dans ' + a + ('' if a.endswith("'") else ' ') + nom


def virgule(x, n=1):
    return ('%.' + str(n) + 'f') % x if n else '%d' % round(x)


def fr(x, n=1):
    return virgule(x, n).replace('.', ',').replace('-', '−')


def local(t):
    return t.utc_datetime().astimezone(PARIS)


def heure(t):
    d = local(t)
    return '%d h %02d' % (d.hour, d.minute)


def sortie(t, genre, titre, detail, niveau, heure_utile=True, **extra):
    d = local(t)
    e = {'t': t.utc_strftime('%Y-%m-%dT%H:%MZ'), 'jour': d.strftime('%Y-%m-%d'),
         'heure': heure(t) if heure_utile else None,
         'genre': genre, 'titre': titre, 'detail': detail, 'niveau': niveau}
    e.update(extra)
    return e


def hauteurs(cible, t):
    alt, az, _ = ICI.at(t).observe(cible).apparent().altaz()
    return float(alt.degrees), float(az.degrees)


CARD = ['le nord', 'le nord-est', 'l’est', 'le sud-est', 'le sud', 'le sud-ouest',
        'l’ouest', 'le nord-ouest']


def cardinal(az):
    return CARD[int(((az % 360) + 22.5) // 45) % 8]


def de(nom):
    """« de Jupiter », « d’Antarès », « des Pléiades »."""
    if nom.startswith('les '):
        return 'des ' + nom[4:]
    return ('d’' if nom[0] in 'AEÉIOUÂÊ' else 'de ') + nom


MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août',
        'septembre', 'octobre', 'novembre', 'décembre']


def date_courte(d):
    return ('1er' if d.day == 1 else str(d.day)) + ' ' + MOIS[d.month - 1]


def nuit_du(veille, lendemain):
    if veille.month == lendemain.month:
        return 'la nuit du ' + str(veille.day) + ' au ' + date_courte(lendemain)
    return 'la nuit du ' + date_courte(veille) + ' au ' + date_courte(lendemain)


def recouvrement(sep, r1, r2):
    """Part de la surface du disque 1 cachee par le disque 2."""
    if sep >= r1 + r2:
        return 0.0
    if sep <= abs(r1 - r2):
        return 1.0 if r2 >= r1 else (r2 / r1) ** 2
    a1 = r1 * r1 * np.arccos((sep * sep + r1 * r1 - r2 * r2) / (2 * sep * r1))
    a2 = r2 * r2 * np.arccos((sep * sep + r2 * r2 - r1 * r1) / (2 * sep * r2))
    a3 = 0.5 * np.sqrt((-sep + r1 + r2) * (sep + r1 - r2) * (sep - r1 + r2) * (sep + r1 + r2))
    return float((a1 + a2 - a3) / (np.pi * r1 * r1))


def nuit_autour(t_centre, demi_heures=14, pas_min=5):
    """Instants d'une nuit autour de t, tous les pas_min minutes."""
    n = int(demi_heures * 2 * 60 / pas_min) + 1
    jd = t_centre.tt + (np.arange(n) * pas_min - demi_heures * 60) / 1440.0
    return ts.tt_jd(jd)


# ------------------------------------------------------------------------
def phases(t0, t1):
    noms = ['Nouvelle lune', 'Premier quartier', 'Pleine lune', 'Dernier quartier']
    aide = ['Ciel sans Lune : la meilleure période pour le ciel profond.',
            'La Lune éclaire la première moitié de la nuit.',
            'La Lune éclaire toute la nuit : pause pour le ciel profond, place à la Lune.',
            'La Lune ne se lève qu’en seconde partie de nuit.']
    t, y = find_discrete(t0, t1, almanac.moon_phases(eph))
    return [sortie(ti, 'lune', noms[yi], aide[yi], 2 if yi in (0, 2) else 1)
            for ti, yi in zip(t, y)]


def saisons(t0, t1):
    noms = ['Équinoxe de printemps', 'Solstice d’été', 'Équinoxe d’automne',
            'Solstice d’hiver']
    aide = ['Jours et nuits d’égale durée.', 'La nuit la plus courte de l’année.',
            'Jours et nuits d’égale durée.', 'La nuit la plus longue de l’année.']
    t, y = find_discrete(t0, t1, almanac.seasons(eph))
    return [sortie(ti, 'saison', noms[yi], aide[yi], 1) for ti, yi in zip(t, y)]


def oppositions(t0, t1):
    ev = []
    for nom, cible in EXTERIEURES:
        t, y = find_discrete(t0, t1, almanac.oppositions_conjunctions(eph, cible))
        for ti, yi in zip(t, y):
            if yi != 1:
                continue
            pos = TERRE.at(ti).observe(cible)
            mag = float(planetary_magnitude(pos))
            c = CONST(pos)
            d = pos.distance().au
            prop = (' Hors de portée de l’œil nu, mais facile au télescope.'
                    if nom in ('Uranus', 'Neptune') else '')
            ev.append(sortie(ti, 'planete', nom + ' à l’opposition',
                             'Au plus près de la Terre (' + fr(d, 2) + ' ua) et visible toute la nuit, '
                             + dans(c) + ', magnitude ' + fr(mag) + '.' + prop,
                             3 if nom in ('Mars', 'Jupiter', 'Saturne') else 1,
                             heure_utile=False, astre=nom))
    return ev


def elongations(t0, t1):
    ev = []
    for nom, cible, _ in PLANETES[:2]:
        def elong(t):
            e = TERRE.at(t)
            return e.observe(SOLEIL).apparent().separation_from(
                e.observe(cible).apparent()).degrees
        elong.step_days = 3
        t, v = find_maxima(t0, t1, elong)
        for ti, vi in zip(t, v):
            e = TERRE.at(ti)
            ls = e.observe(SOLEIL).apparent().frame_latlon(ecliptic_frame)[1].degrees
            lp = e.observe(cible).apparent().frame_latlon(ecliptic_frame)[1].degrees
            soir = ((lp - ls) % 360) < 180
            # hauteur au crepuscule civil, la ou on la cherche vraiment
            jour = local(ti).date()
            ta = ts.from_datetime(datetime(jour.year, jour.month, jour.day, 12, tzinfo=PARIS))
            tb = ts.from_datetime(datetime(jour.year, jour.month, jour.day, 12, tzinfo=PARIS)
                                  + timedelta(days=1))
            f = almanac.dark_twilight_day(eph, wgs84.latlon(LAT, LON))
            tt, yy = find_discrete(ts.tt_jd(ta.tt - 1), tb, f)
            # 3 -> 2 le soir et 2 -> 3 le matin : Soleil a -6 degres
            moments = [x for x, a, b in zip(tt[1:], yy[:-1], yy[1:])
                       if (soir and a == 3 and b == 2) or (not soir and a == 2 and b == 3)]
            moments = [m for m in moments if abs(m.tt - ti.tt) < 1.5]
            haut = None
            if moments:
                m = min(moments, key=lambda x: abs(x.tt - ti.tt))
                haut = hauteurs(cible, m)[0]
            mag = float(planetary_magnitude(TERRE.at(ti).observe(cible)))
            quand = 'le soir, à l’ouest après le coucher du Soleil' if soir \
                else 'le matin, à l’est avant le lever du Soleil'
            det = (nom + ' s’écarte au plus du Soleil (' + fr(vi) + '°) : à chercher '
                   + quand + ', magnitude ' + fr(mag) + '.')
            if haut is not None:
                det += (' Hauteur ' + ('à la fin' if soir else 'au début')
                        + ' du crépuscule civil : ' + fr(haut, 0) + '°.')
            niveau = 2 if (haut is not None and haut >= 8) or nom == 'Vénus' else 1
            ev.append(sortie(ti, 'planete', nom + ' à sa plus grande élongation '
                             + ('du soir' if soir else 'du matin'), det, niveau,
                             heure_utile=False, astre=nom))
    return ev


def meilleur_moment(a, b, t_centre, rayon_lune=False):
    """Dans la nuit qui entoure t_centre, l'instant ou les deux astres sont
    au plus pres, a condition que le ciel soit sombre et les deux assez hauts.
    None si le rapprochement n'est pas observable depuis Albigny."""
    t = nuit_autour(t_centre, 13, 5)
    o = ICI.at(t)
    sa, _, _ = o.observe(SOLEIL).apparent().altaz()
    pa = o.observe(a).apparent()
    pb = o.observe(b).apparent()
    ha, aza, _ = pa.altaz()
    hb, _, _ = pb.altaz()
    sep = pa.separation_from(pb).degrees
    ok = (sa.degrees < -6) & (ha.degrees > 8) & (hb.degrees > 8)
    if not ok.any():
        return None
    i = int(np.argmin(np.where(ok, sep, 999)))
    return t[i], float(sep[i]), float(ha.degrees[i]), float(aza.degrees[i])


def rapprochements_lune(t0, t1):
    ev = []
    cibles = [(n, c, 4.0, 2) for n, c, _ in PLANETES] + \
             [(n, Star(ra_hours=ra, dec_degrees=de), 1.2, 1) for n, ra, de in ETOILES]
    for nom, cible, seuil, niveau in cibles:
        def sep(t):
            e = TERRE.at(t)
            return e.observe(LUNE).apparent().separation_from(e.observe(cible).apparent()).degrees
        sep.step_days = 0.5
        t, v = find_minima(t0, t1, sep)
        for ti, vi in zip(t, v):
            if vi > seuil + 1.2:      # le point de vue d'Albigny peut rapprocher d'un degre
                continue
            m = meilleur_moment(LUNE, cible, ti)
            if not m:
                continue
            tm, s, h, az = m
            if s > seuil:
                continue
            rl = np.degrees(1737.4 / ICI.at(tm).observe(LUNE).apparent().distance().km)
            occ = s < rl
            titre = 'La Lune ' + ('occulte ' + nom if occ else 'près ' + de(nom))
            det = ('Écart de ' + fr(s) + '° vers ' + heure(tm) + ', à ' + fr(h, 0) + '° de hauteur vers '
                   + cardinal(az) + '.') if not occ else (
                   ('Les étoiles de l’amas passent' if nom.startswith('les ')
                    else nom + ' passe') + ' derrière la Lune vers ' + heure(tm) + ', à ' + fr(h, 0)
                   + '° de hauteur vers ' + cardinal(az) + '. Heure à préciser auprès de l’IMCCE.')
            ev.append(sortie(tm, 'conjonction', titre, det, 3 if occ else niveau,
                             astre=nom))
    return ev


def rapprochements_planetes(t0, t1):
    ev = []
    for i in range(len(PLANETES)):
        for j in range(i + 1, len(PLANETES)):
            na, a, _ = PLANETES[i]
            nb, b, _ = PLANETES[j]

            def sep(t, a=a, b=b):
                e = TERRE.at(t)
                return e.observe(a).apparent().separation_from(e.observe(b).apparent()).degrees
            sep.step_days = 1
            t, v = find_minima(t0, t1, sep)
            for ti, vi in zip(t, v):
                if vi > 3:
                    continue
                m = meilleur_moment(a, b, ti)
                if not m:
                    continue
                tm, s, h, az = m
                ev.append(sortie(tm, 'conjonction', na + ' et ' + nb + ' se rapprochent',
                                 'Écart de ' + fr(s) + '° vers ' + heure(tm) + ', à ' + fr(h, 0)
                                 + '° de hauteur vers ' + cardinal(az) + '.',
                                 3 if s < 1 else 2))
    return ev


def eclipses_lune(t0, t1):
    ev = []
    t, y, det = eclipselib.lunar_eclipses(t0, t1, eph)
    noms = ['Éclipse de Lune par la pénombre', 'Éclipse partielle de Lune',
            'Éclipse totale de Lune']
    for k, (ti, yi) in enumerate(zip(t, y)):
        h, az = hauteurs(LUNE, ti)
        sa, _ = hauteurs(SOLEIL, ti)
        vis = bool(h > 0 and sa < -0.8)
        mag = float(det['umbral_magnitude'][k]) if yi > 0 \
            else float(det['penumbral_magnitude'][k])
        if vis:
            d = ('Maximum à ' + heure(ti) + ', la Lune à ' + fr(h, 0) + '° de hauteur vers '
                 + cardinal(az) + '. Magnitude ' + ('dans l’ombre ' if yi > 0 else 'de pénombre ')
                 + fr(mag, 2) + '.')
            if yi == 0:
                d += ' Assombrissement discret, à peine visible.'
        else:
            d = ('Maximum à ' + heure(ti) + ', alors que la Lune est sous l’horizon '
                 'd’Albigny : invisible depuis la France.' if h <= 0 else
                 'Maximum à ' + heure(ti) + ', en plein jour à Albigny : invisible.')
        ev.append(sortie(ti, 'eclipse', noms[yi], d,
                         (3 if yi > 0 else 1) if vis else 1, visible=vis))
    return ev


def eclipses_soleil(t0, t1):
    """Eclipse vue d'Albigny : on cherche autour de chaque nouvelle lune si
    les disques du Soleil et de la Lune se recouvrent, Soleil leve."""
    ev = []
    t, y = find_discrete(t0, t1, almanac.moon_phases(eph))
    for ti in [a for a, b in zip(t, y) if b == 0]:
        n = int(0.5 * 1440 / 1) + 1
        tt = ts.tt_jd(ti.tt - 0.25 + np.arange(n) / 1440.0)
        o = ICI.at(tt)
        s = o.observe(SOLEIL).apparent()
        m = o.observe(LUNE).apparent()
        sep = s.separation_from(m).radians
        rs = 696000.0 / s.distance().km
        rm = 1737.4 / m.distance().km
        alt = s.altaz()[0].degrees
        mag = np.where((sep < rs + rm) & (alt > -0.8), (rs + rm - sep) / (2 * rs), 0)
        if mag.max() <= 0:
            continue
        i = int(np.argmax(mag))
        idx = np.nonzero(mag > 0)[0]
        debut, fin = tt[int(idx[0])], tt[int(idx[-1])]
        g = recouvrement(float(sep[i]), float(rs[i]), float(rm[i]))
        genre = 'totale' if (rm[i] >= rs[i] and sep[i] < rm[i] - rs[i]) else \
            'annulaire' if (sep[i] < rs[i] - rm[i]) else 'partielle'
        leve_tard = alt[int(idx[0])] < 0.5        # commence avant le lever du Soleil
        couche_tot = alt[int(idx[-1])] < 0.5      # finit apres le coucher
        de_ = ('du lever du Soleil (' + heure(debut) + ')') if leve_tard else 'de ' + heure(debut)
        a_ = (' au coucher du Soleil (' + heure(fin) + ')') if couche_tot else ' à ' + heure(fin)
        d = ('Vue d’Albigny : ' + de_ + a_ + ', maximum à '
             + heure(tt[i]) + ', le Soleil à ' + fr(alt[i], 0) + '° de hauteur. La Lune masque '
             + fr(g * 100, 0) + ' % de la surface du Soleil. Jamais sans filtre solaire homologué.')
        ev.append(sortie(tt[i], 'eclipse', 'Éclipse ' + genre + ' de Soleil', d, 3))
    return ev


def pluies(t0, t1):
    ev = []
    for nom, lam, zhr, radiant, niveau in PLUIES:
        def f(t, lam=lam):
            lon = TERRE.at(t).observe(SOLEIL).apparent().frame_latlon(ecliptic_J2000_frame)[1].degrees
            return ((lon - lam) % 360) < 180
        f.step_days = 30
        t, y = find_discrete(t0, t1, f)
        for ti, yi in zip(t, y):
            if not yi:
                continue
            # la Lune la nuit du maximum, vers 3 h du matin
            dl = local(ti)
            nuit = dl if dl.hour < 12 else dl + timedelta(days=1)
            t3 = ts.from_datetime(datetime(nuit.year, nuit.month, nuit.day, 3, tzinfo=PARIS))
            e = TERRE.at(t3)
            pl = e.observe(LUNE).apparent()
            fr_ecl = float(almanac.fraction_illuminated(eph, 'moon', t3))
            hl = ICI.at(t3).observe(LUNE).apparent().altaz()[0].degrees
            lune = ('Lune éclairée à ' + fr(fr_ecl * 100, 0) + ' %'
                    + (', couchée à 3 h : bonnes conditions.' if hl < 0 else
                       ', levée à 3 h : elle gênera.' if fr_ecl > 0.4 else ', levée à 3 h.'))
            veille = (nuit - timedelta(days=1))
            if 8 <= dl.hour < 19:
                # maximum en plein jour : les deux nuits qui l'encadrent se valent
                guet = (nuit_du(dl - timedelta(days=1), dl) + ' et '
                        + nuit_du(dl, dl + timedelta(days=1)).replace('la nuit ', 'celle '))
            else:
                guet = nuit_du(veille, nuit)
            d = ('Maximum vers ' + heure(ti) + '. À guetter ' + guet + ', radiant '
                 + ('dans le ' if radiant in ('Bouvier', 'Verseau', 'Lion') else
                    'dans la ' if radiant in ('Lyre', 'Petite Ourse') else
                    'dans les ' if radiant == 'Gémeaux' else 'dans ') + radiant
                 + ', jusqu’à ' + str(zhr) + ' météores par heure en ciel parfait. ' + lune)
            ev.append(sortie(ti, 'meteores', nom, d, niveau))
    return ev


def planetes_visibles(depart, semaines=58):
    """Pour chaque semaine : quelles planetes voir, et quand dans la nuit."""
    sortie_ = []
    f = almanac.dark_twilight_day(eph, wgs84.latlon(LAT, LON))
    for k in range(semaines):
        jour = depart + timedelta(days=7 * k)
        midi = ts.from_datetime(datetime(jour.year, jour.month, jour.day, 12, tzinfo=PARIS))
        demain = ts.from_datetime(datetime(jour.year, jour.month, jour.day, 12, tzinfo=PARIS)
                                  + timedelta(days=1))
        tt = ts.tt_jd(np.linspace(midi.tt, demain.tt, 24 * 6 + 1))
        o = ICI.at(tt)
        sa = o.observe(SOLEIL).apparent().altaz()[0].degrees
        nuit = sa < -6
        if not nuit.any():
            continue
        i0, i1 = np.nonzero(nuit)[0][[0, -1]]
        liste = []
        for nom, cible, _ in PLANETES:
            p = o.observe(cible).apparent()
            h = p.altaz()[0].degrees
            vu = nuit & (h > 8)
            pos = TERRE.at(tt[(i0 + i1) // 2]).observe(cible)
            mag = float(planetary_magnitude(pos))
            c = CONST(pos)
            if not vu.any():
                liste.append({'astre': nom, 'visible': False, 'mag': round(mag, 1),
                              'const': NOMS_CONST.get(c, c), 'texte': 'trop proche du Soleil'})
                continue
            idx = np.nonzero(vu)[0]
            a, b = idx[0], idx[-1]
            part = (b - a + 1) / (i1 - i0 + 1)
            milieu = (a + b) / 2 - i0
            moment = ('toute la nuit' if part > 0.75 else
                      'le soir' if milieu < (i1 - i0) * 0.4 else
                      'le matin' if milieu > (i1 - i0) * 0.6 else 'en milieu de nuit')
            liste.append({'astre': nom, 'visible': True, 'mag': round(mag, 1),
                          'const': NOMS_CONST.get(c, c), 'moment': moment,
                          'de': heure(tt[a]), 'a': heure(tt[b]),
                          'haut': round(float(h[idx].max()))})
        sortie_.append({'semaine': jour.strftime('%Y-%m-%d'), 'planetes': liste})
    return sortie_


def tout(aujourdhui=None):
    a = aujourdhui or datetime.now(PARIS).date()
    t0 = ts.from_datetime(datetime(a.year, a.month, a.day, tzinfo=PARIS) - timedelta(days=JOURS_AVANT))
    t1 = ts.from_datetime(datetime(a.year, a.month, a.day, tzinfo=PARIS) + timedelta(days=JOURS_APRES))
    ev = []
    for f in (phases, saisons, oppositions, elongations, rapprochements_lune,
              rapprochements_planetes, eclipses_lune, eclipses_soleil, pluies):
        ev += f(t0, t1)
    ev.sort(key=lambda e: e['t'])
    # la semaine qui commence le lundi precedent, pour couvrir le jour meme
    lundi = a - timedelta(days=a.weekday())
    return {'calcule': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
            'du': a.strftime('%Y-%m-%d'), 'lieu': 'Albigny-sur-Saône',
            'source': 'Éphémérides JPL DE421 (Skyfield) ; pluies d’étoiles filantes : IMO',
            'liste': ev, 'planetes': planetes_visibles(lundi)}


if __name__ == '__main__':
    import json
    import sys
    d = tout()
    json.dump(d, sys.stdout, ensure_ascii=False, indent=1)
