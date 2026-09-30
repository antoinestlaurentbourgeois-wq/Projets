# -*- coding: utf-8 -*-
"""
Demande d'image faite PAR l'IA d'une salle, en langage naturel : elle répond avec UN bloc

    [[IMAGE]]
    taille: carre|portrait|paysage
    description: <texte détaillé>
    [[/IMAGE]]

Le Centre repère ce bloc dans la réponse de l'IA (au fil du flux), le RETIRE du texte affiché et le transforme en PROPOSITION : une carte montre la
description complète, et seul le clic de l'utilisateur lance la création. Jamais d'exécution automatique : une sortie d'IA peut être détournée par un
texte piégé (page web, document, fichier joint). Règles : au plus UN bloc par réponse (les suivants restent du texte, sans effet), description de
4 000 caractères au plus, bloc mal formé ou jamais fermé = affiché tel quel, sans effet. Seul le texte de l'IA est examiné : jamais celui de l'utilisateur,
d'une pièce jointe ou d'un résultat d'outil.
"""

import re
import secrets

DEBUT, FIN = "[[IMAGE]]", "[[/IMAGE]]"
TAILLES = ("carre", "portrait", "paysage")
MAX_DESCRIPTION = 4000

CONSIGNE = ("Si l'utilisateur te demande de créer une image, réponds avec UN seul bloc, exactement sous cette forme : "
            "[[IMAGE]] puis une ligne « taille: carre » (ou portrait, ou paysage), puis une ligne « description: » suivie d'un texte détaillé de l'image, "
            "puis [[/IMAGE]]. Tu ne crées pas l'image toi-même : le Centre demandera d'abord confirmation à l'utilisateur.")


def analyser(bloc):
    """Contenu entre les balises -> {taille, description} ou None si mal formé."""
    taille, description, dans_description = "carre", [], False
    for ligne in bloc.strip("\r\n").splitlines():
        m = re.match(r"^\s*(taille|description)\s*:\s*(.*)$", ligne, re.IGNORECASE) if not dans_description else None
        if m and m.group(1).lower() == "taille":
            taille = m.group(2).strip().lower()
            if taille not in TAILLES:
                return None
        elif m and m.group(1).lower() == "description":
            dans_description = True
            description.append(m.group(2))
        elif dans_description:
            description.append(ligne)
        elif ligne.strip():
            return None                       # ligne inattendue avant la description
    texte = "\n".join(description).strip()
    if not texte or len(texte) > MAX_DESCRIPTION or "[[" in texte:
        return None
    return {"taille": taille, "description": texte}


class FiltreImage:
    """Filtre de flux : laisse passer le texte, retient le bloc. `pousser` et `fin` renvoient des couples ("texte", str) ou ("image", proposition)."""

    def __init__(self):
        self.tampon = ""
        self.dans = False
        self.pris = 0

    def pousser(self, morceau):
        self.tampon += str(morceau or "")
        sortie = []
        while True:
            if not self.dans:
                i = self.tampon.find(DEBUT)
                if i < 0:
                    garde = 0                              # on retient un début de balise possible (« [[IMA »)
                    for k in range(min(len(DEBUT) - 1, len(self.tampon)), 0, -1):
                        if DEBUT.startswith(self.tampon[-k:]):
                            garde = k
                            break
                    if len(self.tampon) > garde:
                        sortie.append(("texte", self.tampon[:len(self.tampon) - garde]))
                        self.tampon = self.tampon[len(self.tampon) - garde:]
                    return sortie
                if self.pris >= 1:                         # un seul bloc par réponse : les suivants restent du texte
                    sortie.append(("texte", self.tampon[:i + len(DEBUT)]))
                    self.tampon = self.tampon[i + len(DEBUT):]
                    continue
                if i > 0:
                    sortie.append(("texte", self.tampon[:i]))
                self.tampon = self.tampon[i + len(DEBUT):]
                self.dans = True
            j = self.tampon.find(FIN)
            if j < 0:
                if len(self.tampon) > MAX_DESCRIPTION + 500:   # trop long : abandonné, affiché tel quel
                    sortie.append(("texte", DEBUT + self.tampon))
                    self.tampon, self.dans = "", False
                return sortie
            contenu, self.tampon = self.tampon[:j], self.tampon[j + len(FIN):]
            self.dans = False
            p = analyser(contenu)
            if p is None:
                sortie.append(("texte", DEBUT + contenu + FIN))
            else:
                self.pris += 1
                sortie.append(("image", {"id": secrets.token_hex(6), "taille": p["taille"], "description": p["description"], "statut": "proposee"}))

    def fin(self):
        """Fin du flux : un bloc jamais fermé est rendu tel quel."""
        reste = (DEBUT if self.dans else "") + self.tampon
        self.tampon, self.dans = "", False
        return [("texte", reste)] if reste else []
