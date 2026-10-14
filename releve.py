#!/usr/bin/env python3
"""
Robot de releve des actualites de SkyJo.

Lance toutes les quatre heures par GitHub (voir .github/workflows/releve.yml).
Il lit quelques flux d'actualite astronomique et la liste des supernovae
brillantes, et ecrit le tout dans actus.json, que le site SkyJo vient lire.

Regles qu'il respecte :
- des articles, il ne garde que le titre, la date, la source, le lien et
  l'adresse de l'image d'illustration que l'editeur publie lui-meme (dans
  son flux, ou a defaut dans l'aperçu de sa page). Jamais le texte, pas
  meme le resume. L'image n'est pas copiee : la page l'affiche depuis le
  site de l'editeur, comme le ferait un lecteur de flux ;
- des supernovae, il ne garde que des faits publies (nom, galaxie, position,
  magnitudes et leurs dates). Aucun chiffre n'est extrapole ;
- si une source ne repond pas, il garde ce qu'il avait releve la fois
  precedente pour elle, et le note dans le fichier.

Aucune bibliotheque a installer : tout vient de Python lui-meme.
"""
import gzip
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

ICI = os.path.dirname(os.path.abspath(__file__))
SORTIE = os.path.join(ICI, 'actus.json')

# ------------------------------------------------------------------------
# Les sources. Pour en ajouter une : copier un bloc et changer nom, site et
# flux. "exclure" ecarte les articles dont le titre ou les etiquettes
# contiennent l'un de ces mots (Futura melange astronomie et industrie
# spatiale, satellites militaires compris).
# ------------------------------------------------------------------------
SOURCES = [
    # Le blog d'un photographe du ciel : observations, ephemerides du mois,
    # images commentees. Heberge par Futura, mais tenu par son seul auteur.
    {'id': 'cielmania', 'nom': 'Cielmania (J.-B. Feldmann)',
     'site': 'https://blogs.futura-sciences.com/feldmann/',
     'flux': 'https://blogs.futura-sciences.com/feldmann/feed/',
     'images': ['blogs.futura-sciences.com']},
    # Rendez-vous du ciel a observer, par un site de vulgarisation francais
    {'id': 'stelvision', 'nom': 'Stelvision',
     'site': 'https://www.stelvision.com/astro/',
     'flux': 'https://www.stelvision.com/astro/feed/',
     'images': ['www.stelvision.com'],
     # le site tient aussi une boutique : on ecarte ce qui en fait la promotion
     'exclure': ['boutique', 'lunettes d', 'filtre', 'de stelvision', 'où trouver',
                 'ou trouver', 'promo', 'offre', 'soldes', 'cadeau', 'livraison',
                 'commande', 'nouveauté', 'nouveaute']},
    # Communiques de l'Observatoire europeen austral, en francais
    {'id': 'eso', 'nom': 'ESO',
     'site': 'https://www.eso.org/public/france/news/',
     'flux': 'https://www.eso.org/public/france/news/feed/',
     'images': ['cdn.eso.org']},
    {'id': 'obspm', 'nom': 'Observatoire de Paris',
     'site': 'https://observatoiredeparis.psl.eu',
     'flux': 'https://observatoiredeparis.psl.eu/spip.php?id_rubrique=105&page=backend',
     # le flux ne porte pas d'image : on lit l'aperçu publie par la page
     'images': ['observatoiredeparis.psl.eu'], 'image_de_la_page': True,
     # l'Observatoire publie aussi ses prix et nominations : utiles, mais
     # pas de l'actualite du ciel
     'exclure': ['laureat', 'lauréat', 'médaille', 'medaille', 'prix ', 'recrute',
                 'nomination', 'nommé', 'nommée']},
    # Peu d'articles, mais de fond, ecrits avec les chercheurs du CNRS
    {'id': 'cnrs', 'nom': 'CNRS Le Journal',
     'site': 'https://lejournal.cnrs.fr/astronomie',
     'flux': 'https://lejournal.cnrs.fr/rss/32',
     'images': ['lejournal.cnrs.fr']},
]
# Les sites d'ou une image d'illustration peut venir. La page web n'affiche
# que celles-la, et sa politique de securite (fichier _headers du site) ne
# laisse charger des images que depuis eux : en ajouter un ici demande de
# l'ajouter aussi la-bas.

