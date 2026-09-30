"use strict";
/* Pages « Salles » et « Tiroir ». Les textes venant des IA sont affichés comme du texte, jamais comme du HTML. */
(function () {
  var C = window.Centre, h = C.h, vider = C.vider, api = C.api;
  var S = { salles: [], politique: null, memoire: null, salle: null, convs: [], conv: null, actives: [], selection: [],
            brouillon: "", enCours: false, live: null, images: [], titres: {} };
  var racine = null;
  S.opt = { memoire: false, lire: relire("opt.lire") === "oui", ecriture: false };
  S.voixOpts = null;
  // Table ronde : une question à plusieurs IA, TOUJOURS par Crew (le Centre envoie la liste cochée, Crew applique la confidentialité).
  var DEFAUT_TR = ["gemini", "deepseek", "gemma"];
  S.tr = { ouvert: window.innerWidth > 720, actif: relire("tr.actif") === "oui", participants: DEFAUT_TR.slice(), critique: false, synthese: true, options: null, est: null };
  try { var sauve = JSON.parse(relire("tr.participants") || "null"); if (Array.isArray(sauve) && sauve.length) S.tr.participants = sauve.filter(function (x) { return typeof x === "string"; }); } catch (e) { /* défaut */ }
  function libellesTr(o) { (o.participants || []).forEach(function (p) { LIBELLE_TR[p.id] = p.libelle; }); }      // « gemma » s'affiche « Chef local (<modèle>) »
  var LIBELLE_TR = { claude: "Claude", codex: "ChatGPT / Codex", gemini: "Gemini", grok: "Grok", deepseek: "DeepSeek", gemma: "Chef local", synthese: "Synthèse de Crew" };
  function trActive() { return S.tr.actif && S.salle === "crew"; }

  function stocker(k, v) { try { localStorage.setItem("centre." + k, v); } catch (e) { /* facultatif */ } }
  function relire(k) { try { return localStorage.getItem("centre." + k); } catch (e) { return null; } }

  // ------------------------------------------------ rendu du texte (Markdown minimal, sans HTML)
  function inline(parent, texte) {
    var motif = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g, dernier = 0, m;
    while ((m = motif.exec(texte)) !== null) {
      if (m.index > dernier) parent.appendChild(document.createTextNode(texte.slice(dernier, m.index)));
      var t = m[0];
      parent.appendChild(t.charAt(0) === "`" ? h("code", { texte: t.slice(1, -1) }) : h("strong", { texte: t.slice(2, -2) }));
      dernier = m.index + t.length;
    }
    if (dernier < texte.length) parent.appendChild(document.createTextNode(texte.slice(dernier)));
  }
  function rendre(el, texte) {
    vider(el);
    var morceaux = String(texte || "").split(/```/);
    morceaux.forEach(function (bloc, i) {
      if (i % 2 === 1) {
        var lignes = bloc.replace(/^[^\n]*\n/, "");             // retire le nom du langage
        var pre = h("pre", null, h("code", { texte: lignes.replace(/\n$/, "") }));
        el.appendChild(pre);
        el.appendChild(h("button", { class: "petit", type: "button", texte: "Copier le code", onclick: function () { copier(lignes.replace(/\n$/, "")); } }));
      } else if (bloc) {
        bloc.split(/\n{2,}/).forEach(function (para) {
          if (!para.trim()) return;
          var p = h("p"); inline(p, para.replace(/^\s+|\s+$/g, "")); el.appendChild(p);
        });
      }
    });
  }
  function copier(texte) { if (navigator.clipboard) navigator.clipboard.writeText(texte).catch(function () {}); }

  // ------------------------------------------------ flux SSE
  function lireFlux(url, opts, surEvenement, signal) {
    opts = opts || {};
    opts.credentials = "same-origin"; opts.headers = Object.assign({ "X-Centre": "1" }, opts.headers || {});
    if (signal) opts.signal = signal;
    return fetch(url, opts).then(function (r) {
      if (r.status === 401) { location.replace("/connexion"); throw new Error("session"); }
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (d) {
        if (r.status === 403 && d.nip_requis && !opts._nip) {      // appareil distant : NIP à confirmer, puis on recommence
          return C.demanderNip().then(function (ok) {
            if (!ok) throw new Error("NIP non confirmé : action annulée.");
            return lireFlux(url, Object.assign({}, opts, { _nip: true }), surEvenement, signal);
          });
        }
        throw new Error(d.erreur || ("Erreur " + r.status));
      });
      var lecteur = r.body.getReader(), dec = new TextDecoder(), tampon = "";
      function pomper() {
        return lecteur.read().then(function (x) {
          if (x.done) return;
          tampon += dec.decode(x.value, { stream: true });
          var blocs = tampon.split("\n\n"); tampon = blocs.pop();
          blocs.forEach(function (b) {
            b.split("\n").forEach(function (l) {
              if (l.indexOf("data: ") === 0) { try { surEvenement(JSON.parse(l.slice(6))); } catch (e) { /* ligne illisible */ } }
            });
          });
          return pomper();
        });
      }
      return pomper();
    });
  }

  // ------------------------------------------------ page Salles
  function pageSalles() {
    racine = h("div", { id: "salles" });
    C.page.appendChild(racine);
    S.salle = S.salle || relire("salle") || "crew";
    api("GET", "/api/table-ronde/options").then(function (o) { S.tr.options = o; libellesTr(o); if (C.courante() === "salles") dessinerDock(salleCourante()); }).catch(function () {});
    C.voixOptions().then(function (o) { S.voixOpts = o; if (C.courante() === "salles") dessinerDock(salleCourante()); }).catch(function () {});
    charger().then(function () {
      if (S.pendingConv) { var id = S.pendingConv; S.pendingConv = null; if (S.memoireInitiale) { S.opt.memoire = true; S.memoireInitiale = false; } return ouvrir(id); }
      if (S.conv == null) dessiner();
    });
  }

  function charger() {
    return Promise.all([api("GET", "/api/salles"), api("GET", "/api/conversations?salle=" + encodeURIComponent(S.salle || "crew")),
                        api("GET", "/api/table-ronde/options").catch(function () { return null; })]).then(function (r) {
      if (r[2]) { S.tr.options = r[2]; libellesTr(r[2]); }
      S.salles = r[0].salles; S.politique = r[0].politique; S.memoire = r[0].memoire; S.actives = r[1].actives; S.convs = r[1].conversations;
      dessiner();
    }).catch(function (e) { if (e.message !== "session") { vider(racine); racine.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); } });
  }

  function salleCourante() { return S.salles.filter(function (s) { return s.id === S.salle; })[0]; }

  function dessiner(sansCapture) {
    if (!racine || C.courante() !== "salles") return;
    var garde = document.getElementById("saisie");
    if (!sansCapture && garde && garde.dataset.conv === (S.conv ? S.conv.id : "")) S.brouillon = garde.value;
    vider(racine);
    var s = salleCourante();
    // bandeau de politique
    if (S.politique && !S.politique.nuage) racine.appendChild(h("div", { class: "bandeau", role: "status" }, h("strong", { texte: "Mode " + S.politique.libelle + " : " }), S.politique.message));
    // pastilles de salles
    racine.appendChild(h("div", { class: "chips", role: "tablist" }, S.salles.map(function (x) {
      var code = x.disponible ? "actif" : "arrete";
      return h("button", { class: "chip" + (x.disponible ? "" : " indispo"), type: "button", role: "tab", "aria-pressed": x.id === S.salle ? "true" : "false",
        title: x.disponible ? x.description : x.raison, onclick: function () { choisirSalle(x.id); } },
        h("span", { class: "voyant v-" + code, "aria-hidden": "true" }), h("span", { class: "nom-salle", texte: x.libelle }));
    })));
    if (!s) { dessinerDock(null); return; }
    if (!s.disponible) racine.appendChild(h("div", { class: "bandeau erreur", role: "status" }, s.libelle + " : " + s.raison + (s.lecture_seule ? " Vous pouvez relire les anciennes conversations. " : " "),
      s.lien === "chef" ? h("button", { class: "petit", type: "button", texte: "Ouvrir « Chef d'équipe »", onclick: function () { C.aller("chef"); } }) : null));
    // en-tête de salle
    racine.appendChild(h("div", { class: "rangee-titre" },
      h("span", { class: "doux", texte: s.description + " — " + (s.auths.filter(function (a) { return a.id === s.auth; })[0] || {}).texte + (s.modele ? " · " + s.modele : "") }),
      h("button", { class: "petit", type: "button", texte: "Réglages", onclick: reglagesSalle }),
      h("button", { class: "petit", type: "button", texte: "Nouvelle conversation", onclick: nouvelle })));
    // liste des conversations
    var details = h("details", { class: "convs" }, h("summary", { texte: "Conversations (" + S.convs.length + ")" }),
      h("div", { class: "liste-convs" }, S.convs.length ? S.convs.map(function (c) {
        return h("button", { type: "button", "aria-current": S.conv && S.conv.id === c.id ? "true" : "false", onclick: function () { ouvrir(c.id); } },
          c.titre || "(sans titre)", h("span", { class: "doux", texte: new Date(c.maj * 1000).toLocaleString("fr-CA") + (c.prive ? " · privé" : "") + (S.actives.indexOf(c.id) >= 0 ? " · en cours…" : "") }));
      }) : h("div", { class: "doux", texte: "Aucune conversation dans cette salle." })));
    if (!S.conv) details.setAttribute("open", "");
    racine.appendChild(details);
    if (S.conv) racine.appendChild(zoneChat(s));
    else racine.appendChild(h("div", { class: "accueil" }, "🏠 ", h("b", { texte: "Centre" }), " — votre poste de commande. Écrivez ci-dessous, ou maintenez le grand bouton pour parler. Une conversation se crée toute seule à votre premier message."));
    dessinerDock(s);
  }

  // ------------------------------------------------ bas d'écran : parole, saisie, bascules
  var ptt = { actif: false, enregistrement: null, finDemandee: false };
  function court(t) { return String(t || "").replace(/ \(.*$/, "").replace(" par demande", ""); }
  function indice(t) { var e = document.getElementById("dock-indice"); if (e) e.textContent = t || ""; }
  function bascule(texte, actif, titre, action, desactive) {
    return h("button", { class: "bascule" + (actif ? " on" : ""), type: "button", title: titre || "", disabled: !!desactive, "aria-pressed": actif ? "true" : "false", texte: texte, onclick: action });
  }
  function dessinerDock(s) {
    var dock = document.getElementById("dock");
    if (!dock || C.courante() !== "salles") return;
    vider(dock); dock.hidden = false;
    var pret = !!(s && s.disponible);
    var saisie = h("textarea", { id: "saisie", rows: "1", placeholder: pret ? "Écrire à " + s.libelle + "…" : "Cette salle est indisponible", disabled: !pret || S.enCours, "aria-label": "Votre message" });
    saisie.value = S.brouillon || ""; saisie.dataset.conv = S.conv ? S.conv.id : "";
    // Hauteur mesurée sur un miroir invisible : la vraie zone n'est jamais repliée puis rouverte (ce qui faisait « sauter » la page à chaque touche).
    var miroir = h("textarea", { class: "saisie-miroir", rows: "1", tabindex: "-1", "aria-hidden": "true", readonly: "" });
    function ajuster() {
      if (!saisie.isConnected) return;
      if (!miroir.isConnected) saisie.parentNode.appendChild(miroir);
      miroir.style.width = saisie.offsetWidth + "px";
      miroir.value = saisie.value + "\u200b";
      var bord = getComputedStyle(saisie).boxSizing === "border-box" ? saisie.offsetHeight - saisie.clientHeight : 0;
      var cible = Math.max(44, Math.min(miroir.scrollHeight + bord, 140)) + "px";
      if (saisie.style.height !== cible) saisie.style.height = cible;
    }
    saisie.addEventListener("input", function () { ajuster(); estimer(saisie, s); });
    saisie.addEventListener("keydown", function (e) {
      var tactile = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
      if (e.key === "Enter" && !e.shiftKey && !tactile) { e.preventDefault(); envoyer(); }
    });
    setTimeout(ajuster, 0);
    if (window.ResizeObserver) new ResizeObserver(function () { if (saisie.isConnected) ajuster(); }).observe(saisie);          // rotation, clavier…
    var voixOk = !!(S.voixOpts && S.voixOpts.disponible);
    var bouton = h("button", { class: "cbbar", id: "ptt", type: "button", "aria-label": "Maintenir pour parler", disabled: !pret || S.enCours },
      "🎙 ", h("span", { id: "ptt-label", texte: voixOk ? "MAINTENIR POUR PARLER" : "MAINTENIR POUR PARLER (voix indisponible)" }));
    bouton.addEventListener("pointerdown", pttDebut); bouton.addEventListener("pointerup", pttFin); bouton.addEventListener("pointercancel", pttFin);
    bouton.addEventListener("pointerleave", pttFin); bouton.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    bouton.addEventListener("keydown", function (e) { if (e.key === " " && !e.repeat) pttDebut(e); });
    bouton.addEventListener("keyup", function (e) { if (e.key === " ") pttFin(e); });
    var entreeFichier = h("input", { type: "file", id: "fichier-joint", multiple: "", hidden: true, accept: ".txt,.md,.csv,.tsv,.json,.log,.py,.js,.ts,.html,.css,.xml,.yaml,.yml,.ini,.toml,.sql,.sh,.bat,.ps1,.cfg,.conf,image/*", "aria-label": "Choisir des fichiers à joindre" });
    entreeFichier.addEventListener("change", function () { var f = Array.prototype.slice.call(entreeFichier.files); entreeFichier.value = ""; joindre(f); });
    saisie.addEventListener("paste", function (e) {             // coller une image (capture d'écran, image copiée) : elle est jointe au message
      var fichiers = Array.prototype.filter.call((e.clipboardData && e.clipboardData.files) || [], function (f) { return /^image\//.test(f.type); });
      if (fichiers.length) { e.preventDefault(); joindre(fichiers); }
    });
    dock.ondragover = function (e) { if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0) e.preventDefault(); };
    dock.ondrop = function (e) { if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) { e.preventDefault(); joindre(Array.prototype.slice.call(e.dataTransfer.files)); } };
    var memoireOk = !!(S.memoire && S.memoire.disponible);
    var bascules = h("div", { class: "bascules" },
      bascule("◉ Live", false, "Conversation vocale en direct (page Voix)", function () { C.aller("voix"); }),
      s && s.id === "crew" ? bascule("🎯 Table ronde", S.tr.actif, trOk() ? "Poser la même question à plusieurs IA, par Crew" : trRaison(),
        function () { S.tr.actif = !S.tr.actif; stocker("tr.actif", S.tr.actif ? "oui" : "non"); S.tr.est = null; dessinerDock(s); if (S.tr.actif) trEstimer(); }, !trOk()) : null,
      bascule("🧠 Mémoire", S.opt.memoire && memoireOk, memoireOk ? (s && s.id === "crew" ? "Crew consulte déjà la mémoire tout seul" : "Ajouter des extraits de votre bibliothèque (partageables seulement pour le nuage)") : "Mémoire indisponible (Crew éteint ou pas exposée)",
        function () { S.opt.memoire = !S.opt.memoire; dessinerDock(s); }, !memoireOk),
      bascule("🔊 Voix", S.opt.lire && voixOk, voixOk ? "Lire les réponses à voix haute (voix du nuage ; jamais du contenu privé)" : ((S.voixOpts && S.voixOpts.raison) || "Voix indisponible"),
        function () { S.opt.lire = !S.opt.lire; stocker("opt.lire", S.opt.lire ? "oui" : "non"); if (!S.opt.lire) C.micro.arreterLecture(); dessinerDock(s); }, !voixOk),
      bascule(S.selection.length ? "🗄 Tiroir (" + S.selection.length + ")" : "🗄 Tiroir", S.selection.length > 0, "Joindre des éléments déjà rangés dans le tiroir", choisirTiroir),
      s && s.ecriture ? bascule("✍ Écriture", S.opt.ecriture, "Autoriser l'écriture dans l'atelier pour le prochain message seulement", function () { S.opt.ecriture = !S.opt.ecriture; dessinerDock(s); }) : null,
      h("button", { class: "bascule stop", id: "bouton-stop", type: "button", texte: "⏹ Stop", hidden: !S.enCours, onclick: arreter }),
      h("span", { class: "indice", id: "dock-indice", texte: court((s && s.estimation) || ""), title: (s && s.estimation) || "" }));
    dock.appendChild(h("div", { class: "dock-inner" }, trActive() ? panneauTr() : null, bouton,
      rangeePieces(),
      h("div", { class: "saisie-rangee" }, boutonJoindre(pret), saisie, entreeFichier,
        h("button", { class: "rond envoyer", id: "bouton-envoyer", type: "button", title: "Envoyer", "aria-label": "Envoyer", texte: "➤", disabled: !pret || S.enCours, onclick: function () { envoyer(); } })),
      bascules));
    if (trActive() && !S.tr.est && !S.tr.enCours) { S.tr.enCours = true; trEstimer().then(function () { S.tr.enCours = false; }); }
  }
  var minuteurEstimation = null;
  function trOk() { return !S.tr.options || S.tr.options.crew_actif; }
  function trRaison() { return (S.tr.options && S.tr.options.raison) || "Table ronde indisponible."; }
  function auMoins(e) { return e && e.total_incomplet ? "au moins " : "≈ "; }        // tarif inconnu (ex. Grok) : le total n'est qu'un minimum
  function dollars3(n) { return (Number(n) || 0).toLocaleString("fr-CA", { style: "currency", currency: "USD", minimumFractionDigits: 3, maximumFractionDigits: 3 }); }

  // Panneau de la table ronde : cases à cocher (grisées avec la raison), options, coût estimé AVANT l'envoi.
  function texteCoutCase(d, coche) {
    if (!d || !d.disponible) return "";
    if (d.cout_estime_usd) return " ≈ " + dollars3(d.cout_estime_usd);
    return coche && d.cout_estime_usd === null ? " · coût inconnu" : "";
  }
  function grisageTr(est) {                      // ce qui change la STRUCTURE du panneau (le reste se met à jour sur place)
    return est && est.ok ? est.participants.map(function (p) { return p.id + ":" + (p.disponible ? 1 : 0) + ":" + (p.raison || ""); }).join("|") : "?";
  }
  function texteResumeTr() {
    var est = S.tr.est;
    return "🎯 Table ronde — " + S.tr.participants.length + " IA, via Crew" + (est && est.ok ? " · " + auMoins(est) + dollars3(est.total_usd) + (est.depasse ? " ⚠" : "") : "") + (S.tr.critique ? " · critique" : "");
  }
  // Met à jour le panneau SANS le reconstruire (la page ne bouge pas pendant la frappe). Renvoie false si la structure a changé.
  function majPanneauTrSurPlace() {
    var resume = document.getElementById("tr-resume");
    if (!resume || grisageTr(S.tr.est) !== S.tr.sigDessinee) return false;
    resume.textContent = texteResumeTr();
    var dispo = {};
    if (S.tr.est && S.tr.est.ok) S.tr.est.participants.forEach(function (p) { dispo[p.id] = p; });
    Object.keys(dispo).forEach(function (id) {
      var el = document.getElementById("tr-c-" + id);
      if (el) el.textContent = texteCoutCase(dispo[id], S.tr.participants.indexOf(id) >= 0);
    });
    trAfficherCout();
    return true;
  }
  function panneauTr() {
    var est = S.tr.est, dispo = {};
    S.tr.sigDessinee = grisageTr(est);
    if (est && est.ok) est.participants.forEach(function (p) { dispo[p.id] = p; });
    var cases = (S.tr.options ? S.tr.options.participants : Object.keys(LIBELLE_TR).filter(function (k) { return k !== "synthese"; }).map(function (id) { return { id: id, libelle: LIBELLE_TR[id] }; })).map(function (p) {
      var d = dispo[p.id], grise = !!(d && !d.disponible), coche = S.tr.participants.indexOf(p.id) >= 0 && !grise;
      var c = h("input", { type: "checkbox", id: "tr-" + p.id, checked: coche, disabled: grise });
      c.addEventListener("change", function () {
        var i = S.tr.participants.indexOf(p.id);
        if (c.checked && i < 0) S.tr.participants.push(p.id); else if (!c.checked && i >= 0) S.tr.participants.splice(i, 1);
        stocker("tr.participants", JSON.stringify(S.tr.participants)); trEstimer();
      });
      return h("label", { class: "tr-case" + (grise ? " grise" : ""), title: grise ? (d.raison || "indisponible") : "" }, c, " " + p.libelle,
        h("span", { class: "doux", id: "tr-c-" + p.id, texte: texteCoutCase(d, coche) }),
        grise ? h("span", { class: "tr-raison", texte: " — " + (d.raison || "indisponible") }) : null);
    });
    var sans = h("input", { type: "checkbox", id: "tr-sans", checked: !S.tr.synthese });
    sans.addEventListener("change", function () { S.tr.synthese = !sans.checked; trEstimer(); });
    var crit = h("input", { type: "checkbox", id: "tr-critique", checked: S.tr.critique });
    crit.addEventListener("change", function () {
      if (!crit.checked) { S.tr.critique = false; trEstimer(); return; }
      crit.checked = false;                               // on n'active qu'après avoir affiché le surcoût
      trEstimer({ critique: true }).then(function (e2) {
        if (!e2 || !e2.ok) { C.informer("Tour de critique indisponible", (e2 && e2.message) || "Estimation impossible."); return; }
        var base = S.tr.est && S.tr.est.ok ? S.tr.est.total_usd : 0;
        C.confirmer("Activer le tour de critique ?", "Chaque IA relit les réponses des autres et réagit (2e tour).\nCoût estimé avec le tour de critique : " + (e2.total_incomplet ? "au moins " : "") + dollars3(e2.total_usd) +
          " (au lieu de " + dollars3(base) + ", soit +" + dollars3(e2.total_usd - base) + ").\nSeuil d'avertissement : " + dollars3(e2.seuil_usd) + ".", "Activer").then(function (ok) {
          if (ok) { S.tr.critique = true; }
          trEstimer();
        });
      });
    });
    var ligne = h("div", { class: "tr-cout", id: "tr-cout", role: "status" });
    trAfficherCout(ligne);
    var panneau = h("details", { class: "tr-panneau" }, h("summary", { id: "tr-resume", texte: texteResumeTr() }),
      h("div", { class: "tr-cases" }, cases),
      h("div", { class: "tr-options" }, h("label", null, sans, " Sans synthèse"), h("label", null, crit, " Tour de critique (2e tour)")),
      ligne);
    if (S.tr.ouvert) panneau.setAttribute("open", "");
    panneau.addEventListener("toggle", function () { S.tr.ouvert = panneau.open; });      // replié ou non : on s'en souvient
    return panneau;
  }
  function trAfficherCout(el) {
    var e = S.tr.est;
    el = el || document.getElementById("tr-cout"); if (!el) return;
    el.classList.toggle("alerte", !!(e && e.ok && e.depasse));
    if (!e) el.textContent = "Estimation du coût en cours…";
    else if (!e.ok) el.textContent = "⚠ " + e.message + " (aucune IA ne sera appelée)";
    else el.textContent = "Coût estimé : " + (e.total_incomplet ? "au moins " : "") + dollars3(e.total_usd) + " au total" + (e.total_incomplet ? " (tarif inconnu pour au moins une IA)" : "") + (e.depasse ? " — ⚠ au-dessus du seuil de " + dollars3(e.seuil_usd) + " : confirmation demandée." : " (seuil " + dollars3(e.seuil_usd) + ").");
  }
  var minuteurTr = null;
  function trEstimer(opts) {
    opts = opts || {};
    var corps = { participants: S.tr.participants, critique: opts.critique === true ? true : S.tr.critique, synthese: S.tr.synthese,
                  texte: (document.getElementById("saisie") || {}).value || "", conversation: S.conv ? S.conv.id : null };
    var appel = function () {
      return api("POST", "/api/table-ronde/estimation", corps).catch(function (e) { return { ok: false, message: e.message, participants: [], total_usd: 0, depasse: false, seuil_usd: 0 }; });
    };
    if (opts.critique === true) return appel();                       // demande ponctuelle : ne touche pas à l'affichage
    clearTimeout(minuteurTr);
    return new Promise(function (resolve) {
      minuteurTr = setTimeout(function () {
        appel().then(function (e) {
          S.tr.est = e;
          var grises = e.ok ? e.participants.filter(function (p) { return !p.disponible; }).map(function (p) { return p.id; }) : [];
          if (grises.length) S.tr.participants = S.tr.participants.filter(function (x) { return grises.indexOf(x) < 0; });
          if (C.courante() === "salles" && trActive() && !majPanneauTrSurPlace()) redessinerDockEnGardantSaisie();
          resolve(e);
        });
      }, 250);
    });
  }

  function redessinerDockEnGardantSaisie() {
    var t = document.getElementById("saisie");
    var actif = !!t && document.activeElement === t, pos = t ? t.selectionStart : 0;
    if (t && t.dataset.conv === (S.conv ? S.conv.id : "")) S.brouillon = t.value;
    dessinerDock(salleCourante());
    if (actif) { var n = document.getElementById("saisie"); if (n) { n.focus(); try { n.setSelectionRange(pos, pos); } catch (e) { /* ok */ } } }
  }

  function estimer(saisie, s) {
    clearTimeout(minuteurEstimation);
    if (!s) return;
    if (trActive()) { trEstimer(); return; }
    minuteurEstimation = setTimeout(function () {
      api("GET", "/api/salles/" + s.id + "/estimation?longueur=" + saisie.value.length + (S.conv ? "&conversation=" + S.conv.id : "")).then(function (e) { indice("≈ " + court(e.texte).replace(/^≈ /, "")); }).catch(function () {});
    }, 400);
  }
  function pttDebut(e) {
    e.preventDefault();
    var s = salleCourante();
    if (ptt.actif || S.enCours || !s || !s.disponible) return;
    if (!(S.voixOpts && S.voixOpts.disponible)) { C.informer("Voix indisponible", (S.voixOpts && S.voixOpts.raison) || "Aucune voix du nuage n'est disponible (clé OpenAI/xAI absente, mode confidentiel ou plafond atteint)."); return; }
    ptt.actif = true; ptt.finDemandee = false; C.micro.arreterLecture();
    var b = document.getElementById("ptt"); if (b) b.classList.add("rec");
    C.etat("ecoute"); indice("Autorisation du micro…");
    C.micro.demarrer().then(function (r) {
      ptt.enregistrement = r;
      indice("Je vous écoute… relâchez pour envoyer.");
      if (ptt.finDemandee) pttTerminer();
    }).catch(function (err) {
      ptt.actif = false; if (b) b.classList.remove("rec"); C.etat("repos");
      indice(err && err.name === "NotAllowedError" ? "Micro refusé : autorisez-le dans le navigateur." : "Micro indisponible.");
    });
  }
  function pttFin(e) {
    if (e) e.preventDefault();
    if (!ptt.actif) return;
    ptt.actif = false;
    var b = document.getElementById("ptt"); if (b) b.classList.remove("rec");
    if (!ptt.enregistrement) { ptt.finDemandee = true; return; }
    pttTerminer();
  }
  function pttTerminer() {
    var r = ptt.enregistrement; ptt.enregistrement = null; ptt.finDemandee = false;
    if (!r) return;
    r.arreter().then(function (enr) {
      if (enr.duree < 0.6) { indice("Trop court : maintenez le bouton pendant que vous parlez."); C.etat("repos"); return; }
      indice("Transcription…"); C.etat("reflexion");
      return C.micro.transcrire(enr).then(function (texte) {
        if (!texte.trim()) { indice("Je n'ai rien entendu de clair. Réessayez."); C.etat("repos"); return; }
        indice(""); envoyer(texte);
      });
    }).catch(function (err) { indice("⚠ " + err.message); C.etat("repos"); });
  }

  function choisirSalle(id) {
    if (S.enCours) { C.informer("Réponse en cours", "Attendez la fin de la réponse (ou arrêtez-la) avant de changer de salle."); return; }
    S.salle = id; S.conv = null; S.selection = []; S.images = []; S.brouillon = ""; stocker("salle", id); charger();
  }
  function nouvelle() {
    api("POST", "/api/conversations", { salle: S.salle }).then(function (c) { S.convs.unshift({ id: c.id, titre: c.titre, maj: c.maj, prive: false }); return ouvrir(c.id); })
      .catch(function (e) { C.informer("Impossible", e.message); });
  }
  function ouvrir(id) {
    return api("GET", "/api/conversations/" + id).then(function (c) {
      S.conv = c; S.selection = []; S.images = []; dessiner(); defiler();
      if (c.en_cours) reprendreFlux(c.id);
    }).catch(function (e) { C.informer("Impossible d'ouvrir", e.message); });
  }

  // Réglages de la salle Crew : menu de modèles (liste fixe) + « IA sur abonnement dans Crew » (Claude, Codex).
  var AIDE_ABONNEMENT = "Ces IA passent par votre abonnement (limites d'usage) et leurs questions partent dans le nuage. Elles répondent en texte seulement, sans accès à vos fichiers. Jamais utilisées en mode Confidentiel ou Ultra-confidentiel.";
  var NOM_ABONNEMENT = { claude: "Claude", codex: "ChatGPT / Codex" };
  function reglagesCrew(s, m) {
    return api("GET", "/api/crew/autorisations").catch(function (e) { return { disponible: false, message: e.message, autorisations: [] }; }).then(function (aut) {
      var actuel = s.modele || m.defaut, connu = m.modeles.indexOf(actuel) >= 0;
      var options = m.modeles.map(function (id) {
        return { valeur: id, texte: id + (id === m.defaut ? " (par défaut)" : "") + (!connu && id === m.defaut ? " — recommandé pour remplacer" : "") };
      });
      var expl = {}; m.modeles.forEach(function (id) { expl[id] = m.explications[id]; });
      if (!connu) {                                                    // valeur enregistrée hors liste : affichée, jamais supprimée en silence
        options.unshift({ valeur: actuel, texte: actuel + " — inconnue" });
        expl[actuel] = "⚠ « " + actuel + " » n'est pas un modèle connu de Crew (ancienne valeur ou faute de frappe) : Crew répondrait « Modèle inconnu ». Choisissez " + m.defaut + " pour la remplacer.";
      }
      var champs = [{ nom: "modele", label: "Modèle", type: "select", valeur: actuel, options: options, explications: expl }];
      var texte = "La table ronde ne se choisit pas ici : elle a son bouton dans la salle Crew.\n\nIA sur abonnement dans Crew — " + AIDE_ABONNEMENT;
      var avant = {};
      if (aut.disponible) {
        aut.autorisations.forEach(function (a) {
          avant[a.nom] = a;
          champs.push({ nom: "aut_" + a.nom, label: "Autoriser Crew à utiliser " + (NOM_ABONNEMENT[a.nom] || a.nom), type: "checkbox", valeur: a.autorise });
          champs.push({ nom: "lim_" + a.nom, label: "Limite par jour — " + (NOM_ABONNEMENT[a.nom] || a.nom) + " (" + aut.limite_min + " à " + aut.limite_max + ")",
                        type: "number", min: aut.limite_min, max: aut.limite_max, valeur: a.limite_jour,
                        aide: a.utilise_aujourdhui + (a.utilise_aujourdhui > 1 ? " appels utilisés" : " appel utilisé") + " aujourd'hui" });
        });
      } else {
        texte += "\n\n" + (aut.message ? aut.message + " : les autorisations s'afficheront quand Crew sera allumé." : "Autorisations indisponibles pour le moment.");
      }
      return C.formulaire("Réglages : " + s.libelle, texte, champs, "Enregistrer").then(function (v) {
        if (!v) return;
        var changements = [];
        Object.keys(avant).forEach(function (nom) {
          var lim = Number(v["lim_" + nom]), a = avant[nom];
          if (!/^\d+$/.test(String(v["lim_" + nom]).trim()) || lim < aut.limite_min || lim > aut.limite_max) { changements.erreur = "La limite par jour de " + NOM_ABONNEMENT[nom] + " doit être un nombre entier de " + aut.limite_min + " à " + aut.limite_max + "."; return; }
          if (v["aut_" + nom] !== a.autorise || lim !== a.limite_jour) changements.push({ nom: nom, autorise: v["aut_" + nom], limite_jour: lim, active: v["aut_" + nom] && !a.autorise });
        });
        if (changements.erreur) { C.informer("Réglage impossible", changements.erreur); return; }
        // Confirmation seulement pour AUTORISER (désautoriser : sans confirmation). Rien n'est envoyé à Crew sans ce clic sur « Enregistrer ».
        var aConfirmer = changements.filter(function (c) { return c.active; });
        var suite = aConfirmer.length
          ? C.confirmer("Autoriser " + aConfirmer.map(function (c) { return NOM_ABONNEMENT[c.nom]; }).join(" et ") + " dans Crew ?",
              "• Passe par votre abonnement (limites d'usage).\n• Les questions partent dans le nuage ; réponses en texte seulement, sans accès à vos fichiers.\n• Jamais utilisée en mode Confidentiel ou Ultra-confidentiel.", "Autoriser")
          : Promise.resolve(true);
        return suite.then(function (ok) {
          if (!ok) return;
          var chaine = api("PUT", "/api/salles/" + s.id + "/reglage", { modele: v.modele });
          changements.forEach(function (c) {
            chaine = chaine.then(function () { return api("PUT", "/api/crew/autorisations", { nom: c.nom, autorise: c.autorise, limite_jour: c.limite_jour }); });
          });
          return chaine.then(charger).catch(function (e) { C.informer("Réglage impossible", e.message); });
        });
      });
    });
  }

  function reglagesSalle() {
    var s = salleCourante();
    api("GET", "/api/salles/" + s.id + "/modeles").then(function (m) {
      if (m.explications) return reglagesCrew(s, m);            // Crew : menu de 4 choix fixes, avec explication
      var aide = m.modeles.length ? "Modèles proposés : " + m.modeles.slice(0, 25).join(", ") : "Laissez vide pour le modèle par défaut.";
      var champs = [];
      if (s.auths.length > 1) champs.push({ nom: "auth", label: "Connexion", type: "select", valeur: s.auth, options: s.auths.map(function (a) { return { valeur: a.id, texte: a.texte }; }) });
      champs.push({ nom: "modele", label: "Modèle (nom exact)", type: "text", valeur: s.modele });
      return C.formulaire("Réglages : " + s.libelle, aide, champs, "Enregistrer").then(function (v) {
        if (!v) return;
        return api("PUT", "/api/salles/" + s.id + "/reglage", { auth: v.auth, modele: v.modele }).then(charger);
      });
    }).catch(function (e) { C.informer("Réglages impossibles", e.message); });
  }

  // ------------------------------------------------ zone de conversation
  function bulleMessage(m) {
    var estIA = m.role === "assistant";
    var meta = h("div", { class: "meta" }, h("strong", { texte: estIA ? ((S.salles.filter(function (x) { return x.id === m.salle; })[0] || {}).libelle || "IA") : "Vous" }),
      new Date(m.ts * 1000).toLocaleTimeString("fr-CA", { hour: "2-digit", minute: "2-digit" }),
      m.modele ? h("span", { texte: m.modele }) : null,
      m.sensible ? h("span", { class: "badge prive", texte: "privé" }) : null,
      m.interrompu ? h("span", { class: "badge", texte: "interrompu" }) : null,
      estIA && m.cout_usd ? h("span", { texte: "≈ " + m.cout_usd.toFixed(4) + " $" }) : null);
    var corps = h("div");
    if (m.table_ronde && m.table_ronde.reponses) corps.appendChild(grilleDepuisMessage(m.table_ronde)); else rendre(corps, m.texte);
    var b = h("div", { class: "bulle " + (estIA ? "assistant" : "user") + (m.table_ronde ? " tableronde" : "") + (m.erreur ? " erreur" : "") }, meta, corps);
    if ((m.pieces || []).length) b.appendChild(h("div", { class: "vignettes" }, m.pieces.map(function (p) {
      return h("a", { href: "/api/pieces/" + p.id, target: "_blank", rel: "noopener" }, h("img", { src: "/api/pieces/" + p.id, alt: p.nom || "image jointe", title: p.nom || "image jointe", loading: "lazy" }));
    })));
    (m.contexte || []).forEach(function (c) {
      b.appendChild(h("div", { class: "doux", texte: c.type === "tiroir" ? "📎 Tiroir : " + c.titre : (c.chemin ? "📚 Mémoire : " + c.chemin : "📚 Mémoire : " + (c.message || "rien trouvé")) }));
    });
    if (estIA && !m.erreur) {
      b.appendChild(h("div", { class: "actions" },
        h("button", { class: "petit", type: "button", texte: "Copier", onclick: function () { copier(m.texte); } }),
        h("button", { class: "petit", type: "button", texte: "Demander aussi à…", onclick: function () { demanderAussi(m); } }),
        h("button", { class: "petit", type: "button", texte: "Mettre dans le tiroir", onclick: function () { versTiroir(m); } }),
        h("button", { class: "petit", type: "button", title: "Faire examiner cette réponse par une autre IA (second avis automatique)", texte: "Vérifier", onclick: function () { verifier(m); } })));
    }
    return b;
  }

  function zoneChat(s) {
    var c = S.conv;
    var fil = h("div", { class: "fil", id: "fil" }, c.messages.map(bulleMessage));
    if (S.live) fil.appendChild(S.live.bulle);
    var zone = h("div", null,
      h("div", { class: "rangee-titre" }, h("h2", { texte: c.titre }),
        c.prive ? h("span", { class: "badge prive", texte: "contenu privé : IA locales seulement" }) : null,
        h("button", { class: "petit", type: "button", texte: "Renommer", onclick: renommer }),
        h("button", { class: "petit", type: "button", texte: "Supprimer", onclick: supprimer })),
      fil);
    if ((c.en_attente || []).length) zone.appendChild(panneauApprobation(c.en_attente));
    return zone;
  }
  function defiler() { var f = document.getElementById("fil"); if (f && f.lastChild) f.lastChild.scrollIntoView({ block: "nearest" }); }

  function renommer() {
    C.formulaire("Renommer la conversation", "", [{ nom: "titre", label: "Titre", type: "text", valeur: S.conv.titre }], "Renommer").then(function (v) {
      if (!v) return;
      return api("PUT", "/api/conversations/" + S.conv.id, { titre: v.titre }).then(function (r) { S.conv.titre = r.titre; return charger(); });
    }).catch(function (e) { C.informer("Impossible", e.message); });
  }
  function supprimer() {
    C.confirmer("Supprimer cette conversation ?", "« " + S.conv.titre + " » sera effacée définitivement de ce PC. Cette action est irréversible.", "Supprimer", "danger").then(function (ok) {
      if (!ok) return;
      return api("DELETE", "/api/conversations/" + S.conv.id).then(function () { S.conv = null; return charger(); });
    }).catch(function (e) { C.informer("Impossible", e.message); });
  }

  // ------------------------------------------------ envoi et flux
  function envoyer(texteForce) {
    var s = salleCourante(), saisie = document.getElementById("saisie");
    var texte = String(texteForce != null ? texteForce : (saisie ? saisie.value : "")).trim();
    if (!texte || S.enCours || !s || !s.disponible) return;
    var ecr = S.opt.ecriture && s.ecriture;
    var suite = ecr
      ? C.confirmer("Autoriser l'écriture ?", "Codex pourra créer et modifier des fichiers dans l'atelier pour CE message seulement. Continuer ?", "Autoriser")
      : Promise.resolve(true);
    var confirmeTr = false;
    if (trActive()) {
      // Aucune IA payante n'est appelée sans avoir vu le coût : estimation fraîche, puis confirmation si le seuil est dépassé.
      suite = suite.then(function (ok) {
        if (!ok) return false;
        clearTimeout(minuteurTr);
        return api("POST", "/api/table-ronde/estimation", { participants: S.tr.participants, critique: S.tr.critique, synthese: S.tr.synthese, texte: texte, conversation: S.conv ? S.conv.id : null })
          .then(function (e) {
            S.tr.est = e;
            if (!e.ok) { C.informer("Table ronde impossible", e.message + "\nAucune IA n'a été appelée. Les salles individuelles fonctionnent toujours."); return false; }
            if (!e.depasse) return true;
            return C.confirmer("Coût au-dessus du seuil", "Coût estimé : " + (e.total_incomplet ? "au moins " : "") + dollars3(e.total_usd) + " pour ce message, au-dessus du seuil de " + dollars3(e.seuil_usd) + ".\n" +
              e.participants.filter(function (p) { return p.disponible && S.tr.participants.indexOf(p.id) >= 0; }).map(function (p) { return "• " + p.libelle + " : " + (p.cout_estime_usd === null ? "coût inconnu" : "≈ " + dollars3(p.cout_estime_usd)); }).join("\n") + "\n\nEnvoyer quand même ?", "Envoyer", "danger").then(function (ok2) { confirmeTr = ok2; return ok2; });
          });
      });
    }
    suite.then(function (ok) {
      if (!ok) return;
      var pret = S.conv ? Promise.resolve(S.conv) : api("POST", "/api/conversations", { salle: S.salle }).then(function (c) {
        S.conv = c; S.convs.unshift({ id: c.id, titre: c.titre, maj: c.maj, prive: false }); return c;
      });
      return pret.then(function () {
        var corps = { texte: texte, memoire: S.opt.memoire && !!(S.memoire && S.memoire.disponible), tiroir: S.selection.slice(), autoriser_ecriture: ecr };
        if (S.images.length) { corps.images = S.images.map(function (im) { return im.id; }); corps.noms_images = {}; S.images.forEach(function (im) { corps.noms_images[im.id] = im.nom; }); }
        if (trActive()) { if (window.innerWidth <= 720) S.tr.ouvert = false; }      // téléphone : on libère la place pour les réponses
        if (trActive()) corps.table_ronde = { participants: S.tr.participants.slice(), critique: S.tr.critique, synthese: S.tr.synthese, confirme_depassement: !!confirmeTr };
        S.brouillon = ""; if (saisie) saisie.value = "";
        S.opt.ecriture = false;
        S.conv.messages.push({ id: "tmp", role: "user", texte: texte, ts: Date.now() / 1000, contexte: [] });
        demarrerLive();
        lancerFlux("/api/conversations/" + S.conv.id + "/messages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
        S.selection = []; S.images = [];
      });
    }).catch(function (e) { C.informer("Envoi impossible", e.message); });
  }
  function reprendreFlux(cid) { demarrerLive(); lancerFlux("/api/conversations/" + cid + "/flux?depuis=0", { method: "GET" }); }

  // ------------------------------------------------ table ronde : colonnes par IA
  function grilleTr() { return h("div", { class: "tr-grille" }); }
  function colonneTr(grille, id, libelle) {
    var existante = grille.querySelector('[data-p="' + id + '"]');
    if (existante) return existante._refs;
    var badge = h("span", { class: "badge tr-statut" }), meta = h("span", { class: "doux tr-meta" });
    var corps = h("div", { class: "tr-corps" }), corps2 = h("div", { class: "tr-corps" });
    var tour2 = h("div", { class: "tr-tour2", hidden: true }, h("strong", { texte: "Tour 2 : critique des autres réponses" }), corps2);
    var d = h("details", { class: "tr-col" + (id === "synthese" ? " synthese" : ""), open: "", "data-p": id },
      h("summary", null, h("strong", { texte: libelle }), " ", badge, " ", meta), corps, tour2);
    d._refs = { el: d, badge: badge, meta: meta, corps: corps, corps2: corps2, tour2: tour2, texte1: "", texte2: "" };
    if (id === "synthese") grille.appendChild(d);
    else { var syn = grille.querySelector('[data-p="synthese"]'); if (syn) grille.insertBefore(d, syn); else grille.appendChild(d); }   // la synthèse reste en dernier
    return d._refs;
  }
  function majMetaTr(r, cout, duree) {
    var t = [];
    if (cout !== null && cout !== undefined) t.push(cout === 0 ? "gratuit" : dollars3(cout)); else t.push("coût inconnu");
    if (duree !== null && duree !== undefined) t.push(Number(duree).toLocaleString("fr-CA", { maximumFractionDigits: 1 }) + " s");
    r.meta.textContent = t.join(" · ");
  }
  function appliquerTr(grille, e) {
    var r = colonneTr(grille, e.participant, LIBELLE_TR[e.participant] || e.participant);
    if (e.t === "tr_debut") {
      if (e.tour === 2) { r.tour2.hidden = false; r.badge.textContent = "tour 2 en cours…"; }
      else if (!r.badge.textContent) r.badge.textContent = "en cours…";
    } else if (e.t === "tr_delta") {
      if (e.tour === 2) { r.tour2.hidden = false; r.texte2 += e.texte; rendre(r.corps2, r.texte2); }
      else { r.texte1 += e.texte; rendre(r.corps, r.texte1); }
      if (!r.badge.textContent) { r.badge.textContent = "en cours…"; }
    } else if (e.t === "tr_fin") {
      if (e.tour === 1 || !r.badge.dataset.fini) { r.badge.textContent = "terminé"; r.badge.dataset.fini = "1"; }
      majMetaTr(r, e.cout_usd, e.duree_s);
    } else if (e.t === "tr_exclu") {
      var raison = String(e.raison || "");
      r.badge.textContent = "exclue"; r.badge.classList.add("prive");
      rendre(r.corps, /^exclue/i.test(raison) ? raison : "exclue : " + raison);
    } else if (e.t === "tr_erreur") {
      r.badge.textContent = "échec"; r.badge.classList.add("prive");
      rendre(r.corps, "⚠ Cette IA a échoué : " + (e.message || "erreur") + " (les autres continuent).");
    }
    return r;
  }
  function notesTr(grille, notes) {                      // extraits de la mémoire de Crew utilisés (indiqués par Crew sur la ligne finale)
    if (!notes || !notes.length || grille.querySelector(".tr-notes")) return;
    grille.appendChild(h("p", { class: "doux tr-notes", texte: "Notes de la mémoire utilisées par Crew : " + notes.join(", ") }));
  }
  function trEvenement(e) {
    if (!S.live) return;
    if (e.t === "tr_total") { if (S.live.grille) notesTr(S.live.grille, e.notes); return; }
    if (!S.live.grille) { S.live.grille = grilleTr(); vider(S.live.corps); S.live.corps.appendChild(S.live.grille); S.live.meta.lastChild.textContent = "table ronde en cours…"; }
    appliquerTr(S.live.grille, e);
    var f = document.getElementById("fil"); if (f && f.lastChild) f.lastChild.scrollIntoView({ block: "nearest" });
  }
  // Un message enregistré : mêmes colonnes, reconstruites depuis les réponses stockées.
  function grilleDepuisMessage(tr) {
    var g = grilleTr();
    tr.reponses.forEach(function (x) {
      var texteX = x.texte || "";
      var r = colonneTr(g, x.participant, x.libelle || LIBELLE_TR[x.participant] || x.participant);
      if (x.statut === "exclu") { appliquerTr(g, { t: "tr_exclu", participant: x.participant, tour: x.tour, raison: x.raison }); return; }
      if (x.statut === "erreur") { appliquerTr(g, { t: "tr_erreur", participant: x.participant, tour: x.tour, message: x.raison }); return; }
      appliquerTr(g, { t: "tr_delta", participant: x.participant, tour: x.tour, texte: texteX });
      appliquerTr(g, { t: "tr_fin", participant: x.participant, tour: x.tour, cout_usd: x.cout_usd, duree_s: x.duree_s });
    });
    notesTr(g, tr.notes);
    return g;
  }

  function demarrerLive() {
    var corps = h("div"); var meta = h("div", { class: "meta" }, h("strong", { texte: (salleCourante() || {}).libelle || "IA" }), h("span", { texte: "réponse en cours…" }));
    S.live = { texte: "", corps: corps, meta: meta, bulle: h("div", { class: "bulle assistant" }, meta, corps), demandes: null, cout: "", erreur: "" };
    S.enCours = true; C.enCours = true; C.etat("reflexion"); dessiner(); defiler();
  }
  var rafraichi = false;
  function afficherLive() {
    if (rafraichi || !S.live) return; rafraichi = true;
    requestAnimationFrame(function () { rafraichi = false; if (S.live) { rendre(S.live.corps, S.live.texte); defiler(); } });
  }
  function lancerFlux(url, opts) {
    var cid = S.conv.id;
    lireFlux(url, opts, function (e) {
      if (!S.live) return;
      if (e.t === "delta") { S.live.texte += e.texte; afficherLive(); }
      else if (e.t === "erreur") { S.live.erreur = e.message; }
      else if (e.t === "cout") { S.live.cout = e.texte; }
      else if (e.t === "fin") { S.dernierMsg = e.message_id; }
      else if (e.t.indexOf("tr_") === 0) { trEvenement(e); }
    }).catch(function (e) {
      if (e.message !== "session" && S.live) S.live.erreur = S.live.erreur || ("Connexion interrompue : " + e.message + ". La réponse continue peut-être sur le PC : rouvrez la conversation.");
    }).then(function () {
      S.live = null; S.enCours = false;
      return api("GET", "/api/conversations/" + cid).then(function (c) {
        if (S.conv && S.conv.id === cid) { S.conv = c; }
        if (c.en_cours) { S.enCours = false; }
      }).catch(function () {});
    }).then(function () { C.enCours = false; C.etat("repos"); return charger(); }).then(function () {
      defiler();
      if (S.opt.lire && S.dernierMsg && S.conv && S.conv.id === cid) {
        var id = S.dernierMsg; S.dernierMsg = null;
        C.micro.lire(cid, id).catch(function (err) { indice("🔊 " + err.message); });
      }
    });
    // les erreurs de flux sont aussi enregistrées dans la conversation par le serveur : on les relit ci-dessus
  }
  function arreter() { if (S.conv) api("POST", "/api/conversations/" + S.conv.id + "/arreter", {}).catch(function () {}); }

  document.addEventListener("visibilitychange", function () {
    // Téléphone : au retour, si le flux est mort mais que le PC répond encore, on se raccroche.
    if (document.hidden || C.courante() !== "salles" || !S.conv || S.enCours) return;
    api("GET", "/api/conversations/" + S.conv.id).then(function (c) {
      S.conv = c; dessiner();
      if (c.en_cours) reprendreFlux(c.id);
    }).catch(function () {});
  });

  // ------------------------------------------------ approbations
  function panneauApprobation(demandes) {
    var choix = {};
    demandes.forEach(function (d) { choix[d.id] = d.motif ? "approuver" : "refuser"; });
    var lignes = demandes.map(function (d) {
      var etat = h("span", { class: "badge", texte: choix[d.id] === "approuver" ? "à approuver" : "refusé" });
      var bo = h("button", { class: "petit", type: "button", texte: "Approuver", disabled: !d.motif, onclick: function () { choix[d.id] = "approuver"; etat.textContent = "à approuver"; } });
      var br = h("button", { class: "petit", type: "button", texte: "Refuser", onclick: function () { choix[d.id] = "refuser"; etat.textContent = "refusé"; } });
      return h("div", { class: "ligne" }, h("span", { class: "texte", texte: d.resume + (d.motif ? "" : " — trop complexe pour être approuvé ici : faites-le vous-même") }), bo, br, etat);
    });
    return h("div", { class: "demande-approbation", role: "alert" },
      h("strong", { texte: "Claude demande votre approbation" }), h("div", { class: "doux", texte: "Rien n'est exécuté sans votre accord. Chaque approbation vaut pour cette demande seulement." }), lignes,
      h("button", { class: "bouton principal", type: "button", texte: "Valider mes choix", onclick: function () {
        demarrerLive();
        lancerFlux("/api/conversations/" + S.conv.id + "/approbation", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decisions: choix }) });
      } }));
  }

  // ------------------------------------------------ relais, tiroir
  function demanderAussi(m) {
    var autres = S.salles.filter(function (x) { return x.id !== S.salle && x.disponible; });
    if (!autres.length) { C.informer("Aucune autre IA disponible", "Les autres salles sont indisponibles (mode, clé, plafond ou service éteint) : voyez les pastilles grisées."); return; }
    C.formulaire("Demander aussi à…", "Une nouvelle conversation s'ouvre dans l'autre salle avec un texte prêt à envoyer (vous pouvez le modifier).", [
      { nom: "vers", label: "IA", type: "select", valeur: autres[0].id, options: autres.map(function (x) { return { valeur: x.id, texte: x.libelle + " — " + x.estimation }; }) },
      { nom: "portee", label: "Que transmettre ?", type: "select", valeur: "reponse", options: [{ valeur: "reponse", texte: "La question et cette réponse (deuxième avis)" }, { valeur: "question", texte: "Seulement la question" }] }], "Ouvrir").then(function (v) {
      if (!v) return;
      return api("POST", "/api/conversations/" + S.conv.id + "/relais", { vers: v.vers, message_id: m.id, portee: v.portee }).then(function (r) {
        S.salle = r.salle; stocker("salle", r.salle); S.brouillon = r.brouillon;
        return charger().then(function () { return ouvrir(r.conversation); }).then(function () { S.brouillon = r.brouillon; dessiner(true); });
      });
    }).catch(function (e) { C.informer("Transmission impossible", e.message); });
  }
  var LIBELLE_STATUT = { confirmee: "✔ confirmée", douteuse: "? douteuse", fausse: "✘ fausse", inverifiable: "… invérifiable" };
  var LIBELLE_VERDICT = { fiable: "Plutôt fiable", a_verifier: "À vérifier", douteux: "Douteux" };
  function verifier(m) {
    var autres = S.salles.filter(function (x) { return x.id !== S.salle && x.disponible; });
    if (!autres.length) { C.informer("Aucune autre IA disponible", "Une vérification doit être faite par une IA différente de celle qui a répondu."); return; }
    C.formulaire("Vérifier cette réponse", "Une autre IA examine la réponse et note chaque affirmation. C'est un second avis automatique, pas une preuve : elle peut se tromper aussi. Cela coûte une demande.", [
      { nom: "salle", label: "IA vérificatrice", type: "select", valeur: autres[0].id, options: autres.map(function (x) { return { valeur: x.id, texte: x.libelle + " — " + x.estimation }; }) }], "Vérifier").then(function (v) {
      if (!v) return;
      C.informer("Vérification en cours…", "Patientez (jusqu'à quelques dizaines de secondes).");
      return api("POST", "/api/conversations/" + S.conv.id + "/verifier", { message_id: m.id, salle: v.salle }).then(function (r) {
        var res = r.resultat, texte;
        if (!res) texte = "Le vérificateur n'a pas répondu dans le format attendu. Sa réponse brute :\n\n" + r.brut;
        else texte = "Verdict : " + LIBELLE_VERDICT[res.verdict] + "\n" + res.resume + "\n\n" + res.affirmations.map(function (a) { return LIBELLE_STATUT[a.statut] + " — " + a.texte + (a.raison ? "\n     " + a.raison : ""); }).join("\n");
        C.informer("Vérification par " + ((S.salles.filter(function (x) { return x.id === r.salle; })[0] || {}).libelle || r.salle), texte + "\n\n(Second avis automatique : à recouper avec une source.)");
      });
    }).catch(function (e) { C.informer("Vérification impossible", e.message); });
  }

  function versTiroir(m) {
    C.formulaire("Mettre dans le tiroir", "Le tiroir est partagé entre toutes les salles.", [
      { nom: "titre", label: "Titre", type: "text", valeur: m.texte.slice(0, 60) },
      { nom: "zone", label: "Zone", type: "select", valeur: "prive", options: [{ valeur: "prive", texte: "Privé : jamais envoyé à une IA du nuage" }, { valeur: "partageable", texte: "Partageable : peut être envoyé aux IA du nuage" }] }], "Enregistrer").then(function (v) {
      if (!v) return;
      return api("POST", "/api/tiroir", { titre: v.titre, texte: m.texte, zone: v.zone, origine: m.salle || "" });
    }).catch(function (e) { C.informer("Impossible", e.message); });
  }
  // ------------------------------------------------ pièces jointes : fichiers texte (rangés dans le tiroir) et images (collées ou choisies)
  var TEXTES_OK = /\.(txt|md|markdown|csv|tsv|json|log|py|js|ts|html|css|xml|yaml|yml|ini|toml|sql|sh|bat|ps1|cfg|conf)$/i;
  var MAX_IMAGES = 4;
  function boutonJoindre(pret) {
    return h("button", { class: "rond joindre", id: "bouton-joindre", type: "button", title: "Joindre un fichier texte ou une image (vous pouvez aussi coller une image)", "aria-label": "Joindre un fichier ou une image",
      texte: "📎", disabled: !pret || S.enCours, onclick: function () { var e = document.getElementById("fichier-joint"); if (e) e.click(); } });
  }
  function rangeePieces() {
    if (!S.selection.length && !S.images.length) return null;
    var puces = [];
    S.selection.forEach(function (id) {
      puces.push(h("span", { class: "piece" }, "📄 " + (S.titres[id] || "élément du tiroir"),
        h("button", { class: "retirer", type: "button", "aria-label": "Retirer cet élément", texte: "✕", onclick: function () { S.selection = S.selection.filter(function (x) { return x !== id; }); redessinerDockEnGardantSaisie(); } })));
    });
    S.images.forEach(function (im) {
      puces.push(h("span", { class: "piece image" }, h("img", { src: im.url, alt: im.nom, title: im.nom }),
        h("button", { class: "retirer", type: "button", "aria-label": "Retirer cette image", texte: "✕", onclick: function () {
          S.images = S.images.filter(function (x) { return x.id !== im.id; }); api("DELETE", "/api/pieces/" + im.id).catch(function () {}); redessinerDockEnGardantSaisie(); } })));
    });
    return h("div", { class: "pieces-jointes", id: "pieces-jointes", "aria-label": "Pièces jointes" }, puces);
  }
  function blobEnBase64(blob) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () { resolve(String(r.result).split(",")[1] || ""); };
      r.onerror = function () { reject(new Error("Lecture du fichier impossible.")); };
      r.readAsDataURL(blob);
    });
  }
  // Réduit l'image (1600 px au plus) : plus léger à envoyer, et les données cachées (lieu, appareil…) disparaissent.
  function reduireImage(fichier) {
    // createImageBitmap (et non une image « blob: », que la politique de sécurité de la page refuse) ; un nouveau dessin ne garde aucune donnée cachée.
    if (!window.createImageBitmap) return Promise.reject(new Error("Ce navigateur ne sait pas lire les images collées."));
    return createImageBitmap(fichier).then(function (bmp) {
      var echelle = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
      if (echelle === 1 && fichier.size <= 1500000 && /^image\/(png|jpeg|webp)$/.test(fichier.type)) { bmp.close(); return fichier; }
      var c = document.createElement("canvas"); c.width = Math.max(1, Math.round(bmp.width * echelle)); c.height = Math.max(1, Math.round(bmp.height * echelle));
      var g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(bmp, 0, 0, c.width, c.height); bmp.close();
      return new Promise(function (resolve, reject) { c.toBlob(function (blob) { blob ? resolve(blob) : reject(new Error("Image illisible.")); }, "image/jpeg", 0.88); });
    }, function () { throw new Error("Ce fichier n'est pas une image lisible."); });
  }
  function ajouterImage(fichier) {
    var s = salleCourante();
    if (!s || !s.images) { C.informer("Cette salle ne lit pas les images", (s && s.raison_images) || "Choisissez une salle qui lit les images."); return Promise.resolve(); }
    if (S.images.length >= MAX_IMAGES) { C.informer("Trop d'images", "Quatre images au plus par message."); return Promise.resolve(); }
    return reduireImage(fichier).then(function (blob) {
      return blobEnBase64(blob).then(function (b64) { return api("POST", "/api/pieces", { nom: fichier.name || "image collée", donnees: b64 }); });
    }).then(function (e) {
      S.images.push({ id: e.id, nom: e.nom, type: e.type, url: "/api/pieces/" + e.id });
    });
  }
  function ajouterTexte(fichier) {
    if (fichier.size > 200000) { C.informer("Fichier trop gros", fichier.name + " dépasse 200 Ko : coupez-le en morceaux."); return Promise.resolve(); }
    return fichier.text().then(function (texte) {
      if (texte.length > 20000) { C.informer("Texte trop long", fichier.name + " fait " + texte.length + " caractères (maximum 20 000) : coupez-le en morceaux."); return; }
      if (texte.indexOf("\u0000") >= 0) { C.informer("Fichier non pris en charge", fichier.name + " n'est pas un fichier texte."); return; }
      var nuage = !(salleCourante() || {}).locale;
      return C.formulaire("Joindre « " + fichier.name + " »", "Le fichier est d'abord rangé dans le tiroir, puis joint à votre prochain message. En zone « privé », il ne peut jamais être envoyé à une IA du nuage.",
        [{ nom: "titre", label: "Titre", type: "text", valeur: fichier.name },
         { nom: "zone", label: "Zone", type: "select", valeur: "prive", options: [{ valeur: "prive", texte: "Privé : jamais envoyé à une IA du nuage" }, { valeur: "partageable", texte: "Partageable : peut être envoyé aux IA du nuage" }] }], "Ranger et joindre").then(function (v) {
        if (!v) return;
        return api("POST", "/api/tiroir", { titre: v.titre || fichier.name, texte: texte, zone: v.zone, origine: "fichier" }).then(function (e) {
          S.titres[e.id] = e.titre;
          if (nuage && v.zone !== "partageable") { C.informer("Rangé dans le tiroir, pas joint", "« " + e.titre + " » est privé : cette IA est dans le nuage. Changez sa zone dans la page Tiroir, ou choisissez une IA locale."); return; }
          if (S.selection.indexOf(e.id) < 0) S.selection.push(e.id);
        });
      });
    });
  }
  function joindre(fichiers) {
    var suite = Promise.resolve();
    fichiers.forEach(function (f) {
      suite = suite.then(function () {
        if (/^image\//.test(f.type)) return ajouterImage(f);
        if (TEXTES_OK.test(f.name) || /^text\//.test(f.type)) return ajouterTexte(f);
        C.informer("Fichier non pris en charge", (f.name || "Ce fichier") + " : seuls les fichiers texte ou code et les images sont acceptés (les PDF et documents ne sont pas lus pour l'instant).");
      });
    });
    suite.then(function () { redessinerDockEnGardantSaisie(); }).catch(function (e) { if (e.message !== "session") C.informer("Pièce jointe impossible", e.message); redessinerDockEnGardantSaisie(); });
  }

  function choisirTiroir() {
    api("GET", "/api/tiroir").then(function (d) {
      if (!d.elements.length) return C.informer("Tiroir vide", "Ajoutez des éléments dans la page Tiroir, ou depuis une réponse (« Mettre dans le tiroir »).");
      var nuage = !salleCourante().locale;
      var champs = d.elements.slice(0, 40).map(function (e) {
        var interdit = nuage && e.zone !== "partageable";
        return { nom: e.id, type: "checkbox", valeur: S.selection.indexOf(e.id) >= 0 && !interdit, label: e.titre + " (" + e.zone + ", " + e.taille + " car.)" + (interdit ? " — refusé : privé, IA du nuage" : "") };
      });
      return C.formulaire("Joindre des éléments du tiroir", "Ils sont envoyés à l'IA comme des données, avec votre prochain message.", champs, "Joindre").then(function (v) {
        if (!v) return;
        S.selection = Object.keys(v).filter(function (k) { return v[k]; });
        d.elements.forEach(function (e) { S.titres[e.id] = e.titre; });
        dessiner();
      });
    }).catch(function (e) { C.informer("Impossible", e.message); });
  }

  // ------------------------------------------------ page Tiroir
  function pageTiroir() {
    var zone = h("div"); C.page.appendChild(zone); chargerTiroir(zone);
  }
  function chargerTiroir(zone) {
    Promise.all([api("GET", "/api/tiroir"), api("GET", "/api/salles")]).then(function (r) { dessinerTiroir(zone, r[0].elements, r[1].memoire); })
      .catch(function (e) { if (e.message !== "session") { vider(zone); zone.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); } });
  }
  function dessinerTiroir(zone, elements, memoire) {
    vider(zone);
    zone.appendChild(h("div", { class: "carte" }, h("div", { class: "rangee-titre" }, h("h2", { texte: "Tiroir (" + elements.length + ")" }),
      h("button", { class: "bouton principal", type: "button", texte: "Ajouter un texte", onclick: function () {
        C.formulaire("Ajouter au tiroir", "", [{ nom: "titre", label: "Titre", type: "text" }, { nom: "texte", label: "Texte", type: "textarea" },
          { nom: "zone", label: "Zone", type: "select", valeur: "prive", options: [{ valeur: "prive", texte: "Privé" }, { valeur: "partageable", texte: "Partageable" }] }], "Ajouter").then(function (v) {
          if (!v) return;
          return api("POST", "/api/tiroir", { titre: v.titre, texte: v.texte, zone: v.zone }).then(function () { chargerTiroir(zone); });
        }).catch(function (e) { C.informer("Impossible", e.message); });
      } })),
      h("p", { class: "doux", texte: "Bibliothèque partagée entre toutes les salles. Un élément « privé » n'est jamais envoyé à une IA du nuage." }),
      elements.length ? h("table", { class: "tab" }, h("tbody", null, elements.map(function (e) {
        return h("tr", null, h("td", null, h("strong", { texte: e.titre }), h("div", { class: "msg", texte: (e.origine ? e.origine + " · " : "") + e.taille + " caractères" })),
          h("td", null, h("button", { class: "badge " + e.zone, type: "button", title: "Changer la zone", texte: e.zone === "prive" ? "privé" : "partageable", onclick: function () { changerZone(zone, e); } })),
          h("td", null, h("button", { class: "petit", type: "button", texte: "Voir", onclick: function () {
            api("GET", "/api/tiroir/" + e.id).then(function (x) { C.informer(x.titre, x.texte); });
          } }), " ", h("button", { class: "petit", type: "button", texte: "Supprimer", onclick: function () {
            C.confirmer("Supprimer « " + e.titre + " » ?", "Suppression définitive.", "Supprimer", "danger").then(function (ok) {
              if (ok) api("DELETE", "/api/tiroir/" + e.id).then(function () { chargerTiroir(zone); });
            });
          } })));
      }))) : h("p", { class: "doux", texte: "Le tiroir est vide." })));
    // mémoire
    var res = h("div");
    var q = h("input", { type: "search", id: "q-memoire", placeholder: "Chercher dans ma bibliothèque…" });
    var carteMem = h("div", { class: "carte" }, h("h2", { texte: "Mémoire (bibliothèque de documents)" }),
      memoire && memoire.disponible
        ? h("p", { class: "doux", texte: memoire.fichiers + " fichiers, " + memoire.morceaux + " morceaux (privé : " + ((memoire.par_zone || {}).prive || 0) + ", partageable : " + ((memoire.par_zone || {}).partageable || 0) + "). Dernière indexation : " + (memoire.derniere_indexation || "?") })
        : h("p", { class: "doux", texte: (memoire && memoire.message) || "Indisponible." }));
    if (memoire && memoire.disponible) {
      var f = h("form", null, q, h("button", { class: "bouton", type: "submit", texte: "Chercher" }), res);
      f.addEventListener("submit", function (ev) {
        ev.preventDefault(); vider(res);
        api("POST", "/api/memoire/chercher", { question: q.value }).then(function (r) {
          if (!r.passages.length) res.appendChild(h("p", { class: "doux", texte: r.message || "Aucun résultat." }));
          r.passages.forEach(function (p) {
            res.appendChild(h("div", { class: "bulle" }, h("div", { class: "meta" }, h("strong", { texte: p.chemin }), h("span", { class: "badge " + (p.zone === "partageable" ? "partageable" : "prive"), texte: p.zone || "?" }), p.score != null ? h("span", { texte: "score " + p.score }) : null), h("p", { texte: p.texte })));
          });
        }).catch(function (e) { res.appendChild(h("p", { class: "doux", texte: e.message })); });
      });
      carteMem.appendChild(f);
    }
    zone.appendChild(carteMem);
  }
  function changerZone(zone, e) {
    var vers = e.zone === "prive" ? "partageable" : "prive";
    var msg = vers === "partageable" ? "« " + e.titre + " » pourra être envoyé aux IA du nuage (Claude, ChatGPT, Gemini, Grok, DeepSeek)." : "« " + e.titre + " » ne sera plus envoyé aux IA du nuage.";
    C.confirmer("Passer en « " + vers + " » ?", msg, "Confirmer", vers === "partageable" ? "danger" : "principal").then(function (ok) {
      if (ok) return api("PUT", "/api/tiroir/" + e.id, { zone: vers }).then(function () { chargerTiroir(zone); });
    }).catch(function (x) { C.informer("Impossible", x.message); });
  }

  // Départements : ouvre une nouvelle conversation dans la salle voulue, avec le texte prêt à compléter.
  C.demarrerDans = function (salle, titre, brouillon, memoire) {
    return api("POST", "/api/conversations", { salle: salle, titre: titre }).then(function (c) {
      S.salle = salle; stocker("salle", salle); S.conv = null; S.selection = []; S.images = []; S.brouillon = brouillon || "";
      S.pendingConv = c.id; S.memoireInitiale = !!memoire;
      C.aller("salles");
    });
  };
  C.lireFlux = lireFlux;
  C.rendre = rendre;
  // Si le fil était en bas, il le reste quand le bas d'écran grandit ou rétrécit (nouvelle ligne de saisie, panneau…) : rien ne « saute ».
  (function () {
    var zone = C.page, enBas = true;
    zone.addEventListener("scroll", function () { enBas = zone.scrollHeight - zone.scrollTop - zone.clientHeight < 48; }, { passive: true });
    if (window.ResizeObserver) new ResizeObserver(function () {
      if (C.courante() === "salles" && enBas) zone.scrollTop = zone.scrollHeight;
    }).observe(zone);
  })();
  C.pages.salles = pageSalles;
  C.pages.tiroir = pageTiroir;
})();
