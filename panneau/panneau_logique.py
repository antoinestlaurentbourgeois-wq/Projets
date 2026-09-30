# -*- coding: utf-8 -*-
"""
Logique du panneau de contrôle (sans interface graphique).

Ce fichier sait :
  - quels composants existent et de quoi ils dépendent ;
  - dans quel ordre les démarrer et les arrêter ;
  - comment vérifier l'état de chacun (voyant) ;
  - comment démarrer / arrêter chacun.

Il ne lance jamais une commande directement : il passe par un objet « système »
(SystemeWindows sur votre PC, Simulateur dans les tests). C'est ce qui permet
de tester toute la logique sans Windows, sans Docker et sans LM Studio.
"""

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import reglages as R

journal = logging.getLogger("panneau")
journal.addHandler(logging.NullHandler())  # le panneau branche le fichier journal

# ---------------------------------------------------------------------------
# États possibles d'un composant (= couleur du voyant)
# ---------------------------------------------------------------------------

ACTIF = "actif"            # vert
ARRETE = "arrete"          # rouge
TRANSITION = "transition"  # orange : démarre ou s'arrête
INCONNU = "inconnu"        # gris


@dataclass
class Etat:
    code: str
    message: str = ""


@dataclass(frozen=True)
class Composant:
    ident: str
    nom: str
    description: str
    dependances: tuple = ()


# L'ordre de cette liste sert aussi à départager les ex æquo dans le tri.
COMPOSANTS = [
    Composant("docker", "Docker Desktop", "Moteur des conteneurs"),
    Composant("openwebui", "Open WebUI", "Interface web — http://localhost:3000", ("docker",)),
    Composant("kokoro", "Kokoro (voix)", "Synthèse vocale — port 8880", ("docker",)),
    Composant("lmstudio", "Serveur LM Studio", "API sur http://localhost:1234"),
    Composant("gemma", "Chef local", "Modèle chef de Crew (à changer dans la page « Chef d'équipe » du Centre)", ("lmstudio",)),
    Composant("embeddings", "Modèle d'embeddings", "nomic-embed-text v1.5 — 84 Mo", ("lmstudio",)),
    Composant("crew", "Serveur Crew", "Équipe d'agents CrewAI — port 8765", ("gemma",)),
]
PAR_ID = {c.ident: c for c in COMPOSANTS}


def nom(ident):
    return PAR_ID[ident].nom


# ---------------------------------------------------------------------------
# Chef local de Crew (modèle LM Studio choisi par Antoine ; gemma par défaut)
# ---------------------------------------------------------------------------

_ID_MODELE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$")


def identifiant_modele_valide(m):
    """Identifiant LM Studio sûr avant tout emploi dans une commande : caractères simples, pas de « .. », pas de tiret au début."""
    return isinstance(m, str) and bool(_ID_MODELE.match(m)) and ".." not in m and not m.startswith(("-", "/"))


@dataclass
class Chef:
    modele: str = R.MODELE_CHEF_DEFAUT
    contexte: int = R.CONTEXTE_CHEF_DEFAUT
    parallele: int = R.PARALLELE_CHEF_DEFAUT


def _entier_borne(v, defaut, bas, haut):
    return v if isinstance(v, int) and not isinstance(v, bool) and bas <= v <= haut else defaut


def chef_depuis_donnees(d):
    """{"modele", "contexte", "parallele"} -> Chef ; toute valeur absente ou invalide redevient la valeur par défaut (gemma)."""
    if not isinstance(d, dict):
        return Chef()
    modele = d.get("modele") if identifiant_modele_valide(d.get("modele")) else R.MODELE_CHEF_DEFAUT
    return Chef(modele, _entier_borne(d.get("contexte"), R.CONTEXTE_CHEF_DEFAUT, 512, 4_000_000),
                _entier_borne(d.get("parallele"), R.PARALLELE_CHEF_DEFAUT, 1, 64))


def lire_chef_fichier(texte):
    """Contenu de chef_crew.json -> Chef. Absent, illisible ou invalide -> gemma (google/gemma-4-12b-qat, 32000, 4)."""
    try:
        return chef_depuis_donnees(json.loads((texte or "").lstrip("\ufeff")))
    except (TypeError, ValueError):
        return Chef()


# ---------------------------------------------------------------------------
# Ordre des dépendances
# ---------------------------------------------------------------------------

def ordre_demarrage(composants=COMPOSANTS):
    """Trie les composants pour que chacun vienne APRÈS ses dépendances.

    En cas d'égalité, on garde l'ordre de la liste (tri topologique stable).
    Lève ValueError si les dépendances forment une boucle.
    """
    position = {c.ident: i for i, c in enumerate(composants)}
    restants = {c.ident: set(c.dependances) for c in composants}
    for ident, deps in restants.items():
        inconnues = deps - set(position)
        if inconnues:
            raise ValueError(f"{ident} dépend d'un composant inconnu : {inconnues}")
    ordre = []
    while restants:
        prets = [i for i, deps in restants.items() if not deps]
        if not prets:
            raise ValueError("Les dépendances forment une boucle : " + ", ".join(restants))
        choisi = min(prets, key=position.get)
        ordre.append(choisi)
        del restants[choisi]
        for deps in restants.values():
            deps.discard(choisi)
    return ordre


