"use strict";
/* Page « Voix » : conversation en direct (LIVE) et talkie-walkie. Aucune clé ici : tout passe par le serveur du PC. */
(function () {
  var C = window.Centre, h = C.h, vider = C.vider, api = C.api;
  var opts = null, live = null, talkie = { conv: null, salle: null, enregistrement: null, lecture: null };
  var racine = null;
  function elt(id) { return document.getElementById(id); }

  function b64depuisBuffer(buf) {
    var octets = new Uint8Array(buf), s = "";
    for (var i = 0; i < octets.length; i += 0x8000) s += String.fromCharCode.apply(null, octets.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function bufferDepuisB64(b64) {
    var s = atob(b64), n = s.length, u = new Uint8Array(n);
    for (var i = 0; i < n; i++) u[i] = s.charCodeAt(i);
    return u.buffer;
  }
  function dollars(n) { return (Number(n) || 0).toLocaleString("fr-CA", { style: "currency", currency: "USD", minimumFractionDigits: 3, maximumFractionDigits: 3 }); }

  // ------------------------------------------------ page
  function pageVoix() {
    racine = h("div", { id: "voix" });
    C.page.appendChild(racine);
    api("GET", "/api/voix/options").then(function (d) { opts = d; dessiner(); })
      .catch(function (e) { if (e.message !== "session") racine.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); });
  }

  function dessiner() {
    if (!racine || C.courante() !== "voix") return;
    vider(racine);
    if (!opts.disponible) racine.appendChild(h("div", { class: "bandeau erreur", role: "status" }, h("strong", { texte: "Voix indisponible : " }), opts.raison));
    racine.appendChild(h("div", { class: "bandeau" }, "La voix passe par le nuage (OpenAI ou xAI) : votre voix et les réponses lues quittent le PC. ",
      "Elle est désactivée en modes Confidentiel et Ultra-confidentiel. Jamais de contenu privé (zone « prive », conversations privées)."));
    racine.appendChild(carteLive());
    racine.appendChild(carteTalkie());
    restaurerLive();
  }

  // ------------------------------------------------ LIVE
  function carteLive() {
    var selM = h("select", { id: "live-modele", "aria-label": "Modèle" }, opts.live.map(function (m) {
      return h("option", { value: m.id, texte: m.libelle + (m.disponible ? "" : " (indisponible)"), selected: m.defaut });
    }));
    var selV = h("select", { id: "live-voix", "aria-label": "Voix" });
    var aide = h("div", { class: "msg", id: "live-aide" });
    function maj() {
      var m = opts.live.filter(function (x) { return x.id === selM.value; })[0];
      vider(selV); m.voix.forEach(function (v) { selV.appendChild(h("option", { value: v, texte: v })); });
      aide.textContent = "Coût estimé : " + m.estimation + (m.disponible ? "" : " — " + m.raison);
      bouton.disabled = !m.disponible || !!live;
    }
    var bouton = h("button", { class: "bouton principal", id: "live-demarrer", type: "button", texte: "Démarrer la conversation", onclick: demarrerLive });
    selM.addEventListener("change", maj);
    var etat = h("div", { id: "live-etat", class: "doux", role: "status" });
    var compteur = h("div", { id: "live-compteur", class: "nom" });
    var fil = h("div", { class: "fil", id: "live-fil" });
    var carte = h("div", { class: "carte" }, h("h2", { texte: "Conversation en direct (LIVE)" }),
      h("div", { class: "grille2" }, h("label", { class: "champ" }, h("span", { texte: "Modèle" }), selM), h("label", { class: "champ" }, h("span", { texte: "Voix" }), selV)),
      aide,
      h("p", { class: "doux", texte: "Durée maximale " + opts.duree_max_minutes + " min, fermeture après " + Math.round(opts.silence_max_secondes / 60) + " min de silence, coupure automatique au plafond de dépense"
        + (opts.restant_usd != null ? " (reste " + opts.restant_usd.toFixed(2) + " $)." : ".") }),
      h("div", { class: "boutons-ligne" }, bouton, h("button", { class: "bouton danger cache", id: "live-arreter", type: "button", texte: "Terminer", onclick: function () { finLive(true); } })),
      etat, compteur, fil);
    maj();
    return carte;
  }

  // Les lignes du live sont mémorisées : la conversation continue même si l'on change de page, et on les retrouve en revenant sur « Voix ».
  function ligneLive(role, texte) {
    var e = { role: role, texte: texte, el: null };
    if (live) live.lignes.push(e);
    monterLigne(e);
    return e;
  }
  function monterLigne(e) {
    var fil = elt("live-fil");
    if (!fil) { e.el = null; return; }
    e.el = h("div", { class: "bulle " + (e.role === "user" ? "user" : e.role === "outil" ? "" : "assistant") },
      h("div", { class: "meta", texte: e.role === "user" ? "Vous" : e.role === "outil" ? "Outil" : "Assistant vocal" }), h("div", { texte: e.texte }));
    fil.appendChild(e.el); e.el.scrollIntoView({ block: "nearest" });
  }
  function ecrireLigne(e, texte) { e.texte = texte; if (e.el) e.el.lastChild.textContent = texte; }
  function dire(texte) { if (live) live.dernierEtat = texte; var e = elt("live-etat"); if (e) e.textContent = texte; }
  function restaurerLive() {       // retour sur la page Voix pendant un live : on remet les boutons, l'état, le compteur et les lignes
    var d = elt("live-demarrer"), ar = elt("live-arreter");
    if (!live) return;
    if (d) d.disabled = true;
    if (ar) ar.classList.remove("cache");
    if (live.dernierEtat) dire(live.dernierEtat);
    var c = elt("live-compteur"); if (c && live.compteurTexte) c.textContent = live.compteurTexte;
    live.lignes.forEach(monterLigne);
  }
  // Le rond du haut (toutes pages) : état du bouton et coût en direct
  function majBouton() {
    var b = elt("noyau-bouton"); if (!b) return;
    b.setAttribute("aria-pressed", live ? "true" : "false");
    b.setAttribute("aria-label", live ? "Conversation vocale en direct en cours : toucher pour arrêter" : "Conversation vocale en direct : démarrer");
    b.title = live ? "Conversation vocale en cours : touchez pour l'arrêter (les frais s'arrêtent avec elle)" : "Conversation vocale en direct : touchez pour démarrer, touchez de nouveau pour arrêter (limite les frais quand vous ne parlez pas)";
    document.body.dataset.live = live ? "1" : "0";
    C.liveActif = !!live;
    var t = elt("live-cout"); if (t) { t.hidden = !live; if (!live) t.textContent = ""; else if (!t.textContent) t.textContent = "LIVE…"; }
  }

  function demarrerLive() {
    var m = opts.live.filter(function (x) { return x.id === document.getElementById("live-modele").value; })[0];
    C.confirmer("Démarrer la conversation vocale ?",
      m.libelle + "\nCoût estimé : " + m.estimation + "\n" + (opts.restant_usd != null ? "Reste avant plafond : " + opts.restant_usd.toFixed(2) + " $\n" : "Aucun plafond réglé.\n") +
      "Durée maximale : " + opts.duree_max_minutes + " min.\nLe compteur de coût s'affichera en direct.", "Démarrer").then(function (ok) {
      if (!ok) return;
      return lancerLive(m, document.getElementById("live-voix").value);
    }).catch(function (e) { C.informer("Impossible", e.message); });
  }

  function lancerLive(m, voix) {
    live = { ws: null, ctx: null, flux: null, noeud: null, sources: [], prochain: 0, verrou: null, ligneIA: null, fini: false, lignes: [], dernierEtat: "", compteurTexte: "" };
    var bd = elt("live-demarrer"); if (bd) bd.disabled = true;
    majBouton();
    dire("Autorisation du micro…");
    var constraints = { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } };
    return navigator.mediaDevices.getUserMedia(constraints).then(function (flux) {
      live.flux = flux;
      var AC = window.AudioContext || window.webkitAudioContext;
      live.ctx = new AC({ sampleRate: 24000 });
      return live.ctx.resume().then(function () { return live.ctx.audioWorklet.addModule("/s/worklet-micro.js"); });
    }).then(function () {
      var src = live.ctx.createMediaStreamSource(live.flux);
      live.noeud = new AudioWorkletNode(live.ctx, "capture-micro");
      src.connect(live.noeud);
      if (navigator.wakeLock) navigator.wakeLock.request("screen").then(function (w) { live.verrou = w; }).catch(function () {});
      var url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/voix";
      live.ws = new WebSocket(url);
      live.ws.onopen = function () { live.ws.send(JSON.stringify({ t: "demarrer", modele: m.id, voix: voix })); dire("Connexion…"); };
      live.ws.onmessage = function (ev) { try { recevoir(JSON.parse(ev.data)); } catch (e) { /* message illisible */ } };
      live.ws.onclose = function () { finLive(false); };
      live.ws.onerror = function () { dire("Erreur de connexion avec le serveur."); };
      live.noeud.port.onmessage = function (e) {
        if (live && live.ws && live.ws.readyState === 1 && !live.fini) live.ws.send(JSON.stringify({ t: "audio", pcm: b64depuisBuffer(e.data) }));
      };
      var ba = elt("live-arreter"); if (ba) ba.classList.remove("cache");
    }).catch(function (e) {
      var msg = e && e.name === "NotAllowedError" ? "Le micro a été refusé : autorisez-le dans le navigateur." : (e.message || String(e));
      finLive(false); dire(msg); C.informer("Micro ou audio indisponible", msg);
    });
  }

  function recevoir(m) {
    if (!live) return;
    if (m.t === "pret") { dire("À l'écoute — parlez. (" + m.modele + ", voix " + m.voix + ")"); C.etat("ecoute"); }
    else if (m.t === "audio") { jouer(m.pcm); C.etat("parole"); }
    else if (m.t === "parole_debut") { couper(); dire("Je vous écoute…"); C.etat("ecoute"); }
    else if (m.t === "parole_fin") { dire("Réflexion…"); C.etat("reflexion"); }
    else if (m.t === "transcription") {
      if (m.role === "user") { ligneLive("user", m.texte); live.ligneIA = null; }
      else {
        if (!live.ligneIA) live.ligneIA = ligneLive("assistant", "");
        ecrireLigne(live.ligneIA, m.final ? m.texte : live.ligneIA.texte + m.texte);
        if (m.final) live.ligneIA = null;
      }
    }
    else if (m.t === "outil") { dire(m.etat === "appel" ? "Consultation : " + m.nom + "…" : "Réponse de l'outil reçue."); if (m.etat === "fini") ligneLive("outil", m.nom + " → " + (m.resume || "")); }
    else if (m.t === "cout") {
      var texteC = dollars(m.usd) + " · " + m.minutes.toFixed(1) + " min" + (m.restant_usd != null ? " · reste " + m.restant_usd.toFixed(2) + " $" : "");
      live.compteurTexte = texteC;
      var e = elt("live-compteur"); if (e) e.textContent = texteC;
      var t = elt("live-cout"); if (t) t.textContent = "LIVE · " + dollars(m.usd) + " · " + m.minutes.toFixed(1) + " min";
    }
    else if (m.t === "erreur") { dire(m.message); ligneLive("outil", "⚠ " + m.message); }
    else if (m.t === "fin") { dire("Terminé (" + m.raison + ") — coût " + dollars(m.cout_usd) + " pour " + m.minutes + " min."); finLive(false); }
  }

  function jouer(b64) {
    if (!live || !live.ctx) return;
    var pcm = new Int16Array(bufferDepuisB64(b64));
    var f = new Float32Array(pcm.length);
    for (var i = 0; i < pcm.length; i++) f[i] = pcm[i] / 32768;
    var buf = live.ctx.createBuffer(1, f.length, 24000);
    buf.copyToChannel(f, 0);
    var s = live.ctx.createBufferSource();
    s.buffer = buf; s.connect(live.ctx.destination);
    var debut = Math.max(live.ctx.currentTime + 0.02, live.prochain);
    s.start(debut); live.prochain = debut + buf.duration;
    live.sources.push(s);
    s.onended = function () { var k = live && live.sources.indexOf(s); if (k >= 0) live.sources.splice(k, 1); };
    dire("Je parle…");
  }
  function couper() {   // l'utilisateur reprend la parole : on coupe tout de suite ce qui est en cours de lecture
    if (!live) return;
    live.sources.forEach(function (s) { try { s.stop(); } catch (e) { /* déjà arrêté */ } });
    live.sources = []; live.prochain = 0;
  }

  function finLive(demander) {
    var l = live;
    if (!l) return;
    if (demander && l.ws && l.ws.readyState === 1) { try { l.ws.send(JSON.stringify({ t: "couper" })); } catch (e) { /* fermée */ } return; }
    if (l.fini) return;
    l.fini = true;
    couper();
    try { if (l.ws && l.ws.readyState <= 1) l.ws.close(); } catch (e) { /* déjà fermée */ }
    if (l.flux) l.flux.getTracks().forEach(function (t) { t.stop(); });
    if (l.noeud) { try { l.noeud.disconnect(); } catch (e) { /* ok */ } }
    if (l.ctx) l.ctx.close().catch(function () {});
    if (l.verrou) l.verrou.release().catch(function () {});
    live = null;
    majBouton();
    C.etat("repos");
    var d = elt("live-demarrer"); if (d) d.disabled = false;
    var ar = elt("live-arreter"); if (ar) ar.classList.add("cache");
    api("GET", "/api/voix/options").then(function (o) { opts = o; }).catch(function () {});
  }

  // ------------------------------------------------ talkie-walkie
  function carteTalkie() {
    var salles = opts.salles;
    var selS = h("select", { id: "t-salle", "aria-label": "Salle" }, salles.map(function (s) { return h("option", { value: s.id, disabled: !s.disponible, texte: s.libelle + (s.disponible ? "" : " (indisponible)") }); }));
    var selF = h("select", { id: "t-fournisseur", "aria-label": "Fournisseur de voix" }, opts.talkie.map(function (t) { return h("option", { value: t.id, disabled: !t.disponible, texte: t.libelle + (t.disponible ? "" : " (indisponible)") }); }));
    var lire = h("input", { type: "checkbox", id: "t-lire", checked: true });
    var bouton = h("button", { class: "bouton principal gros", id: "t-parler", type: "button", disabled: !opts.disponible, texte: "Maintenir pour parler" });
    var etat = h("div", { class: "doux", id: "t-etat", role: "status" });
    var fil = h("div", { class: "fil", id: "t-fil" });
    var carte = h("div", { class: "carte" }, h("h2", { texte: "Talkie-walkie (appuyer pour parler)" }),
      h("p", { class: "doux", texte: "Vous parlez, l'audio est transcrit dans le nuage, la question part vers la salle choisie, puis la réponse est lue par une voix du nuage. Coût estimé par échange : quelques centimes (transcription + lecture, plus le coût de la salle)." }),
      h("div", { class: "grille2" }, h("label", { class: "champ" }, h("span", { texte: "Salle" }), selS), h("label", { class: "champ" }, h("span", { texte: "Voix (transcription et lecture)" }), selF)),
      h("label", null, lire, " Lire la réponse à voix haute"),
      bouton, etat, fil);
    var d = opts.talkie.filter(function (t) { return t.disponible; })[0]; if (d) selF.value = d.id;
    var s0 = salles.filter(function (s) { return s.disponible; })[0]; if (s0) selS.value = s0.id;
    var actif = false;
    function debut(e) { e.preventDefault(); if (actif) return; actif = true; bouton.classList.add("enregistre"); commencerEnregistrement(); }
    function fin(e) { if (e) e.preventDefault(); if (!actif) return; actif = false; bouton.classList.remove("enregistre"); finirEnregistrement(); }
    bouton.addEventListener("pointerdown", debut);
    bouton.addEventListener("pointerup", fin);
    bouton.addEventListener("pointercancel", fin);
    bouton.addEventListener("pointerleave", fin);
    bouton.addEventListener("keydown", function (e) { if (e.key === " " || e.key === "Enter") debut(e); });
    bouton.addEventListener("keyup", function (e) { if (e.key === " " || e.key === "Enter") fin(e); });
    bouton.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    return carte;
  }
  function etatT(t) { var e = document.getElementById("t-etat"); if (e) e.textContent = t; }
  function bulleT(role, texte) {
    var fil = document.getElementById("t-fil"); if (!fil) return null;
    var corps = h("div"); C.rendre(corps, texte);
    var b = h("div", { class: "bulle " + (role === "user" ? "user" : "assistant") }, h("div", { class: "meta", texte: role === "user" ? "Vous (transcrit)" : "Réponse" }), corps);
    fil.appendChild(b); b.scrollIntoView({ block: "nearest" });
    return { el: b, corps: corps };
  }

  function typeAudio() {
    var candidats = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    for (var i = 0; i < candidats.length; i++) if (window.MediaRecorder && MediaRecorder.isTypeSupported(candidats[i])) return candidats[i];
    return "";
  }
  function commencerEnregistrement() {
    if (talkie.lecture) { talkie.lecture.pause(); talkie.lecture = null; }
    etatT("Autorisation du micro…");
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } }).then(function (flux) {
      var type = typeAudio();
      var rec = type ? new MediaRecorder(flux, { mimeType: type }) : new MediaRecorder(flux);
      var morceaux = [], t0 = Date.now();
      rec.ondataavailable = function (e) { if (e.data && e.data.size) morceaux.push(e.data); };
      talkie.enregistrement = { rec: rec, flux: flux, morceaux: morceaux, t0: t0, type: rec.mimeType || type || "audio/webm", annule: false };
      rec.start(250);
      etatT("Je vous écoute… relâchez pour envoyer.");
      if (talkie.enregistrement.arreterTot) finirEnregistrement();
    }).catch(function (e) { etatT(e && e.name === "NotAllowedError" ? "Micro refusé : autorisez-le dans le navigateur." : "Micro indisponible : " + (e.message || e)); });
  }
  function finirEnregistrement() {
    var r = talkie.enregistrement;
    if (!r) return;
    if (r.rec.state === "inactive") { return; }
    r.rec.onstop = function () {
      r.flux.getTracks().forEach(function (t) { t.stop(); });
      talkie.enregistrement = null;
      var duree = (Date.now() - r.t0) / 1000;
      if (duree < 0.6) { etatT("Trop court : maintenez le bouton pendant que vous parlez."); return; }
      envoyerAudio(new Blob(r.morceaux, { type: r.type }), duree, r.type);
    };
    r.rec.stop();
  }

  function envoyerAudio(blob, duree, type) {
    var f = document.getElementById("t-fournisseur").value, salle = document.getElementById("t-salle").value;
    etatT("Transcription…");
    fetch("/api/voix/transcrire?fournisseur=" + encodeURIComponent(f) + "&duree=" + duree.toFixed(1), {
      method: "POST", credentials: "same-origin", headers: { "X-Centre": "1", "Content-Type": type.split(";")[0] }, body: blob
    }).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.erreur || ("Erreur " + r.status)); return d; }); })
      .then(function (d) {
        if (!d.texte) { etatT("Je n'ai rien entendu de clair. Réessayez."); return; }
        bulleT("user", d.texte);
        return poserQuestion(salle, d.texte, f);
      }).catch(function (e) { etatT("⚠ " + e.message); });
  }

  function poserQuestion(salle, texte, fournisseur) {
    var creer = (talkie.conv && talkie.salle === salle) ? Promise.resolve(talkie.conv)
      : api("POST", "/api/conversations", { salle: salle, titre: "Talkie-walkie" }).then(function (c) { talkie.conv = c.id; talkie.salle = salle; return c.id; });
    return creer.then(function (cid) {
      etatT("La salle réfléchit…");
      var b = bulleT("assistant", ""), acc = "", msgId = null, err = "";
      return C.lireFlux("/api/conversations/" + cid + "/messages", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texte: texte }) }, function (e) {
        if (e.t === "delta") { acc += e.texte; C.rendre(b.corps, acc); }
        else if (e.t === "erreur") { err = e.message; }
        else if (e.t === "fin") { msgId = e.message_id; }
      }).then(function () {
        if (err) { C.rendre(b.corps, "⚠ " + err); etatT("La salle n'a pas pu répondre."); return; }
        if (!document.getElementById("t-lire").checked || !msgId) { etatT("Terminé."); return; }
        etatT("Lecture de la réponse…");
        return fetch("/api/voix/parler", { method: "POST", credentials: "same-origin", headers: { "X-Centre": "1", "Content-Type": "application/json" },
          body: JSON.stringify({ conversation: cid, message_id: msgId, fournisseur: fournisseur }) }).then(function (r) {
          if (!r.ok) return r.json().then(function (d) { throw new Error(d.erreur || ("Erreur " + r.status)); });
          var tronque = r.headers.get("X-Tronque") === "1";
          return r.blob().then(function (audio) {
            var a = new Audio(URL.createObjectURL(audio)); talkie.lecture = a;
            a.onended = function () { etatT("Terminé." + (tronque ? " (Lecture limitée au début de la réponse.)" : "")); URL.revokeObjectURL(a.src); };
            return a.play().catch(function () { etatT("Lecture bloquée par le navigateur : touchez la page puis réessayez."); });
          });
        });
      });
    }).catch(function (e) { etatT("⚠ " + e.message); });
  }

  // ------------------------------------------------ outils partagés avec le bas d'écran des salles (bouton « maintenir pour parler »)
  var optsCache = null;
  C.voixOptions = function (forcer) {
    if (optsCache && !forcer) return Promise.resolve(optsCache);
    return api("GET", "/api/voix/options").then(function (o) { optsCache = o; return o; });
  };
  function fournisseurTalkie(o) {
    var dispo = o.talkie.filter(function (t) { return t.disponible; });
    return (dispo.filter(function (t) { return t.id === "openai"; })[0] || dispo[0] || {}).id || null;
  }
  C.micro = {
    // Démarre l'enregistrement. Renvoie une promesse d'un objet { arreter() -> promesse de { blob, duree, type } }.
    demarrer: function () {
      return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } }).then(function (flux) {
        var type = typeAudio();
        var rec = type ? new MediaRecorder(flux, { mimeType: type }) : new MediaRecorder(flux);
        var morceaux = [], t0 = Date.now(), mime = rec.mimeType || type || "audio/webm";
        rec.ondataavailable = function (e) { if (e.data && e.data.size) morceaux.push(e.data); };
        rec.start(250);
        return { arreter: function () {
          return new Promise(function (resolve) {
            rec.onstop = function () {
              flux.getTracks().forEach(function (t) { t.stop(); });
              resolve({ blob: new Blob(morceaux, { type: mime }), duree: (Date.now() - t0) / 1000, type: mime });
            };
            if (rec.state === "inactive") rec.onstop(); else rec.stop();
          });
        } };
      });
    },
    // Envoie l'enregistrement à la transcription (nuage) ; renvoie le texte.
    transcrire: function (enr) {
      return C.voixOptions().then(function (o) {
        var f = fournisseurTalkie(o);
        if (!f) throw new Error(o.raison || "Aucune voix du nuage n'est disponible (clé absente ?).");
        return fetch("/api/voix/transcrire?fournisseur=" + encodeURIComponent(f) + "&duree=" + enr.duree.toFixed(1), {
          method: "POST", credentials: "same-origin", headers: { "X-Centre": "1", "Content-Type": enr.type.split(";")[0] }, body: enr.blob });
      }).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.erreur || ("Erreur " + r.status)); return d.texte || ""; }); });
    },
    // Lit à voix haute une réponse déjà enregistrée (jamais un contenu privé : le serveur refuse).
    lire: function (cid, msgId) {
      return C.voixOptions().then(function (o) {
        var f = fournisseurTalkie(o);
        if (!f) throw new Error(o.raison || "Aucune voix du nuage n'est disponible.");
        return fetch("/api/voix/parler", { method: "POST", credentials: "same-origin", headers: { "X-Centre": "1", "Content-Type": "application/json" },
          body: JSON.stringify({ conversation: cid, message_id: msgId, fournisseur: f }) });
      }).then(function (r) {
        if (!r.ok) return r.json().then(function (d) { throw new Error(d.erreur || ("Erreur " + r.status)); });
        return r.blob().then(function (audio) {
          if (talkie.lecture) talkie.lecture.pause();
          var a = new Audio(URL.createObjectURL(audio)); talkie.lecture = a;
          C.etat("parole");
          a.onended = function () { C.etat("repos"); URL.revokeObjectURL(a.src); };
          return a.play().catch(function () { C.etat("repos"); throw new Error("Lecture bloquée par le navigateur : touchez la page puis réessayez."); });
        });
      });
    },
    arreterLecture: function () { if (talkie.lecture) { talkie.lecture.pause(); talkie.lecture = null; C.etat("repos"); } }
  };

  // ------------------------------------------------ le rond du haut : un appui démarre le LIVE, un autre l'arrête (pour ne pas payer quand on ne parle pas)
  function arreterRapide() {
    finLive(true);                                              // demande polie : le serveur termine et enregistre le coût
    setTimeout(function () { if (live) finLive(false); }, 1500);      // sinon on coupe nous-mêmes la connexion (le serveur enregistre aussi dans ce cas)
  }
  function confirmeDeja() { try { return sessionStorage.getItem("centre.live.confirme") === "1"; } catch (e) { return false; } }
  C.basculerLive = function () {
    if (live) { arreterRapide(); return Promise.resolve(); }
    var b = elt("noyau-bouton"); if (b) b.disabled = true;
    return C.voixOptions(true).then(function (o) {
      opts = o;
      if (!o.disponible) { C.informer("Voix indisponible", o.raison); return; }
      var sm = elt("live-modele"), sv = elt("live-voix");
      var m = (sm && o.live.filter(function (x) { return x.id === sm.value && x.disponible; })[0]) || o.live.filter(function (x) { return x.defaut && x.disponible; })[0] || o.live.filter(function (x) { return x.disponible; })[0];
      if (!m) { C.informer("Voix indisponible", (o.live[0] && o.live[0].raison) || "Aucun modèle vocal n'est disponible."); return; }
      var voix = (sv && m.voix.indexOf(sv.value) >= 0 && sv.value) || m.voix[0];
      var suite = confirmeDeja() ? Promise.resolve(true) : C.confirmer("Démarrer la conversation vocale en direct ?",
        m.libelle + "\nCoût estimé : " + m.estimation + "\n" + (o.restant_usd != null ? "Reste avant plafond : " + o.restant_usd.toFixed(2) + " $\n" : "Aucun plafond réglé.\n") +
        "Durée maximale : " + o.duree_max_minutes + " min.\nPour arrêter (et arrêter les frais), touchez de nouveau le rond en haut à gauche. Cette confirmation ne sera plus demandée pendant cette session.", "Démarrer");
      return suite.then(function (ok) {
        if (!ok) return;
        try { sessionStorage.setItem("centre.live.confirme", "1"); } catch (e) { /* facultatif */ }
        return lancerLive(m, voix);
      });
    }).catch(function (e) { if (e.message !== "session") C.informer("Impossible", e.message); }).then(function () { if (b) b.disabled = false; });
  };
  (function () { var b = elt("noyau-bouton"); if (b) b.addEventListener("click", function () { C.basculerLive(); }); })();

  document.addEventListener("visibilitychange", function () { /* le LIVE continue en arrière-plan tant que le micro reste autorisé */ });
  window.addEventListener("pagehide", function () { if (live) finLive(true); });
  C.pages.voix = pageVoix;
})();
