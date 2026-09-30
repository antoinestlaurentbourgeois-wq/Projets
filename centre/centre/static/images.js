"use strict";
/* Images : page « 🎨 Images » (création + galerie) ET fenêtre de création utilisable depuis toutes les salles (Centre.dialogueImage).
   Un seul menu de moteur (groupes « Nuage » / « Local »), un menu de modèle selon le moteur. Le serveur décide (confidentialité, coûts, carte
   graphique) : l'écran ne fait que demander confirmation quand le serveur le demande. Texte affiché comme texte. */
(function () {
  var C = window.Centre, h = C.h, vider = C.vider, api = C.api;
  var S = { opts: null, racine: null, images: [], job: null, minuteur: null, resultat: null,
            etat: { moteur: "", modele: "", taille: "carre", n: 1, prive: false, prompt: "", laisser_libre: false } };

  function dollars(n) { return (Number(n) || 0).toLocaleString("fr-CA", { style: "currency", currency: "USD", minimumFractionDigits: 3, maximumFractionDigits: 3 }); }
  function quand(ts) { return new Date(ts * 1000).toLocaleString("fr-CA", { dateStyle: "medium", timeStyle: "short" }); }
  function moteurDe(o, id) { return o.moteurs.filter(function (m) { return m.id === id; })[0]; }
  function utilisable(m, prive) { return !!m && m.disponible && !(prive && m.nuage); }
  function prixTexte(m) { return m.usd_image ? "≈ " + dollars(m.usd_image) : "gratuit"; }

  // Choix par défaut : le dernier utilisé (mémorisé côté serveur), sinon ComfyUI s'il répond, sinon xAI ; jamais un moteur du nuage pour du contenu confidentiel.
  function initEtat(o, etat, prive) {
    etat.prive = !!prive;
    var m = moteurDe(o, etat.moteur);
    if (!utilisable(m, etat.prive)) {
      var pref = moteurDe(o, o.defaut);
      m = utilisable(pref, etat.prive) ? pref : o.moteurs.filter(function (x) { return utilisable(x, etat.prive); })[0];
      etat.moteur = m ? m.id : "";
      etat.modele = m && pref && m.id === pref.id ? (o.modele_defaut || "") : "";
    }
    if (m && m.modeles.indexOf(etat.modele) < 0) etat.modele = m.modeles[0] || "";
    if (!etat.taille) etat.taille = o.taille_defaut || "carre";
  }

  // Formulaire commun à la page et à la fenêtre des salles. cfg : { priveFixe: bool (conversation privée), inclurePrive: bool }.
  function champs(o, etat, cfg, surChangement) {
    cfg = cfg || {};
    var prive = function () { return !!(cfg.priveFixe || etat.prive); };
    var sel = h("select", { id: "img-moteur", "aria-label": "Moteur d'images" });
    var selModele = h("select", { id: "img-modele", "aria-label": "Modèle" });
    var blocModele = h("label", { class: "champ" }, h("span", { texte: "Modèle" }), selModele);
    var raisons = h("div", { class: "doux", id: "img-raisons" });
    var cout = h("p", { class: "doux", id: "img-cout", role: "status" });
    var gpu = h("div", { class: "note-gpu", id: "img-gpu", hidden: true },
      h("p", { class: "doux", id: "img-gpu-texte", texte: "ComfyUI utilise la carte graphique, que le chef d'équipe de Crew occupe : Crew la libère, ComfyUI démarre tout seul (environ 20 à 40 s), crée l'image puis s'arrête, et Crew recharge son chef (environ 10 s). Pendant ce temps Crew continue par un modèle de nuage en mode normal et reste indisponible en mode confidentiel." }));
    var libre = h("input", { type: "checkbox", id: "img-libre", checked: !!etat.laisser_libre });
    libre.addEventListener("change", function () { etat.laisser_libre = libre.checked; });
    gpu.appendChild(h("label", { class: "case-prive" }, libre, " Laisser la carte graphique libre ensuite (ne pas recharger le chef)"));
    var manuel = h("input", { type: "checkbox", id: "img-arreter-comfyui", checked: !!etat.arreter_comfyui });
    manuel.addEventListener("change", function () { etat.arreter_comfyui = manuel.checked; });
    var blocManuel = h("div", { class: "note-gpu", id: "img-comfy-manuel", hidden: true },
      h("label", { class: "case-prive" }, manuel, " ComfyUI tourne déjà (lancé à la main) : l'arrêter ensuite"));
    var autoComfy = h("p", { class: "doux", id: "img-comfy-auto", hidden: true, texte: "ComfyUI n'est pas lancé : le Centre le démarre tout seul (environ 20 à 40 s), crée l'image puis l'arrête." });

    function remplirMoteurs() {
      vider(sel);
      ["Nuage", "Local"].forEach(function (groupe) {
        var g = h("optgroup", { label: groupe });
        o.moteurs.filter(function (m) { return m.groupe === groupe; }).forEach(function (m) {
          var grise = !m.disponible || (prive() && m.nuage);
          var opt = h("option", { value: m.id, texte: m.libelle + " — " + prixTexte(m) + (grise ? " (indisponible)" : ""), disabled: grise,
            title: !m.disponible ? m.raison : (prive() && m.nuage ? "Contenu confidentiel : moteur local seulement" : "") });
          if (m.id === etat.moteur) opt.selected = true;
          g.appendChild(opt);
        });
        sel.appendChild(g);
      });
      vider(raisons);
      o.moteurs.forEach(function (m) {
        var r = !m.disponible ? m.raison : (prive() && m.nuage ? "Contenu confidentiel : moteur local seulement." : "");
        if (r) raisons.appendChild(h("div", { texte: m.libelle + " : " + r }));
      });
    }
    function remplirModeles() {
      var m = moteurDe(o, etat.moteur);
      vider(selModele);
      var liste = m ? m.modeles : [];
      liste.forEach(function (x) { selModele.appendChild(h("option", { value: x, texte: x, selected: x === etat.modele })); });
      blocModele.hidden = liste.length < 2 && !(m && m.id === "local");
      selModele.disabled = liste.length < 2;
    }
    function majCout() {
      var m = moteurDe(o, etat.moteur);
      if (!m) { cout.textContent = "Aucun moteur disponible."; gpu.hidden = true; blocManuel.hidden = true; autoComfy.hidden = true; return; }
      var usd = m.usd_image * etat.n;
      cout.textContent = usd === 0 ? "Gratuit (moteur local, rien ne quitte le PC)." :
        "Coût estimé : ≈ " + dollars(usd) + " pour " + etat.n + " image" + (etat.n > 1 ? "s" : "") + (m.tarif_verifie ? "" : " (estimation indicative)") +
        " ; seuil de confirmation " + dollars(o.seuil_usd) + ".";
      gpu.hidden = !(m.id === "local" && o.chef_a_liberer);
      var comfy = o.comfy || {};
      blocManuel.hidden = !(m.id === "local" && comfy.repond && comfy.manuel);
      autoComfy.hidden = !(m.id === "local" && !comfy.repond && !o.chef_a_liberer);
    }
    function tout() { remplirMoteurs(); remplirModeles(); majCout(); if (surChangement) surChangement(); }
    sel.addEventListener("change", function () { etat.moteur = sel.value; var m = moteurDe(o, etat.moteur); etat.modele = m && m.modeles[0] || ""; tout(); });
    selModele.addEventListener("change", function () { etat.modele = selModele.value; });

    var prompt = h("textarea", { id: "img-prompt", rows: "4", maxlength: "4000", placeholder: "Décrivez l'image : sujet, style, lumière, ambiance…", "aria-label": "Description de l'image" });
    prompt.value = etat.prompt || "";
    prompt.addEventListener("input", function () { etat.prompt = prompt.value; });
    var taille = h("select", { id: "img-taille", "aria-label": "Format" }, o.tailles.map(function (t) { return h("option", { value: t.id, texte: t.libelle, selected: t.id === etat.taille }); }));
    taille.addEventListener("change", function () { etat.taille = taille.value; });
    var nombre = h("select", { id: "img-n", "aria-label": "Nombre d'images" }, [1, 2, 3, 4].filter(function (n) { return n <= o.max_images; }).map(function (n) {
      return h("option", { value: String(n), texte: n + (n > 1 ? " images" : " image"), selected: n === etat.n }); }));
    nombre.addEventListener("change", function () { etat.n = Number(nombre.value); majCout(); });

    var corps = h("div", { class: "formulaire-image" },
      h("label", { class: "champ" }, h("span", { texte: "Moteur" }), sel), raisons, blocModele,
      h("label", { class: "champ" }, h("span", { texte: "Description" }), prompt),
      h("div", { class: "rangee-img" }, h("label", { class: "champ" }, h("span", { texte: "Format" }), taille), h("label", { class: "champ" }, h("span", { texte: "Nombre" }), nombre)));
    if (cfg.priveFixe) corps.appendChild(h("p", { class: "doux", texte: "Cette conversation est privée : seul le moteur local est permis." }));
    else if (cfg.inclurePrive !== false) {
      var cp = h("input", { type: "checkbox", id: "img-prive", checked: !!etat.prive });
      cp.addEventListener("change", function () { etat.prive = cp.checked; initEtat(o, etat, etat.prive); tout(); });
      corps.appendChild(h("label", { class: "case-prive" }, cp, " Contenu confidentiel : moteur local seulement (jamais le nuage)"));
    }
    corps.appendChild(cout); corps.appendChild(gpu); corps.appendChild(autoComfy); corps.appendChild(blocManuel);
    tout();
    return { el: corps, prompt: prompt };
  }

  // Demande au serveur ; s'il réclame une confirmation (seuil de coût, libération de la carte graphique), on la demande puis on recommence.
  function poster(url, etat, extra, drapeaux) {
    drapeaux = drapeaux || {};
    var corps = { moteur: etat.moteur, modele: etat.modele, prompt: etat.prompt, taille: etat.taille, n: etat.n, prive: !!etat.prive, laisser_libre: !!etat.laisser_libre, arreter_comfyui: !!etat.arreter_comfyui,
                  confirme_depassement: !!drapeaux.depassement, confirme_liberation: !!drapeaux.liberation };
    Object.keys(extra || {}).forEach(function (k) { corps[k] = extra[k]; });
    return api("POST", url, corps).catch(function (e) {
      var d = e.donnees || {};
      if (d.depassement && !drapeaux.depassement) {
        return C.confirmer("Coût au-dessus du seuil", e.message + "\nLa description part vers ce fournisseur dans le nuage.\n\nCréer quand même ?", "Créer", "danger").then(function (ok) {
          return ok ? poster(url, etat, extra, { depassement: true, liberation: drapeaux.liberation }) : null; });
      }
      if (d.liberation && !drapeaux.liberation) {
        return C.confirmer("Créer cette image en local ?", e.message, "Continuer").then(function (ok) {
          return ok ? poster(url, etat, extra, { depassement: drapeaux.depassement, liberation: true }) : null; });
      }
      throw e;
    });
  }

  // ---------------------------------------------------------------- fenêtre de création (salles)
  // options : { titre, prompt, taille, moteur, modele, prive (conversation privée), url, extra } -> promesse du job lancé (ou null si annulé)
  C.dialogueImage = function (options) {
    return api("GET", "/api/images/options").then(function (o) {
      var etat = { moteur: options.moteur || "", modele: options.modele || "", taille: options.taille || "", n: options.n || 1, prive: !!options.prive, prompt: options.prompt || "", laisser_libre: false };
      initEtat(o, etat, options.prive);
      var f = champs(o, etat, { priveFixe: !!options.prive });
      return C.demander(options.titre || "🎨 Créer une image", "L'IA de la salle n'est pas appelée : l'image est créée par le moteur choisi, puis revient dans la conversation.",
        [{ texte: "Annuler", valeur: false }, { texte: "Créer l'image", valeur: true, style: "principal" }], f.el).then(function (v) {
        if (v !== true) return null;
        if (!(etat.prompt || "").trim()) { C.informer("Description vide", "Décrivez l'image à créer."); return null; }
        if (!etat.moteur) { C.informer("Aucun moteur", "Aucun moteur d'images n'est disponible pour le moment."); return null; }
        return poster(options.url, etat, options.extra);
      });
    });
  };
  // Moteur et modèle que l'écran propose par défaut (pour la carte d'une proposition de l'IA) : mêmes règles que la fenêtre de création.
  C.moteurParDefaut = function (o, prive) {
    var e = { moteur: "", modele: "", taille: "", n: 1, prive: !!prive };
    initEtat(o, e, prive);
    var m = moteurDe(o, e.moteur);
    return m ? { moteur: m, modele: e.modele } : null;
  };
  C.optionsImages = function () { return api("GET", "/api/images/options"); };
  C.lancerImageDirect = function (url, etatPartiel, extra, prive) {
    return api("GET", "/api/images/options").then(function (o) {
      var etat = { moteur: "", modele: "", taille: etatPartiel.taille || "", n: 1, prive: !!prive, prompt: etatPartiel.prompt || "", laisser_libre: false };
      initEtat(o, etat, prive);
      if (!etat.moteur) throw new Error("Aucun moteur d'images n'est disponible" + (prive ? " pour du contenu confidentiel (ComfyUI doit être lancé)." : "."));
      return poster(url, etat, extra);
    });
  };

  // ---------------------------------------------------------------- bandeaux ComfyUI (réconciliation : un bouton, JAMAIS d'action automatique)
  // d : réponse de GET /api/comfyui ; apres : fonction appelée après l'action pour rafraîchir l'écran.
  C.bandeauxComfyUI = function (d, apres) {
    var sortie = [];
    if (!d) return sortie;
    if (d.bandeau_chef) {
      sortie.push(h("div", { class: "bandeau", role: "status", id: "bandeau-chef-libre" },
        h("strong", { texte: "La carte graphique est encore libérée. Recharger le chef ?" }), " ",
        h("button", { class: "petit", type: "button", id: "bouton-recharger-chef", texte: "Recharger le chef", onclick: function () {
          api("POST", "/api/comfyui/reprendre-chef").then(function () {
            return C.informer("Chef en cours de rechargement", "Crew recharge son chef (environ 10 s). Crew sera de nouveau disponible ensuite.");
          }).then(function () { if (apres) apres(); })
            .catch(function (e) { if (e.message !== "session") C.informer("Rechargement impossible", e.message); });
        } })));
    }
    if (d.bandeau_comfyui) {
      sortie.push(h("div", { class: "bandeau", role: "status", id: "bandeau-comfyui" },
        h("strong", { texte: "ComfyUI tourne et occupe la carte graphique." }), " ",
        h("button", { class: "petit", type: "button", id: "bouton-arreter-comfyui", texte: "Arrêter", onclick: function () {
          C.confirmer("Arrêter ComfyUI ?", "ComfyUI sera arrêté et la carte graphique rendue. Le chef de Crew ne sera rechargé que si vous le demandez.", "Arrêter").then(function (ok) {
            if (!ok) return;
            return api("POST", "/api/comfyui/arreter").then(function () { if (apres) apres(); });
          }).catch(function (e) { if (e.message !== "session") C.informer("Arrêt impossible", e.message); });
        } })));
    }
    return sortie;
  };

  // ---------------------------------------------------------------- page « Images »
  function coutPage() { var e = document.getElementById("img-cout"); return e; }
  function dessinerPage() {
    var r = S.racine; if (!r || C.courante() !== "images" || !S.opts) return;
    vider(r);
    r.appendChild(h("h2", { texte: "🎨 Images" }));
    r.appendChild(h("p", { class: "doux", texte: "Créez des images avec l'IA, ici ou depuis n'importe quelle salle (bouton 🎨 ou commande /image). Les images restent sur ce PC. Un moteur du nuage reçoit votre description ; avec la case « confidentiel », ou en mode Confidentiel / Ultra-confidentiel, seul ComfyUI (local) est utilisé." }));
    C.bandeauxComfyUI(S.comfy, charger).forEach(function (b) { r.appendChild(b); });
    if (S.resultat && S.resultat.etat === "erreur") r.appendChild(h("div", { class: "bandeau erreur", role: "alert", texte: S.resultat.message || "La création a échoué." }));
    if (S.resultat && S.resultat.etat === "annule") r.appendChild(h("div", { class: "bandeau", role: "status", texte: "Création annulée." }));
    if (S.resultat && S.resultat.etat === "termine") r.appendChild(h("div", { class: "bandeau ok", role: "status", texte: S.resultat.images.length + " image" + (S.resultat.images.length > 1 ? "s créées" : " créée") + " : elles sont en haut de la galerie." + (S.resultat.message ? " " + S.resultat.message : "") }));
    if (S.job) r.appendChild(bandeauJob(S.job));
    var f = champs(S.opts, S.etat, { inclurePrive: true });
    var bouton = h("button", { class: "bouton principal", id: "img-creer", type: "button", texte: "🎨 Créer l'image", onclick: creer });
    r.appendChild(h("div", { class: "carte" }, f.el, bouton));
    r.appendChild(h("h3", { texte: "Galerie" }));
    var g = h("div", { class: "galerie" });
    if (!S.images.length) g.appendChild(h("div", { class: "doux", texte: "Aucune image pour le moment." }));
    S.images.forEach(function (m) { g.appendChild(carte(m)); });
    r.appendChild(g);
  }
  function bandeauJob(j) {
    var texte = j.etat === "attente" ? "En attente" + (j.position ? " (position " + j.position + ")" : "") + "…" : (j.etape || "Création en cours…") + " — " + j.fait + " sur " + j.sur;
    return h("div", { class: "progression", role: "status", "aria-live": "polite" }, h("strong", { id: "img-progression", texte: texte }),
      h("div", { class: "barre", "aria-hidden": "true" }, h("span", { class: "barre-anim" })),
      h("button", { class: "petit", type: "button", id: "img-annuler", texte: "Annuler", onclick: function () { api("POST", "/api/images/jobs/" + j.id + "/annuler").catch(function () {}); } }));
  }
  function creer() {
    var e = S.etat;
    if (!(e.prompt || "").trim()) { C.informer("Description vide", "Décrivez l'image à créer."); return; }
    if (!e.moteur) { C.informer("Aucun moteur", "Aucun moteur d'images n'est disponible pour le moment."); return; }
    S.resultat = null;
    poster("/api/images", e, {}).then(function (job) { if (job) { S.job = job; dessinerPage(); suivre(job.id); } })
      .catch(function (er) { if (er.message !== "session") C.informer("Création impossible", er.message); });
  }
  function suivre(id) {
    clearTimeout(S.minuteur);
    S.minuteur = setTimeout(function () {
      api("GET", "/api/images/jobs/" + id).then(function (j) {
        if (j.etat === "attente" || j.etat === "en_cours") { S.job = j; if (C.courante() === "images") { dessinerPage(); suivre(id); } return; }
        S.job = null; S.resultat = j;
        if (C.courante() === "images") charger();
      }).catch(function (er) { S.job = null; if (er.message !== "session" && C.courante() === "images") dessinerPage(); });
    }, 1500);
  }
  function carte(m) {
    var url = "/api/images/" + m.id + "/fichier";
    return h("div", { class: "carte-image" },
      h("a", { href: url, target: "_blank", rel: "noopener", title: "Ouvrir en grand" }, h("img", { src: url, alt: m.prompt || "image créée", loading: "lazy" })),
      h("div", { class: "infos-image" },
        h("div", { class: "doux", texte: quand(m.ts) + " · " + (m.moteur_libelle || m.moteur) + (m.prive ? " · confidentiel" : "") + (m.cout_usd ? " · " + (m.cout_reel ? "" : "≈ ") + dollars(m.cout_usd) : "") }),
        h("div", { class: "prompt-image", title: m.prompt, texte: m.prompt }),
        h("div", { class: "actions" },
          h("a", { class: "petit", href: url + "?telecharger=1", texte: "Télécharger", download: "" }),
          h("button", { class: "petit", type: "button", texte: "Réutiliser la description", onclick: function () {
            S.etat.prompt = m.prompt; var p = document.getElementById("img-prompt"); if (p) { p.value = m.prompt; p.focus(); p.scrollIntoView({ block: "center" }); } } }),
          h("button", { class: "petit", type: "button", texte: "Supprimer", onclick: function () {
            C.confirmer("Supprimer cette image ?", "Elle sera effacée de ce PC (irréversible).", "Supprimer", "danger").then(function (ok) {
              if (!ok) return;
              api("DELETE", "/api/images/" + m.id).then(charger).catch(function (er) { C.informer("Suppression impossible", er.message); });
            }); } }))));
  }
  function charger() {
    Promise.all([api("GET", "/api/images/options"), api("GET", "/api/images"), api("GET", "/api/comfyui").catch(function () { return null; })]).then(function (res) {
      S.opts = res[0]; S.images = res[1].images; S.comfy = res[2];
      initEtat(S.opts, S.etat, S.etat.prive);
      dessinerPage();
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
