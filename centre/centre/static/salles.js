"use strict";
/* Pages « Salles » et « Tiroir ». Les textes venant des IA sont affichés comme du texte, jamais comme du HTML. */
(function () {
  var C = window.Centre, h = C.h, vider = C.vider, api = C.api;
  var S = { salles: [], politique: null, memoire: null, salle: null, convs: [], conv: null, actives: [], selection: [],
            brouillon: "", enCours: false, live: null };
  var racine = null;

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
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (d) { throw new Error(d.erreur || ("Erreur " + r.status)); });
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
    charger().then(function () { if (S.conv == null) dessiner(); });
  }

  function charger() {
    return Promise.all([api("GET", "/api/salles"), api("GET", "/api/conversations?salle=" + encodeURIComponent(S.salle || "crew"))]).then(function (r) {
      S.salles = r[0].salles; S.politique = r[0].politique; S.memoire = r[0].memoire; S.actives = r[1].actives; S.convs = r[1].conversations;
      dessiner();
    }).catch(function (e) { if (e.message !== "session") { vider(racine); racine.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); } });
  }

  function salleCourante() { return S.salles.filter(function (s) { return s.id === S.salle; })[0]; }

  function dessiner(sansCapture) {
    if (!racine || C.courante() !== "salles") return;
    var garde = document.getElementById("saisie");
    if (!sansCapture && garde && S.conv && garde.dataset.conv === S.conv.id) S.brouillon = garde.value;
    vider(racine);
    var s = salleCourante();
    // bandeau de politique
    if (S.politique && !S.politique.nuage) racine.appendChild(h("div", { class: "bandeau", role: "status" }, h("strong", { texte: "Mode " + S.politique.libelle + " : " }), S.politique.message));
    // pastilles de salles
    racine.appendChild(h("div", { class: "chips", role: "tablist" }, S.salles.map(function (x) {
      var code = x.disponible ? "actif" : "arrete";
      return h("button", { class: "chip" + (x.disponible ? "" : " indispo"), type: "button", role: "tab", "aria-pressed": x.id === S.salle ? "true" : "false",
        title: x.disponible ? x.description : x.raison, onclick: function () { choisirSalle(x.id); } },
        h("span", { class: "voyant v-" + code, "aria-hidden": "true" }), x.libelle);
    })));
    if (!s) return;
    if (!s.disponible) racine.appendChild(h("div", { class: "bandeau erreur", role: "status", texte: s.libelle + " : " + s.raison }));
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
    if (window.innerWidth > 900 || !S.conv) details.setAttribute("open", "");
    racine.appendChild(details);
    if (S.conv) racine.appendChild(zoneChat(s));
    else racine.appendChild(h("p", { class: "doux", texte: "Choisissez une conversation, ou démarrez-en une nouvelle." }));
  }

  function choisirSalle(id) {
    if (S.enCours) { C.informer("Réponse en cours", "Attendez la fin de la réponse (ou arrêtez-la) avant de changer de salle."); return; }
    S.salle = id; S.conv = null; S.selection = []; S.brouillon = ""; stocker("salle", id); charger();
  }
  function nouvelle() {
    api("POST", "/api/conversations", { salle: S.salle }).then(function (c) { S.convs.unshift({ id: c.id, titre: c.titre, maj: c.maj, prive: false }); return ouvrir(c.id); })
      .catch(function (e) { C.informer("Impossible", e.message); });
  }
  function ouvrir(id) {
    return api("GET", "/api/conversations/" + id).then(function (c) {
      S.conv = c; S.selection = []; dessiner(); defiler();
      if (c.en_cours) reprendreFlux(c.id);
    }).catch(function (e) { C.informer("Impossible d'ouvrir", e.message); });
  }

  function reglagesSalle() {
    var s = salleCourante();
    api("GET", "/api/salles/" + s.id + "/modeles").then(function (m) {
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
    var corps = h("div"); rendre(corps, m.texte);
    var b = h("div", { class: "bulle " + (estIA ? "assistant" : "user") + (m.erreur ? " erreur" : "") }, meta, corps);
    (m.contexte || []).forEach(function (c) {
      b.appendChild(h("div", { class: "doux", texte: c.type === "tiroir" ? "📎 Tiroir : " + c.titre : (c.chemin ? "📚 Mémoire : " + c.chemin : "📚 Mémoire : " + (c.message || "rien trouvé")) }));
    });
    if (estIA && !m.erreur) {
      b.appendChild(h("div", { class: "actions" },
        h("button", { class: "petit", type: "button", texte: "Copier", onclick: function () { copier(m.texte); } }),
        h("button", { class: "petit", type: "button", texte: "Demander aussi à…", onclick: function () { demanderAussi(m); } }),
        h("button", { class: "petit", type: "button", texte: "Mettre dans le tiroir", onclick: function () { versTiroir(m); } })));
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
    var saisie = h("textarea", { id: "saisie", rows: "3", placeholder: "Votre message (Ctrl+Entrée pour envoyer)", disabled: !s.disponible || S.enCours });
    saisie.value = S.brouillon || ""; saisie.dataset.conv = c.id;
    saisie.addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); envoyer(); } });
    var estimation = h("span", { class: "doux", id: "estimation", texte: s.estimation || "" });
    var memoire = h("input", { type: "checkbox", id: "opt-memoire", disabled: !(S.memoire && S.memoire.disponible) });
    var ecriture = s.ecriture ? h("input", { type: "checkbox", id: "opt-ecriture" }) : null;
    var options = h("div", { class: "options" },
      h("label", null, memoire, " Utiliser la mémoire", (S.memoire && S.memoire.disponible) ? "" : " (indisponible)"),
      h("button", { class: "petit", type: "button", texte: S.selection.length ? "📎 Tiroir (" + S.selection.length + ")" : "📎 Tiroir", onclick: choisirTiroir }),
      ecriture ? h("label", null, ecriture, " Autoriser l'écriture dans l'atelier (ce message)") : null,
      estimation);
    var envoi = h("button", { class: "bouton principal", id: "bouton-envoyer", type: "button", texte: "Envoyer", disabled: !s.disponible || S.enCours, onclick: envoyer });
    var stop = h("button", { class: "bouton danger" + (S.enCours ? "" : " cache"), id: "bouton-stop", type: "button", texte: "Arrêter", onclick: arreter });
    zone.appendChild(h("div", { class: "barre-envoi" }, saisie, options, h("div", { class: "boutons" }, envoi, stop)));
    var minuteur = null;
    saisie.addEventListener("input", function () {
      clearTimeout(minuteur);
      minuteur = setTimeout(function () {
        api("GET", "/api/salles/" + s.id + "/estimation?longueur=" + saisie.value.length + "&conversation=" + c.id).then(function (e) { estimation.textContent = "Coût estimé : " + e.texte; }).catch(function () {});
      }, 400);
    });
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
  function envoyer() {
    var s = salleCourante(), saisie = document.getElementById("saisie");
    var texte = saisie.value.trim();
    if (!texte || S.enCours || !s.disponible) return;
    var ecr = document.getElementById("opt-ecriture");
    var suite = (ecr && ecr.checked)
      ? C.confirmer("Autoriser l'écriture ?", "Codex pourra créer et modifier des fichiers dans l'atelier pour CE message seulement. Continuer ?", "Autoriser")
      : Promise.resolve(true);
    suite.then(function (ok) {
      if (!ok) return;
      var corps = { texte: texte, memoire: document.getElementById("opt-memoire").checked, tiroir: S.selection.slice(), autoriser_ecriture: !!(ecr && ecr.checked) };
      S.brouillon = ""; saisie.value = "";
      S.conv.messages.push({ id: "tmp", role: "user", texte: texte, ts: Date.now() / 1000, contexte: [] });
      demarrerLive();
      lancerFlux("/api/conversations/" + S.conv.id + "/messages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
      S.selection = [];
    });
  }
  function reprendreFlux(cid) { demarrerLive(); lancerFlux("/api/conversations/" + cid + "/flux?depuis=0", { method: "GET" }); }

  function demarrerLive() {
    var corps = h("div"); var meta = h("div", { class: "meta" }, h("strong", { texte: (salleCourante() || {}).libelle || "IA" }), h("span", { texte: "réponse en cours…" }));
    S.live = { texte: "", corps: corps, meta: meta, bulle: h("div", { class: "bulle assistant" }, meta, corps), demandes: null, cout: "", erreur: "" };
    S.enCours = true; dessiner(); defiler();
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
    }).catch(function (e) {
      if (e.message !== "session" && S.live) S.live.erreur = S.live.erreur || ("Connexion interrompue : " + e.message + ". La réponse continue peut-être sur le PC : rouvrez la conversation.");
    }).then(function () {
      S.live = null; S.enCours = false;
      return api("GET", "/api/conversations/" + cid).then(function (c) {
        if (S.conv && S.conv.id === cid) { S.conv = c; }
        if (c.en_cours) { S.enCours = false; }
      }).catch(function () {});
    }).then(function () { return charger(); }).then(function () { defiler(); });
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
  function versTiroir(m) {
    C.formulaire("Mettre dans le tiroir", "Le tiroir est partagé entre toutes les salles.", [
      { nom: "titre", label: "Titre", type: "text", valeur: m.texte.slice(0, 60) },
      { nom: "zone", label: "Zone", type: "select", valeur: "prive", options: [{ valeur: "prive", texte: "Privé : jamais envoyé à une IA du nuage" }, { valeur: "partageable", texte: "Partageable : peut être envoyé aux IA du nuage" }] }], "Enregistrer").then(function (v) {
      if (!v) return;
      return api("POST", "/api/tiroir", { titre: v.titre, texte: m.texte, zone: v.zone, origine: m.salle || "" });
    }).catch(function (e) { C.informer("Impossible", e.message); });
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

  C.pages.salles = pageSalles;
  C.pages.tiroir = pageTiroir;
})();
