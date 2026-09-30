"use strict";
/* Pages « Rappels » (avec bulletin du matin) et « Départements », rapport d'usage, entretien. Texte affiché comme texte, jamais comme HTML. */
(function () {
  var C = window.Centre, h = C.h, vider = C.vider, api = C.api;

  function stocker(k, v) { try { localStorage.setItem("centre." + k, v); } catch (e) { /* facultatif */ } }
  function relire(k) { try { return localStorage.getItem("centre." + k); } catch (e) { return null; } }
  function aujourdhui() { var d = new Date(); return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate(); }
  function local(ts) { return new Date(ts * 1000).toLocaleString("fr-CA", { dateStyle: "medium", timeStyle: "short" }); }
  function pourInput(ts) {
    var d = new Date(ts * 1000), p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  // ------------------------------------------------ alertes de rappels (toutes pages, page ouverte)
  var deja = {};
  function alertes() {
    api("GET", "/api/rappels/dus").then(function (d) {
      var zone = document.getElementById("alertes"); if (!zone) return;
      vider(zone);
      d.dus.forEach(function (r) {
        zone.appendChild(h("div", { class: "bandeau erreur", role: "alert" }, h("strong", { texte: "Rappel : " }), r.texte + " (" + local(r.echeance) + ") ",
          h("button", { class: "petit", type: "button", texte: "Fait", onclick: function () { api("PUT", "/api/rappels/" + r.id, { action: "terminer" }).then(alertes); } }), " ",
          h("button", { class: "petit", type: "button", texte: "+1 h", onclick: function () { api("PUT", "/api/rappels/" + r.id, { action: "reporter", minutes: 60 }).then(alertes); } })));
        if (!deja[r.id + ":" + r.echeance] && window.Notification && Notification.permission === "granted") {
          try { new Notification("Rappel", { body: r.zone === "prive" ? "Vous avez un rappel (ouvrez le Centre)." : r.texte }); } catch (e) { /* non disponible */ }
        }
        deja[r.id + ":" + r.echeance] = true;
      });
    }).catch(function () { /* session expirée ou serveur arrêté : la page s'en occupe */ });
  }
  window.addEventListener("load", function () { setTimeout(alertes, 1500); setInterval(function () { if (!document.hidden) alertes(); }, 30000); });

  // ------------------------------------------------ page Rappels + bulletin
  function pageRappels() {
    var zone = h("div"); C.page.appendChild(zone); dessinerRappels(zone);
  }
  function dessinerRappels(zone) {
    Promise.all([api("GET", "/api/rappels"), api("GET", "/api/bulletin")]).then(function (r) {
      vider(zone);
      zone.appendChild(carteBulletin(r[1]));
      zone.appendChild(carteRappels(r[0].rappels, zone));
    }).catch(function (e) { if (e.message !== "session") { vider(zone); zone.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); } });
  }

  function texteBulletin(b) {
    return b.sections.map(function (s) { return (s.titre ? s.titre + " : " : "") + s.lignes.join(" "); }).join("\n\n");
  }
  function carteBulletin(b) {
    var auto = h("input", { type: "checkbox", id: "bulletin-auto", checked: relire("bulletin.auto") !== "non" });
    auto.addEventListener("change", function () { stocker("bulletin.auto", auto.checked ? "oui" : "non"); });
    var etat = h("div", { class: "msg", role: "status" });
    return h("div", { class: "carte" }, h("h2", { texte: "Bulletin du matin — " + b.date }),
      b.sections.map(function (s) { return h("div", null, s.titre ? h("strong", { texte: s.titre }) : null, h("ul", { class: "doux" }, s.lignes.map(function (l) { return h("li", { texte: l }); }))); }),
      h("div", { class: "boutons-ligne" },
        h("button", { class: "bouton principal", type: "button", texte: "Lire à voix haute", onclick: function () { lireBulletin(etat); } }),
        h("button", { class: "bouton", type: "button", texte: "Actualiser", onclick: function () { C.aller("rappels"); } })),
      h("label", null, auto, " Afficher le bulletin automatiquement, une fois par jour"),
      etat, h("p", { class: "doux", texte: "La lecture à voix haute passe par le nuage : le texte de vos rappels privés n'est jamais envoyé (seulement « vous avez N rappels privés »)." }));
  }
  var audioBulletin = null;
  function lireBulletin(etat) {
    etat.textContent = "Préparation de la voix…";
    fetch("/api/bulletin/lire", { method: "POST", credentials: "same-origin", headers: { "X-Centre": "1", "Content-Type": "application/json" }, body: JSON.stringify({ fournisseur: "openai" }) })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (d) { throw new Error(d.erreur || ("Erreur " + r.status)); });
        return r.blob();
      }).then(function (blob) {
        if (audioBulletin) audioBulletin.pause();
        audioBulletin = new Audio(URL.createObjectURL(blob));
        audioBulletin.onended = function () { etat.textContent = "Terminé."; };
        etat.textContent = "Lecture…";
        return audioBulletin.play();
      }).catch(function (e) { etat.textContent = "⚠ " + e.message; });
  }

  var RECURRENCES = [{ valeur: "aucune", texte: "Une seule fois" }, { valeur: "quotidien", texte: "Tous les jours" }, { valeur: "hebdomadaire", texte: "Toutes les semaines" }, { valeur: "mensuel", texte: "Tous les mois" }];
  function carteRappels(liste, zone) {
    var texte = h("input", { type: "text", id: "r-texte", maxlength: "500", placeholder: "Ex. : appeler le client Durand" });
    var quand = h("input", { type: "datetime-local", id: "r-quand", value: pourInput(Date.now() / 1000 + 3600) });
    var rec = h("select", { id: "r-rec" }, RECURRENCES.map(function (o) { return h("option", { value: o.valeur, texte: o.texte }); }));
    var zoneSel = h("select", { id: "r-zone" }, [h("option", { value: "prive", texte: "Privé (jamais lu par une voix du nuage)" }), h("option", { value: "partageable", texte: "Partageable" })]);
    var retour = h("div", { class: "msg", role: "status" });
    var form = h("form", null,
      h("label", { class: "champ", for: "r-texte" }, h("span", { texte: "Rappel" }), texte),
      h("div", { class: "grille2" }, h("label", { class: "champ", for: "r-quand" }, h("span", { texte: "Quand" }), quand), h("label", { class: "champ", for: "r-rec" }, h("span", { texte: "Répéter" }), rec)),
      h("label", { class: "champ", for: "r-zone" }, h("span", { texte: "Confidentialité" }), zoneSel),
      h("button", { class: "bouton principal", type: "submit", texte: "Ajouter le rappel" }), retour);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var ts = new Date(quand.value).getTime() / 1000;
      api("POST", "/api/rappels", { texte: texte.value, echeance: ts, recurrence: rec.value, zone: zoneSel.value }).then(function () { dessinerRappels(zone); alertes(); })
        .catch(function (x) { retour.textContent = x.message; });
    });
    var notif = (window.Notification && Notification.permission === "default")
      ? h("button", { class: "petit", type: "button", texte: "Activer les notifications du navigateur", onclick: function () { Notification.requestPermission().then(function () { C.aller("rappels"); }); } }) : null;
    var maintenant = Date.now() / 1000;
    var lignes = liste.map(function (r) {
      var enRetard = r.echeance < maintenant;
      return h("tr", null, h("td", null, h("strong", { texte: r.texte }), h("div", { class: "msg", texte: local(r.echeance) + (enRetard ? " — EN RETARD" : "") + (r.recurrence !== "aucune" ? " · " + r.recurrence : "") + " · " + (r.zone === "prive" ? "privé" : "partageable") })),
        h("td", null,
          h("button", { class: "petit", type: "button", texte: "Fait", onclick: function () { api("PUT", "/api/rappels/" + r.id, { action: "terminer" }).then(function () { dessinerRappels(zone); alertes(); }); } }), " ",
          h("button", { class: "petit", type: "button", texte: "+1 h", onclick: function () { api("PUT", "/api/rappels/" + r.id, { action: "reporter", minutes: 60 }).then(function () { dessinerRappels(zone); alertes(); }); } }), " ",
          h("button", { class: "petit", type: "button", texte: "Supprimer", onclick: function () {
            C.confirmer("Supprimer ce rappel ?", r.texte, "Supprimer", "danger").then(function (ok) { if (ok) api("DELETE", "/api/rappels/" + r.id).then(function () { dessinerRappels(zone); alertes(); }); });
          } })));
    });
    return h("div", { class: "carte" }, h("h2", { texte: "Rappels (" + liste.length + ")" }),
      liste.length ? h("table", { class: "tab" }, h("tbody", null, lignes)) : h("p", { class: "doux", texte: "Aucun rappel en attente." }),
      form, notif,
      h("p", { class: "doux", texte: "Les alertes s'affichent quand le Centre est ouvert (PC ou téléphone). Il n'y a pas de notification quand l'application est fermée." }));
  }

  // ------------------------------------------------ bulletin automatique, une fois par jour
  window.addEventListener("load", function () {
    if (relire("bulletin.auto") === "non" || relire("bulletin.jour") === aujourdhui()) return;
    setTimeout(function () {
      if (relire("bulletin.jour") === aujourdhui()) return;
      api("GET", "/api/bulletin").then(function (b) {
        stocker("bulletin.jour", aujourdhui());
        return C.demander("Bulletin du matin — " + b.date, texteBulletin(b), [{ texte: "Fermer", valeur: false }, { texte: "Ouvrir la page Rappels", valeur: true, style: "principal" }]).then(function (v) { if (v) C.aller("rappels"); });
      }).catch(function () { /* pas grave */ });
    }, 2500);
  });

  // ------------------------------------------------ page Départements
  function pageDepartements() {
    var zone = h("div"); C.page.appendChild(zone);
    api("GET", "/api/departements").then(function (d) {
      if (d.problemes.length) zone.appendChild(h("div", { class: "bandeau", role: "status" }, h("strong", { texte: "Fichiers de départements ignorés : " }), d.problemes.join(" ; ")));
      zone.appendChild(h("p", { class: "doux", texte: "Des raccourcis de travail : un clic ouvre une nouvelle conversation, dans la bonne salle, avec le texte prêt à compléter. Pour ajouter ou modifier des départements : voir README (dossier donnees\\departements)." }));
      d.departements.forEach(function (dep) {
        zone.appendChild(h("div", { class: "carte" }, h("h2", { texte: dep.nom }), h("p", { class: "doux", texte: dep.description }),
          h("div", { class: "boutons-ligne" }, dep.demarrages.map(function (x) {
            return h("button", { class: "bouton", type: "button", title: "Salle : " + x.salle + (x.memoire ? " · avec la mémoire" : ""), texte: x.titre, onclick: function () {
              C.demarrerDans(x.salle, x.titre, x.prompt, x.memoire).catch(function (e) { C.informer("Impossible", e.message); });
            } });
          }))));
      });
    }).catch(function (e) { if (e.message !== "session") zone.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); });
  }

  // ------------------------------------------------ Coûts : rapport d'usage
  C.apresCouts.push(function (zone) {
    var carte = h("div", { class: "carte" }, h("h2", { texte: "Rapport d'usage" }));
    var sel = h("select", { id: "rapport-jours", "aria-label": "Période" }, [7, 30, 90, 365].map(function (n) { return h("option", { value: String(n), texte: "Derniers " + n + " jours", selected: n === 30 }); }));
    var corps = h("div");
    var lien = h("a", { class: "petit", href: "/api/rapport.csv?jours=30", texte: "Télécharger en CSV" });
    function charger() {
      lien.setAttribute("href", "/api/rapport.csv?jours=" + sel.value);
      api("GET", "/api/rapport?jours=" + sel.value).then(function (r) {
        vider(corps);
        corps.appendChild(h("p", null, h("strong", { texte: C.dollars(r.total_usd) }), " au total (moyenne " + C.dollars(r.moyenne_par_jour_usd) + " par jour), " + r.conversations_actives + " conversations actives, voix : " + r.voix.sessions + " session(s), " + r.voix.minutes + " min."));
        var ias = Object.keys(r.par_ia);
        corps.appendChild(ias.length ? h("table", { class: "tab" }, h("thead", null, h("tr", null, h("th", { texte: "IA" }), h("th", { class: "num", texte: "Dépense estimée" }), h("th", { class: "num", texte: "Messages IA" }))),
          h("tbody", null, ias.map(function (k) { return h("tr", null, h("td", { texte: k }), h("td", { class: "num", texte: C.dollars(r.par_ia[k]) }), h("td", { class: "num", texte: String(r.messages_par_salle[k] || 0) })); })))
          : h("p", { class: "doux", texte: "Aucune dépense sur la période." }));
        var jours = Object.keys(r.par_jour), maxi = Math.max.apply(null, jours.map(function (j) { return r.par_jour[j]; }).concat([0.0001]));
        if (jours.length) corps.appendChild(h("div", { class: "histo", role: "img", "aria-label": "Dépenses par jour" }, jours.slice(-30).map(function (j) {
          var b = h("div", { class: "barre", title: j + " : " + C.dollars(r.par_jour[j]) }); b.style.height = Math.max(2, Math.round(60 * r.par_jour[j] / maxi)) + "px"; return b;
        })));
      }).catch(function (e) { corps.textContent = e.message; });
    }
    sel.addEventListener("change", charger);
    carte.appendChild(h("div", { class: "boutons-ligne" }, sel, lien)); carte.appendChild(corps); zone.appendChild(carte); charger();
  });

  // ------------------------------------------------ Journal : entretien (gardien + sauvegardes)
  C.apresJournal.push(function (zone) {
    var carte = h("div", { class: "carte" }, h("h2", { texte: "Entretien : gardien et sauvegardes" }));
    var corps = h("div"), retour = h("div", { class: "msg", role: "status" });
    function charger() {
      Promise.all([api("GET", "/api/gardien"), api("GET", "/api/sauvegardes")]).then(function (r) {
        var g = r[0], s = r[1].sauvegardes; vider(corps);
        corps.appendChild(h("p", { class: (g.ok === false || g.silencieux) ? "" : "doux" }, h("strong", { texte: "Gardien : " }), g.ts ? "dernier passage " + local(g.ts) + (g.ok ? " — tout va bien." : " — PROBLÈME.") : "jamais exécuté."));
        (g.alertes || []).forEach(function (a) { corps.appendChild(h("div", { class: "bandeau erreur", texte: a })); });
        corps.appendChild(h("p", null, h("strong", { texte: "Sauvegardes : " }), s.length ? s.length + " gardée(s), la dernière le " + local(s[0].date) + " (" + Math.round(s[0].taille / 1024) + " Ko)." : "aucune pour l'instant."));
      }).catch(function (e) { corps.textContent = e.message; });
    }
    carte.appendChild(corps);
    carte.appendChild(h("button", { class: "bouton", type: "button", texte: "Sauvegarder maintenant", onclick: function () {
      retour.textContent = "Sauvegarde en cours…";
      api("POST", "/api/sauvegardes", {}).then(function (r) { retour.textContent = r.message + (r.ecartes && r.ecartes.length ? " (" + r.ecartes.length + " fichier(s) écarté(s) : secrets ou temporaires)" : ""); charger(); })
        .catch(function (e) { retour.textContent = "⚠ " + e.message; });
    } }));
    carte.appendChild(retour);
    carte.appendChild(h("p", { class: "doux", texte: "La sauvegarde de nuit (03:00) ne contient aucun secret ; on garde les 7 dernières dans I:\\IA\\CENTRE\\sauvegardes." }));
    zone.insertBefore(carte, zone.firstChild);
    charger();
  });

  C.pages.rappels = pageRappels;
  C.pages.departements = pageDepartements;
})();