def ordre_arret(composants=COMPOSANTS):
    """L'arrêt se fait dans l'ordre inverse du démarrage."""
    return list(reversed(ordre_demarrage(composants)))


def toutes_dependances(ident, composants=COMPOSANTS):
    """Dépendances directes ET indirectes (Crew -> gemma -> serveur LM Studio)."""
    par_id = {c.ident: c for c in composants}
    trouvees, a_voir = set(), list(par_id[ident].dependances)
    while a_voir:
        d = a_voir.pop()
        if d not in trouvees:
            trouvees.add(d)
            a_voir.extend(par_id[d].dependances)
    return trouvees


def tous_dependants(ident, composants=COMPOSANTS):
    """Composants qui ont besoin de `ident`, directement ou non."""
    return {c.ident for c in composants if ident in toutes_dependances(c.ident, composants)}


def dependances_a_demarrer(ident, etats, composants=COMPOSANTS):
    """Dépendances pas encore actives, dans l'ordre où il faut les démarrer."""
    deps = toutes_dependances(ident, composants)
    return [i for i in ordre_demarrage(composants)
            if i in deps and etats.get(i, Etat(INCONNU)).code != ACTIF]


def dependants_a_arreter(ident, etats, composants=COMPOSANTS):
    """Composants allumés qui dépendent de `ident`, dans l'ordre d'arrêt."""
    deps = tous_dependants(ident, composants)
    return [i for i in ordre_arret(composants)
            if i in deps and etats.get(i, Etat(INCONNU)).code in (ACTIF, TRANSITION)]


# ---------------------------------------------------------------------------
# Analyse des réponses des commandes et des API
# ---------------------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def nettoyer(texte):
    """Retire les codes couleur du terminal et les retours chariot."""
    return _ANSI.sub("", texte or "").replace("\r", "\n")


def resume(texte, longueur=140):
    """Dernière ligne utile d'une sortie de commande, raccourcie."""
    lignes = [l.strip() for l in nettoyer(texte).splitlines() if l.strip()]
    if not lignes:
        return ""
    ligne = lignes[-1]
    return ligne if len(ligne) <= longueur else ligne[:longueur - 1] + "…"


def correspond_modele(identifiant, cle):
    """Vrai si l'identifiant LM Studio désigne le modèle `cle`.

    LM Studio ajoute « :2 », « :3 »... quand il charge une copie supplémentaire.
    Selon les versions, l'éditeur (« google/ ») peut être présent ou non.
    """
    base = re.sub(r":\d+$", "", identifiant.strip()).lower()
    cle = cle.lower()
    return base == cle or base.split("/")[-1] == cle.split("/")[-1]


def analyser_api_modeles(corps, cle):
    """Réponse de GET /api/v0/models -> liste des identifiants chargés pour `cle`.

    Format attendu : {"data": [{"id": "...", "state": "loaded"}, ...]}
    Lève ValueError si la réponse est illisible.
    """
    try:
        donnees = json.loads(corps)
    except (TypeError, ValueError) as e:
        raise ValueError(f"réponse LM Studio illisible : {e}")
    entrees = donnees.get("data") if isinstance(donnees, dict) else donnees
    if not isinstance(entrees, list):
        raise ValueError("réponse LM Studio inattendue (pas de liste « data »)")
    charges = []
    for m in entrees:
        if not isinstance(m, dict):
            continue
        ident = str(m.get("id", ""))
        if m.get("state") == "loaded" and ident and correspond_modele(ident, cle):
            charges.append(ident)
    return charges


def analyser_lms_ps(sortie, cle):
    """Sortie de `lms ps` (JSON ou texte) -> liste des identifiants chargés pour `cle`."""
    texte = nettoyer(sortie).strip()
    # 1) Format JSON (`lms ps --json`) : liste d'objets.
    if texte.startswith("[") or texte.startswith("{"):
        try:
            donnees = json.loads(texte)
            if isinstance(donnees, dict):
                donnees = donnees.get("data") or donnees.get("models") or []
            trouves = []
            for m in donnees:
                if not isinstance(m, dict):
                    continue
                ident = str(m.get("identifier") or m.get("id") or "")
                modele = str(m.get("modelKey") or m.get("path") or ident)
                if ident and (correspond_modele(ident, cle) or correspond_modele(modele, cle)):
                    trouves.append(ident)
            return trouves
        except ValueError:
            pass  # on retente en mode texte
    # 2) Format texte : « Identifier: xxx » (anciennes versions) ou tableau.
    if re.search(r"no models (are )?(currently )?loaded", texte, re.I):
        return []
    trouves = []
    for ligne in texte.splitlines():
        ligne = re.sub(r"^\s*identifier\s*:\s*", "", ligne, flags=re.I)
        premier = ligne.strip().split()
        if premier and correspond_modele(premier[0], cle) and premier[0] not in trouves:
            trouves.append(premier[0])
    return trouves


def analyser_sante_crew(statut, corps):
    """GET /sante doit répondre 200 avec {"ok": true}."""
    if statut != 200:
        return False
    try:
        return json.loads(corps).get("ok") is True
    except (TypeError, ValueError, AttributeError):
        return False


