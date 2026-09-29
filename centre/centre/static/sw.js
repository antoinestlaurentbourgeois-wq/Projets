"use strict";
// Service worker minimal : rend l'application installable, sans rien mettre en cache.
// Volontairement : aucune réponse du serveur n'est gardée (elles contiennent l'état de votre PC).
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function (e) {
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(function () {
      return new Response("Le Centre de contrôle est injoignable (PC éteint, serveur arrêté ou Tailscale coupé).",
        { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
    }));
  }
});