SUPERNOVAE = {
    'nom': 'Rochester Astronomy, liste des supernovae actives',
    'page': 'https://www.rochesterastronomy.org/snimages/snactive.html',
    'lien': 'https://www.rochesterastronomy.org/supernova.html',
}

JOURS_ARTICLES = 75        # au-dela, un article n'est plus une actualite
PAGES_PAR_RELEVE = 8       # apercus de pages lus au plus par passage (politesse)
PAR_SOURCE = 12
TOTAL = 40
MAG_LIMITE = 16.0          # au-dela, hors de portee d'un petit instrument
DEC_MINIMUM = -35.0        # en dessous, ne se leve pas assez depuis la France
JOURS_MESURE = 45          # derniere mesure plus vieille : on l'ecarte

AGENT = ('SkyJo-releve/1.0 (lecteur de flux personnel, une visite toutes les '
         'quatre heures)')


def maintenant():
    return datetime.now(timezone.utc)


def lire(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': AGENT,
        'Accept': 'application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.5',
        'Accept-Encoding': 'gzip',
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        brut = r.read()
        if r.headers.get('Content-Encoding', '').lower() == 'gzip' or brut[:2] == b'\x1f\x8b':
            brut = gzip.decompress(brut)
        jeu = r.headers.get_content_charset() or 'utf-8'
    try:
        return brut.decode(jeu)
    except (LookupError, UnicodeDecodeError):
        return brut.decode('utf-8', 'replace')


# ------------------------------------------------------------------------
# Flux RSS et Atom
# ------------------------------------------------------------------------
def propre(texte):
    """Titre lisible : sans balises, entites decodees, espaces ecrases."""
    if not texte:
        return ''
    t = re.sub(r'<[^>]+>', ' ', texte)
    t = html.unescape(html.unescape(t))
    return re.sub(r'\s+', ' ', t).strip()


def date_de(texte):
    if not texte:
        return None
    texte = texte.strip()
    try:
        d = parsedate_to_datetime(texte)           # format des pubDate
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = datetime.fromisoformat(texte.replace('Z', '+00:00'))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def local(el):
    """Nom d'une balise sans son espace de noms."""
    return el.tag.rsplit('}', 1)[-1] if isinstance(el.tag, str) else ''


def image_valide(url, source):
    """Une adresse d'image chiffree, venue d'un des sites prevus pour la source."""
    if not url:
        return None
    url = html.unescape(url.strip())
    m = re.match(r'https://([^/:?#]+)[/?#]', url)
    if not m or m.group(1).lower() not in source.get('images', []):
        return None
    if re.search(r'[\s"<>\\]', url) or len(url) > 400:
        return None
    return url


def premiere_image(texte):
    m = re.search(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']', texte or '', re.I)
    return m.group(1) if m else None


def image_de_la_page(page):
    """L'aperçu que la page publie pour les reseaux (twitter:image, plus leger,
    puis og:image)."""
    for nom in ('twitter:image', 'og:image'):
        for motif in (r'<meta[^>]+(?:name|property)\s*=\s*["\']' + re.escape(nom)
                      + r'["\'][^>]*content\s*=\s*["\']([^"\']+)',
                      r'<meta[^>]+content\s*=\s*["\']([^"\']+)["\'][^>]*(?:name|property)\s*=\s*["\']'
                      + re.escape(nom) + r'["\']'):
            m = re.search(motif, page, re.I)
            if m:
                return m.group(1)
    return None


def articles_du_flux(xml, source):
    racine = ET.fromstring(xml.encode('utf-8') if isinstance(xml, str) else xml)
    entrees = [e for e in racine.iter() if local(e) in ('item', 'entry')]
    exclure = [m.lower() for m in source.get('exclure', [])]
    sortie = []
    for e in entrees:
        titre = lien = None
        dates = []
        etiquettes = []
        images = []           # par ordre de preference
        for f in e:
            n = local(f)
            if n == 'title':
                titre = propre(''.join(f.itertext()))
            elif n == 'link':
                # RSS : le lien est le texte ; Atom : il est dans href
                if f.get('href') and f.get('rel', 'alternate') == 'alternate':
                    lien = f.get('href')
                elif (f.text or '').strip() and not lien:
                    lien = f.text.strip()
            elif n in ('pubDate', 'date', 'published', 'updated', 'issued'):
                dates.append((n, f.text))
            elif n == 'category':
                etiquettes.append((f.text or f.get('term') or '').lower())
            elif n == 'guid' and not lien and (f.text or '').startswith('http') \
                    and f.get('isPermaLink', 'true') != 'false':
                lien = f.text.strip()
            elif n == 'enclosure' and (f.get('type') or '').startswith('image/'):
                images.insert(0, f.get('url'))
            elif n in ('thumbnail', 'content') and f.get('url') and \
                    ((f.get('medium') == 'image') or (f.get('type') or '').startswith('image/')
                     or n == 'thumbnail'):
                images.insert(0, f.get('url'))
            elif n in ('encoded', 'description', 'summary'):
                images.append(premiere_image(''.join(f.itertext()) or f.text or ''))
        # la date de publication prime sur celle de mise a jour
        ordre = {'pubDate': 0, 'published': 0, 'date': 1, 'issued': 2, 'updated': 3}
        dates.sort(key=lambda x: ordre.get(x[0], 9))
        quand = None
        for _, t in dates:
            quand = date_de(t)
            if quand:
                break
        # liens chiffres seulement : un lien en http, ou de tout autre type,
        # n'a rien a faire dans la page
        if not titre or not lien or not lien.startswith('https://') or not quand:
            continue
        botte = (titre.lower() + ' | ' + ' | '.join(etiquettes))
        if any(m in botte for m in exclure):
            continue
        art = {'titre': titre[:220], 'date': quand.strftime('%Y-%m-%dT%H:%M:%SZ'),
               'source': source['id'], 'lien': lien}
        for im in images:
            im = image_valide(im, source)
            if im:
                art['image'] = im
                break
        sortie.append(art)
    return sortie


# ------------------------------------------------------------------------
# Supernovae
# ------------------------------------------------------------------------
class Tableaux(HTMLParser):
    """Lit tous les tableaux d'une page, meme mal fermes (cas frequent sur
    les pages anciennes) : une nouvelle ligne ou cellule ferme la precedente."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tableaux = []
        self.ligne = None
        self.cellule = None

    def _fin_cellule(self):
        if self.cellule is not None and self.ligne is not None:
            self.ligne.append(re.sub(r'\s+', ' ', ''.join(self.cellule)).strip())
        self.cellule = None

    def _fin_ligne(self):
        self._fin_cellule()
        if self.ligne and self.tableaux:
            self.tableaux[-1].append(self.ligne)
        self.ligne = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._fin_ligne()
            self.tableaux.append([])
        elif tag == 'tr':
            self._fin_ligne()
            if not self.tableaux:
                self.tableaux.append([])
            self.ligne = []
        elif tag in ('td', 'th'):
            self._fin_cellule()
            if self.ligne is None:
                self.ligne = []
            self.cellule = []
        elif tag == 'br' and self.cellule is not None:
            self.cellule.append(' ')

    def handle_endtag(self, tag):
        if tag in ('td', 'th'):
            self._fin_cellule()
        elif tag in ('tr', 'table'):
            self._fin_ligne()

    def handle_data(self, data):
        if self.cellule is not None:
            self.cellule.append(data)


def sexa(texte, heures):
    m = re.match(r'\s*([-+\u2212]?)(\d{1,3})[:\s](\d{1,2})[:\s](\d{1,2}(?:\.\d+)?)', texte or '')
    if not m:
        return None
    v = int(m.group(2)) + int(m.group(3)) / 60 + float(m.group(4)) / 3600
    if m.group(1) in ('-', '\u2212'):
        v = -v
    return round(v * 15 if heures else v, 5)


def nombre(texte):
    m = re.search(r'-?\d+(?:\.\d+)?', texte or '')
    return float(m.group(0)) if m else None


def jour(texte):
    m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', texte or '')
    return '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3))) if m else None


COLONNES = {          # intitule publie -> notre nom ; compare sans casse ni espaces
    'sn': 'nom', 'hostgalaxy': 'hote', 'host': 'hote', 'r.a.': 'ra', 'decl.': 'dec',
    'latestmag': 'mag', 'lastobserved': 'mag_date', 'type': 'type',
    'maxmag': 'max', 'maxmagdate': 'max_date', 'firstobserved': 'decouverte',
    'discoverer(s)': 'decouvreur', 'discoverer': 'decouvreur',
}


def supernovae_de(page):
    p = Tableaux()
    p.feed(page)
    p.close()
    for tab in p.tableaux:
        for i, ligne in enumerate(tab[:5]):
            cles = [re.sub(r'\s+', '', c).lower() for c in ligne]
            if 'sn' in cles and 'r.a.' in cles and 'decl.' in cles:
                carte = {k: COLONNES[c] for k, c in enumerate(cles) if c in COLONNES}
                return [dict((carte[k], v) for k, v in enumerate(r) if k in carte)
                        for r in tab[i + 1:]]
    raise ValueError("tableau des supernovae introuvable : la page a change de forme")


def selection_supernovae(lignes):
    limite = (maintenant() - timedelta(days=JOURS_MESURE)).strftime('%Y-%m-%d')
    garde = []
    for r in lignes:
        nom = (r.get('nom') or '').strip()
        if not re.match(r'^\d{4}[a-z]+$', nom):
            continue
        ra, dec = sexa(r.get('ra'), True), sexa(r.get('dec'), False)
        mag, md = nombre(r.get('mag')), jour(r.get('mag_date'))
        ancienne = '*' in (r.get('mag') or '')
        if ra is None or dec is None or mag is None:
            continue
        if mag > MAG_LIMITE or dec < DEC_MINIMUM or ancienne or not md or md < limite:
            continue
        typ = (r.get('type') or '').strip()
        classee = bool(typ) and typ.lower() not in ('none', 'unk', '?', '-')
        hote = (r.get('hote') or '').strip()
        garde.append({
            'nom': ('SN ' if classee else 'AT ') + nom,
            'hote': '' if hote.lower() in ('none', 'anon', 'anonymous', '-') else hote,
            'ra': ra, 'dec': dec,
            'mag': mag, 'mag_date': md,
            'max': nombre(r.get('max')), 'max_date': jour(r.get('max_date')),
            'type': typ if classee else '',
            'decouverte': jour(r.get('decouverte')),
            'decouvreur': (r.get('decouvreur') or '').strip()[:60],
        })
    garde.sort(key=lambda x: x['mag'])
    return garde[:20]


# ------------------------------------------------------------------------
def precedent():
    try:
        with open(SORTIE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def sans_horodatage(d):
    d = json.loads(json.dumps(d))
    d.pop('maj', None)
    for s in d.get('sources', []):
        s.pop('verifie', None)
    d.get('supernovae', {}).pop('verifie', None)
    (d.get('evenements') or {}).pop('calcule', None)
    for v in (d.get('ciel') or {}).values():
        if isinstance(v, dict):
            v.pop('verifie', None)
    return d


def main():
    avant = precedent()
    anciens = {}
    for a in avant.get('articles', []):
        anciens.setdefault(a.get('source'), []).append(a)
    etats_avant = {s.get('id'): s for s in avant.get('sources', [])}
    t = maintenant().strftime('%Y-%m-%dT%H:%M:%SZ')
    limite = maintenant() - timedelta(days=JOURS_ARTICLES)

    images_avant = {a['lien']: a['image'] for a in avant.get('articles', [])
                    if a.get('lien') and a.get('image')}
    pages_lues = 0

    articles, etats = [], []
    for s in SOURCES:
        etat = {'id': s['id'], 'nom': s['nom'], 'site': s['site']}
        try:
            liste = articles_du_flux(lire(s['flux']), s)
            liste = [a for a in liste if date_de(a['date']) >= limite]
            liste.sort(key=lambda a: a['date'], reverse=True)
            liste = liste[:PAR_SOURCE]
            # Sans image dans le flux : l'aperçu de la page, lu une seule fois
            # par article (ensuite on reprend ce qu'on avait trouve).
            if s.get('image_de_la_page'):
                for a in liste:
                    if a.get('image'):
                        continue
                    if a['lien'] in images_avant:
                        a['image'] = images_avant[a['lien']]
                        continue
                    if pages_lues >= PAGES_PAR_RELEVE:
                        continue
                    pages_lues += 1
                    try:
                        im = image_valide(image_de_la_page(lire(a['lien'])), s)
                    except Exception:
                        im = None
                    if im:
                        a['image'] = im
            etat.update(ok=True, verifie=t, n=len(liste))
            print('%-24s %2d articles' % (s['nom'], len(liste)))
        except Exception as e:                       # une source en panne n'arrete rien
            liste = anciens.get(s['id'], [])
            prec = etats_avant.get(s['id'], {})
            etat.update(ok=False, erreur=str(e)[:160], n=len(liste),
                        verifie=prec.get('verifie'))
            print('%-24s ECHEC (%s), on garde les %d precedents' % (s['nom'], e, len(liste)))
        articles += liste
        etats.append(etat)

    vus, uniques = set(), []
    for a in sorted(articles, key=lambda a: a['date'], reverse=True):
        if a['lien'] in vus:
            continue
        vus.add(a['lien'])
        uniques.append(a)
    uniques = uniques[:TOTAL]

    sn = {'nom': SUPERNOVAE['nom'], 'lien': SUPERNOVAE['lien'],
          'limite_mag': MAG_LIMITE}
    try:
        liste = selection_supernovae(supernovae_de(lire(SUPERNOVAE['page'])))
        # Depuis quand chacune est-elle a portee ? Reprise du releve precedent ;
        # une nouvelle venue prend la date du jour (le site en fait un bandeau).
        # Au premier passage de ce calcul, les anciennes restent sans date.
        avant_sn = {x.get('nom'): x for x in avant.get('supernovae', {}).get('liste', [])}
        for x in liste:
            if x['nom'] in avant_sn:
                x['a_portee_depuis'] = avant_sn[x['nom']].get('a_portee_depuis', '')
            elif avant_sn or avant.get('supernovae'):
                x['a_portee_depuis'] = t[:10]
            else:
                x['a_portee_depuis'] = ''
        sn.update(ok=True, verifie=t, liste=liste)
        print('%-24s %2d plus brillantes que %.1f' % ('Supernovae', len(liste), MAG_LIMITE))
    except Exception as e:
        prec = avant.get('supernovae', {})
        sn.update(ok=False, erreur=str(e)[:160], verifie=prec.get('verifie'),
                  liste=prec.get('liste', []))
        print('Supernovae               ECHEC (%s), on garde la liste precedente' % e)

    # Les evenements du ciel : calcules, pas releves. Une erreur de calcul
    # ne doit pas priver le site des autres rubriques.
    try:
        import evenements
        ev = evenements.tout()
        print('%-24s %2d evenements sur 400 jours' % ('Evenements', len(ev['liste'])))
    except Exception as e:
        ev = avant.get('evenements')
        print('Evenements               ECHEC (%s), on garde le calcul precedent' % e)

    # Seeing et transparence, cometes, aurores : chacun a part, et en cas
    # d'echec on garde le releve precedent.
    ciel = {}
    try:
        import extras
        for cle, fonction in (('seeing', extras.seeing), ('cometes', extras.cometes),
                              ('aurores', extras.aurores)):
            try:
                ciel[cle] = fonction()
                ciel[cle]['verifie'] = t
                print('%-24s ok' % cle.capitalize())
            except Exception as e:
                prec = (avant.get('ciel') or {}).get(cle)
                if prec:
                    ciel[cle] = prec
                ciel.setdefault('pannes', {})[cle] = (type(e).__name__ + ' : ' + str(e))[:160]
                print('%-24s ECHEC (%s)' % (cle.capitalize(), str(e)[:120]))
    except Exception as e:
        ciel = dict(avant.get('ciel') or {})
        ciel['pannes'] = {'module': (type(e).__name__ + ' : ' + str(e))[:160]}
        print('Ciel                     ECHEC (%s)' % e)

    nouveau = {'version': 1, 'maj': t, 'sources': etats,
               'articles': uniques, 'supernovae': sn, 'evenements': ev, 'ciel': ciel}

    # Rien de neuf : on ne touche pas au fichier, il n'y aura pas d'envoi.
    if avant and sans_horodatage(avant) == sans_horodatage(nouveau):
        print('Rien de nouveau depuis le dernier releve.')
        return 0
    with open(SORTIE, 'w', encoding='utf-8') as f:
        json.dump(nouveau, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    print('actus.json mis a jour : %d articles, %d supernovae.'
          % (len(uniques), len(sn['liste'])))
    if not any(s['ok'] for s in etats) and not sn['ok']:
        print('Toutes les sources ont echoue : a regarder.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