def analyser_inspect(sortie):
    """`docker inspect -f "{{.State.Running}}"` -> True / False / None (illisible)."""
    valeur = nettoyer(sortie).strip().strip('"').lower()
    return {"true": True, "false": False}.get(valeur)


def analyser_tasklist(sortie, programme):
    """`tasklist /FO CSV /NH` -> vrai si `programme` apparaît (indépendant de la langue)."""
    cible = '"' + programme.lower() + '"'
    return any(l.strip().lower().startswith(cible) for l in sortie.splitlines())


def analyser_pids(sortie):
    """Une liste de numéros de processus, un par ligne."""
    return [int(l.strip()) for l in sortie.splitlines() if l.strip().isdigit()]


def analyser_retour_wmi(sortie):
    """Lit « RETOUR=0 » écrit par notre script PowerShell. None si absent."""
    m = re.search(r"RETOUR=(\d+)", sortie or "")
    return int(m.group(1)) if m else None


def chaine_powershell(texte):
    """Met un texte entre apostrophes pour PowerShell (les ' sont doublées)."""
    return "'" + texte.replace("'", "''") + "'"


def url_est_locale(url):
    """Le panneau ne doit contacter QUE ce PC."""
    hote = urllib.parse.urlparse(url).hostname
    return hote in ("localhost", "127.0.0.1")


# ---------------------------------------------------------------------------
# Accès réel à Windows
# ---------------------------------------------------------------------------

@dataclass
class Resultat:
    code: object          # code de sortie, ou None si délai dépassé / introuvable
    sortie: str = ""
    erreur: str = ""

    @property
    def ok(self):
        return self.code == 0

    @property
    def texte(self):
        return (self.sortie or "") + "\n" + (self.erreur or "")


CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                          "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def _decoder(octets):
    for codage in ("utf-8", "cp1252"):
        try:
            return octets.decode(codage)
        except UnicodeDecodeError:
            pass
    return octets.decode("utf-8", errors="replace")


class SystemeWindows:
    """Lance les vraies commandes sur Windows. Aucune n'ouvre de fenêtre."""

    def __init__(self, dossier_temp=None):
        # Fichiers temporaires dans le dossier du panneau (pas sur C:).
        self.dossier_temp = dossier_temp

    def executer(self, args, delai):
        """Lance une commande, attend au plus `delai` secondes."""
        # La sortie va dans des fichiers et non dans des « tuyaux » : si la
        # commande lance un programme qui reste ouvert (ex. LM Studio),
        # on n'attend pas ce programme indéfiniment.
        try:
            with tempfile.TemporaryFile(dir=self.dossier_temp) as f_out, \
                    tempfile.TemporaryFile(dir=self.dossier_temp) as f_err:
                try:
                    proc = subprocess.Popen(args, stdout=f_out, stderr=f_err,
                                            stdin=subprocess.DEVNULL,
                                            creationflags=CREATE_NO_WINDOW)
                except FileNotFoundError:
                    return Resultat(None, "", f"programme introuvable : {args[0]}")
                try:
                    code = proc.wait(timeout=delai)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    return Resultat(None, "", f"délai dépassé ({delai} s)")
                f_out.seek(0)
                f_err.seek(0)
                return Resultat(code, _decoder(f_out.read()), _decoder(f_err.read()))
        except OSError as e:
            return Resultat(None, "", f"erreur système : {e}")

    def powershell(self, script, delai):
        # -EncodedCommand : le script est transmis encodé, donc aucun souci
        # de guillemets ou d'apostrophes dans la ligne de commande.
        code = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return self.executer([POWERSHELL, "-NoProfile", "-NonInteractive",
                              "-ExecutionPolicy", "Bypass", "-EncodedCommand", code], delai)

    def http_get(self, url, delai):
        """Renvoie (code HTTP, texte) ; code None si personne ne répond."""
        return self.http("GET", url, delai)

    def http(self, methode, url, delai, entetes=None, corps_json=None):
        """Requête HTTP vers ce PC uniquement. Renvoie (code HTTP, texte).

        Les en-têtes (qui peuvent contenir une clé) ne sont jamais écrits
        dans le journal ni renvoyés dans un message d'erreur.
        """
        if not url_est_locale(url):
            raise ValueError(f"adresse refusée (pas locale) : {url}")
        donnees = None
        entetes = dict(entetes or {})
        if corps_json is not None:
            donnees = json.dumps(corps_json).encode("utf-8")
            entetes["Content-Type"] = "application/json"
        requete = urllib.request.Request(url, data=donnees, headers=entetes, method=methode)
        # ProxyHandler({}) : ne jamais passer par un proxy, même s'il y en a un.
        ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with ouvreur.open(requete, timeout=delai) as rep:
                return rep.status, rep.read(5_000_000).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                corps = e.read(20_000).decode("utf-8", "replace")
            except OSError:
                corps = ""
            return e.code, corps
        except (urllib.error.URLError, OSError, ValueError) as e:
            return None, str(getattr(e, "reason", e))

    def ouvrir_url(self, url):
        """Ouvre une adresse LOCALE dans le navigateur par défaut."""
        if not url_est_locale(url):
            raise ValueError(f"adresse refusée (pas locale) : {url}")
        os.startfile(url)  # noqa: disponible seulement sous Windows

    def lire_fichier(self, chemin):
        """Texte du fichier (UTF-8, avec ou sans BOM), ou None s'il n'existe pas."""
        try:
            with open(chemin, encoding="utf-8-sig") as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            return None

    def ecrire_fichier(self, chemin, texte):
        """Écrit d'un coup (fichier temporaire puis remplacement) : jamais de fichier à moitié écrit."""
        temporaire = chemin + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            f.write(texte)
        os.replace(temporaire, chemin)

    def fichier_existe(self, chemin):
        return os.path.isfile(chemin)

    def chemin_programme(self, nom_court, candidats):
        """Cherche un programme dans le PATH, puis dans la liste de candidats."""
        trouve = shutil.which(nom_court) if nom_court else None
        if trouve:
            return trouve
        for c in candidats:
            if os.path.isfile(c):
                return c
        return candidats[0] if candidats else nom_court

    def ouvrir_programme(self, chemin):
        """Comme un double-clic (programme indépendant du panneau)."""
        os.startfile(chemin)  # noqa: disponible seulement sous Windows

    def variable_utilisateur_presente(self, nom_var):
        """Vrai si la variable existe dans HKCU\\Environment et n'est pas vide."""
        return bool(self.valeur_variable_utilisateur(nom_var))

    def valeur_variable_utilisateur(self, nom_var):
        """Valeur de la variable dans HKCU\\Environment, ou None.

        Sert uniquement à s'authentifier auprès d'Open WebUI : la valeur n'est
        ni gardée, ni affichée, ni écrite dans le journal.
        """
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as cle:
                valeur, _ = winreg.QueryValueEx(cle, nom_var)
                valeur = str(valeur).strip()
                return valeur or None
        except OSError:
            return None

    def maintenant(self):
        return time.monotonic()

    def dormir(self, secondes):
        time.sleep(secondes)


