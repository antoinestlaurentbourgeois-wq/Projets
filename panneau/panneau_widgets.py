# -*- coding: utf-8 -*-
"""
Éléments graphiques du panneau (tkinter) : couleurs communes, bulle d'aide,
sélecteur de mode Crew, section repliable « État des IA ».

Ces éléments n'appellent jamais le réseau eux-mêmes : ils affichent ce qu'on
leur donne et signalent les clics par des fonctions de rappel.
"""

import tkinter as tk
import tkinter.font  # noqa: F401 (tk.font)

import panneau_crew as C
from panneau_logique import ACTIF, ARRETE, INCONNU, TRANSITION

COULEURS = {ACTIF: "#2e9d4f", ARRETE: "#d64545", TRANSITION: "#e8962e", INCONNU: "#9a9a9a"}
TEXTE_ETAT = {ACTIF: "Actif", ARRETE: "Arrêté", TRANSITION: "En cours…", INCONNU: "Inconnu"}
FOND = "#f4f5f7"
CARTE = "#ffffff"
TEXTE = "#1f2328"
GRIS = "#6b7280"
LIEN = "#1d4ed8"
POLICE = "Segoe UI"


def rendre_cliquable(etiquette, commande):
    """Curseur « main » et soulignement au survol, clic = commande()."""
    police = tk.font.Font(font=etiquette.cget("font"))
    soulignee = police.copy()
    soulignee.configure(underline=True)
    etiquette.configure(cursor="hand2")
    etiquette.bind("<Enter>", lambda _e: etiquette.configure(font=soulignee, fg=LIEN))
    etiquette.bind("<Leave>", lambda _e: etiquette.configure(font=police, fg=TEXTE))
    etiquette.bind("<Button-1>", lambda _e: commande())
    etiquette._polices = (police, soulignee)   # garder une référence


class Bulle:
    """Petite bulle d'explication : au survol (après un court délai) ou au clic."""

    def __init__(self, widget, texte, echelle=1.0):
        self.widget, self.echelle = widget, echelle
        self.texte = texte                    # texte, ou fonction qui renvoie le texte
        self.fenetre = None
        self._minuterie = None
        widget.bind("<Enter>", self._programmer, add="+")
        widget.bind("<Leave>", self.cacher, add="+")
        widget.bind("<Button-1>", self._basculer, add="+")

    def _texte(self):
        return self.texte() if callable(self.texte) else self.texte

    def _programmer(self, _e=None):
        self._annuler()
        self._minuterie = self.widget.after(250, self.montrer)

    def _annuler(self):
        if self._minuterie:
            self.widget.after_cancel(self._minuterie)
            self._minuterie = None

    def _basculer(self, _e=None):
        self._annuler()
        self.cacher() if self.fenetre else self.montrer()
        return "break"

    def montrer(self):
        texte = self._texte()
        if self.fenetre or not texte:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 6
        y = self.widget.winfo_rooty() - 4
        self.fenetre = f = tk.Toplevel(self.widget)
        f.wm_overrideredirect(True)
        f.attributes("-topmost", True)
        tk.Label(f, text=texte, bg="#fffbe6", fg=TEXTE, font=(POLICE, 9), justify="left",
                 wraplength=int(320 * self.echelle), padx=8, pady=6, relief="solid",
                 borderwidth=1).pack()
        f.update_idletasks()
        # Ne pas sortir de l'écran.
        largeur = f.winfo_reqwidth()
        if x + largeur > f.winfo_screenwidth():
            x = max(0, self.widget.winfo_rootx() - largeur - 6)
        f.geometry(f"+{x}+{y}")

    def cacher(self, _e=None):
        self._annuler()
        if self.fenetre:
            self.fenetre.destroy()
            self.fenetre = None


