"use strict";
(function () {
  var f = document.getElementById("formulaire");
  var err = document.getElementById("erreur");
  var bouton = document.getElementById("envoyer");

  function montrer(el, texte) { el.textContent = texte; el.classList.toggle("cache", !texte); }

  fetch("/api/verrou", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
    if (!d.defini) { document.getElementById("non-defini").classList.remove("cache"); bouton.disabled = true; }
    if (d.connecte) { location.replace("/"); }
  }).catch(function () { montrer(err, "Le serveur ne répond pas."); });

  f.addEventListener("submit", function (e) {
    e.preventDefault();
    montrer(err, "");
    bouton.disabled = true;
    fetch("/api/connexion", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Centre": "1" },
      body: JSON.stringify({ nip: document.getElementById("nip").value,
                             secret: document.getElementById("secret").value })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) {
        if (x.ok) { location.replace("/"); return; }
        montrer(err, x.d.erreur || "Connexion refusée.");
        document.getElementById("secret").value = "";
        bouton.disabled = false;
      }).catch(function () { montrer(err, "Le serveur ne répond pas."); bouton.disabled = false; });
  });
})();
