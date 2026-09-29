"use strict";
/* Page « Voix » : conversation en direct (LIVE) et talkie-walkie. Aucune clé ici : tout passe par le serveur du PC. */
(function () {
  var C = window.Centre, h = C.h, vider = C.vider, api = C.api;
  var opts = null, live = null, talkie = { conv: null, salle: null, enregistrement: null, lecture: null };
  var racine = null;

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
      "Elle est désactivée en modes Confidentiel et Ultra. Jamais de contenu privé (zone « prive », conversations privées)."));
    racine.appendChild(carteLive());
    racine.appendChild(carteTalkie());
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

  function ligneLive(role, texte) {
    var fil = document.getElementById("live-fil"); if (!fil) return null;
    var b = h("div", { class: "bulle " + (role === "user" ? "user" : role === "outil" ? "" : "assistant") }, h("div", { class: "meta", texte: role === "user" ? "Vous" : role === "outil" ? "Outil" : "Assistant vocal" }), h("div", { texte: texte }));
    fil.appendChild(b); b.scrollIntoView({ block: "nearest" });
    return b;
  }
  function dire(texte) { var e = document.getElementById("live-etat"); if (e) e.textContent = texte; }

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
    live = { ws: null, ctx: null, flux: null, noeud: null, sources: [], prochain: 0, verrou: null, ligneIA: null, fini: false };
    document.getElementById("live-demarrer").disabled = true;
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
      document.getElementById("live-arreter").classList.remove("cache");
    }).catch(function (e) {
      var msg = e && e.name === "NotAllowedError" ? "Le micro a été refusé : autorisez-le dans le navigateur." : (e.message || String(e));
      finLive(false); dire(msg); C.informer("Micro ou audio indisponible", msg);
    });
  }

  function recevoir(m) {
    if (!live) return;
    if (m.t === "pret") { dire("À l'écoute — parlez. (" + m.modele + ", voix " + m.voix + ")"); }
    else if (m.t === "audio") { jouer(m.pcm); }
    else if (m.t === "parole_debut") { couper(); dire("Je vous écoute…"); }
    else if (m.t === "parole_fin") { dire("Réflexion…"); }
    else if (m.t === "transcription") {
      if (m.role === "user") { ligneLive("user", m.texte); live.ligneIA = null; }
      else {
        if (!live.ligneIA) live.ligneIA = ligneLive("assistant", "");
        if (live.ligneIA) { var zone = live.ligneIA.lastChild; zone.textContent = m.final ? m.texte : zone.textContent + m.texte; }
        if (m.final) live.ligneIA = null;
      }
    }
    else if (m.t === "outil") { dire(m.etat === "appel" ? "Consultation : " + m.nom + "…" : "Réponse de l'outil reçue."); if (m.etat === "fini") ligneLive("outil", m.nom + " → " + (m.resume || "")); }
    else if (m.t === "cout") {
      var e = document.getElementById("live-compteur");
      if (e) e.textContent = dollars(m.usd) + " · " + m.minutes.toFixed(1) + " min" + (m.restant_usd != null ? " · reste " + m.restant_usd.toFixed(2) + " $" : "");
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
    var d = document.getElementById("live-demarrer"); if (d) d.disabled = false;
    var a = document.getElementById("live-arreter"); if (a) a.classList.add("cache");
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

  document.addEventListener("visibilitychange", function () { /* le LIVE continue en arrière-plan tant que le micro reste autorisé */ });
  window.addEventListener("pagehide", function () { if (live) finLive(true); });
  C.pages.voix = pageVoix;
})();
