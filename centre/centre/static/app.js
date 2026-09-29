"use strict";
/* Centre de contrôle : interface. Les données sont toujours insérées comme du texte, jamais comme du HTML. */
(function () {
  // ---------------------------------------------------------------- petits outils
  function h(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === false || v == null) return;
      if (k === "class") el.className = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else if (k === "texte") el.textContent = v;
      else el.setAttribute(k, v === true ? "" : v);
    });
    (function ajouter(liste) {
      liste.forEach(function (c) {
        if (c == null || c === false) return;
        if (Array.isArray(c)) return ajouter(c);
        el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
      });
    })(Array.prototype.slice.call(arguments, 2));
    return el;
  }
  function vider(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function api(methode, url, corps) {
    var opts = { method: methode, credentials: "same-origin", headers: { "X-Centre": "1" } };
    if (corps !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(corps); }
    return fetch(url, opts).then(function (r) {
      if (r.status === 401) { location.replace("/connexion"); return Promise.reject(new Error("session")); }
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) { var e = new Error(d.erreur || ("Erreur " + r.status)); e.statut = r.status; e.donnees = d; throw e; }
        return d;
      });
    });
  }

  var dlg = document.getElementById("dialogue");
  function demander(titre, texte, boutons) {
    return new Promise(function (resolve) {
      document.getElementById("dialogue-titre").textContent = titre;
      document.getElementById("dialogue-texte").textContent = texte;
      var zone = document.getElementById("dialogue-boutons");
      vider(zone);
      boutons.forEach(function (b) {
        zone.appendChild(h("button", { class: "bouton " + (b.style || ""), type: "button", texte: b.texte,
          onclick: function () { dlg.close(); resolve(b.valeur); } }));
      });
      dlg.onclose = function () { resolve(null); };
      dlg.showModal();
    });
  }
  function informer(titre, texte) { return demander(titre, texte, [{ texte: "OK", valeur: true, style: "principal" }]); }
  function confirmer(titre, texte, oui, style) {
    return demander(titre, texte, [{ texte: "Annuler", valeur: false }, { texte: oui || "Oui", valeur: true, style: style || "principal" }])
      .then(function (v) { return v === true; });
  }
  function dollars(n) { return (Number(n) || 0).toLocaleString("fr-CA", { style: "currency", currency: "USD" }); }

  // ---------------------------------------------------------------- pages
  var page = document.getElementById("page");
  var pageCourante = null;
  var minuterie = null;
  var etat = { centre: null, ouvert: { mode: false, explication: null, moteurs: false }, moteurs: null, derniereSignature: "" };

  var TEXTE_VOYANT = { actif: "actif", arrete: "arrêté", transition: "en cours", inconnu: "inconnu" };
  var OUVRABLES = { openwebui: 1, lmstudio: 1, docker: 1 };

  function voyant(code) {
    return h("span", { class: "voyant v-" + code, role: "img", "aria-label": TEXTE_VOYANT[code] || code, title: TEXTE_VOYANT[code] || code });
  }

  function aller(nom) {
    pageCourante = nom;
    clearTimeout(minuterie);
    Array.prototype.forEach.call(document.querySelectorAll("#onglets button"), function (b) {
      if (b.dataset.page === nom) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    if (location.hash !== "#" + nom) history.replaceState(null, "", "#" + nom);
    vider(page);
    etat.derniereSignature = "";
    ({ centre: pageCentre, couts: pageCouts, journal: pageJournal }[nom] || pageCentre)();
  }

  // ------------------------------------------------ page Centre
  function pageCentre() {
    var conteneur = h("div", { id: "centre" });
    page.appendChild(conteneur);
    tick(conteneur);
  }

  function tick(conteneur) {
    if (pageCourante !== "centre") return;
    api("GET", "/api/etat").then(function (d) {
      etat.centre = d;
      var signature = JSON.stringify([d, etat.ouvert, etat.moteurs]);
      if (signature !== etat.derniereSignature) { etat.derniereSignature = signature; dessinerCentre(conteneur, d); }
    }).catch(function (e) {
      if (e.message === "session") return;
      vider(conteneur);
      conteneur.appendChild(h("div", { class: "bandeau erreur", texte: "Le serveur ne répond pas : " + e.message }));
      etat.derniereSignature = "";
    }).then(function () {
      var enCours = etat.centre && etat.centre.action && etat.centre.action.statut === "en_cours";
      minuterie = setTimeout(function () { tick(conteneur); }, document.hidden ? 8000 : (enCours ? 1200 : 4000));
    });
  }

  function dessinerCentre(conteneur, d) {
    vider(conteneur);
    var action = d.action;
    var enCours = !!(action && action.statut === "en_cours");

    // Actions globales
    conteneur.appendChild(h("div", { class: "actions-globales" },
      h("button", { class: "bouton danger", type: "button", disabled: enCours, texte: "Mode jeu (tout éteindre)", onclick: modeJeu }),
      h("button", { class: "bouton principal", type: "button", disabled: enCours, texte: "Tout démarrer", onclick: toutDemarrer })));

    if (action) conteneur.appendChild(bandeauAction(action));

    d.composants.forEach(function (c) { conteneur.appendChild(carteComposant(c, d, enCours)); });

    // Clés
    var cles = Object.keys(d.cles || {});
    if (cles.length) {
      conteneur.appendChild(h("div", { class: "carte" }, h("h2", { texte: "Clés API" }),
        h("div", { class: "cles" }, cles.map(function (n) {
          return h("span", { class: "puce " + (d.cles[n] ? "oui" : "non"), texte: n + " : " + (d.cles[n] ? "présente" : "absente") });
        })),
        h("p", { class: "doux", texte: "Seule la présence est indiquée : la valeur ne quitte jamais le PC." })));
    }
  }

  function bandeauAction(a) {
    var titre = a.statut === "en_cours" ? "En cours : " + a.libelle
      : a.statut === "erreur" ? "Erreur : " + a.libelle : "Terminé : " + a.libelle;
    var lignes = Object.keys(a.progres).map(function (i) {
      var p = a.progres[i];
      return h("li", { texte: i + " : " + (p.message || p.code) });
    });
    return h("div", { class: "bandeau" + (a.statut === "erreur" ? " erreur" : "") },
      h("strong", { texte: titre }), a.erreur ? h("div", { texte: a.erreur }) : null,
      lignes.length ? h("ul", null, lignes.slice(-8)) : null);
  }

  function carteComposant(c, d, enCours) {
    var code = c.etat.code;
    var actif = code === "actif";
    var nom = OUVRABLES[c.ident]
      ? h("button", { class: "nom", type: "button", title: "Ouvrir " + c.nom, texte: c.nom, onclick: function () { ouvrir(c); } })
      : h("span", { class: "nom", texte: c.nom });
    var interrupteur = h("button", { class: "interrupteur", type: "button", role: "switch",
      "aria-checked": actif ? "true" : "false", "aria-label": c.nom, disabled: enCours || code === "transition",
      onclick: function () { basculer(c, actif ? "arreter" : "demarrer"); } });
    var carte = h("div", { class: "carte" },
      h("div", { class: "rangee" }, voyant(code),
        h("div", { class: "corps" }, nom, h("div", { class: "doux", texte: c.description }),
          c.etat.message ? h("div", { class: "msg", texte: c.etat.message }) : null),
        interrupteur));
    if (c.ident === "crew") carte.appendChild(sousCrew(d, enCours));
    return carte;
  }

  // ---- mode Crew et état des IA
  function sousCrew(d) {
    var m = d.mode;
    var zone = h("div", { class: "sous" });
    if (!m || !m.modes.length) {
      zone.appendChild(h("div", { class: "msg", texte: (m && m.message) || "Modes de Crew inconnus pour l'instant (allumez Crew une fois)." }));
    } else {
      zone.appendChild(h("div", null, "Mode de Crew : ",
        h("button", { class: "mode-bouton", type: "button", "aria-expanded": etat.ouvert.mode ? "true" : "false",
          disabled: !m.modifiable, onclick: function () { etat.ouvert.mode = !etat.ouvert.mode; etat.derniereSignature = ""; dessinerCentre(document.getElementById("centre"), etat.centre); } },
          (m.libelle || m.actuel || "?") + " ▾")));
      if (m.message) zone.appendChild(h("div", { class: "msg", texte: m.message }));
      if (etat.ouvert.mode) {
        zone.appendChild(h("div", { class: "mode-liste", role: "listbox" }, m.modes.map(function (x) {
          var courant = x.id === m.actuel;
          var ouvertExpl = etat.ouvert.explication === x.id;
          return h("div", null,
            h("div", { class: "mode-ligne" + (courant ? " courant" : "") },
              h("button", { class: "choix", type: "button", role: "option", "aria-selected": courant ? "true" : "false",
                texte: (courant ? "✓ " : "") + x.libelle, onclick: function () { changerMode(x.id); } }),
              h("button", { class: "info", type: "button", "aria-label": "Explication : " + x.libelle, "aria-expanded": ouvertExpl ? "true" : "false",
                texte: "i", onclick: function () { etat.ouvert.explication = ouvertExpl ? null : x.id; etat.derniereSignature = ""; dessinerCentre(document.getElementById("centre"), etat.centre); } })),
            ouvertExpl ? h("div", { class: "explication", texte: x.explication || "(pas d'explication)" }) : null);
        })));
      }
    }
    zone.appendChild(h("div", null,
      h("button", { class: "depliant", type: "button", "aria-expanded": etat.ouvert.moteurs ? "true" : "false",
        texte: (etat.ouvert.moteurs ? "▾" : "▸") + " État des IA utilisées par Crew", onclick: basculerMoteurs })));
    if (etat.ouvert.moteurs) zone.appendChild(tableMoteurs());
    return zone;
  }

  function basculerMoteurs() {
    etat.ouvert.moteurs = !etat.ouvert.moteurs;
    if (etat.ouvert.moteurs) chargerMoteurs();
    etat.derniereSignature = "";
    dessinerCentre(document.getElementById("centre"), etat.centre);
  }
  function chargerMoteurs() {
    etat.moteurs = { chargement: true };
    api("GET", "/api/crew/moteurs").then(function (d) { etat.moteurs = d; }).catch(function (e) {
      etat.moteurs = { moteurs: null, message: e.message };
    }).then(function () {
      etat.derniereSignature = "";
      var c = document.getElementById("centre");
      if (c && pageCourante === "centre" && etat.centre) dessinerCentre(c, etat.centre);
    });
  }
  function tableMoteurs() {
    var m = etat.moteurs;
    if (!m || m.chargement) return h("div", { class: "msg", texte: "Chargement…" });
    if (!m.moteurs) return h("div", { class: "msg", texte: m.message || "Liste indisponible." });
    return h("table", { class: "tab" },
      h("thead", null, h("tr", null, h("th", { texte: "" }), h("th", { texte: "IA" }), h("th", { texte: "Niveau" }), h("th", { texte: "Coût" }), h("th", { texte: "État" }))),
      h("tbody", null, m.moteurs.map(function (x) {
        return h("tr", null, h("td", null, voyant(x.voyant)),
          h("td", null, x.libelle + (x.local ? " (local)" : ""), x.forces.length ? h("div", { class: "msg", texte: x.forces.join(", ") }) : null),
          h("td", { texte: x.capacite }), h("td", { texte: x.cout }),
          h("td", null, x.etat_texte, x.detail ? h("div", { class: "msg", texte: x.detail }) : null));
      })));
  }

  function changerMode(id) {
    api("PUT", "/api/crew/mode", { mode: id }).then(function (m) {
      etat.centre.mode = { actuel: m.actuel, libelle: m.libelle, modes: m.modes, serveur_actif: m.serveur_actif, modifiable: m.modifiable, message: m.message };
      etat.ouvert.mode = false; etat.derniereSignature = "";
      dessinerCentre(document.getElementById("centre"), etat.centre);
    }).catch(function (e) { informer("Changement de mode impossible", e.message); });
  }

  // ---- actions
  function noms(liees) { return liees.map(function (x) { return "• " + x.nom; }).join("\n"); }

  function lancer(sens, ident, avecLiees) {
    return api("POST", "/api/action", { sens: sens, ident: ident, avec_liees: !!avecLiees }).then(function (job) {
      etat.centre.action = job; etat.derniereSignature = ""; clearTimeout(minuterie);
      dessinerCentre(document.getElementById("centre"), etat.centre);
      tick(document.getElementById("centre"));
      return job;
    });
  }

  function basculer(c, sens) {
    api("GET", "/api/plan?sens=" + sens + "&ident=" + encodeURIComponent(c.ident)).then(function (p) {
      if (!p.liees.length) return lancer(sens, c.ident, false);
      var q = sens === "demarrer"
        ? c.nom + " a besoin de :\n" + noms(p.liees) + "\n\nLes allumer d'abord ?"
        : "Ces composants ont besoin de " + c.nom + " :\n" + noms(p.liees) + "\n\nLes éteindre aussi ?";
      return confirmer(sens === "demarrer" ? "Allumer d'abord ?" : "Éteindre aussi ?", q, "Oui").then(function (ok) {
        if (ok) return lancer(sens, c.ident, true);
      });
    }).catch(function (e) { if (e.message !== "session") informer("Action impossible", e.message); });
  }
  function modeJeu() {
    confirmer("Mode jeu", "Tout va être éteint (Crew, modèles, LM Studio, Open WebUI, Kokoro, Docker) pour libérer la carte graphique.\n\nContinuer ?", "Tout éteindre", "danger")
      .then(function (ok) { return ok && lancer("mode_jeu"); })
      .catch(function (e) { informer("Action impossible", e.message); });
  }
  function toutDemarrer() {
    confirmer("Tout démarrer", "Tout va être rallumé, dans le bon ordre. Cela peut prendre plusieurs minutes (Docker, modèles).\n\nContinuer ?", "Tout démarrer")
      .then(function (ok) { return ok && lancer("tout_demarrer"); })
      .catch(function (e) { informer("Action impossible", e.message); });
  }

  function attendreFinAction() {
    return new Promise(function (resolve) {
      (function boucle() {
        api("GET", "/api/action").then(function (d) {
          if (!d.action || d.action.statut !== "en_cours") resolve(d.action); else setTimeout(boucle, 1500);
        }).catch(function () { resolve(null); });
      })();
    });
  }

  function ouvrir(c) {
    var etapeAllumer = c.etat.code === "actif" ? Promise.resolve(true)
      : confirmer(c.nom + " est éteint", "Voulez-vous l'allumer d'abord ? (l'ouverture se fera ensuite)", "Allumer puis ouvrir").then(function (ok) {
        if (!ok) return false;
        return api("GET", "/api/plan?sens=demarrer&ident=" + encodeURIComponent(c.ident)).then(function (p) {
          return lancer("demarrer", c.ident, true);
        }).then(attendreFinAction).then(function (a) {
          if (!a || a.resultats[c.ident] === undefined || a.resultats[c.ident].code !== "actif") {
            return informer("Démarrage impossible", "Le démarrage de " + c.nom + " n'a pas abouti : voyez le message sous le composant.").then(function () { return false; });
          }
          return true;
        });
      });
    etapeAllumer.then(function (ok) {
      if (!ok) return;
      return api("POST", "/api/ouvrir", { ident: c.ident }).then(function (r) {
        var texte = r.message || "";
        var distant = ["127.0.0.1", "localhost"].indexOf(location.hostname) < 0;
        if (distant) texte = (texte ? texte + "\n\n" : "") + "L'application s'ouvre sur le PC, pas sur cet appareil.";
        if (r.presse_papiers && navigator.clipboard) {
          navigator.clipboard.writeText(r.presse_papiers).catch(function () {});
        }
        if (texte) return informer("Ouverture de " + c.nom, texte);
      });
    }).catch(function (e) { if (e.message !== "session") informer("Ouverture impossible", e.message); });
  }

  // ------------------------------------------------ page Coûts
  function pageCouts() {
    var zone = h("div");
    page.appendChild(zone);
    chargerCouts(zone);
  }

  function chargerCouts(zone) {
    api("GET", "/api/couts").then(function (d) { dessinerCouts(zone, d); })
      .catch(function (e) { if (e.message !== "session") { vider(zone); zone.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); } });
  }

  function tableauIA(bloc, noms) {
    var cles = Object.keys(bloc.par_ia);
    if (!cles.length) return h("p", { class: "doux", texte: "Aucune dépense enregistrée." });
    return h("table", { class: "tab" }, h("tbody", null, cles.map(function (k) {
      return h("tr", null, h("td", { texte: noms[k] || k }), h("td", { class: "num", texte: dollars(bloc.par_ia[k]) }));
    })));
  }

  function dessinerCouts(zone, d) {
    vider(zone);
    if (d.bloque) zone.appendChild(h("div", { class: "bandeau erreur", role: "alert", texte: d.message }));
    zone.appendChild(h("div", { class: "grille2" },
      h("div", { class: "carte" }, h("h2", { texte: "Aujourd'hui (estimé)" }),
        h("div", { class: "nom", texte: dollars(d.totaux.aujourdhui.total) }), tableauIA(d.totaux.aujourdhui, d.ia)),
      h("div", { class: "carte" }, h("h2", { texte: "Ce mois-ci (estimé)" }),
        h("div", { class: "nom", texte: dollars(d.totaux.mois.total) }), tableauIA(d.totaux.mois, d.ia))));
    zone.appendChild(h("p", { class: "doux", texte: "Ces montants sont des estimations calculées par le Centre à partir de ses propres compteurs, en dollars US. Ils ne remplacent pas les factures des fournisseurs." }));

    // DeepSeek
    var carteDS = h("div", { class: "carte" }, h("h2", { texte: "Solde DeepSeek" }));
    var contenuDS = h("div", { class: "msg", texte: "Chargement…" });
    carteDS.appendChild(contenuDS);
    carteDS.appendChild(h("button", { class: "bouton", type: "button", texte: "Actualiser", onclick: function () { solde(contenuDS, true); } }));
    zone.appendChild(carteDS);
    solde(contenuDS, false);

    // Plafonds
    var jour = h("input", { type: "number", min: "0", step: "0.01", inputmode: "decimal", id: "plafond-jour", value: d.plafonds.jour.plafond == null ? "" : String(d.plafonds.jour.plafond) });
    var mois = h("input", { type: "number", min: "0", step: "0.01", inputmode: "decimal", id: "plafond-mois", value: d.plafonds.mois.plafond == null ? "" : String(d.plafonds.mois.plafond) });
    var retour = h("div", { class: "msg", role: "status" });
    var form = h("form", { class: "carte" }, h("h2", { texte: "Plafonds de dépense (dollars US)" }),
      h("p", { class: "doux", texte: "Quand un plafond est atteint, les IA payantes sont bloquées avec un message clair. Laissez vide pour ne pas avoir de plafond. Les IA locales (gemma) ne sont jamais bloquées." }),
      h("div", { class: "grille2" },
        h("label", { class: "champ", for: "plafond-jour" }, h("span", { texte: "Par jour (dépensé aujourd'hui : " + dollars(d.plafonds.jour.depense) + ")" }), jour),
        h("label", { class: "champ", for: "plafond-mois" }, h("span", { texte: "Par mois (dépensé ce mois-ci : " + dollars(d.plafonds.mois.depense) + ")" }), mois)),
      h("button", { class: "bouton principal", type: "submit", texte: "Enregistrer les plafonds" }), retour);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      api("PUT", "/api/couts/plafonds", { jour: jour.value, mois: mois.value }).then(function (r) { dessinerCouts(zone, r); })
        .catch(function (err) { retour.textContent = err.message; });
    });
    zone.appendChild(form);

    var t = d.tarifs;
    zone.appendChild(h("div", { class: "carte" }, h("h2", { texte: "Tarifs de référence (vérifiés le " + t.verifie_le + ", à revérifier)" }),
      h("ul", { class: "doux" },
        h("li", { texte: "Grok Voice : " + t.grok_voice_par_minute + " $/min" }),
        h("li", { texte: "gpt-realtime-mini : " + t.gpt_realtime_mini_par_million_jetons_audio.entrant + " $ / " + t.gpt_realtime_mini_par_million_jetons_audio.sortant + " $ par million de jetons audio (entrant / sortant)" }),
        h("li", { texte: "gpt-realtime-2 : " + t.gpt_realtime_2_par_million_jetons_audio.entrant + " $ / " + t.gpt_realtime_2_par_million_jetons_audio.sortant + " $" }),
        h("li", { texte: "Transcription xAI : " + t.transcription_xai_par_heure + " $/h" }),
        h("li", { texte: "Synthèse vocale xAI : " + t.synthese_xai_par_million_caracteres + " $ par million de caractères" }))));
  }

  function solde(el, forcer) {
    el.textContent = "Chargement…";
    api("GET", "/api/couts/deepseek" + (forcer ? "?forcer=1" : "")).then(function (r) {
      vider(el);
      if (!r.ok) { el.textContent = r.message; return; }
      if (!r.soldes.length) { el.textContent = "Aucun solde renvoyé."; return; }
      r.soldes.forEach(function (s) {
        el.appendChild(h("div", null, h("strong", { texte: s.total + " " + s.devise }),
          h("span", { class: "doux", texte: "  (offert : " + s.accorde + ", rechargé : " + s.recharge + ")" })));
      });
      if (r.disponible === false) el.appendChild(h("div", { class: "msg", texte: "DeepSeek indique que le solde est insuffisant pour appeler l'API." }));
    }).catch(function (e) { el.textContent = e.message; });
  }

  // ------------------------------------------------ page Journal
  function pageJournal() {
    var zone = h("div");
    page.appendChild(zone);
    Promise.all([api("GET", "/api/recus"), api("GET", "/api/journal")]).then(function (r) {
      var recus = r[0].recus, lignes = r[1].lignes;
      zone.appendChild(h("div", { class: "carte" }, h("h2", { texte: "Reçus (actions récentes)" }),
        recus.length ? h("table", { class: "tab" }, h("tbody", null, recus.map(function (x) {
          return h("tr", null, h("td", { texte: x.ts.replace("T", " ").slice(0, 19) }), h("td", { texte: x.action }),
            h("td", { texte: x.resultat }), h("td", { class: "msg", texte: JSON.stringify(x.details) }));
        }))) : h("p", { class: "doux", texte: "Aucun reçu pour l'instant." })));
      zone.appendChild(h("div", { class: "carte" }, h("h2", { texte: "Journal du serveur (200 dernières lignes)" }),
        h("pre", { class: "journal", texte: lignes.join("\n") || "(vide)" })));
    }).catch(function (e) { if (e.message !== "session") zone.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); });
  }

  // ------------------------------------------------ démarrage
  Array.prototype.forEach.call(document.querySelectorAll("#onglets button"), function (b) {
    b.addEventListener("click", function () { aller(b.dataset.page); });
  });
  document.getElementById("deconnexion").addEventListener("click", function () {
    api("POST", "/api/deconnexion", {}).catch(function () {}).then(function () { location.replace("/connexion"); });
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && pageCourante === "centre") { clearTimeout(minuterie); aller("centre"); }
  });
  if ("serviceWorker" in navigator) { navigator.serviceWorker.register("/sw.js").catch(function () {}); }
  aller((location.hash || "#centre").slice(1));
})();