# ---------------------------------------------------------------------------
# Le contrôleur : vérifier, démarrer, arrêter
# ---------------------------------------------------------------------------

class ErreurAction(Exception):
    """Une action a échoué ; le message est affiché sous le composant."""


class Controleur:
    def __init__(self, systeme):
        self.sys = systeme
        self.docker = systeme.chemin_programme("docker", R.DOCKER_CLI_CANDIDATS)
        self.lms = systeme.chemin_programme("", R.LMS_CANDIDATS)
        # Dernier état connu des modèles (True = chargé), utile quand le
        # serveur LM Studio est arrêté et ne peut plus être interrogé.
        self._modeles_connus = {}
        self._verrou = threading.Lock()
        self._chef_fourni = None      # réglages du chef donnés par le Centre (GET /chef) ; sinon fichier de secours, sinon gemma

    # ----- le chef local (modèle « gemma » des anciennes versions) -------------

    def definir_chef_connu(self, chef):
        """Le Centre donne ici le chef lu auprès de Crew (GET /chef). None : on retombe sur le fichier de secours."""
        self._chef_fourni = chef

    def chef_actuel(self):
        if self._chef_fourni is not None:
            return self._chef_fourni
        return lire_chef_fichier(self.sys.lire_fichier(R.FICHIER_CHEF))

    def _cle_modele(self, ident):
        return self.chef_actuel().modele if ident == "gemma" else R.MODELE_EMBEDDINGS

    # ----- petits outils --------------------------------------------------

    def _cmd(self, args, delai=R.DELAI_COMMANDE_COURTE):
        res = self.sys.executer(args, delai)
        journal.debug("commande %s -> %s", " ".join(args[:4]), res.code)
        return res

    def _attendre(self, condition, delai_max, ident, message, progres, intervalle=3):
        """Répète `condition()` jusqu'à ce qu'elle soit vraie ou que le délai expire."""
        debut = self.sys.maintenant()
        while True:
            if condition():
                return True
            ecoule = self.sys.maintenant() - debut
            if ecoule >= delai_max:
                return False
            progres(ident, Etat(TRANSITION, f"{message} ({int(ecoule)} s)"), False)
            self.sys.dormir(intervalle)

    # ----- tests élémentaires (sans message) -------------------------------

    def _docker_repond(self):
        return self._cmd([self.docker, "info"]).ok

    def _docker_desktop_ouvert(self):
        res = self._cmd(["tasklist", "/FI", "IMAGENAME eq Docker Desktop.exe", "/FO", "CSV", "/NH"])
        return analyser_tasklist(res.sortie, "Docker Desktop.exe")

    def _conteneur_lance(self, conteneur):
        """True / False, ou lève ErreurAction si le conteneur n'existe pas."""
        res = self._cmd([self.docker, "inspect", "-f", "{{.State.Running}}", conteneur])
        if "no such" in res.texte.lower():
            raise ErreurAction(f"Conteneur « {conteneur} » introuvable dans Docker")
        return analyser_inspect(res.sortie) is True

    def _http_ok(self, url):
        statut, _ = self.sys.http_get(url, R.DELAI_HTTP)
        return statut == 200

    def _lmstudio_repond(self):
        return self._http_ok(R.URL_LMSTUDIO)

    def _crew_repond(self):
        return analyser_sante_crew(*self.sys.http_get(R.URL_CREW_SANTE, R.DELAI_HTTP))

    def _pids_crew(self):
        """Processus pythonw/python qui font tourner serveur_crew.py (None si inconnu)."""
        script = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'\" | "
                  "Where-Object { $_.CommandLine -like '*serveur_crew.py*' } | "
                  "ForEach-Object { $_.ProcessId }")
        res = self.sys.powershell(script, R.DELAI_POWERSHELL)
        return analyser_pids(res.sortie) if res.ok else None

    def modeles_charges(self, ident, via_lms_si_besoin=True):
        """Identifiants chargés pour ce modèle, ou None si impossible à savoir.

        1) l'API LM Studio (le plus fiable) ;
        2) sinon `lms ps` (fonctionne aussi quand le serveur HTTP est arrêté,
           mais peut réveiller LM Studio : on ne l'utilise pas pour les voyants).
        """
        cle = self._cle_modele(ident)
        statut, corps = self.sys.http_get(R.URL_LMSTUDIO_MODELES, R.DELAI_HTTP)
        if statut == 200:
            try:
                return analyser_api_modeles(corps, cle)
            except ValueError as e:
                journal.warning("API modèles : %s", e)
        if not via_lms_si_besoin:
            return None
        res = self._cmd([self.lms, "ps", "--json"], R.DELAI_COMMANDE_COURTE)
        if not res.ok:
            res = self._cmd([self.lms, "ps"], R.DELAI_COMMANDE_COURTE)
        return analyser_lms_ps(res.sortie, cle) if res.ok else None

    # ----- vérification des voyants ---------------------------------------

    def verifier_docker(self):
        if self._docker_repond():
            return Etat(ACTIF)
        if self._docker_desktop_ouvert():
            return Etat(TRANSITION, "Docker Desktop est ouvert, mais son moteur n'est pas encore prêt")
        return Etat(ARRETE, "Docker Desktop n'est pas lancé")

    def _verifier_conteneur(self, ident, conteneur, etat_docker, url=None):
        if etat_docker.code != ACTIF:
            return Etat(ARRETE, f"Docker n'est pas lancé : {nom(ident)} ne peut pas démarrer")
        try:
            lance = self._conteneur_lance(conteneur)
        except ErreurAction as e:
            return Etat(ARRETE, str(e))
        if not lance:
            return Etat(ARRETE, "Conteneur arrêté")
        if url is None or self._http_ok(url):
            return Etat(ACTIF)
        return Etat(TRANSITION, "Conteneur lancé, mais le site ne répond pas encore sur le port 3000")

    def verifier_openwebui(self, etat_docker=None):
        etat_docker = etat_docker or self.verifier_docker()
        # Si le site répond, inutile d'interroger Docker.
        if etat_docker.code == ACTIF and self._http_ok(R.URL_WEBUI):
            return Etat(ACTIF)
        return self._verifier_conteneur("openwebui", R.CONTENEUR_WEBUI, etat_docker, R.URL_WEBUI)

    def verifier_kokoro(self, etat_docker=None):
        etat_docker = etat_docker or self.verifier_docker()
        return self._verifier_conteneur("kokoro", R.CONTENEUR_KOKORO, etat_docker)

    def verifier_lmstudio(self):
        if self._lmstudio_repond():
            return Etat(ACTIF)
        if not self.sys.fichier_existe(self.lms):
            return Etat(INCONNU, "lms.exe introuvable (chemin à corriger dans reglages.py)")
        return Etat(ARRETE, "Serveur arrêté")

    def verifier_modele(self, ident, etat_lmstudio=None):
        etat_lmstudio = etat_lmstudio or self.verifier_lmstudio()
        if etat_lmstudio.code == ACTIF:
            charges = self.modeles_charges(ident, via_lms_si_besoin=True)
            if charges is None:
                return Etat(INCONNU, "Impossible de lire la liste des modèles de LM Studio")
            self._modeles_connus[ident] = bool(charges)
            if len(charges) > 1:
                return Etat(ACTIF, f"Attention : {len(charges)} copies chargées (mémoire gaspillée). "
                                   "Éteignez puis rallumez pour n'en garder qu'une.")
            if charges:
                return Etat(ACTIF)
            return Etat(ARRETE, "Non chargé")
        # Serveur arrêté : on ne peut pas interroger LM Studio sans risquer de le réveiller.
        connu = self._modeles_connus.get(ident)
        if connu is False:
            return Etat(ARRETE, "Non chargé (serveur LM Studio arrêté)")
        if connu is True:
            return Etat(INCONNU, "Serveur LM Studio arrêté : état inconnu (le modèle était chargé)")
        return Etat(INCONNU, "Serveur LM Studio arrêté : impossible de vérifier")

    def verifier_crew(self, etat_gemma=None, repond=None):
        if repond is None:
            repond = self._crew_repond()
        if repond:
            return Etat(ACTIF)
        etat_gemma = etat_gemma or self.verifier_modele("gemma")
        if etat_gemma.code == ARRETE:
            return Etat(ARRETE, "gemma n'est pas chargé : le serveur Crew ne peut pas démarrer")
        if etat_gemma.code != ACTIF:
            return Etat(ARRETE, "gemma n'est pas disponible : le serveur Crew ne peut pas démarrer")
        pids = self._pids_crew()
        if pids:
            return Etat(TRANSITION, "Processus présent, mais /sante ne répond pas (démarrage en cours ou bloqué)")
        return Etat(ARRETE, "Arrêté")

    def verifier(self, ident):
        """Vérifie un seul composant."""
        return {
            "docker": self.verifier_docker,
            "openwebui": self.verifier_openwebui,
            "kokoro": self.verifier_kokoro,
            "lmstudio": self.verifier_lmstudio,
            "gemma": lambda: self.verifier_modele("gemma"),
            "embeddings": lambda: self.verifier_modele("embeddings"),
            "crew": self.verifier_crew,
        }[ident]()

    def verifier_cles(self):
        """{nom: True/False} — jamais la valeur de la clé."""
        return {n: bool(self.sys.variable_utilisateur_presente(n)) for n in R.CLES_API}

    def verifier_tout(self):
        """Vérifie tous les composants, en parallèle quand c'est possible."""
        def sur(fonction, *args):
            try:
                return fonction(*args)
            except Exception as e:  # une vérification ne doit jamais planter le panneau
                journal.exception("vérification impossible")
                return Etat(INCONNU, f"Vérification impossible : {e}")

        with ThreadPoolExecutor(max_workers=4) as ex:
            f_docker = ex.submit(sur, self.verifier_docker)
            f_lms = ex.submit(sur, self.verifier_lmstudio)
            f_crew = ex.submit(sur, self._crew_repond)
            docker, lms = f_docker.result(), f_lms.result()
            f_webui = ex.submit(sur, self.verifier_openwebui, docker)
            f_kokoro = ex.submit(sur, self.verifier_kokoro, docker)
            f_emb = ex.submit(sur, self.verifier_modele, "embeddings", lms)
            gemma = sur(self.verifier_modele, "gemma", lms)
            repond = f_crew.result()
            crew = sur(self.verifier_crew, gemma, repond if isinstance(repond, bool) else False)
            etats = {"docker": docker, "openwebui": f_webui.result(), "kokoro": f_kokoro.result(),
                     "lmstudio": lms, "gemma": gemma, "embeddings": f_emb.result(), "crew": crew}
        return etats

    # ----- actions ---------------------------------------------------------

    def demarrer(self, ident, progres):
        return self._action(ident, "demarrer", progres)

    def arreter(self, ident, progres):
        return self._action(ident, "arreter", progres)

    def _action(self, ident, sens, progres):
        """Enveloppe commune : voyant orange, journal, gestion des erreurs."""
        verbe = "Démarrage" if sens == "demarrer" else "Arrêt"
        journal.info("%s de %s", verbe, nom(ident))
        progres(ident, Etat(TRANSITION, f"{verbe} en cours…"), False)
        fonction = getattr(self, f"_{sens}_{ident}", None) or (
            lambda p: getattr(self, f"_{sens}_modele")(ident, p))
        try:
            with self._verrou:
                etat = fonction(progres)
            journal.info("%s de %s : terminé (%s) %s", verbe, nom(ident), etat.code, etat.message)
        except ErreurAction as e:
            etat = Etat(ARRETE if sens == "demarrer" else INCONNU, str(e))
            journal.error("%s de %s : ÉCHEC — %s", verbe, nom(ident), e)
        except Exception as e:
            etat = Etat(INCONNU, f"Erreur inattendue : {e}")
            journal.exception("%s de %s : erreur inattendue", verbe, nom(ident))
        progres(ident, etat, True)
        return etat

    # Docker Desktop

    def _demarrer_docker(self, progres):
        if self._docker_repond():
            return Etat(ACTIF)
        if not self._docker_desktop_ouvert():
            exe = next((c for c in R.DOCKER_DESKTOP_CANDIDATS if self.sys.fichier_existe(c)), None)
            if exe is None:
                raise ErreurAction("Docker Desktop.exe introuvable (chemin à corriger dans reglages.py)")
            self.sys.ouvrir_programme(exe)
        if not self._attendre(self._docker_repond, R.DELAI_DEMARRAGE_DOCKER, "docker",
                              "Docker démarre…", progres, intervalle=4):
            raise ErreurAction(f"Docker ne répond toujours pas après {R.DELAI_DEMARRAGE_DOCKER} s")
        return Etat(ACTIF)

    def _arreter_docker(self, progres):
        if not self._docker_repond() and not self._docker_desktop_ouvert():
            return Etat(ARRETE, "Docker Desktop n'est pas lancé")
        res = self._cmd([self.docker, "desktop", "stop"], R.DELAI_ARRET_DOCKER)
        if not res.ok:
            # Repli : la commande n'existe pas dans cette version, ou a échoué.
            journal.warning("« docker desktop stop » a échoué (%s) : fermeture forcée", resume(res.texte))
            progres("docker", Etat(TRANSITION, "Fermeture de Docker Desktop (méthode de secours)…"), False)
            self._cmd(["taskkill", "/IM", "Docker Desktop.exe", "/T", "/F"])
            self._cmd(["taskkill", "/IM", "com.docker.backend.exe", "/T", "/F"])
        arrete = self._attendre(lambda: not self._docker_repond() and not self._docker_desktop_ouvert(),
                                30, "docker", "Arrêt de Docker…", progres)
        if not arrete:
            raise ErreurAction("Docker est toujours actif après la demande d'arrêt")
        if not res.ok:
            return Etat(ARRETE, "Arrêté par fermeture forcée (la mémoire de WSL peut rester occupée)")
        return Etat(ARRETE)

    # Conteneurs

    def _exiger_docker(self, ident):
        if not self._docker_repond():
            raise ErreurAction(f"Docker n'est pas lancé : {nom(ident)} ne peut pas démarrer")

    def _demarrer_openwebui(self, progres):
        self._exiger_docker("openwebui")
        if self._http_ok(R.URL_WEBUI):
            return Etat(ACTIF)
        if not self._conteneur_lance(R.CONTENEUR_WEBUI):
            res = self._cmd([self.docker, "start", R.CONTENEUR_WEBUI], 60)
            if not res.ok:
                raise ErreurAction("docker start a échoué : " + resume(res.texte))
        if not self._attendre(lambda: self._http_ok(R.URL_WEBUI), R.DELAI_DEMARRAGE_WEBUI,
                              "openwebui", "Open WebUI démarre…", progres):
            raise ErreurAction(f"Le conteneur tourne mais le site ne répond pas après "
                               f"{R.DELAI_DEMARRAGE_WEBUI} s")
        return Etat(ACTIF)

    def _demarrer_kokoro(self, progres):
        self._exiger_docker("kokoro")
        if self._conteneur_lance(R.CONTENEUR_KOKORO):
            return Etat(ACTIF)
        res = self._cmd([self.docker, "start", R.CONTENEUR_KOKORO], 60)
        if not res.ok:
            raise ErreurAction("docker start a échoué : " + resume(res.texte))
        if not self._attendre(lambda: self._conteneur_lance(R.CONTENEUR_KOKORO),
                              R.DELAI_DEMARRAGE_KOKORO, "kokoro", "Kokoro démarre…", progres):
            raise ErreurAction("Le conteneur Kokoro ne reste pas allumé")
        return Etat(ACTIF)

    def _arreter_conteneur(self, ident, conteneur, progres):
        if not self._docker_repond():
            return Etat(ARRETE, "Docker n'est pas lancé : conteneur déjà arrêté")
        if not self._conteneur_lance(conteneur):
            return Etat(ARRETE, "Conteneur arrêté")
        res = self._cmd([self.docker, "stop", conteneur], R.DELAI_ARRET_CONTENEUR)
        if not res.ok or self._conteneur_lance(conteneur):
            raise ErreurAction("docker stop a échoué : " + (resume(res.texte) or "conteneur toujours actif"))
        return Etat(ARRETE, "Conteneur arrêté")

    def _arreter_openwebui(self, progres):
        return self._arreter_conteneur("openwebui", R.CONTENEUR_WEBUI, progres)

    def _arreter_kokoro(self, progres):
        return self._arreter_conteneur("kokoro", R.CONTENEUR_KOKORO, progres)

    # Serveur LM Studio

    def _demarrer_lmstudio(self, progres):
        if self._lmstudio_repond():
            return Etat(ACTIF)
        res = self._cmd([self.lms, "server", "start"], R.DELAI_DEMARRAGE_LMSTUDIO)
        if not self._attendre(self._lmstudio_repond, 30, "lmstudio", "Le serveur démarre…", progres, 2):
            raise ErreurAction("lms server start : " + (resume(res.texte) or "le serveur ne répond pas"))
        return Etat(ACTIF)

    def _arreter_lmstudio(self, progres):
        if not self._lmstudio_repond():
            return Etat(ARRETE, "Serveur arrêté")
        res = self._cmd([self.lms, "server", "stop"], R.DELAI_ARRET_LMSTUDIO)
        if not self._attendre(lambda: not self._lmstudio_repond(), 15, "lmstudio",
                              "Arrêt du serveur…", progres, 2):
            raise ErreurAction("lms server stop : " + (resume(res.texte) or "le serveur répond encore"))
        return Etat(ARRETE, "Serveur arrêté")

    # Modèles

    def _demarrer_modele(self, ident, progres):
        cle = self._cle_modele(ident)
        if not self._lmstudio_repond():
            raise ErreurAction("Le serveur LM Studio est arrêté : impossible de charger le modèle")
        # Vérification juste avant de charger : sinon LM Studio chargerait une 2e copie.
        charges = self.modeles_charges(ident)
        if charges is None:
            raise ErreurAction("Impossible de savoir si le modèle est déjà chargé : chargement annulé "
                               "(pour éviter une 2e copie)")
        if charges:
            self._modeles_connus[ident] = True
            return self.verifier_modele(ident, Etat(ACTIF))
        if ident == "gemma":
            # Le CHEF ACTUEL avec SES réglages (jamais gemma en dur : sinon une 2e copie de gemma saturerait la carte).
            chef = self.chef_actuel()
            args = [self.lms, "load", cle, "--context-length", str(chef.contexte), "--parallel", str(chef.parallele), "-y"]
            delai = R.DELAI_CHARGEMENT_GEMMA
        else:
            args = [self.lms, "load", cle, "-y"]
            delai = R.DELAI_CHARGEMENT_EMBEDDINGS
        progres(ident, Etat(TRANSITION, "Chargement en mémoire vidéo…"), False)
        res = self._cmd(args, delai)
        if not res.ok and "--parallel" in args and "parallel" in res.texte.lower():
            # Ancienne version de lms qui ne connaît pas --parallel : on recharge avec le seul contexte.
            args = [a for i, a in enumerate(args) if a != "--parallel" and args[i - 1] != "--parallel"]
            res = self._cmd(args, delai)
        charges = self.modeles_charges(ident)
        if not charges:
            raise ErreurAction("Chargement échoué : " + (resume(res.texte) or "modèle absent après chargement"))
        self._modeles_connus[ident] = True
        return self.verifier_modele(ident, Etat(ACTIF))

    def _arreter_modele(self, ident, progres):
        if not self._lmstudio_repond() and self._modeles_connus.get(ident) is False:
            return Etat(ARRETE, "Non chargé")
        charges = self.modeles_charges(ident)
        if charges is None:
            raise ErreurAction("Impossible de savoir si le modèle est chargé")
        for identifiant in charges:  # décharge aussi les copies en trop (« :2 »)
            res = self._cmd([self.lms, "unload", identifiant], R.DELAI_DECHARGEMENT)
            if not res.ok:
                journal.warning("lms unload %s : %s", identifiant, resume(res.texte))
        reste = self.modeles_charges(ident)
        if reste:
            raise ErreurAction("Le modèle est toujours chargé après lms unload")
        self._modeles_connus[ident] = False
        return Etat(ARRETE, "Non chargé")

    # Serveur Crew

    def _demarrer_crew(self, progres):
        if self._crew_repond():
            return Etat(ACTIF)
        pids = self._pids_crew()
        if not pids:
            charges = self.modeles_charges("gemma")
            if not charges:
                raise ErreurAction(f"Le chef local ({self.chef_actuel().modele}) n'est pas chargé : le serveur Crew échouerait")
            for f in (R.PYTHONW_CREW, R.SCRIPT_CREW):
                if not self.sys.fichier_existe(f):
                    raise ErreurAction(f"Fichier introuvable : {f}")
            # Lancement par WMI : le serveur ne dépend pas du panneau et
            # survit à sa fermeture (voir la note de la demande).
            ligne = f'"{R.PYTHONW_CREW}" "{R.SCRIPT_CREW}"'
            script = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ "
                      f"CommandLine = {chaine_powershell(ligne)}; "
                      f"CurrentDirectory = {chaine_powershell(R.DOSSIER_CREW)} }}; "
                      "Write-Output (\"RETOUR=\" + $r.ReturnValue)")
            res = self.sys.powershell(script, R.DELAI_POWERSHELL)
            retour = analyser_retour_wmi(res.sortie)
            if retour != 0:
                raise ErreurAction(f"Lancement WMI refusé (code {retour}) : {resume(res.texte)}")
        if not self._attendre(self._crew_repond, R.DELAI_DEMARRAGE_CREW, "crew",
                              "Le serveur Crew démarre…", progres):
            if not self._pids_crew():
                raise ErreurAction("Le serveur Crew s'est arrêté juste après son lancement")
            raise ErreurAction(f"Le serveur Crew ne répond pas sur /sante après {R.DELAI_DEMARRAGE_CREW} s")
        return Etat(ACTIF)

    def _arreter_crew(self, progres):
        pids = self._pids_crew()
        if pids is None:
            raise ErreurAction("Impossible de lister les processus (PowerShell)")
        if not pids:
            return Etat(ARRETE, "Arrêté")
        args = ["taskkill", "/F"]
        for p in pids:
            args += ["/PID", str(p)]
        self._cmd(args)
        if not self._attendre(lambda: not self._pids_crew(), R.DELAI_ARRET_CREW, "crew",
                              "Arrêt du serveur Crew…", progres, 2):
            raise ErreurAction("Des processus serveur_crew.py tournent encore")
        return Etat(ARRETE, "Arrêté")

    # ----- séquences --------------------------------------------------------

    def executer_sequence(self, etapes, progres):
        """Exécute une liste d'étapes [(« demarrer »|« arreter », ident), ...].

        Au démarrage, si une dépendance a échoué, les composants qui en ont
        besoin sont ignorés (avec un message clair). À l'arrêt, on continue
        quoi qu'il arrive, pour libérer le plus de mémoire possible.
        Renvoie {ident: Etat final}.
        """
        resultats = {}
        for sens, ident in etapes:
            if sens == "demarrer":
                en_echec = [d for d in PAR_ID[ident].dependances
                            if d in resultats and resultats[d].code != ACTIF]
                if en_echec:
                    etat = Etat(ARRETE, f"Ignoré : {nom(en_echec[0])} n'a pas pu démarrer")
                    journal.warning("%s ignoré (%s en échec)", nom(ident), nom(en_echec[0]))
                    progres(ident, etat, True)
                    resultats[ident] = etat
                    continue
                resultats[ident] = self.demarrer(ident, progres)
            else:
                resultats[ident] = self.arreter(ident, progres)
        return resultats

    def tout_demarrer(self, progres):
        journal.info("=== Tout démarrer ===")
        return self.executer_sequence([("demarrer", i) for i in ordre_demarrage()], progres)

    def mode_jeu(self, progres):
        journal.info("=== Mode jeu ===")
        return self.executer_sequence([("arreter", i) for i in ordre_arret()], progres)
