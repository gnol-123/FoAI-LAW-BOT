/* ============================================================
   LoRRAai — Brand Emoji
   A custom glyph set in the Aperture geometric language.
   • Structural strokes use currentColor (adapt to light/dark)
   • Brass (#B7935A) is the single accent
   Drop-in & non-invasive: defines window.BrandEmoji and a
   self-healing, idempotent enhancer that swaps :shortcodes:
   and standard emoji inside chat messages for brand glyphs.
   No edits to chat.js required.
   ============================================================ */
(function () {
  "use strict";
  var B = "#B7935A";

  /* ---- glyph library (inner SVG markup, 24×24 grid) ---- */
  var G = {
    balance:
      '<circle cx="12" cy="4.3" r="1.1" fill="'+B+'" stroke="none"/>' +
      '<path d="M12 4.3V19"/><path d="M8 19h8"/><path d="M4 7.7h16"/>' +
      '<path d="M6 7.7V10.6"/><path d="M18 7.7V10.6"/>' +
      '<path d="M2.6 10.6a3.4 3.4 0 006.8 0z" stroke="'+B+'"/>' +
      '<path d="M14.6 10.6a3.4 3.4 0 006.8 0z" stroke="'+B+'"/>',
    court:
      '<path d="M3.5 9 12 4l8.5 5"/><path d="M4.5 9h15"/>' +
      '<path d="M5 9v8"/><path d="M12 9v8" stroke="'+B+'"/><path d="M19 9v8"/>' +
      '<path d="M3.5 17.5h17"/>',
    reasoning:
      '<circle cx="5" cy="12" r="2.1" fill="'+B+'" stroke="none"/>' +
      '<path d="M7.1 12h2.4"/><path d="M9.5 12 13 6.8"/><path d="M9.5 12h3.4"/><path d="M9.5 12 13 17.2"/>' +
      '<circle cx="15" cy="6.4" r="2"/><circle cx="15.3" cy="12" r="2"/><circle cx="15" cy="17.6" r="2"/>',
    document:
      '<path d="M7 3.5h6.5L19 9v9.5a2 2 0 01-2 2H7a2 2 0 01-2-2v-13a2 2 0 012-2z"/>' +
      '<path d="M13.3 3.6v4a1.2 1.2 0 001.2 1.2h4" stroke="'+B+'"/>' +
      '<path d="M8 12.5h8"/><path d="M8 15.5h8"/><path d="M8 18.5h5"/>',
    statute:
      '<path d="M12 6.4C10 5 7 5 4 5.6v12.8c3-.6 6-.6 8 .8"/>' +
      '<path d="M12 6.4C14 5 17 5 20 5.6v12.8c-3-.6-6-.6-8 .8"/>' +
      '<path d="M12 6.4V20" stroke="'+B+'"/>',
    precedent:
      '<rect x="4" y="5" width="16" height="3.6" rx="1.4" stroke="'+B+'"/>' +
      '<rect x="4" y="10.2" width="16" height="3.6" rx="1.4"/>' +
      '<rect x="4" y="15.4" width="16" height="3.6" rx="1.4"/>',
    verified:
      '<rect x="4" y="4" width="16" height="16" rx="5"/>' +
      '<path d="M8.5 12.3l2.4 2.4 4.6-5.1" stroke="'+B+'" stroke-width="2"/>',
    caveat:
      '<path d="M12 4.2 21 19H3z"/>' +
      '<path d="M12 10v4.2" stroke="'+B+'" stroke-width="2"/>' +
      '<circle cx="12" cy="16.8" r="1" fill="'+B+'" stroke="none"/>',
    research:
      '<circle cx="10.2" cy="10.2" r="6"/><path d="M14.6 14.6 20 20" stroke-width="2"/>' +
      '<path d="M7.6 9.4h5" stroke="'+B+'"/><path d="M7.6 11.6h3.2" stroke="'+B+'"/>',
    insight:
      '<path d="M11.5 3.5C11.5 7.5 12.5 8.5 16.5 10C12.5 11.5 11.5 12.5 11.5 16.5C11.5 12.5 10.5 11.5 6.5 10C10.5 8.5 11.5 7.5 11.5 3.5Z" fill="'+B+'" stroke="none"/>' +
      '<path d="M19 11C19 12.7 19.6 13.3 21.3 14C19.6 14.7 19 15.3 19 17C19 15.3 18.4 14.7 16.7 14C18.4 13.3 19 12.7 19 11Z" fill="'+B+'" stroke="none"/>',
    keypoint:
      '<path d="M12 13.5V20"/>' +
      '<path d="M12 3.5 16.5 8 12 12.5 7.5 8z" fill="'+B+'" stroke="'+B+'"/>',
    citation:
      '<path d="M9 5H6.5a1.5 1.5 0 00-1.5 1.5v11A1.5 1.5 0 006.5 19H9"/>' +
      '<path d="M15 5h2.5A1.5 1.5 0 0119 6.5v11a1.5 1.5 0 01-1.5 1.5H15"/>' +
      '<path d="M12 9.8 14.2 12 12 14.2 9.8 12z" fill="'+B+'" stroke="'+B+'"/>'
  };

  /* standard emoji → brand glyph (so the model can emit normal emoji too) */
  var STD = {
    "⚖️":"balance","⚖":"balance","🧠":"reasoning","📄":"document","📃":"document",
    "📝":"document","📚":"statute","📖":"statute","📕":"statute","🗂️":"precedent",
    "🗂":"precedent","✅":"verified","✔️":"verified","☑️":"verified","⚠️":"caveat",
    "⚠":"caveat","🔍":"research","🔎":"research","💡":"insight","✨":"insight",
    "📌":"keypoint","📍":"keypoint","🏛️":"court","🏛":"court","🔖":"citation"
  };

  function svg(name, size) {
    if (!G[name]) return "";
    var s = size || 18;
    return '<svg width="'+s+'" height="'+s+'" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true">' + G[name] + '</svg>';
  }

  /* ---- enhancer ---- */
  function esc(s){ return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  var stdKeys = Object.keys(STD).sort(function(a,b){ return b.length - a.length; });
  var RE = new RegExp("(" + stdKeys.map(esc).join("|") + ")|:([a-z0-9_]+):", "g");

  function replaceIn(node) {
    var text = node.nodeValue, m, last = 0, any = false;
    var frag = document.createDocumentFragment();
    RE.lastIndex = 0;
    while ((m = RE.exec(text))) {
      var name = m[1] ? STD[m[1]] : (G[m[2]] ? m[2] : null);
      if (!name || !G[name]) continue;
      any = true;
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      var span = document.createElement("span");
      span.className = "be-emoji";
      span.setAttribute("title", name);
      span.innerHTML = svg(name);
      frag.appendChild(span);
      last = m.index + m[0].length;
    }
    if (any) {
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    }
  }

  function process(root) {
    if (!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.nodeValue || !n.parentNode) return NodeFilter.FILTER_REJECT;
        var p = n.parentNode;
        if (p.closest && p.closest("code,pre,textarea,.msg-icon,.be-skip,.be-emoji")) return NodeFilter.FILTER_REJECT;
        return RE.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var nodes = [], n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(replaceIn);
  }

  /* idempotent, rAF-debounced observer — self-heals if chat.js re-renders */
  function install() {
    var target = document.getElementById("messages");
    if (!target) return;
    var raf = 0;
    var obs = new MutationObserver(function () {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(function () { process(target); });
    });
    obs.observe(target, { childList: true, subtree: true, characterData: true });
    process(target);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install);
  } else {
    install();
  }

  window.BrandEmoji = { svg: svg, names: Object.keys(G), map: G, std: STD, process: process };
})();
