"use strict";
/* Page « Chef d'équipe » : choisir le modèle LM Studio qui sert de chef local à Crew. UN SEUL interrupteur actif (le chef actuel).
   Rien ne part vers Crew sans un clic confirmé ; pendant le changement on interroge le Centre toutes les 2 s. Texte affiché comme texte. */
(function () {
  var C = window.Centre, h = C.h, vider = C.vider, api = C.api;
  var AIDE = "Le chef classe chaque demande, fait seul le travail en mode Confidentiel et Ultra-confidentiel, assemble les réponses et fait les synthèses. " +
    "Les modèles d'embeddings (mémoire) ne peuvent pas être chef et ne sont pas listés.";
  var S = { data: null, minuteur: null, suivi: false, resultat: null, bulle: null, racine: null };

  function go(n) { return n === null || n === undefined ? "" : Number(n).toLocaleString("fr-CA", { maximumFractionDigits: 2 }) + " Go"; }
  function secondes(n) { return Number(n).toLocaleString("fr-CA", { maximumFractionDigits: 1 }) + " s"; }
  function nomDe(id) {
    var m = S.data ? S.data.modeles.filter(function (x) { return x.id === id; })[0] : null;
    return (m && m.libelle) || String(id || "").split("/").pop();
  }
  function enCours() { return !!(S.data && S.data.changement && S.data.changement.etat === "en_cours"); }

  function charger(silencieux) {
    return api("GET", "/api/crew/chef").then(function (d) {
      var avant = S.data && S.data.changement;
      S.data = d;
      var ch = d.changement;
      if (ch && ch.etat === "en_cours") { S.suivi = true; planifier(); }
      else if (S.suivi && ch && (ch.etat === "termine" || ch.etat === "echec")) {          // un changement qu'on suivait vient de finir
        S.suivi = false; S.resultat = { etat: ch.etat, message: ch.message, cible: ch.cible };
      } else if (!S.resultat && ch && (ch.etat === "termine" || ch.etat === "echec") && ch.debut && Date.now() / 1000 - ch.debut < 600 && !avant) {
        S.resultat = { etat: ch.etat, message: ch.message, cible: ch.cible };               // changement récent, constaté à l'ouverture de la page
      }
      dessiner();
    }).catch(function (e) {
      if (e.message === "session") return;
      if (!silencieux && S.racine) { vider(S.racine); S.racine.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); }
      if (S.suivi) planifier();
    });
  }
  function planifier() {
    clearTimeout(S.minuteur);
    S.minuteur = setTimeout(function () { if (C.courante() === "chef") charger(true); else S.suivi = S.suivi && true; }, 2000);
  }

  function interrupteur(m, actif, desactive, raison) {
    var piste = h("span", { class: "piste", "aria-hidden": "true" }, h("span", { class: "bouton-rond" }));
    return h("button", { class: "glissiere" + (actif ? " on" : ""), type: "button", role: "switch", "aria-checked": actif ? "true" : "false",
      "aria-label": "Chef d'équipe : " + m.libelle, title: desactive ? raison : (actif ? "Chef actuel" : "Choisir ce modèle comme chef"),
      disabled: !!desactive, onclick: function () { cliquer(m, actif); } }, piste);
  }

  function bulleExplicative(ligne) {
    if (S.bulle) S.bulle.remove();
    S.bulle = h("div", { class: "bulle-aide", role: "status", texte: "Activez un autre modèle pour changer de chef." });
    ligne.appendChild(S.bulle);
    setTimeout(function () { if (S.bulle) { S.bulle.remove(); S.bulle = null; } }, 4000);
  }

  function cliquer(m, actif) {
    if (actif) { bulleExplicative(document.getElementById("chef-" + S.data.modeles.indexOf(m)) || S.racine); return; }     // impossible de ne pas avoir de chef
    var ancien = S.data.chef_nom || nomDe(S.data.chef);
    C.confirmer("Changer de chef ?", "Crew sera indisponible environ 30 secondes. " + m.libelle + " sera chargé à la place de " + ancien + "." +
      (m.avertissement ? "\n\n⚠ " + m.avertissement : ""), "Changer de chef").then(function (ok) {
      if (!ok) return;
      lancer(m.id);
    });
  }
  function lancer(id) {
    S.resultat = null;
    api("PUT", "/api/crew/chef", { modele: id }).then(function (r) {
      S.suivi = true; S.data.changement = r.changement || { etat: "en_cours", cible: id, etape: "Démarrage…", message: "" };
      dessiner(); planifier();
    }).catch(function (e) { if (e.message !== "session") C.informer("Changement impossible", e.message + "\nRien n'a été changé."); charger(true); });
  }

  function bandeauResultat() {
    var r = S.resultat, d = S.data;
    if (!r || !d || enCours()) return null;
    if (r.etat === "echec") {
      return h("div", { class: "bandeau erreur", role: "alert" }, h("strong", { texte: "Le changement a échoué. " }), r.message || "Crew n'a pas pu charger le nouveau chef.",
        /a remis/i.test(r.message || "") ? "" : " Crew a remis " + (d.chef_nom || nomDe(d.chef)) + ".");
    }
    var t = d.dernier_test && d.dernier_test.modele === d.chef ? d.dernier_test : null;
    var ok = h("div", { class: "bandeau ok", role: "status" }, h("strong", { texte: (d.chef_nom || nomDe(d.chef)) + " est le nouveau chef. " }),
      t && t.ok ? t.json_valides + " demandes classées correctement" + (t.duree_moy_s !== null ? " en " + secondes(t.duree_moy_s) + " en moyenne" : "") + "." : "");
    if (t && !t.ok) {
      return h("div", null, ok, h("div", { class: "bandeau erreur", role: "alert" }, h("strong", { texte: "Ce modèle suit mal les consignes de Crew. " }),
        "Test : " + t.json_valides + " demande(s) bien classée(s) sur " + t.sur + ". Le changement est fait, mais Crew risque de se tromper. ",
        d.ancien_chef ? h("button", { class: "petit", type: "button", texte: "Revenir à " + (d.ancien_nom || nomDe(d.ancien_chef)),
          onclick: function () { C.confirmer("Revenir à l'ancien chef ?", "Crew sera indisponible environ 30 secondes. " + (d.ancien_nom || nomDe(d.ancien_chef)) + " sera rechargé à la place de " +
            (d.chef_nom || nomDe(d.chef)) + ".", "Revenir").then(function (oui) { if (oui) lancer(d.ancien_chef); }); } }) : null));
    }
    return ok;
  }

  function dessiner() {
    var racine = S.racine, d = S.data;
    if (!racine || C.courante() !== "chef" || !d) return;
    vider(racine);
    racine.appendChild(h("h2", { texte: "🧠 Chef d'équipe" }));
    racine.appendChild(h("p", { class: "doux", texte: AIDE }));
    var b = bandeauResultat(); if (b) racine.appendChild(b);
    var bloque = enCours() || !d.modifiable;
    if (!d.modifiable && !enCours()) racine.appendChild(h("div", { class: "bandeau", role: "status", texte: d.raison || "Changement de chef indisponible pour le moment." }));
    if (d.message && d.lmstudio === false) racine.appendChild(h("div", { class: "bandeau", role: "status", texte: d.message }));
    if (enCours()) {
      var ch = d.changement;
      racine.appendChild(h("div", { class: "progression", role: "status", "aria-live": "polite" },
        h("div", { class: "rangee" }, h("strong", { texte: "Changement en cours vers " + nomDe(ch.cible) }), h("span", { class: "doux", texte: " — Crew est indisponible quelques instants." })),
        h("div", { class: "barre", "aria-hidden": "true" }, h("span", { class: "barre-anim" })), h("div", { class: "etape", texte: ch.etape || "…" })));
    }
    var dt = d.dernier_test && d.dernier_test.modele === d.chef ? d.dernier_test : null;
    if (dt && !S.resultat) racine.appendChild(h("p", { class: "doux", texte: "Dernier test du chef : " + dt.json_valides + "/" + dt.sur + (dt.ok ? " demandes bien classées" : " — suit mal les consignes de Crew") +
      (dt.duree_moy_s !== null ? ", " + secondes(dt.duree_moy_s) + " en moyenne." : ".") }));
    var liste = h("div", { class: "modeles-chef", role: "list" });
    if (!d.modeles.length) liste.appendChild(h("div", { class: "doux", texte: "Aucun modèle à afficher pour le moment." }));
    d.modeles.forEach(function (m, i) {
      var actif = m.id === d.chef;
      var details = [go(m.taille_go), m.params, m.quantification].filter(function (x) { return x; }).join(" · ");
      var etat = h("span", { class: "badge" + (m.charge ? " ok" : "") , texte: m.charge ? "chargé" : "non chargé" });
      var ligne = h("div", { class: "ligne-chef" + (actif ? " actif" : ""), role: "listitem", id: "chef-" + i },
        h("div", { class: "infos-chef" },
          h("div", null, h("strong", { texte: m.libelle }), " ", actif ? h("span", { class: "badge ok", texte: "chef actuel" }) : null, " ", etat),
          h("div", { class: "doux", texte: details || m.id }),
          m.avertissement ? h("div", { class: "avert", texte: "⚠ " + m.avertissement }) : null),
        interrupteur(m, actif, bloque, enCours() ? "Un changement est en cours" : d.raison));
      liste.appendChild(ligne);
    });
    racine.appendChild(liste);
  }

  function pageChef() {
    var racine = h("div", { class: "page-chef" });
    S.racine = racine; S.data = null; S.resultat = null;
    C.page.appendChild(racine);
    racine.appendChild(h("div", { class: "doux", texte: "Chargement…" }));
    charger(false);
  }
  C.pages.chef = pageChef;
})();
