# skyjo-actus

Le robot qui alimente la page « Actualités » de SkyJo.

Toutes les quatre heures, GitHub lance `releve.py`, qui lit :

- les flux d'actualité de **Cielmania** (le blog de Jean-Baptiste Feldmann, photographe du ciel), de **Stelvision**, de l'**ESO** (communiqués en français), de l'**Observatoire de Paris** et de **CNRS Le Journal** (rubrique Astronomie) ;
- la liste des **supernovae actives** tenue par Rochester Astronomy.

Il écrit le résultat dans `actus.json`, que le site vient lire.

**Ce qui est conservé :** des articles, seulement le titre, la date, la source, le lien et l'adresse de l'image d'illustration publiée par l'éditeur (jamais le texte ; l'image n'est pas copiée, la page l'affiche depuis le site de l'éditeur). Des supernovae, seulement des faits publiés : nom, galaxie hôte, position, dernière magnitude mesurée et sa date, magnitude maximale et sa date. Rien n'est extrapolé.

**Si une source ne répond pas**, le robot garde ce qu'il avait relevé la fois précédente pour elle et le note dans le fichier (`"ok": false`).

## Entretien

- **Lancer un relevé à la main :** onglet *Actions*, « Releve des actualites », bouton *Run workflow*.
- **Si le robot s'est arrêté :** GitHub met en sommeil les tâches planifiées d'un dépôt public resté soixante jours sans activité. Les relevés suffisent normalement à l'entretenir. Sinon, onglet *Actions*, « Releve des actualites », bouton *Enable workflow*.
- **Ajouter ou retirer une source :** liste `SOURCES` en tête de `releve.py`.

**Ciel de la nuit (depuis octobre 2026, fichier `extras.py`)** : seeing et transparence pour Albigny d'après 7Timer! (produit ASTRO, classes 1 à 8), comètes à portée calculées à partir des éléments d'orbite du Minor Planet Center (magnitude selon la formule du MPC, magnitude 12 au plus, au moins 15° de hauteur en nuit noire), indice Kp observé et prévu de la NOAA (SWPC). Chaque source peut échouer seule : le relevé précédent est alors gardé. Pour les supernovae, `a_portee_depuis` note le jour où chacune est entrée dans la liste.
