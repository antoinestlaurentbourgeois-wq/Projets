"use strict";
// Capture du micro : blocs de 100 ms en PCM 16 bits (le contexte audio tourne à 24 000 Hz), envoyés à la page.
class CaptureMicro extends AudioWorkletProcessor {
  constructor() {
    super();
    this.tampon = new Float32Array(2400);
    this.n = 0;
  }
  process(entrees) {
    const canal = entrees[0] && entrees[0][0];
    if (!canal) return true;
    for (let i = 0; i < canal.length; i++) {
      this.tampon[this.n++] = canal[i];
      if (this.n === this.tampon.length) {
        const pcm = new Int16Array(this.n);
        for (let j = 0; j < this.n; j++) {
          const v = Math.max(-1, Math.min(1, this.tampon[j]));
          pcm[j] = v < 0 ? v * 0x8000 : v * 0x7fff;
        }
        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        this.n = 0;
      }
    }
    return true;
  }
}
registerProcessor("capture-micro", CaptureMicro);
