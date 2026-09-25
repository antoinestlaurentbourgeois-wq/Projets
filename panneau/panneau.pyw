# -*- coding: utf-8 -*-
"""
Panneau de contrôle de l'IA locale — fenêtre principale (tkinter).

Lancement normal :   pythonw.exe panneau.pyw
Mode démo (simulé) : pythonw.exe panneau.pyw --demo   (ne touche à rien)

Règle d'or : la fenêtre ne fait JAMAIS d'attente elle-même. Toutes les
vérifications et actions tournent dans des fils (threads) séparés, qui
envoient leurs résultats par une file d'attente lue toutes les 150 ms.
"""

import logging
import logging.handlers
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

import reglages as R  # noqa: E402
import panneau_logique as L  # noqa: E402
from panneau_logique import ACTIF, ARRETE, INCONNU, TRANSITION, Etat  # noqa: E402

FICHIER_JOURNAL = os.path.join(DOSSIER, "panneau.log")

COULEURS = {ACTIF: "#2e9d4f", ARRETE: "#d64545", TRANSITION: "#e8962e", INCONNU: "#9a9a9a"}
TEXTE_ETAT = {ACTIF: "Actif", ARRETE: "Arrêté", TRANSITION: "En cours…", INCONNU: "Inconnu"}
FOND = "#f4f5f7"
CARTE = "#ffffff"
TEXTE = "#1f2328"
GRIS = "#6b7280"
POLICE = "Segoe UI"


def configurer_journal():
    """Petit fichier journal dans le dossier du panneau (500 Ko max, 1 copie)."""
    gestionnaire = logging.handlers.RotatingFileHandler(
        FICHIER_JOURNAL, maxBytes=500_000, backupCount=1, encoding="utf-8")
    gestionnaire.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                                "%Y-%m-%d %H:%M:%S"))
    journal = logging.getLogger("panneau")
    journal.setLevel(logging.INFO)
    journal.addHandler(gestionnaire)
    return journal


class Interrupteur(tk.Canvas):
    """Un interrupteur dessiné (pilule + rond), cliquable."""

    def __init__(self, parent, commande, echelle=1.0):
        self.L, self.H = int(52 * echelle), int(26 * echelle)
        super().__init__(parent, width=self.L, height=self.H, bg=CARTE,
                         highlightthickness=0, cursor="hand2")
        self.commande = commande
        self.allume = False
        self.actif = True
        self.bind("<Button-1>", lambda _e: self.actif and self.commande())
        self.dessiner()

    def regler(self, allume, actif):
        if (allume, actif) != (self.allume, self.actif):
            self.allume, self.actif = allume, actif
            self.configure(cursor="hand2" if actif else "arrow")
            self.dessiner()

    def dessiner(self):
        self.delete("all")
        l, h, r = self.L, self.H, self.H // 2
        fond = "#2e9d4f" if self.allume else "#c4c8cf"
        if not self.actif:
            fond = "#9fd3b0" if self.allume else "#e1e4e8"
        self.create_oval(0, 0, h, h, fill=fond, outline=fond)
        self.create_oval(l - h, 0, l, h, fill=fond, outline=fond)
        self.create_rectangle(r, 0, l - r, h, fill=fond, outline=fond)
        x = l - h + 3 if self.allume else 3
        self.create_oval(x, 3, x + h - 6, h - 3, fill="white", outline="white")