class ListeModes:
    """La liste déroulante des modes (fenêtre sans bordure sous le bouton)."""

    def __init__(self, bouton, info, au_choix, echelle=1.0):
        self.au_choix = au_choix
        self.bulles = []
        self.fenetre = f = tk.Toplevel(bouton)
        f.wm_overrideredirect(True)
        f.attributes("-topmost", True)
        cadre = tk.Frame(f, bg=CARTE, highlightthickness=1, highlightbackground="#c4c8cf")
        cadre.pack()
        if not info.modes:
            tk.Label(cadre, text="Liste des modes inconnue : démarrez une fois le serveur Crew.",
                     bg=CARTE, fg=GRIS, font=(POLICE, 9), padx=10, pady=8).pack()
        for m in info.modes:
            ligne = tk.Frame(cadre, bg=CARTE, cursor="hand2")
            ligne.pack(fill="x")
            actuel = m.id == info.actuel
            puce = tk.Label(ligne, text="●" if actuel else " ", bg=CARTE, fg=COULEURS[ACTIF],
                            font=(POLICE, 9), width=2)
            nom = tk.Label(ligne, text=m.libelle, bg=CARTE, fg=TEXTE, anchor="w",
                           font=(POLICE, 10, "bold" if actuel else "normal"), padx=4, pady=5)
            info_i = tk.Label(ligne, text=" i ", bg="#e5e7eb", fg=LIEN, font=(POLICE, 8, "bold"),
                              cursor="question_arrow")
            puce.pack(side="left")
            nom.pack(side="left", fill="x", expand=True)
            info_i.pack(side="right", padx=(12, 8))
            self.bulles.append(Bulle(info_i, m.explication or "Pas d'explication fournie par le serveur.",
                                     echelle))
            for w in (ligne, puce, nom):
                w.bind("<Button-1>", lambda _e, ident=m.id: self._choisir(ident))
                w.bind("<Enter>", lambda _e, w2=(ligne, puce, nom): [x.configure(bg="#eef2ff") for x in w2])
                w.bind("<Leave>", lambda _e, w2=(ligne, puce, nom): [x.configure(bg=CARTE) for x in w2])
        f.update_idletasks()
        f.geometry(f"+{bouton.winfo_rootx()}+{bouton.winfo_rooty() + bouton.winfo_height() + 2}")
        # Un clic en dehors, ou Échap, referme la liste.
        f.bind("<Escape>", lambda _e: self.fermer())
        f.bind("<Button-1>", self._clic_dehors)
        f.after(30, self._saisir)

    def _saisir(self, essai=0):
        """Capte clavier et souris une fois la liste affichée (sinon Windows refuse)."""
        if self.fenetre is None:
            return
        try:
            self.fenetre.focus_force()
            self.fenetre.grab_set()
        except tk.TclError:
            if essai < 5:
                self.fenetre.after(50, self._saisir, essai + 1)

    def _choisir(self, ident):
        self.fermer()
        self.au_choix(ident)
        return "break"

    def _clic_dehors(self, e):
        f = self.fenetre
        if f is None:
            return
        dedans = (f.winfo_rootx() <= e.x_root <= f.winfo_rootx() + f.winfo_width()
                  and f.winfo_rooty() <= e.y_root <= f.winfo_rooty() + f.winfo_height())
        if not dedans:
            self.fermer()

    def fermer(self):
        for b in self.bulles:
            b.cacher()
        if self.fenetre is not None:
            try:
                self.fenetre.grab_release()
                self.fenetre.destroy()
            except tk.TclError:
                pass
            self.fenetre = None


class SelecteurMode:
    """« Mode : [Économe ▾] (i) — note » sur la ligne du serveur Crew."""

    def __init__(self, parent, au_choix, echelle=1.0):
        self.au_choix, self.echelle = au_choix, echelle
        self.info = C.InfoMode()
        self.liste = None
        self.cadre = tk.Frame(parent, bg=CARTE)
        tk.Label(self.cadre, text="Mode :", bg=CARTE, fg=GRIS, font=(POLICE, 9)).pack(side="left")
        self.bouton = tk.Label(self.cadre, text="…  ▾", bg="#eef2ff", fg=TEXTE, font=(POLICE, 9, "bold"),
                               padx=8, pady=2, cursor="hand2", relief="groove", borderwidth=1)
        self.bouton.pack(side="left", padx=(6, 4))
        self.bouton.bind("<Button-1>", lambda _e: self.ouvrir())
        self.i = tk.Label(self.cadre, text=" i ", bg="#e5e7eb", fg=LIEN, font=(POLICE, 8, "bold"),
                          cursor="question_arrow")
        self.i.pack(side="left")
        self.bulle = Bulle(self.i, self._explication_actuelle, echelle)
        self.note = tk.Label(self.cadre, text="", bg=CARTE, fg=GRIS, font=(POLICE, 9))
        self.note.pack(side="left", padx=(8, 0))
        self.occupe = False

    def _explication_actuelle(self):
        for m in self.info.modes:
            if m.id == self.info.actuel:
                return m.explication
        return "Explication indisponible (serveur Crew jamais joint depuis l'installation du panneau)."

    def afficher(self, info, occupe=False):
        self.info, self.occupe = info, occupe
        texte = "changement…" if occupe else (info.libelle() if info.actuel else "inconnu")
        self.bouton.configure(text=f"{texte}  ▾")
        note = info.message
        if not info.serveur_actif and info.message == "Serveur Crew éteint" and info.modifiable:
            note = "Serveur Crew éteint (mode lu dans le fichier)"
        self.note.configure(text=note, fg="#b42318" if not info.modifiable else GRIS)

    def ouvrir(self):
        if self.liste and self.liste.fenetre:
            self.liste.fermer()
            return
        if self.occupe or not self.info.modifiable:
            self.bouton.bell()
            return
        self.bulle.cacher()
        self.liste = ListeModes(self.bouton, self.info, self._choisi, self.echelle)

    def _choisi(self, ident):
        if ident != self.info.actuel:
            self.au_choix(ident)


