"use strict";
/* Page « Images » : création d'images par IA (OpenAI, Gemini, Grok, ComfyUI local) et galerie rangée sur ce PC. Texte affiché comme texte. */
(function () {
  var C = window.Centre, h = C.h, vider = C.vider, api = C.api;
  var S = { opts: null, racine: null, galerie: null, job: null, minuteur: null, etat: { moteur: "", taille: "carre", n: 1, prive: false, checkpoint: "" } };

  function dollars(n) { return (Number(n) || 0).toLocaleString("fr-CA", { style: "currency", currency: "USD", minimumFractionDigits: 3, maximumFractionDigits: 3 }); }
  function quand(ts) { return new Date(ts * 1000).toLocaleString("fr-CA", { dateStyle: "medium", timeStyle: "short" }); }
  function moteur(id) { return S.opts ? S.opts.moteurs.filter(function (m) { return m.id === id; })[0] : null; }
  function utilisable(m) { return m && m.disponible && !(S.etat.prive && m.nuage); }

  function coutTexte() {
    var m = moteur(S.etat.moteur);
    if (!m) return "Aucun moteur disponible.";
    var usd = m.usd_image * S.etat.n;
    return usd === 0 ? "Gratuit (moteur local, rien ne quitte le PC)." :
      "Coût estimé : ≈ " + dollars(usd) + " pour " + S.etat.n + " image" + (S.etat.n > 1 ? "s" : "") + " (estimation indicative ; seuil de confirmation " + dollars(S.opts.seuil_usd) + ").";
  }
  function majCout() { var e = document.getElementById("img-cout"); if (e) e.textContent = coutTexte(); }

  function choisirMoteurValide() {
    var m = moteur(S.etat.moteur);
    if (utilisable(m)) return;
    var premier = S.opts.moteurs.filter(utilisable)[0];
    S.etat.moteur = premier ? premier.id : "";
  }

  function formulaire() {
    var o = S.opts, sel = h("select", { id: "img-moteur", "aria-label": "Moteur" });
    function remplir() {
      vider(sel);
      o.moteurs.forEach(function (m) {
        var grise = !m.disponible || (S.etat.prive && m.nuage);
        var raison = !m.disponible ? m.raison : (S.etat.prive && m.nuage ? "Contenu confidentiel : moteur local seulement" : "");
        var opt = h("option", { value: m.id, texte: m.libelle + (m.usd_image ? " — ≈ " + dollars(m.usd_image) + " / image" : " — gratuit") + (grise ? " (indisponible)" : ""), disabled: grise, title: raison });
        if (m.id === S.etat.moteur) opt.selected = true;
        sel.appendChild(opt);
      });
    }
    remplir();
    var raisons = h("div", { class: "doux", id: "img-raisons" });
    function majRaisons() {
      vider(raisons);
      o.moteurs.filter(function (m) { return !m.disponible; }).forEach(function (m) { raisons.appendChild(h("div", { texte: m.libelle + " : " + m.raison })); });
    }
    majRaisons();
    var prompt = h("textarea", { id: "img-prompt", rows: "4", maxlength: "4000", placeholder: "Décrivez l'image : sujet, style, lumière, ambiance…", "aria-label": "Description de l'image" });
    if (S.etat.prompt) prompt.value = S.etat.prompt;
    prompt.addEventListener("input", function () { S.etat.prompt = prompt.value; });
    var taille = h("select", { id: "img-taille", "aria-label": "Format" }, o.tailles.map(function (t) { return h("option", { value: t.id, texte: t.libelle, selected: t.id === S.etat.taille }); }));
    taille.addEventListener("change", function () { S.etat.taille = taille.value; });
    var nombre = h("select", { id: "img-n", "aria-label": "Nombre d'images" }, [1, 2, 3, 4].filter(function (n) { return n <= o.max_images; }).map(function (n) { return h("option", { value: String(n), texte: n + (n > 1 ? " images" : " image"), selected: n === S.etat.n }); }));
    nombre.addEventListener("change", function () { S.etat.n = Number(nombre.value); majCout(); });
    var prive = h("input", { type: "checkbox", id: "img-prive", checked: S.etat.prive });
    var cps = h("select", { id: "img-checkpoint", "aria-label": "Modèle ComfyUI" }, (o.checkpoints || []).map(function (c) { return h("option", { value: c, texte: c, selected: c === S.etat.checkpoint }); }));
    cps.addEventListener("change", function () { S.etat.checkpoint = cps.value; });
    var blocCps = h("label", { class: "champ", id: "img-bloc-cps", hidden: S.etat.moteur !== "local" || !(o.checkpoints || []).length }, h("span", { texte: "Modèle local (ComfyUI)" }), cps);
    function après() { choisirMoteurValide(); remplir(); blocCps.hidden = S.etat.moteur !== "local" || !(o.checkpoints || []).length; majCout(); }
    sel.addEventListener("change", function () { S.etat.moteur = sel.value; après(); });
    prive.addEventListener("change", function () { S.etat.prive = prive.checked; après(); });
    var bouton = h("button", { class: "bouton principal", id: "img-creer", type: "button", texte: "🎨 Créer l'image", onclick: creer, disabled: !S.etat.moteur || !!S.job });
    return h("div", { class: "carte" },
      h("label", { class: "champ" }, h("span", { texte: "Moteur" }), sel), raisons,
      h("label", { class: "champ" }, h("span", { texte: "Description" }), prompt),
      h("div", { class: "rangee-img" }, h("label", { class: "champ" }, h("span", { texte: "Format" }), taille), h("label", { class: "champ" }, h("span", { texte: "Nombre" }), nombre)),
      blocCps,
      h("label", { class: "case-prive" }, prive, " Contenu confidentiel : moteur local seulement (jamais le nuage)"),
      h("p", { class: "doux", id: "img-cout", role: "status", texte: coutTexte() }), bouton);
  }

  function creer() {
    var m = moteur(S.etat.moteur), prompt = (S.etat.prompt || "").trim();
    if (!m) { C.informer("Aucun moteur", "Aucun moteur d'images n'est disponible pour le moment."); return; }
    if (!prompt) { C.informer("Description vide", "Décrivez l'image à créer."); return; }
    var usd = m.usd_image * S.etat.n, depasse = m.nuage && usd > S.opts.seuil_usd;
    var suite = depasse ? C.confirmer("Coût au-dessus du seuil", "Coût estimé : ≈ " + dollars(usd) + " pour " + S.etat.n + " image(s) chez " + m.libelle + ", au-dessus du seuil de " + dollars(S.opts.seuil_usd) +
      ".\nLa description part vers ce fournisseur dans le nuage.\n\nCréer quand même ?", "Créer", "danger") : Promise.resolve(true);
    suite.then(function (ok) {
      if (!ok) return;
      return api("POST", "/api/images", { moteur: m.id, prompt: prompt, taille: S.etat.taille, n: S.etat.n, prive: S.etat.prive, checkpoint: S.etat.checkpoint, confirme_depassement: depasse })
        .then(function (job) { S.job = job; dessiner(); suivre(job.id); })
        .catch(function (e) { if (e.message !== "session") C.informer("Création impossible", e.message); });
    });
  }
  function suivre(id) {
    clearTimeout(S.minuteur);
    S.minuteur = setTimeout(function () {
      api("GET", "/api/images/jobs/" + id).then(function (j) {
        S.job = j;
        if (j.etat === "en_cours") { if (C.courante() === "images") { majProgression(); suivre(id); } return; }
        var fini = j;
        S.job = null; S.resultat = fini;
        if (C.courante() === "images") { charger(); }
      }).catch(function (e) { S.job = null; if (e.message !== "session" && C.courante() === "images") { dessiner(); } });
    }, 1500);
  }
  function majProgression() {
    var e = document.getElementById("img-progression"); if (!e || !S.job) return;
    e.textContent = "Création en cours : " + S.job.fait + " sur " + S.job.sur + "…";
  }

  function carte(m) {
    var url = "/api/images/" + m.id + "/fichier";
    return h("div", { class: "carte-image" },
      h("a", { href: url, target: "_blank", rel: "noopener", title: "Ouvrir en grand" }, h("img", { src: url, alt: m.prompt || "image créée", loading: "lazy" })),
      h("div", { class: "infos-image" },
        h("div", { class: "doux", texte: quand(m.ts) + " · " + (m.moteur_libelle || m.moteur) + (m.prive ? " · confidentiel" : "") + (m.cout_usd ? " · ≈ " + dollars(m.cout_usd) : "") }),
        h("div", { class: "prompt-image", title: m.prompt, texte: m.prompt }),
        h("div", { class: "actions" },
          h("a", { class: "petit", href: url + "?telecharger=1", texte: "Télécharger", download: "" }),
          h("button", { class: "petit", type: "button", texte: "Réutiliser la description", onclick: function () {
            S.etat.prompt = m.prompt; var p = document.getElementById("img-prompt"); if (p) { p.value = m.prompt; p.focus(); p.scrollIntoView({ block: "center" }); } } }),
          h("button", { class: "petit", type: "button", texte: "Supprimer", onclick: function () {
            C.confirmer("Supprimer cette image ?", "Elle sera effacée de ce PC (irréversible).", "Supprimer", "danger").then(function (ok) {
              if (!ok) return;
              api("DELETE", "/api/images/" + m.id).then(charger).catch(function (e) { C.informer("Suppression impossible", e.message); });
            }); } }))));
  }

  function dessiner() {
    var r = S.racine; if (!r || C.courante() !== "images" || !S.opts) return;
    vider(r);
    r.appendChild(h("h2", { texte: "🎨 Images" }));
    r.appendChild(h("p", { class: "doux", texte: "Créez des images avec l'IA. Les images restent sur ce PC (galerie ci-dessous). Un moteur du nuage reçoit votre description ; en mode confidentiel, ou avec la case « confidentiel », seul le moteur local (ComfyUI) est utilisé." }));
    if (S.resultat && S.resultat.etat === "erreur") r.appendChild(h("div", { class: "bandeau erreur", role: "alert", texte: S.resultat.message || "La création a échoué." }));
    if (S.resultat && S.resultat.etat === "termine") r.appendChild(h("div", { class: "bandeau ok", role: "status", texte: S.resultat.images.length + " image" + (S.resultat.images.length > 1 ? "s créées" : " créée") + " : elles sont en haut de la galerie." }));
    if (S.job) r.appendChild(h("div", { class: "progression", role: "status", "aria-live": "polite" }, h("strong", { id: "img-progression", texte: "Création en cours : " + S.job.fait + " sur " + S.job.sur + "…" }),
      h("div", { class: "barre", "aria-hidden": "true" }, h("span", { class: "barre-anim" }))));
    r.appendChild(formulaire());
    var g = h("div", { class: "galerie" });
    S.galerie = g;
    r.appendChild(h("h3", { texte: "Galerie" }));
    if (!S.images.length) g.appendChild(h("div", { class: "doux", texte: "Aucune image pour le moment." }));
    S.images.forEach(function (m) { g.appendChild(carte(m)); });
    r.appendChild(g);
  }

  function charger() {
    Promise.all([api("GET", "/api/images/options"), api("GET", "/api/images")]).then(function (res) {
      S.opts = res[0]; S.images = res[1].images;
      if (!S.etat.moteur) S.etat.moteur = S.opts.defaut;
      if (!S.etat.checkpoint && S.opts.checkpoints && S.opts.checkpoints.length) S.etat.checkpoint = S.opts.checkpoints[0];
      choisirMoteurValide();
      dessiner();
    }).catch(function (e) { if (e.message !== "session" && S.racine) { vider(S.racine); S.racine.appendChild(h("div", { class: "bandeau erreur", texte: e.message })); } });
  }

  function pageImages() {
    S.racine = h("div", { class: "page-images" }); S.images = []; S.resultat = null;
    C.page.appendChild(S.racine);
    S.racine.appendChild(h("div", { class: "doux", texte: "Chargement…" }));
    if (S.job) suivre(S.job.id);
    charger();
  }
  C.pages.images = pageImages;
})();