class LigneComposant:
    """Voyant + nom + description + interrupteur + ligne d'explication."""

    def __init__(self, parent, composant, au_clic, echelle=1.0):
        self.cadre = tk.Frame(parent, bg=CARTE, padx=14, pady=8)
        t = int(18 * echelle)
        self.voyant = tk.Canvas(self.cadre, width=t, height=t, bg=CARTE, highlightthickness=0)
        self.voyant.grid(row=0, column=0, rowspan=2, sticky="n", pady=(3, 0))
        self.rond = self.voyant.create_oval(2, 2, t - 2, t - 2, fill=COULEURS[INCONNU], outline="")
        tk.Label(self.cadre, text=composant.nom, bg=CARTE, fg=TEXTE,
                 font=(POLICE, 11, "bold")).grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.etiquette = tk.Label(self.cadre, text="", bg=CARTE, fg=GRIS, font=(POLICE, 9))
        self.etiquette.grid(row=0, column=2, sticky="e", padx=8)
        tk.Label(self.cadre, text=composant.description, bg=CARTE, fg=GRIS,
                 font=(POLICE, 9)).grid(row=1, column=1, columnspan=2, sticky="w", padx=(10, 0))
        self.message = tk.Label(self.cadre, text="", bg=CARTE, fg=GRIS, font=(POLICE, 9),
                                wraplength=int(420 * echelle), justify="left", anchor="w")
        self.message.grid(row=2, column=1, columnspan=3, sticky="w", padx=(10, 0))
        self.inter = Interrupteur(self.cadre, lambda: au_clic(composant.ident), echelle)
        self.inter.grid(row=0, column=3, rowspan=2, sticky="e")
        self.cadre.columnconfigure(2, weight=1)

    def afficher(self, etat, occupe):
        self.voyant.itemconfigure(self.rond, fill=COULEURS[etat.code])
        self.etiquette.configure(text=TEXTE_ETAT[etat.code], fg=COULEURS[etat.code])
        couleur_msg = {ARRETE: "#b42318", TRANSITION: "#b54708"}.get(etat.code, GRIS)
        if etat.code == ACTIF and etat.message:
            couleur_msg = "#b54708"   # avertissement (ex. modèle en double)
        self.message.configure(text=etat.message, fg=couleur_msg)
        self.message.grid() if etat.message else self.message.grid_remove()
        allume = etat.code == ACTIF or (etat.code == TRANSITION and "Arrêt" not in etat.message)
        self.inter.regler(allume, actif=not occupe and etat.code != TRANSITION)