class SectionMoteurs:
    """Section repliable « État des IA » sous la ligne du serveur Crew."""

    def __init__(self, parent, au_basculement, echelle=1.0):
        self.au_basculement, self.echelle = au_basculement, echelle
        self.ouverte = False
        self._derniere = None
        self.cadre = tk.Frame(parent, bg=CARTE)
        self.entete = tk.Label(self.cadre, text="▸  État des IA utilisées par Crew", bg=CARTE, fg=LIEN,
                               font=(POLICE, 9, "bold"), cursor="hand2")
        self.entete.pack(anchor="w")
        self.entete.bind("<Button-1>", lambda _e: self.basculer())
        self.contenu = tk.Frame(self.cadre, bg=CARTE)

    def basculer(self):
        self.ouverte = not self.ouverte
        fleche = "▾" if self.ouverte else "▸"
        self.entete.configure(text=f"{fleche}  État des IA utilisées par Crew")
        if self.ouverte:
            self.contenu.pack(fill="x", pady=(4, 0))
            self._dessiner()
        else:
            self.contenu.pack_forget()
        self.au_basculement(self.ouverte)

    def afficher(self, info):
        """info : C.InfoMoteurs reçu du fil de vérification."""
        if repr(info) == repr(self._derniere):
            return                                      # rien de neuf : pas de clignotement
        self._derniere = info
        if self.ouverte:
            self._dessiner()

    def _dessiner(self):
        info = self._derniere
        for w in self.contenu.winfo_children():
            w.destroy()
        if info is None:
            tk.Label(self.contenu, text="Chargement…", bg=CARTE, fg=GRIS,
                     font=(POLICE, 9)).pack(anchor="w", padx=(16, 0))
            return
        if info.moteurs is None:
            tk.Label(self.contenu, text=info.message, bg=CARTE, fg=GRIS,
                     font=(POLICE, 9)).pack(anchor="w", padx=(16, 0))
            return
        if not info.moteurs:
            tk.Label(self.contenu, text="Aucune IA déclarée par le serveur Crew.", bg=CARTE, fg=GRIS,
                     font=(POLICE, 9)).pack(anchor="w", padx=(16, 0))
        t = int(12 * self.echelle)
        for m in info.moteurs:
            ligne = tk.Frame(self.contenu, bg="#f8fafc", padx=8, pady=4)
            ligne.pack(fill="x", pady=1, padx=(16, 0))
            voyant = tk.Canvas(ligne, width=t, height=t, bg="#f8fafc", highlightthickness=0)
            voyant.create_oval(1, 1, t - 1, t - 1, fill=COULEURS[C.couleur_moteur(m.etat)], outline="")
            voyant.grid(row=0, column=0, rowspan=2, sticky="n", pady=(3, 0))
            tk.Label(ligne, text=m.libelle, bg="#f8fafc", fg=TEXTE,
                     font=(POLICE, 9, "bold")).grid(row=0, column=1, sticky="w", padx=(8, 0))
            infos = [C.texte_capacite(m.capacite), C.texte_cout(m.cout)]
            if m.local:
                infos.append("sur ce PC")
            tk.Label(ligne, text="  ·  ".join(infos), bg="#f8fafc", fg=GRIS,
                     font=(POLICE, 8)).grid(row=0, column=2, sticky="e", padx=(8, 0))
            etat = C.TEXTE_ETAT_MOTEUR.get(m.etat, m.etat or "état inconnu")
            detail = f"{etat} — {m.detail}" if m.detail else etat
            couleur = {ACTIF: GRIS, ARRETE: "#b42318"}.get(C.couleur_moteur(m.etat), GRIS)
            tk.Label(ligne, text=detail, bg="#f8fafc", fg=couleur, font=(POLICE, 8), anchor="w",
                     justify="left", wraplength=int(400 * self.echelle)).grid(
                row=1, column=1, columnspan=2, sticky="w", padx=(8, 0))
            ligne.columnconfigure(2, weight=1)