class Panneau:
    def __init__(self, racine, controleur, demo=False):
        self.racine = racine
        self.ctrl = controleur
        self.file = queue.Queue()
        self.etats = {i: Etat(INCONNU, "Vérification…") for i in L.PAR_ID}
        self.en_action = set()          # composants dont l'action est en cours
        self.fin_action = {}            # ident -> heure de fin de la dernière action
        self.occupe = False             # une action (ou séquence) est en cours
        self.arret = threading.Event()
        self.reveil = threading.Event()

        racine.title("Panneau IA locale" + (" — DÉMO (simulation)" if demo else ""))
        racine.configure(bg=FOND)
        racine.minsize(520, 400)
        racine.protocol("WM_DELETE_WINDOW", self.fermer)
        # Écran agrandi à 125 % / 150 % : les tailles en pixels suivent.
        self.echelle = max(1.0, racine.winfo_fpixels("1i") / 96.0)
        self.construire(demo)

        threading.Thread(target=self.boucle_verification, daemon=True).start()
        self.racine.after(150, self.depiler)

    # ----- construction de la fenêtre ---------------------------------------

    def construire(self, demo):
        haut = tk.Frame(self.racine, bg=FOND, padx=16, pady=12)
        haut.pack(fill="x")
        tk.Label(haut, text="Mon IA locale", bg=FOND, fg=TEXTE,
                 font=(POLICE, 16, "bold")).pack(anchor="w")
        if demo:
            tk.Label(haut, text="Mode démo : tout est simulé, rien n'est lancé sur le PC.",
                     bg=FOND, fg="#b54708", font=(POLICE, 9)).pack(anchor="w")

        boutons = tk.Frame(self.racine, bg=FOND, padx=16)
        boutons.pack(fill="x")
        self.b_jeu = self.gros_bouton(boutons, "Mode jeu", "Tout éteindre pour libérer\n"
                                      "la carte graphique", "#5b3fd6", "#4a32b3", self.mode_jeu)
        self.b_jeu.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.b_tout = self.gros_bouton(boutons, "Tout démarrer", "Tout rallumer\ndans le bon ordre",
                                       "#2e9d4f", "#257f40", self.tout_demarrer)
        self.b_tout.pack(side="left", expand=True, fill="x", padx=(6, 0))

        # Barre du bas (placée avant la liste pour rester toujours visible).
        bas = tk.Frame(self.racine, bg=FOND, padx=16, pady=8)
        bas.pack(side="bottom", fill="x")
        self.statut = tk.Label(bas, text="Prêt.", bg=FOND, fg=TEXTE,
                               font=(POLICE, 9), anchor="w", justify="left",
                               wraplength=int(330 * self.echelle))
        self.statut.pack(side="left", fill="x", expand=True)
        tk.Button(bas, text="Journal", command=self.ouvrir_journal, relief="flat",
                  bg="#e5e7eb", padx=10).pack(side="right")
        tk.Button(bas, text="Vérifier", command=self.reveil.set, relief="flat",
                  bg="#e5e7eb", padx=10).pack(side="right", padx=6)
        self.heure = tk.Label(bas, text="", bg=FOND, fg=GRIS, font=(POLICE, 8))
        self.heure.pack(side="right", padx=6)

        liste = self.zone_defilante()
        self.lignes = {}
        for c in L.COMPOSANTS:
            ligne = LigneComposant(liste, c, self.clic_interrupteur, self.echelle)
            ligne.cadre.pack(fill="x", pady=2)
            self.lignes[c.ident] = ligne

        cles = tk.Frame(liste, bg=CARTE, padx=14, pady=8)
        cles.pack(fill="x", pady=(8, 2))
        tk.Label(cles, text="Clés API (lecture seule)", bg=CARTE, fg=TEXTE,
                 font=(POLICE, 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        self.etiquettes_cles = {}
        for n, nom_cle in enumerate(R.CLES_API, start=1):
            tk.Label(cles, text=nom_cle, bg=CARTE, fg=GRIS, font=("Consolas", 9)).grid(
                row=n, column=0, sticky="w", padx=(4, 16))
            e = tk.Label(cles, text="…", bg=CARTE, fg=GRIS, font=(POLICE, 9, "bold"))
            e.grid(row=n, column=1, sticky="w")
            self.etiquettes_cles[nom_cle] = e

        # Hauteur de départ : tout le contenu, sans dépasser l'écran.
        self.racine.update_idletasks()
        hauteur = min(self.racine.winfo_reqheight() + liste.winfo_reqheight(),
                      self.racine.winfo_screenheight() - 80)
        self.racine.geometry(f"{int(580 * self.echelle)}x{hauteur}")

    def zone_defilante(self):
        """Zone avec barre de défilement, utile si l'écran est petit ou agrandi (125 %, 150 %)."""
        conteneur = tk.Frame(self.racine, bg=FOND)
        conteneur.pack(fill="both", expand=True)
        toile = tk.Canvas(conteneur, bg=FOND, highlightthickness=0)
        barre = tk.Scrollbar(conteneur, orient="vertical", command=toile.yview)
        interieur = tk.Frame(toile, bg=FOND, padx=16, pady=10)
        fenetre = toile.create_window((0, 0), window=interieur, anchor="nw")
        toile.configure(yscrollcommand=barre.set)
        toile.pack(side="left", fill="both", expand=True)

        def ajuster(_e=None):
            toile.configure(scrollregion=toile.bbox("all"))
            toile.itemconfigure(fenetre, width=toile.winfo_width())
            # La barre n'apparaît que si le contenu dépasse.
            if interieur.winfo_reqheight() > toile.winfo_height():
                barre.pack(side="right", fill="y")
            else:
                barre.pack_forget()
                toile.yview_moveto(0)
        interieur.bind("<Configure>", ajuster)
        toile.bind("<Configure>", ajuster)
        toile.bind_all("<MouseWheel>", lambda e: toile.yview_scroll(int(-e.delta / 120), "units"))
        return interieur

    def gros_bouton(self, parent, titre, sous_titre, couleur, couleur_survol, commande):
        cadre = tk.Frame(parent, bg=couleur, cursor="hand2", padx=12, pady=10)
        t = tk.Label(cadre, text=titre, bg=couleur, fg="white", font=(POLICE, 14, "bold"))
        s = tk.Label(cadre, text=sous_titre, bg=couleur, fg="#eef", font=(POLICE, 9))
        t.pack()
        s.pack()
        cadre.actif = True

        def colorer(c):
            for w in (cadre, t, s):
                w.configure(bg=c)
        for w in (cadre, t, s):
            w.bind("<Button-1>", lambda _e: cadre.actif and commande())
            w.bind("<Enter>", lambda _e: cadre.actif and colorer(couleur_survol))
            w.bind("<Leave>", lambda _e: colorer(couleur if cadre.actif else "#b8bcc4"))

        def activer(oui):
            cadre.actif = oui
            colorer(couleur if oui else "#b8bcc4")
            for w in (cadre, t, s):
                w.configure(cursor="hand2" if oui else "arrow")
        cadre.activer = activer
        return cadre

    # ----- vérifications en arrière-plan ------------------------------------

    def boucle_verification(self):
        """Fil séparé : vérifie tout, toutes les ~5 s (ou quand on le réveille)."""
        while not self.arret.is_set():
            debut = time.monotonic()
            try:
                etats = self.ctrl.verifier_tout()
                cles = self.ctrl.verifier_cles()
                self.file.put(("verification", debut, etats, cles))
            except Exception:
                logging.getLogger("panneau").exception("échec de la vérification automatique")
            self.reveil.wait(R.INTERVALLE_VERIFICATION)
            self.reveil.clear()

    def depiler(self):
        """Fil principal : applique les résultats reçus des autres fils."""
        try:
            while True:
                msg = self.file.get_nowait()
                if msg[0] == "verification":
                    _, debut, etats, cles = msg
                    for ident, etat in etats.items():
                        # On ignore un résultat plus ancien qu'une action en cours ou terminée.
                        if ident in self.en_action or self.fin_action.get(ident, 0) > debut:
                            continue
                        self.etats[ident] = etat
                    self.afficher_cles(cles)
                    self.heure.configure(text="vérifié à " + time.strftime("%H:%M:%S"))
                elif msg[0] == "progres":
                    _, ident, etat, fini = msg
                    self.etats[ident] = etat
                    if fini:
                        self.en_action.discard(ident)
                        self.fin_action[ident] = time.monotonic()
                    else:
                        self.en_action.add(ident)
                        self.statut.configure(text=f"{L.nom(ident)} : {etat.message}")
                elif msg[0] == "fin":
                    self.fin_sequence(*msg[1:])
        except queue.Empty:
            pass
        for ident, ligne in self.lignes.items():
            ligne.afficher(self.etats[ident], self.occupe)
        if not self.arret.is_set():
            self.racine.after(150, self.depiler)

    def afficher_cles(self, cles):
        for nom_cle, presente in cles.items():
            self.etiquettes_cles[nom_cle].configure(
                text="présente" if presente else "absente",
                fg=COULEURS[ACTIF] if presente else COULEURS[ARRETE])

    # ----- actions -----------------------------------------------------------

    def progres(self, ident, etat, fini):
        """Appelé depuis le fil d'action : on passe par la file, jamais directement."""
        self.file.put(("progres", ident, etat, fini))

    def lancer(self, titre, travail, demarrage):
        """Exécute `travail()` dans un fil séparé ; une seule action à la fois."""
        if self.occupe:
            self.racine.bell()
            return
        self.occupe = True
        self.b_jeu.activer(False)
        self.b_tout.activer(False)
        self.statut.configure(text=titre + "…")

        def fil():
            try:
                resultats = travail()
            except Exception as e:
                logging.getLogger("panneau").exception("action interrompue")
                resultats = {"?": Etat(INCONNU, str(e))}
            self.file.put(("fin", titre, resultats, demarrage))
        threading.Thread(target=fil, daemon=True).start()

    def fin_sequence(self, titre, resultats, demarrage):
        self.occupe = False
        self.b_jeu.activer(True)
        self.b_tout.activer(True)
        # Échec = état inconnu, ou composant resté éteint alors qu'on voulait l'allumer.
        problemes = [i for i, e in resultats.items()
                     if e.code == INCONNU or (demarrage and e.code != ACTIF)]
        if titre == "Mode jeu" and not problemes:
            texte = "Mode jeu : tout est éteint. Bon jeu !"
        elif problemes:
            texte = f"{titre} : terminé avec {len(problemes)} problème(s) — voir les lignes en rouge."
        else:
            texte = f"{titre} : terminé."
        self.statut.configure(text=texte)
        self.reveil.set()   # revérifier tout de suite

    def tout_demarrer(self):
        self.lancer("Tout démarrer", lambda: self.ctrl.tout_demarrer(self.progres), True)

    def mode_jeu(self):
        if self.occupe:
            self.racine.bell()
            return
        if messagebox.askyesno("Mode jeu", "Tout éteindre (Crew, modèles, LM Studio, Open WebUI, "
                               "Kokoro, Docker) pour libérer la carte graphique ?", parent=self.racine):
            self.lancer("Mode jeu", lambda: self.ctrl.mode_jeu(self.progres), False)

    def clic_interrupteur(self, ident):
        if self.occupe:
            self.racine.bell()
            return
        etat = self.etats[ident]
        nom_c = L.nom(ident)
        if etat.code == ACTIF:
            # Éteindre : d'abord ce qui en dépend.
            dependants = L.dependants_a_arreter(ident, self.etats)
            if dependants:
                noms = ", ".join(L.nom(d) for d in dependants)
                if not messagebox.askyesno("Éteindre", f"{noms} dépend(ent) de {nom_c}.\n\n"
                                           f"Les éteindre aussi, puis éteindre {nom_c} ?",
                                           parent=self.racine):
                    return
            etapes = [("arreter", d) for d in dependants] + [("arreter", ident)]
            titre, demarrage = f"Arrêt de {nom_c}", False
        else:
            # Allumer : proposer d'allumer d'abord les dépendances éteintes.
            manquantes = L.dependances_a_demarrer(ident, self.etats)
            if manquantes:
                noms = ", ".join(L.nom(d) for d in manquantes)
                if not messagebox.askyesno("Dépendance éteinte", f"{nom_c} a besoin de : {noms}.\n\n"
                                           "Les allumer d'abord ?", parent=self.racine):
                    return
            etapes = [("demarrer", d) for d in manquantes] + [("demarrer", ident)]
            titre, demarrage = f"Démarrage de {nom_c}", True
        self.lancer(titre, lambda: self.ctrl.executer_sequence(etapes, self.progres), demarrage)

    # ----- divers ------------------------------------------------------------

    def ouvrir_journal(self):
        try:
            if not os.path.exists(FICHIER_JOURNAL):
                open(FICHIER_JOURNAL, "a", encoding="utf-8").close()
            os.startfile(FICHIER_JOURNAL)
        except (AttributeError, OSError) as e:
            messagebox.showinfo("Journal", f"Le journal est ici :\n{FICHIER_JOURNAL}\n\n({e})",
                                parent=self.racine)

    def fermer(self):
        if self.occupe and not messagebox.askyesno(
                "Quitter", "Une action est en cours. Fermer quand même ?\n"
                "(ce qui est déjà lancé continuera de tourner)", parent=self.racine):
            return
        self.arret.set()
        self.reveil.set()
        logging.getLogger("panneau").info("Panneau fermé")
        self.racine.destroy()


def deja_ouvert():
    """Empêche d'ouvrir deux panneaux en même temps (Windows seulement)."""
    if sys.platform != "win32":
        return False
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "PanneauIALocale_Unique")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main():
    demo = "--demo" in sys.argv
    journal = configurer_journal()
    if sys.platform == "win32":
        try:  # texte net sur les écrans à haute résolution
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    racine = tk.Tk()
    if deja_ouvert() and not demo:
        racine.withdraw()
        messagebox.showinfo("Panneau IA locale", "Le panneau est déjà ouvert.")
        return
    if demo:
        from simulateur import Simulateur
        systeme = Simulateur(temps_reel=True)
        systeme.delai_docker, systeme.delai_webui, systeme.delai_crew = 8, 5, 3
        systeme.lms_serveur = True
        systeme.modeles[R.MODELE_EMBEDDINGS] = 1
    else:
        systeme = L.SystemeWindows(dossier_temp=DOSSIER)
    journal.info("Panneau ouvert%s", " (démo)" if demo else "")
    Panneau(racine, L.Controleur(systeme), demo=demo)
    racine.mainloop()


if __name__ == "__main__":
    main()
