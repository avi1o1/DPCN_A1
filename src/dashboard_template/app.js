/* ===================================================================
 * Opinion Network Explorer
 *
 * One page, no dependencies, no network access. Everything it draws
 * comes from the JSON blob `build_dashboard.py` embedded above.
 *
 * Structure:
 *   1  payload + shared state
 *   2  small helpers (format, DOM, colour, tooltip)
 *   3  chrome: theme, network picker, section nav
 *   4  headline + stat tiles
 *   5  the node-link canvas
 *   6  the inspector + respondent profile
 *   7  the charts, one function each
 *   8  findings + boot
 * =================================================================== */

(function () {
  "use strict";

  /* ---------------------------------------------------------------
   * 1  payload + state
   * --------------------------------------------------------------- */

  var DATA = JSON.parse(document.getElementById("payload").textContent);

  var NET_LABEL = {
    overall: "Overall",
    technology: "Technology",
    education: "Education",
    ethics: "Ethics",
    environment: "Environment"
  };

  // a network keeps the same hue in every chart on the page: colour
  // follows the entity, never its rank in the current sort
  var NET_SLOT = {
    overall: "--s1",
    technology: "--s2",
    education: "--s3",
    ethics: "--s4",
    environment: "--s5"
  };

  // the network a topic name maps onto, for "colour by opinion"
  var NET_TOPIC = {
    overall: "overall",
    technology: "technology",
    education: "education",
    ethics: "ethics",
    environment: "environment"
  };

  var CENTRALITY_LABEL = {
    degree_centrality: "Degree",
    closeness_centrality: "Closeness",
    betweenness_centrality: "Betweenness",
    eigenvector_centrality: "Eigenvector"
  };

  var state = {
    network: "overall",
    colourBy: "community",
    sizeBy: "degree_centrality",
    showIsolates: true,
    showLabels: false,
    selected: null,
    hovered: null,
    highlightCommunity: null,
    centrality: "degree_centrality",
    sensMeasure: "y_giant_fraction"
  };

  /* ---------------------------------------------------------------
   * 2  helpers
   * --------------------------------------------------------------- */

  var $ = function (id) { return document.getElementById(id); };

  function el(tag, attrs, kids) {
    var node = document.createElement(tag);
    applyAttrs(node, attrs);
    appendKids(node, kids);
    return node;
  }

  function svg(tag, attrs, kids) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    applyAttrs(node, attrs);
    appendKids(node, kids);
    return node;
  }

  function applyAttrs(node, attrs) {
    if (!attrs) return;
    Object.keys(attrs).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "class") node.setAttribute("class", value);
      else if (key === "text") node.textContent = value;      // never innerHTML: ids come from a CSV
      else if (key === "html") node.innerHTML = value;         // only ever used with literals below
      else if (key.slice(0, 2) === "on") node.addEventListener(key.slice(2), value);
      else if (key === "style" && typeof value === "object") Object.assign(node.style, value);
      else node.setAttribute(key, value);
    });
  }

  function appendKids(node, kids) {
    if (!kids) return;
    (Array.isArray(kids) ? kids : [kids]).forEach(function (kid) {
      if (kid === null || kid === undefined || kid === false) return;
      node.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
    });
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  function fmt(value, digits) {
    if (value === null || value === undefined || (typeof value === "number" && !isFinite(value))) return "n/a";
    return Number(value).toFixed(digits === undefined ? 2 : digits);
  }

  function pct(value, digits) {
    return fmt(value * 100, digits === undefined ? 0 : digits) + "%";
  }

  /** "+0.31" / "−0.08" / "0.00". A true zero carries no sign. */
  function signed(value, digits) {
    var places = digits === undefined ? 2 : digits;
    if (Math.abs(value) < 0.5 * Math.pow(10, -places)) return fmt(0, places);
    return (value > 0 ? "+" : "−") + fmt(Math.abs(value), places);
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  // CSS custom properties resolved to real colours, so canvas can use them.
  // Invalidated whenever the theme changes.
  var tokenCache = {};

  function token(name) {
    if (tokenCache[name]) return tokenCache[name];
    var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    tokenCache[name] = value || "#888";
    return tokenCache[name];
  }

  function dropTokenCache() {
    tokenCache = {};
  }

  function parseColour(hex) {
    var clean = hex.trim().replace("#", "");
    if (clean.length === 3) clean = clean.split("").map(function (c) { return c + c; }).join("");
    return [
      parseInt(clean.slice(0, 2), 16),
      parseInt(clean.slice(2, 4), 16),
      parseInt(clean.slice(4, 6), 16)
    ];
  }

  function mix(fromHex, toHex, t) {
    var a = parseColour(fromHex), b = parseColour(toHex);
    return "rgb(" + [0, 1, 2].map(function (i) {
      return Math.round(lerp(a[i], b[i], clamp(t, 0, 1)));
    }).join(",") + ")";
  }

  function rgba(hex, alpha) {
    var c = parseColour(hex);
    return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + alpha + ")";
  }

  /** Diverging blue -> neutral -> red, centred on `mid`. */
  function divergingColour(value, mid, halfRange) {
    if (value === null || value === undefined) return token("--surface-sunken");
    var t = clamp((value - mid) / (halfRange || 1), -1, 1);
    if (t >= 0) return mix(token("--div-mid"), token("--div-high"), Math.pow(t, 0.75));
    return mix(token("--div-mid"), token("--div-low"), Math.pow(-t, 0.75));
  }

  /** Ink that stays legible on top of a diverging fill. */
  function inkOn(value, mid, halfRange) {
    var t = Math.abs(clamp((value - mid) / (halfRange || 1), -1, 1));
    return t > 0.55 ? "#ffffff" : token("--ink-2");
  }

  // ---- tooltip ----------------------------------------------------

  var tip = $("tip");

  function showTip(event, title, rows, foot, keyColour) {
    clear(tip);
    var head = el("div", { class: "tip__title" });
    if (keyColour) head.appendChild(el("span", { class: "key", style: { width: "9px", height: "9px", borderRadius: "3px", background: keyColour, display: "block" } }));
    head.appendChild(document.createTextNode(title));
    tip.appendChild(head);

    if (rows && rows.length) {
      var list = el("dl", { class: "tip__rows" });
      rows.forEach(function (row) {
        list.appendChild(el("dt", { text: row[0] }));
        list.appendChild(el("dd", { text: row[1] }));
      });
      tip.appendChild(list);
    }
    if (foot) tip.appendChild(el("div", { class: "tip__foot", text: foot }));

    tip.classList.add("is-on");
    placeTip(event);
  }

  function placeTip(event) {
    var box = tip.getBoundingClientRect();
    var x = clamp(event.clientX, box.width / 2 + 8, window.innerWidth - box.width / 2 - 8);
    var y = event.clientY;
    if (y - box.height - 16 < 0) {
      tip.style.transform = "translate(-50%, 0) translateY(18px)";
    } else {
      tip.style.transform = "translate(-50%, -100%) translateY(-10px)";
    }
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  }

  function hideTip() {
    tip.classList.remove("is-on");
  }

  // ---- table twins -------------------------------------------------

  /** Build a <table> from a header row and a list of rows. */
  function buildTable(head, rows) {
    var wrap = el("div", { class: "table-wrap" });
    var table = el("table");
    var thead = el("thead");
    var hrow = el("tr");
    head.forEach(function (cell) { hrow.appendChild(el("th", { scope: "col", text: cell })); });
    thead.appendChild(hrow);
    table.appendChild(thead);

    var tbody = el("tbody");
    rows.forEach(function (row) {
      var tr = el("tr");
      row.forEach(function (cell, i) {
        tr.appendChild(i === 0 ? el("th", { scope: "row", text: String(cell) }) : el("td", { text: String(cell) }));
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function setTable(containerId, head, rows) {
    var host = $(containerId);
    if (!host) return;
    clear(host).appendChild(buildTable(head, rows));
  }

  function wireTableToggles() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-table-for]"), function (button) {
      button.addEventListener("click", function () {
        var target = $(button.getAttribute("data-table-for"));
        var open = target.hidden;
        target.hidden = !open;
        button.setAttribute("aria-pressed", String(open));
      });
    });
  }

  /* ---------------------------------------------------------------
   * 3  chrome
   * --------------------------------------------------------------- */

  function currentNetwork() {
    return DATA.networks[state.network];
  }

  function nodeById(id) {
    var nodes = currentNetwork().nodes;
    for (var i = 0; i < nodes.length; i++) if (nodes[i].id === id) return nodes[i];
    return null;
  }

  function initTheme() {
    var stored = null;
    try { stored = localStorage.getItem("dpcn-theme"); } catch (err) { stored = null; }
    if (stored === "light" || stored === "dark") document.documentElement.setAttribute("data-theme", stored);
    paintThemeLabel();

    $("theme-toggle").addEventListener("click", function () {
      var explicit = document.documentElement.getAttribute("data-theme");
      var dark = explicit ? explicit === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      var next = dark ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("dpcn-theme", next); } catch (err) { /* private window */ }
      dropTokenCache();
      paintThemeLabel();
      renderAll();
    });

    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
      if (!document.documentElement.getAttribute("data-theme")) {
        dropTokenCache();
        paintThemeLabel();
        renderAll();
      }
    });
  }

  function paintThemeLabel() {
    var explicit = document.documentElement.getAttribute("data-theme");
    var dark = explicit ? explicit === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    $("theme-label").textContent = dark ? "Dark" : "Light";
  }

  function initNetworkPicker() {
    var host = clear($("netpicker"));
    DATA.meta.networks.forEach(function (name) {
      var button = el("button", {
        type: "button",
        "aria-pressed": String(name === state.network),
        onclick: function () { selectNetwork(name); }
      }, [
        el("span", { class: "key", style: { background: "var(" + NET_SLOT[name] + ")" } }),
        NET_LABEL[name]
      ]);
      host.appendChild(button);
    });
  }

  function selectNetwork(name) {
    if (name === state.network) return;
    var previous = state.network;
    state.network = name;
    state.highlightCommunity = null;
    Array.prototype.forEach.call($("netpicker").children, function (button, i) {
      button.setAttribute("aria-pressed", String(DATA.meta.networks[i] === name));
    });
    graph.morphFrom(previous);
    renderAll();
  }

  function initSectionNav() {
    var links = Array.prototype.slice.call(document.querySelectorAll(".subnav a"));
    var sections = links.map(function (link) { return $(link.getAttribute("href").slice(1)); });

    function mark() {
      var best = 0;
      sections.forEach(function (section, i) {
        if (section && section.getBoundingClientRect().top <= 200) best = i;
      });
      links.forEach(function (link, i) { link.classList.toggle("is-current", i === best); });
    }

    addEventListener("scroll", mark, { passive: true });
    mark();
  }

  function initSegments() {
    buildSegment("colour-mode", [
      { value: "community", label: "Community" },
      { value: "opinion", label: "Opinion" }
    ], state.colourBy, function (value) {
      state.colourBy = value;
      state.highlightCommunity = null;
      renderLegend();
      graph.draw();
    });

    buildSegment("size-mode", [
      { value: "degree_centrality", label: "Degree" },
      { value: "closeness_centrality", label: "Closeness" },
      { value: "betweenness_centrality", label: "Betweenness" },
      { value: "eigenvector_centrality", label: "Eigenvector" },
      { value: "uniform", label: "Uniform" }
    ], state.sizeBy, function (value) {
      state.sizeBy = value;
      graph.draw();
    });

    buildSegment("centrality-pick", DATA.meta.centralities.map(function (key) {
      return { value: key, label: CENTRALITY_LABEL[key] };
    }), state.centrality, function (value) {
      state.centrality = value;
      renderCentrality();
      renderInspector();
    });

    buildSegment("sens-measure", [
      { value: "y_giant_fraction", label: "Giant component" },
      { value: "y_n_isolates", label: "Isolates" },
      { value: "y_avg_clustering", label: "Clustering" },
      { value: "y_n_edges", label: "Edges" }
    ], state.sensMeasure, function (value) {
      state.sensMeasure = value;
      renderSensitivity();
    });

    $("toggle-isolates").addEventListener("change", function (event) {
      state.showIsolates = event.target.checked;
      graph.fit(true);
      graph.draw();
    });

    $("toggle-labels").addEventListener("change", function (event) {
      state.showLabels = event.target.checked;
      graph.draw();
    });
  }

  function buildSegment(hostId, options, current, onPick) {
    var host = clear($(hostId));
    options.forEach(function (option) {
      host.appendChild(el("button", {
        type: "button",
        "aria-pressed": String(option.value === current),
        text: option.label,
        onclick: function () {
          Array.prototype.forEach.call(host.children, function (other, i) {
            other.setAttribute("aria-pressed", String(options[i].value === option.value));
          });
          onPick(option.value);
        }
      }));
    });
  }

  /* ---------------------------------------------------------------
   * 4  headline + tiles
   * --------------------------------------------------------------- */

  function renderHero() {
    var stats = DATA.networkStats[state.network];
    var giant = stats.giant_fraction;

    $("hero-eyebrow").textContent = NET_LABEL[state.network] + " network";
    clear($("hero-figure"));
    $("hero-figure").appendChild(document.createTextNode(Math.round(giant * 100)));
    $("hero-figure").appendChild(el("span", { text: "%" }));

    var connected = Math.round(giant * stats.n_nodes);
    var outside = stats.n_nodes - connected;
    var fragments = stats.n_components - 1;
    var paired = outside - stats.n_isolated;

    // when every fragment is a single person, saying it twice reads as a bug
    var rest = paired === 0
      ? "The other " + outside + " have no similar partner at all."
      : "The other " + outside + " are in " + fragments + " smaller groups: " + paired +
        " in small clusters, and " + stats.n_isolated + " completely alone.";

    $("hero-caption").textContent =
      "of the class is in one big connected group. That is " + connected + " out of " + stats.n_nodes +
      " people. " + rest;
  }

  function renderTiles() {
    var stats = DATA.networkStats[state.network];
    var degroot = DATA.dynamics.degroot[state.network];

    var tiles = [
      {
        label: "Edges",
        tip: "How many connections exist in this network. Out of 3,741 possible pairs among 87 people.",
        value: String(stats.n_edges),
        meter: stats.density
      },
      {
        label: "Average degree",
        tip: "On average, how many connections each person has. Someone with degree 0 has no similar partner.",
        value: fmt(stats.avg_degree, 1),
        meter: stats.avg_degree / 20
      },
      {
        label: "Clustering",
        tip: "How often someone's friends are also friends with each other. Higher means tighter groups. 1.0 would mean everyone's friends all know each other.",
        value: fmt(stats.avg_clustering, 2),
        meter: stats.avg_clustering
      },
      {
        label: "Isolates",
        tip: "People with zero connections. Their answers are not similar enough to anyone else to make the top-10% cut.",
        value: String(stats.n_isolated),
        suffix: " of " + stats.n_nodes,
        meter: stats.n_isolated / stats.n_nodes
      },
      {
        label: "Consensus steps",
        tip: "How many rounds of opinion-averaging it takes for the connected group to agree on one number. Fewer steps means the group is more tightly connected.",
        value: String(degroot.steps_to_converge_giant),
        meter: degroot.steps_to_converge_giant / 80
      }
    ];

    var host = clear($("tiles"));
    tiles.forEach(function (tile) {
      var labelEl = el("div", { class: "tile__label" }, [
        tile.label,
        el("span", { class: "info-icon", "data-tip": tile.tip, text: "i" })
      ]);
      host.appendChild(el("div", { class: "tile" }, [
        labelEl,
        el("div", { class: "tile__value" }, [
          tile.value,
          tile.suffix ? el("small", { text: tile.suffix }) : null
        ]),
        el("div", { class: "tile__meter" }, [
          el("i", { style: { width: pct(clamp(tile.meter, 0, 1)) } })
        ])
      ]));
    });
  }

  /* ---------------------------------------------------------------
   * 5  the canvas
   * --------------------------------------------------------------- */

  var graph = (function () {
    var host = $("stage-canvas");
    var canvas = $("graph");
    var ctx = canvas.getContext("2d");

    var view = { scale: 1, x: 0, y: 0 };
    var size = { w: 1, h: 1, dpr: 1 };

    // live positions, keyed by respondent id, so a network switch can
    // tween the same dot from where it was to where it now belongs
    var live = {};
    var morph = null;
    var dragging = null;
    var panning = null;
    var raf = null;

    function nodes() {
      return currentNetwork().nodes;
    }

    function visible(node) {
      return state.showIsolates || !node.isolate;
    }

    function syncSize() {
      var rect = host.getBoundingClientRect();
      size.dpr = Math.min(window.devicePixelRatio || 1, 2);
      size.w = rect.width;
      size.h = rect.height;
      canvas.width = Math.round(size.w * size.dpr);
      canvas.height = Math.round(size.h * size.dpr);
      ctx.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
    }

    function seed() {
      nodes().forEach(function (node) {
        if (!live[node.id]) live[node.id] = { x: node.x, y: node.y };
      });
    }

    function position(node) {
      var point = live[node.id];
      return point || { x: node.x, y: node.y };
    }

    function toScreen(point) {
      return {
        x: point.x * view.scale + view.x,
        y: point.y * view.scale + view.y
      };
    }

    function fit(animate) {
      var shown = nodes().filter(visible);
      if (!shown.length) return;
      var xs = shown.map(function (n) { return position(n).x; });
      var ys = shown.map(function (n) { return position(n).y; });
      var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
      var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
      var pad = 56;
      var scale = Math.min(
        (size.w - pad * 2) / Math.max(maxX - minX, 0.001),
        (size.h - pad * 2) / Math.max(maxY - minY, 0.001)
      );
      var target = {
        scale: scale,
        x: size.w / 2 - (minX + maxX) / 2 * scale,
        y: size.h / 2 - (minY + maxY) / 2 * scale
      };
      if (animate) tweenView(target);
      else { view = target; draw(); }
    }

    function tweenView(target) {
      var from = { scale: view.scale, x: view.x, y: view.y };
      var start = performance.now();
      var duration = 420;
      (function step(now) {
        var t = clamp((now - start) / duration, 0, 1);
        var e = easeOut(t);
        view.scale = lerp(from.scale, target.scale, e);
        view.x = lerp(from.x, target.x, e);
        view.y = lerp(from.y, target.y, e);
        draw();
        if (t < 1) requestAnimationFrame(step);
      })(performance.now());
    }

    function easeOut(t) {
      return 1 - Math.pow(1 - t, 3);
    }

    /** Animate every dot from its place in `fromNetwork` to the new one. */
    function morphFrom(fromNetwork) {
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
        live = {};
        seed();
        fit(false);
        return;
      }
      var from = {};
      DATA.networks[fromNetwork].nodes.forEach(function (node) {
        from[node.id] = live[node.id] || { x: node.x, y: node.y };
      });
      var to = {};
      nodes().forEach(function (node) { to[node.id] = { x: node.x, y: node.y }; });

      morph = { from: from, to: to, start: performance.now(), duration: 760 };
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tickMorph);

      // aim the viewport at where the nodes are going, in parallel
      var saved = live;
      live = to;
      var shown = nodes().filter(visible);
      if (shown.length) {
        var xs = shown.map(function (n) { return to[n.id].x; });
        var ys = shown.map(function (n) { return to[n.id].y; });
        var pad = 56;
        var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
        var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
        var scale = Math.min(
          (size.w - pad * 2) / Math.max(maxX - minX, 0.001),
          (size.h - pad * 2) / Math.max(maxY - minY, 0.001)
        );
        tweenView({
          scale: scale,
          x: size.w / 2 - (minX + maxX) / 2 * scale,
          y: size.h / 2 - (minY + maxY) / 2 * scale
        });
      }
      live = saved;
    }

    function tickMorph(now) {
      var t = clamp((now - morph.start) / morph.duration, 0, 1);
      var e = easeOut(t);
      Object.keys(morph.to).forEach(function (id) {
        var a = morph.from[id] || morph.to[id];
        var b = morph.to[id];
        live[id] = { x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e) };
      });
      draw();
      if (t < 1) raf = requestAnimationFrame(tickMorph);
      else { morph = null; raf = null; }
    }

    // ---- encodings ----

    function radiusOf(node) {
      if (state.sizeBy === "uniform") return 6;
      var slot = DATA.meta.centralities.indexOf(state.sizeBy);
      var values = nodes().map(function (n) { return n.c[slot]; });
      var max = Math.max.apply(null, values) || 1;
      // sqrt so area, not radius, tracks the value
      return 4 + 11 * Math.sqrt(clamp(node.c[slot] / max, 0, 1));
    }

    /* Four hues at most.
     *
     * Beyond four simultaneous categorical hues the pairs stop being reliably
     * distinguishable under colour-vision deficiency. That was measured with
     * the palette validator rather than judged by eye. So the four largest groups get a hue and any
     * further real group (3+ members) gets the neutral tone plus an outline:
     * the outline is a second, non-colour channel saying "still a group", which
     * keeps a 7-person community from reading as unclustered noise. Singletons
     * get the neutral tone and no outline. Every group, hue or not, stays
     * individually selectable from the legend.
     */
    function communitySlots() {
      var groups = currentNetwork().communities;
      var slots = {};
      var used = 0;
      groups.forEach(function (group) {
        if (group.size >= 3 && used < 4) {
          used += 1;
          slots[group.id] = { fill: token("--c" + used), outlined: false };
        } else if (group.size >= 3) {
          slots[group.id] = { fill: token("--c-other"), outlined: true };
        } else if (group.size > 1) {
          slots[group.id] = { fill: token("--c-other"), outlined: true };
        } else {
          slots[group.id] = { fill: token("--c-none"), outlined: false };
        }
      });
      return slots;
    }

    var slotCache = null;

    function slotFor(node) {
      if (!slotCache) slotCache = communitySlots();
      return slotCache[node.community] || { fill: token("--c-none"), outlined: false };
    }

    function colourOf(node) {
      if (state.colourBy === "opinion") {
        var scale = opinionScale();
        return divergingColour(opinionOf(node), scale.mid, scale.half);
      }
      return slotFor(node).fill;
    }

    function outlined(node) {
      return state.colourBy === "community" && slotFor(node).outlined;
    }

    function opinionOf(node) {
      var person = DATA.respondents[node.id];
      var topic = NET_TOPIC[state.network];
      return topic === "overall" ? person.overall : person.topicMeans[topic];
    }

    function opinionScale() {
      var topic = NET_TOPIC[state.network];
      var mid = DATA.population[topic];
      var half = 0;
      nodes().forEach(function (node) {
        half = Math.max(half, Math.abs(opinionOf(node) - mid));
      });
      return { mid: mid, half: half || 1 };
    }

    function dimmed(node) {
      if (state.highlightCommunity !== null && state.colourBy === "community") {
        return node.community !== state.highlightCommunity;
      }
      var focus = state.hovered || state.selected;
      if (!focus) return false;
      if (node.id === focus) return false;
      return !isNeighbour(focus, node.id);
    }

    var neighbourCache = {};

    function neighbours(id) {
      var key = state.network + "|" + id;
      if (neighbourCache[key]) return neighbourCache[key];
      var list = currentNetwork().nodes;
      var index = -1;
      for (var i = 0; i < list.length; i++) if (list[i].id === id) { index = i; break; }
      var set = {};
      currentNetwork().edges.forEach(function (edge) {
        if (edge[0] === index) set[list[edge[1]].id] = edge[2];
        else if (edge[1] === index) set[list[edge[0]].id] = edge[2];
      });
      neighbourCache[key] = set;
      return set;
    }

    function isNeighbour(a, b) {
      return Object.prototype.hasOwnProperty.call(neighbours(a), b);
    }

    // ---- drawing ----

    function draw() {
      var net = currentNetwork();
      var list = net.nodes;
      ctx.clearRect(0, 0, size.w, size.h);

      var focus = state.hovered || state.selected;
      var surface = token("--surface");
      var edgeInk = token("--ink-3");

      // edges first, so nodes always sit on top of them
      net.edges.forEach(function (edge) {
        var a = list[edge[0]], b = list[edge[1]];
        if (!visible(a) || !visible(b)) return;
        var pa = toScreen(position(a)), pb = toScreen(position(b));

        var hot = focus && (a.id === focus || b.id === focus);
        var muted = (focus && !hot) ||
          (state.highlightCommunity !== null && state.colourBy === "community" &&
            (a.community !== state.highlightCommunity || b.community !== state.highlightCommunity));

        // weight carries edge opacity; similarities sit in a narrow band just
        // above the 0.90-quantile cut, so it is stretched to stay visible
        ctx.strokeStyle = hot
          ? rgba(token("--s1"), 0.8)
          : rgba(edgeInk, muted ? 0.08 : clamp(0.26 + 0.5 * (edge[2] - 0.55), 0.14, 0.7));
        ctx.lineWidth = hot ? 1.8 : 1;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.stroke();
      });

      // a soft halo under the focused node, the only decorative ink here
      if (focus) {
        var target = null;
        for (var i = 0; i < list.length; i++) if (list[i].id === focus) { target = list[i]; break; }
        if (target && visible(target)) {
          var point = toScreen(position(target));
          var glow = ctx.createRadialGradient(point.x, point.y, 0, point.x, point.y, 46);
          glow.addColorStop(0, rgba(token("--s1"), 0.22));
          glow.addColorStop(1, rgba(token("--s1"), 0));
          ctx.fillStyle = glow;
          ctx.beginPath();
          ctx.arc(point.x, point.y, 46, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      list.forEach(function (node) {
        if (!visible(node)) return;
        var point = toScreen(position(node));
        var radius = radiusOf(node);
        var faded = dimmed(node);

        ctx.globalAlpha = faded ? 0.22 : 1;

        // 2px surface ring keeps overlapping dots legible
        ctx.beginPath();
        ctx.arc(point.x, point.y, radius + 2, 0, Math.PI * 2);
        ctx.fillStyle = surface;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = colourOf(node);
        ctx.fill();

        // the non-colour channel for groups past the fourth hue
        if (outlined(node)) {
          ctx.strokeStyle = token("--ink");
          ctx.lineWidth = 1.6;
          ctx.beginPath();
          ctx.arc(point.x, point.y, radius - 0.8, 0, Math.PI * 2);
          ctx.stroke();
        }

        if (node.id === state.selected) {
          ctx.strokeStyle = token("--ink");
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(point.x, point.y, radius + 4.5, 0, Math.PI * 2);
          ctx.stroke();
        }

        ctx.globalAlpha = 1;

        if (state.showLabels && !faded) {
          ctx.font = "600 10px system-ui, -apple-system, 'Segoe UI', sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.lineWidth = 3;
          ctx.strokeStyle = surface;
          ctx.strokeText(node.id, point.x, point.y - radius - 8);
          ctx.fillStyle = token("--ink-2");
          ctx.fillText(node.id, point.x, point.y - radius - 8);
        }
      });
    }

    // ---- interaction ----

    function pick(event) {
      var rect = host.getBoundingClientRect();
      var mx = event.clientX - rect.left, my = event.clientY - rect.top;
      var list = currentNetwork().nodes;
      var best = null, bestDist = Infinity;
      list.forEach(function (node) {
        if (!visible(node)) return;
        var point = toScreen(position(node));
        var dist = Math.hypot(point.x - mx, point.y - my);
        // hit area is the mark plus slack, never only the painted pixels
        if (dist < Math.max(radiusOf(node) + 8, 13) && dist < bestDist) {
          best = node;
          bestDist = dist;
        }
      });
      return best;
    }

    function describe(node) {
      var ranks = currentNetwork().ranks;
      var rows = DATA.meta.centralities.map(function (key, i) {
        return [CENTRALITY_LABEL[key], fmt(node.c[i], 3) + "  (#" + ranks[key][node.id] + ")"];
      });
      rows.unshift(["Degree", String(node.degree)]);
      rows.push(["Opinion, this topic", fmt(opinionOf(node), 2)]);
      var foot = node.isolate
        ? "No connections. Never changes opinion in the averaging model."
        : "Community " + node.community + " · " + (node.inGiant ? "in the main group" : "in a smaller group") +
          " · opinion settles at " + fmt(node.degroot, 2);
      return { title: "Respondent " + node.id, rows: rows, foot: foot, colour: colourOf(node) };
    }

    host.addEventListener("pointermove", function (event) {
      if (panning) {
        view.x = panning.viewX + (event.clientX - panning.x);
        view.y = panning.viewY + (event.clientY - panning.y);
        draw();
        return;
      }
      if (dragging) {
        var rect = host.getBoundingClientRect();
        live[dragging.id] = {
          x: (event.clientX - rect.left - view.x) / view.scale,
          y: (event.clientY - rect.top - view.y) / view.scale
        };
        draw();
        return;
      }

      var node = pick(event);
      var id = node ? node.id : null;
      if (id !== state.hovered) {
        state.hovered = id;
        draw();
      }
      if (node) {
        var info = describe(node);
        showTip(event, info.title, info.rows, info.foot, info.colour);
      } else {
        hideTip();
      }
    });

    host.addEventListener("pointerleave", function () {
      if (state.hovered) { state.hovered = null; draw(); }
      hideTip();
    });

    host.addEventListener("pointerdown", function (event) {
      host.setPointerCapture(event.pointerId);
      var node = pick(event);
      if (node) {
        dragging = node;
      } else {
        panning = { x: event.clientX, y: event.clientY, viewX: view.x, viewY: view.y };
        host.classList.add("is-dragging");
      }
    });

    host.addEventListener("pointerup", function (event) {
      if (dragging) {
        var node = pick(event);
        if (node && node.id === dragging.id) select(node.id);
      }
      dragging = null;
      panning = null;
      host.classList.remove("is-dragging");
    });

    host.addEventListener("wheel", function (event) {
      event.preventDefault();
      var rect = host.getBoundingClientRect();
      var mx = event.clientX - rect.left, my = event.clientY - rect.top;
      var factor = Math.exp(-event.deltaY * 0.0016);
      var next = clamp(view.scale * factor, 12, 900);
      // keep the point under the cursor fixed while zooming
      view.x = mx - (mx - view.x) * (next / view.scale);
      view.y = my - (my - view.y) * (next / view.scale);
      view.scale = next;
      draw();
    }, { passive: false });

    function zoomBy(factor) {
      var next = clamp(view.scale * factor, 12, 900);
      view.x = size.w / 2 - (size.w / 2 - view.x) * (next / view.scale);
      view.y = size.h / 2 - (size.h / 2 - view.y) * (next / view.scale);
      view.scale = next;
      draw();
    }

    $("zoom-in").addEventListener("click", function () { zoomBy(1.3); });
    $("zoom-out").addEventListener("click", function () { zoomBy(1 / 1.3); });
    $("zoom-fit").addEventListener("click", function () { fit(true); });

    addEventListener("resize", function () {
      syncSize();
      fit(false);
    });

    return {
      init: function () { syncSize(); seed(); fit(false); },
      draw: draw,
      fit: fit,
      morphFrom: function (from) { slotCache = null; neighbourCache = {}; morphFrom(from); },
      invalidate: function () { slotCache = null; seed(); },
      colourOf: colourOf,
      communitySlots: function () { if (!slotCache) slotCache = communitySlots(); return slotCache; },
      opinionScale: opinionScale,
      opinionOf: opinionOf
    };
  })();

  function select(id) {
    state.selected = state.selected === id ? null : id;
    graph.draw();
    renderInspector();
    renderProfile();
    renderCentrality();
  }

  /* ---------------------------------------------------------------
   * legend for the canvas
   * --------------------------------------------------------------- */

  function renderLegend() {
    var host = clear($("legend-body"));

    if (state.colourBy === "opinion") {
      var topic = NET_TOPIC[state.network];
      var scale = graph.opinionScale();
      $("legend-title").textContent = "Mean " +
        (topic === "overall" ? "score, all 60 questions" : topic + " score");
      host.appendChild(el("div", { class: "legend-scale" }, [
        el("span", { text: fmt(scale.mid - scale.half, 1) }),
        el("i"),
        el("span", { text: fmt(scale.mid + scale.half, 1) })
      ]));
      host.appendChild(el("div", {
        class: "legend-scale",
        style: { marginTop: "6px" },
        text: "Grey middle = class average, " + fmt(scale.mid, 2)
      }));
      return;
    }

    $("legend-title").textContent = "Community groups";
    var slots = graph.communitySlots();
    var groups = currentNetwork().communities;
    var rows = el("div", { class: "legend-rows" });

    groups.filter(function (group) { return group.size >= 3; }).forEach(function (group) {
      var slot = slots[group.id];
      rows.appendChild(el("button", {
        type: "button",
        class: "legend-row",
        "aria-pressed": String(state.highlightCommunity === group.id),
        onclick: function () {
          state.highlightCommunity = state.highlightCommunity === group.id ? null : group.id;
          renderLegend();
          graph.draw();
        }
      }, [
        el("span", {
          class: "key",
          style: {
            background: slot.fill,
            boxShadow: slot.outlined ? "inset 0 0 0 1.5px var(--ink)" : "none"
          }
        }),
        el("span", { text: "Community " + group.id }),
        el("span", { class: "count", text: String(group.size) })
      ]));
    });

    var small = groups.filter(function (group) { return group.size < 3; });
    if (small.length) {
      var people = small.reduce(function (sum, group) { return sum + group.size; }, 0);
      rows.appendChild(el("div", { class: "legend-row", style: { cursor: "default" } }, [
        el("span", { class: "key", style: { background: token("--c-none") } }),
        el("span", { text: small.length + " groups of 1 or 2" }),
        el("span", { class: "count", text: String(people) })
      ]));
    }

    host.appendChild(rows);

    var coloured = groups.filter(function (g) { return g.size >= 3; }).length;
    if (coloured > 4) {
      host.appendChild(el("div", {
        class: "legend-scale",
        style: { marginTop: "7px", display: "block", lineHeight: "1.45" },
        text: "Only the four largest groups get their own colour. The rest use outlines so you can still tell them apart. Click any row to highlight that group."
      }));
    } else {
      host.appendChild(el("div", {
        class: "legend-scale",
        style: { marginTop: "7px", display: "block" },
        text: "Click a row to highlight that group."
      }));
    }
  }

  /* ---------------------------------------------------------------
   * 6  inspector + profile
   * --------------------------------------------------------------- */

  function initSearch() {
    var list = clear($("respondent-ids"));
    Object.keys(DATA.respondents).forEach(function (id) {
      list.appendChild(el("option", { value: id }));
    });

    $("search").addEventListener("input", function (event) {
      var id = event.target.value.trim();
      if (DATA.respondents[id]) {
        state.selected = id;
        graph.draw();
        renderInspector();
        renderProfile();
        renderCentrality();
      }
    });
  }

  function renderInspector() {
    var host = clear($("inspector-body"));

    if (!state.selected) {
      host.appendChild(el("p", {
        class: "inspector__empty",
        text: "Click a dot in the network, search by id, or pick a bar from the centrality chart. " +
          "You will see that person's centrality scores, their community, and how their answers compare to the class."
      }));
      return;
    }

    var node = nodeById(state.selected);
    var person = DATA.respondents[state.selected];
    if (!node) return;

    var ranks = currentNetwork().ranks;

    host.appendChild(el("div", { class: "person" }, [
      el("span", { class: "person__dot", style: { background: graph.colourOf(node) } }),
      el("div", {}, [
        el("div", { class: "person__id", text: "Respondent " + node.id }),
        el("div", { class: "person__meta" }, [
          node.isolate ? "No edges in this network" : node.degree + " connections"
        ])
      ])
    ]));

    host.appendChild(el("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "12px" } }, [
      el("span", { class: "chip" }, [
        el("span", { class: "key", style: { background: graph.communitySlots()[node.community].fill } }),
        "Community " + node.community
      ]),
      el("span", { class: "chip", text: node.inGiant ? "In the main group" : (node.isolate ? "No connections" : "Smaller group") }),
      person.n_missing ? el("span", { class: "chip", text: person.n_missing + " unanswered" }) : null
    ]));

    var kv = el("dl", { class: "kv" });
    DATA.meta.centralities.forEach(function (key, i) {
      kv.appendChild(el("dt", { text: CENTRALITY_LABEL[key] }));
      kv.appendChild(el("dd", {}, [
        fmt(node.c[i], 3),
        el("span", { class: "rank", text: "#" + ranks[key][node.id] })
      ]));
    });
    kv.appendChild(el("dt", { text: "Final opinion (DeGroot)" }));
    kv.appendChild(el("dd", { text: fmt(node.degroot, 2) }));
    host.appendChild(kv);

    host.appendChild(el("div", { class: "inspector__sub", text: "Opinion vs. the class" }));
    host.appendChild(opinionBars(person));

    host.appendChild(el("p", {
      class: "note",
      style: { marginTop: "12px" },
      text: node.isolate
        ? "With no connections, this person's opinion never changes. They stay at their starting score."
        : "The tick mark on each bar shows the class average for that topic."
    }));
  }

  /** One bar per topic, drawn from a shared zero baseline, with the class mean ticked. */
  function opinionBars(person) {
    var host = el("div", { class: "opbars" });
    var topics = DATA.meta.topics;
    var span = 2; // scores run -2..+2

    topics.concat(["Overall"]).forEach(function (topic) {
      var key = topic.toLowerCase();
      var value = key === "overall" ? person.overall : person.topicMeans[key];
      var mean = DATA.population[key];

      var zero = 50;
      var width = Math.abs(value) / span * 50;
      var left = value >= 0 ? zero : zero - width;

      host.appendChild(el("div", { class: "opbar" }, [
        el("span", { text: topic }),
        el("div", { class: "opbar__track" }, [
          el("i", { class: "opbar__zero", style: { left: zero + "%" } }),
          el("i", {
            class: "opbar__fill",
            style: {
              left: left + "%",
              width: Math.max(width, 0.6) + "%",
              background: value >= 0 ? "var(--s1)" : "var(--s8)"
            }
          }),
          el("i", {
            class: "opbar__pop",
            style: { left: (zero + mean / span * 50) + "%" },
            title: "class mean " + fmt(mean, 2)
          })
        ]),
        el("span", { class: "opbar__val", text: signed(value, 2) })
      ]));
    });

    return host;
  }

  function renderProfile() {
    var host = clear($("profile-answers"));
    var legend = clear($("profile-legend"));

    if (!state.selected) {
      $("profile-title").textContent = "No respondent selected";
      host.appendChild(el("p", { class: "inspector__empty", text: "Click on anyone in the network above to see all their answers." }));
      return;
    }

    var person = DATA.respondents[state.selected];
    var order = DATA.questions.order;
    var meta = DATA.questions.meta;

    $("profile-title").textContent = "Respondent " + person.id + " · all 60 answers";

    var rows = [];
    DATA.meta.topics.forEach(function (topic) {
      var codes = order.filter(function (code) { return meta[code].topic === topic; });
      var cells = el("div", { class: "answers__cells" });

      codes.forEach(function (code) {
        var value = person.answers[order.indexOf(code)];
        var missing = value === null || value === undefined;
        var button = el("button", {
          type: "button",
          class: "answers__cell" + (missing ? " is-missing" : ""),
          text: missing ? "·" : signed(value, 0),
          "aria-label": code + ": " + (missing ? "no answer" : value),
          style: missing ? {} : {
            background: divergingColour(value, 0, 2),
            color: inkOn(value, 0, 2)
          },
          onpointermove: function (event) {
            showTip(event, code + " · " + topic, [
              ["Answer", missing ? "No comments" : signed(value, 0)]
            ], meta[code].text);
          },
          onpointerleave: hideTip,
          onfocus: function (event) {
            showTip({ clientX: event.target.getBoundingClientRect().left + 14, clientY: event.target.getBoundingClientRect().top },
              code + " · " + topic, [["Answer", missing ? "No comments" : signed(value, 0)]], meta[code].text);
          },
          onblur: hideTip
        });
        cells.appendChild(button);
        rows.push([code, topic, missing ? "no answer" : signed(value, 0), meta[code].text]);
      });

      host.appendChild(el("div", { class: "answers__row" }, [
        el("div", { class: "answers__label" }, [
          el("span", { class: "key", style: { width: "9px", height: "9px", borderRadius: "3px", background: "var(--s" + (DATA.meta.topics.indexOf(topic) + 2) + ")", display: "block" } }),
          topic
        ]),
        cells
      ]));
    });

    [
      ["−2 strongly disagree", divergingColour(-2, 0, 2)],
      ["0 neutral", divergingColour(0, 0, 2)],
      ["+2 strongly agree", divergingColour(2, 0, 2)]
    ].forEach(function (pair) {
      legend.appendChild(el("span", { class: "legend__item" }, [
        el("span", { class: "legend__key legend__key--rect", style: { background: pair[1] } }),
        pair[0]
      ]));
    });
    legend.appendChild(el("span", { class: "legend__item" }, [
      el("span", { class: "legend__key legend__key--rect", style: { background: "var(--surface-sunken)", border: "1px solid var(--rule)" } }),
      "No comments (missing)"
    ]));

  }

  /* ---------------------------------------------------------------
   * 7  charts
   *
   * Shared conventions: hairline solid grid, marks capped at 24px,
   * values on the axis plus selective direct labels, a hover readout
   * on every mark, and a table twin behind the "Table" button.
   * --------------------------------------------------------------- */

  var PAD = { top: 18, right: 22, bottom: 42, left: 52 };

  function axisFrame(root, box, opts) {
    // horizontal gridlines + y ticks
    opts.yTicks.forEach(function (tick) {
      var y = opts.yScale(tick);
      root.appendChild(svg("line", {
        class: "grid-line", x1: box.x, x2: box.x + box.w, y1: y, y2: y
      }));
      root.appendChild(svg("text", {
        class: "tick", x: box.x - 8, y: y + 3.5, "text-anchor": "end",
        text: opts.yFormat ? opts.yFormat(tick) : String(tick)
      }));
    });

    root.appendChild(svg("line", {
      class: "axis-line", x1: box.x, x2: box.x + box.w,
      y1: box.y + box.h, y2: box.y + box.h
    }));

    if (opts.xTicks) {
      opts.xTicks.forEach(function (tick) {
        var x = opts.xScale(tick);
        root.appendChild(svg("text", {
          class: "tick", x: x, y: box.y + box.h + 16, "text-anchor": "middle",
          text: opts.xFormat ? opts.xFormat(tick) : String(tick)
        }));
      });
    }

    if (opts.xTitle) {
      root.appendChild(svg("text", {
        class: "axis-title", x: box.x + box.w / 2, y: box.y + box.h + 34, "text-anchor": "middle",
        text: opts.xTitle
      }));
    }
    if (opts.yTitle) {
      root.appendChild(svg("text", {
        class: "axis-title", x: box.x, y: box.y - 7, "text-anchor": "start", text: opts.yTitle
      }));
    }
  }

  /** Round tick values covering [min, max].
   *
   * The last tick is always at or above `max`: callers scale the plot by
   * `ticks[ticks.length - 1]`, so a tick list that stops short of the data
   * draws marks off the top of the chart.
   */
  function niceTicks(min, max, count) {
    var span = max - min || 1;
    var rough = span / (count || 5);
    var mag = Math.pow(10, Math.floor(Math.log10(rough)));
    var step = [1, 2, 2.5, 5, 10].map(function (m) { return m * mag; })
      .filter(function (s) { return s >= rough; })[0] || mag * 10;

    var ticks = [];
    var start = Math.floor(min / step) * step;
    for (var t = start; t < max - step * 1e-9; t += step) {
      ticks.push(Math.round(t / step) * step);
    }
    if (!ticks.length) ticks.push(Math.round(start / step) * step);
    ticks.push(Math.round((ticks[ticks.length - 1] + step) / step) * step);
    return ticks;
  }

  // ---- degree distribution ----------------------------------------

  function renderDegree() {
    var root = clear($("degree-chart"));
    var net = currentNetwork();
    var hist = net.degreeHistogram;
    var stats = DATA.networkStats[state.network];
    var counts = hist.counts;

    $("degree-sub").textContent = "How many people have at least k connections in the " +
      NET_LABEL[state.network].toLowerCase() + " network. Shown on log-log axes.";

    var W = 640, H = 300;
    var box = { x: PAD.left + 6, y: PAD.top, w: W - PAD.left - PAD.right - 6, h: H - PAD.top - PAD.bottom };
    var colour = token(NET_SLOT[state.network]);

    var n = stats.n_nodes;
    var ccdf = [];
    for (var k = 0; k < counts.length; k++) {
      var tail = 0;
      for (var j = k; j < counts.length; j++) tail += counts[j];
      if (tail > 0) ccdf.push({ k: k, prob: tail / n });
    }

    var nonzero = ccdf.filter(function (p) { return p.k >= 1; });
    if (!nonzero.length) nonzero = ccdf;

    var maxK = Math.max.apply(null, nonzero.map(function (p) { return p.k; }));
    var maxP = Math.max.apply(null, nonzero.map(function (p) { return p.prob; }));
    var minP = Math.min.apply(null, nonzero.map(function (p) { return p.prob; }));

    var logMaxK = Math.log10(Math.max(maxK, 2) * 1.3);
    var logMaxP = Math.log10(maxP * 1.5);
    var logMinP = Math.log10(Math.max(minP * 0.5, 1 / (n * 2)));

    var lx = function (val) { return box.x + (Math.log10(Math.max(val, 0.5)) / logMaxK) * box.w; };
    var ly = function (val) {
      var logVal = Math.log10(Math.max(val, 1 / (n * 2)));
      return box.y + box.h - ((logVal - logMinP) / (logMaxP - logMinP)) * box.h;
    };

    var decadeX = [1, 2, 5, 10, 20, 50].filter(function (v) { return v <= maxK * 1.3; });
    var decadeY = [];
    var yVal = 0.01;
    while (yVal <= maxP * 1.5) {
      if (yVal >= minP * 0.5) decadeY.push(yVal);
      yVal *= 10;
    }
    if (!decadeY.length) decadeY = [0.1, 1];
    decadeY.push(1);
    decadeY = decadeY.filter(function (v, i, arr) { return arr.indexOf(v) === i && v <= 1.01; });

    axisFrame(root, box, {
      yScale: ly, yTicks: decadeY, xScale: lx, xTicks: decadeX,
      xTitle: "Degree k (log scale)",
      yTitle: "P(K ≥ k)",
      yFormat: function (t) { return t >= 1 ? "1" : t >= 0.1 ? fmt(t, 1) : fmt(t, 2); }
    });

    var pathParts = nonzero.map(function (p) {
      return lx(p.k) + " " + ly(p.prob);
    });
    if (pathParts.length > 1) {
      root.appendChild(svg("path", {
        class: "mark",
        d: "M" + pathParts.join("L"),
        fill: "none", stroke: colour, "stroke-width": 2.5,
        "stroke-linejoin": "round", "stroke-linecap": "round", opacity: 0.6
      }));
    }

    nonzero.forEach(function (p) {
      var cx = lx(p.k), cy = ly(p.prob);
      root.appendChild(svg("circle", {
        class: "mark", cx: cx, cy: cy, r: 5.5, fill: colour,
        stroke: token("--surface"), "stroke-width": 2
      }));
      root.appendChild(svg("circle", {
        class: "hit", cx: cx, cy: cy, r: 13,
        onpointermove: function (event) {
          var atLeast = Math.round(p.prob * n);
          showTip(event, "Degree ≥ " + p.k, [
            ["Respondents", String(atLeast) + " of " + n],
            ["P(K ≥ " + p.k + ")", fmt(p.prob, 3)]
          ], null, colour);
        },
        onpointerleave: hideTip
      }));
    });

    var isolated = counts[0] || 0;
    if (isolated > 0) {
      root.appendChild(svg("text", {
        class: "axis-title", x: box.x + box.w, y: box.y + 14, "text-anchor": "end",
        text: isolated + " isolates (k = 0) at P = 1.00"
      }));
    }

    var top = net.nodes.slice().sort(function (a, b) { return b.degree - a.degree; })[0];
    $("degree-note").textContent =
      "Most people have very few connections. " + isolated + " of " + n + " have none at all. " +
      "Respondent " + top.id + " has the most with " + top.degree + ". " +
      "The average of " + fmt(stats.avg_degree, 1) + " connections does not describe a typical person here because a few people have many and most have few.";
  }

  // ---- centrality leaderboard --------------------------------------

  function renderCentrality() {
    var root = clear($("central-chart"));
    var net = currentNetwork();
    var slot = DATA.meta.centralities.indexOf(state.centrality);
    var top = net.nodes.slice().sort(function (a, b) { return b.c[slot] - a.c[slot]; }).slice(0, 10);

    var W = 640, H = 340;
    var box = { x: 74, y: 12, w: W - 74 - 66, h: H - 12 - 30 };
    var max = Math.max.apply(null, top.map(function (n) { return n.c[slot]; })) || 1;
    var band = box.h / top.length;
    var barHeight = Math.min(band - 6, 24);
    var xScale = function (v) { return box.x + (v / max) * box.w; };

    var xTicks = niceTicks(0, max, 4);
    xTicks.forEach(function (tick) {
      var x = xScale(tick);
      root.appendChild(svg("line", { class: "grid-line", x1: x, x2: x, y1: box.y, y2: box.y + box.h }));
      root.appendChild(svg("text", {
        class: "tick", x: x, y: box.y + box.h + 16, "text-anchor": "middle",
        text: tick < 1 ? String(Math.round(tick * 1000) / 1000) : String(tick)
      }));
    });
    root.appendChild(svg("line", { class: "axis-line", x1: box.x, x2: box.x, y1: box.y, y2: box.y + box.h }));

    // one series, one colour. The bar length already carries the value, so
    // spending hue on community as well would only add noise the legend for
    // it isn't here to decode
    var colour = token(NET_SLOT[state.network]);

    top.forEach(function (node, i) {
      var y = box.y + band * i + (band - barHeight) / 2;
      var width = Math.max(xScale(node.c[slot]) - box.x, 2);
      var isSelected = node.id === state.selected;

      root.appendChild(svg("rect", {
        class: "mark", x: box.x, y: y, width: width, height: barHeight,
        rx: Math.min(4, barHeight / 2), fill: colour,
        opacity: state.selected && !isSelected ? 0.45 : 1
      }));
      // square off the baseline end
      root.appendChild(svg("rect", {
        class: "mark", x: box.x, y: y, width: Math.min(4, width), height: barHeight, fill: colour,
        opacity: state.selected && !isSelected ? 0.45 : 1
      }));

      root.appendChild(svg("text", {
        class: "series-label", x: box.x - 10, y: y + barHeight / 2 + 4, "text-anchor": "end",
        text: node.id, "font-weight": isSelected ? 700 : 600
      }));
      root.appendChild(svg("text", {
        class: "value-label", x: box.x + width + 8, y: y + barHeight / 2 + 4,
        text: fmt(node.c[slot], 3)
      }));

      root.appendChild(svg("rect", {
        class: "hit", x: box.x, y: box.y + band * i, width: box.w, height: band,
        onclick: function () { select(node.id); },
        onpointermove: function (event) {
          showTip(event, "Respondent " + node.id, [
            [CENTRALITY_LABEL[state.centrality], fmt(node.c[slot], 4)],
            ["Degree", String(node.degree)],
            ["Community", String(node.community)]
          ], "Click to inspect", colour);
        },
        onpointerleave: hideTip
      }));
    });

    root.appendChild(svg("text", {
      class: "axis-title", x: box.x + box.w / 2, y: H - 4, "text-anchor": "middle",
      text: CENTRALITY_LABEL[state.centrality] + " centrality"
    }));

    var ranks = net.ranks;
    var byDegree = net.nodes.slice().sort(function (a, b) { return b.c[0] - a.c[0]; })[0];
    var byBetween = net.nodes.slice().sort(function (a, b) { return b.c[2] - a.c[2]; })[0];
    $("central-note").textContent = byDegree.id === byBetween.id
      ? "Respondent " + byDegree.id + " has both the most connections and sits on the most shortest paths."
      : "The most connected person (" + byDegree.id + ") is not the best bridge. " +
        "Respondent " + byBetween.id + " (ranked #" + ranks.degree_centrality[byBetween.id] +
        " by connections) sits on the most shortest paths between others. " +
        "Having many connections and being important for the flow of information are different things here.";
  }

  // ---- five networks side by side ------------------------------------

  function renderCompare() {
    var host = clear($("compare-grid"));
    var panels = [
      { key: "giant_fraction", label: "Share of class in the giant component", format: function (v) { return pct(v); }, scale: 1 },
      { key: "avg_clustering", label: "Average clustering coefficient", format: function (v) { return fmt(v, 2); }, scale: 0.5 },
      { key: "modularity", label: "Modularity Q", format: function (v) { return fmt(v, 2); }, scale: 0.3 },
      { key: "n_isolated", label: "Respondents with no edge", format: function (v) { return String(Math.round(v)); }, scale: 50 }
    ];

    panels.forEach(function (panel) {
      var W = 300, H = 178;
      var box = { x: 40, y: 16, w: W - 40 - 12, h: H - 16 - 40 };
      var root = svg("svg", {
        class: "chart", viewBox: "0 0 " + W + " " + H,
        preserveAspectRatio: "xMidYMid meet", role: "img"
      });

      var values = DATA.meta.networks.map(function (name) {
        return panel.key === "modularity"
          ? DATA.networks[name].community.modularity
          : DATA.networkStats[name][panel.key];
      });
      var max = Math.max.apply(null, values);
      var yTicks = niceTicks(0, max, 3);
      var yMax = yTicks[yTicks.length - 1] || 1;
      var yScale = function (v) { return box.y + box.h - (v / yMax) * box.h; };

      axisFrame(root, box, {
        yScale: yScale, yTicks: yTicks,
        yFormat: panel.key === "giant_fraction" ? function (t) { return Math.round(t * 100) + "%"; } : function (t) { return String(Math.round(t * 100) / 100); }
      });

      var band = box.w / DATA.meta.networks.length;
      var barWidth = Math.min(band - 8, 24);

      DATA.meta.networks.forEach(function (name, i) {
        var value = values[i];
        var x = box.x + band * i + (band - barWidth) / 2;
        var y = yScale(value);
        var h = box.y + box.h - y;
        var colour = token(NET_SLOT[name]);
        var isCurrent = name === state.network;

        root.appendChild(svg("rect", {
          class: "mark", x: x, y: y, width: barWidth, height: h,
          rx: Math.min(4, barWidth / 2), fill: colour, opacity: isCurrent ? 1 : 0.55
        }));
        if (h > 4) {
          root.appendChild(svg("rect", {
            class: "mark", x: x, y: y + h - 4, width: barWidth, height: 4,
            fill: colour, opacity: isCurrent ? 1 : 0.55
          }));
        }

        root.appendChild(svg("text", {
          class: "tick", x: x + barWidth / 2, y: box.y + box.h + 15, "text-anchor": "middle",
          text: NET_LABEL[name].slice(0, 4)
        }));

        // label only the network the reader is currently looking at
        if (isCurrent) {
          root.appendChild(svg("text", {
            class: "value-label", x: x + barWidth / 2, y: y - 6, "text-anchor": "middle",
            text: panel.format(value)
          }));
        }

        root.appendChild(svg("rect", {
          class: "hit", x: box.x + band * i, y: box.y, width: band, height: box.h,
          onclick: function () { selectNetwork(name); },
          onpointermove: function (event) {
            showTip(event, NET_LABEL[name], [[panel.label, panel.format(value)]], "Click to switch to this network", colour);
          },
          onpointerleave: hideTip
        }));
      });

      host.appendChild(el("div", {}, [
        el("div", { style: { fontSize: "12px", color: "var(--ink-2)", marginBottom: "4px", minHeight: "2.6em" }, text: panel.label }),
        root
      ]));
    });

    $("compare-note").textContent =
      "Technology and Education networks stay well connected. Ethics and Environment fall apart. " +
      "People actually agree more on ethics on average, but their answers vary more from person to person. " +
      "Our similarity measure looks at the pattern of answers, not the average. So a topic where people answer in many different ways produces fewer connections.";
  }

  // ---- DeGroot: where opinions settle ---------------------------------

  function renderDeGroot() {
    var root = clear($("degroot-chart"));
    var net = currentNetwork();
    var degroot = DATA.dynamics.degroot[state.network];

    $("degroot-sub").textContent =
      "Each person updates their opinion to the average of their neighbours' opinions, over and over. " +
      "The connected group reaches agreement in " + degroot.steps_to_converge_giant +
      " steps. People with no connections never change.";

    var W = 640, H = 300;
    var box = { x: 46, y: 46, w: W - 46 - 30, h: H - 46 - 62 };

    var values = net.nodes.map(function (n) { return graph.opinionOf(n); })
      .concat(net.nodes.map(function (n) { return n.degroot; }));
    var min = Math.min.apply(null, values), max = Math.max.apply(null, values);
    var padding = (max - min) * 0.12 || 0.2;
    min -= padding; max += padding;
    var xScale = function (v) { return box.x + (v - min) / (max - min) * box.w; };

    var rowStart = box.y + 16, rowEnd = box.y + box.h - 16;

    var xTicks = niceTicks(min, max, 5);
    xTicks.forEach(function (tick) {
      var x = xScale(tick);
      root.appendChild(svg("line", { class: "grid-line", x1: x, x2: x, y1: box.y, y2: box.y + box.h }));
      root.appendChild(svg("text", { class: "tick", x: x, y: box.y + box.h + 16, "text-anchor": "middle", text: fmt(tick, 1) }));
    });

    root.appendChild(svg("text", { class: "axis-title", x: box.x - 8, y: rowStart + 4, "text-anchor": "end", text: "start" }));
    root.appendChild(svg("text", { class: "axis-title", x: box.x - 8, y: rowEnd + 4, "text-anchor": "end", text: "limit" }));
    root.appendChild(svg("text", {
      class: "axis-title", x: box.x + box.w / 2, y: H - 6, "text-anchor": "middle",
      text: "Opinion score (−2 disagree to +2 agree)"
    }));

    var core = token("--s1"), still = token("--ink-3");

    // connectors first, then the two rows of dots on top of them
    net.nodes.forEach(function (node) {
      var x0 = xScale(graph.opinionOf(node)), x1 = xScale(node.degroot);
      root.appendChild(svg("line", {
        class: "mark", x1: x0, y1: rowStart, x2: x1, y2: rowEnd,
        stroke: node.isolate ? rgba(still, 0.22) : rgba(core, 0.3), "stroke-width": 1
      }));
    });

    net.nodes.forEach(function (node) {
      var colour = node.isolate ? still : core;
      [[xScale(graph.opinionOf(node)), rowStart], [xScale(node.degroot), rowEnd]].forEach(function (point) {
        root.appendChild(svg("circle", {
          class: "mark", cx: point[0], cy: point[1], r: 4.5,
          fill: colour, stroke: token("--surface"), "stroke-width": 2, opacity: 0.9
        }));
      });
      root.appendChild(svg("circle", {
        class: "hit", cx: xScale(graph.opinionOf(node)), cy: rowStart, r: 12,
        onclick: function () { select(node.id); },
        onpointermove: function (event) {
          showTip(event, "Respondent " + node.id, [
            ["Starts at", fmt(graph.opinionOf(node), 2)],
            ["Settles at", fmt(node.degroot, 2)],
            ["Moves by", signed(node.degroot - graph.opinionOf(node), 2)]
          ], node.isolate ? "No connections, so this person never changes" : "Click to inspect", colour);
        },
        onpointerleave: hideTip
      }));
    });

    var consensus = xScale(degroot.consensus_giant);
    root.appendChild(svg("line", {
      class: "ref-line", x1: consensus, y1: rowEnd - 26, x2: consensus, y2: rowEnd + 14
    }));
    root.appendChild(svg("text", {
      class: "value-label", x: consensus, y: rowEnd - 32, "text-anchor": "middle",
      text: "consensus " + fmt(degroot.consensus_giant, 2)
    }));

    var legend = [
      ["In the connected core (" + degroot.giant_size + ")", core],
      ["No edges (" + degroot.n_isolated + "), never moves", still]
    ];
    root.appendChild(svg("g", {}, legend.map(function (pair, i) {
      return svg("g", {}, [
        svg("circle", { cx: box.x + 8 + i * 230, cy: 16, r: 4.5, fill: pair[1] }),
        svg("text", { class: "series-label", x: box.x + 20 + i * 230, y: 20, text: pair[0] })
      ]);
    })));

    $("degroot-note").textContent =
      "The connected group settles on " + fmt(degroot.consensus_giant, 2) + ", but that is only " +
      degroot.giant_size + " of " + DATA.meta.n_respondents + " people. " +
      "The whole class never agrees on one number because " + degroot.n_isolated +
      " people have no connections and never update. It takes " + degroot.steps_to_converge_giant +
      " rounds to settle. The speed depends on the second-largest eigenvalue of the weight matrix (SLEM = " + fmt(degroot.slem, 2) + ").";
  }

  // ---- SIS sweep -------------------------------------------------------

  function renderSIS() {
    var root = clear($("sis-chart"));
    var legendHost = clear($("sis-legend"));
    var sweeps = DATA.curves.sis_sweep;
    var names = Object.keys(sweeps);

    var W = 640, H = 300;
    var box = { x: PAD.left, y: PAD.top + 10, w: W - PAD.left - PAD.right, h: H - PAD.top - PAD.bottom - 10 };

    var maxX = 0, maxY = 0;
    names.forEach(function (name) {
      maxX = Math.max(maxX, Math.max.apply(null, sweeps[name].x_ratio_over_threshold));
      maxY = Math.max(maxY, Math.max.apply(null, sweeps[name].y_prevalence));
    });
    var yTicks = niceTicks(0, maxY, 4);
    var yMax = yTicks[yTicks.length - 1] || 1;
    var xScale = function (v) { return box.x + (v / maxX) * box.w; };
    var yScale = function (v) { return box.y + box.h - (v / yMax) * box.h; };

    axisFrame(root, box, {
      yScale: yScale, yTicks: yTicks,
      yFormat: function (t) { return Math.round(t * 100) + "%"; },
      xScale: xScale, xTicks: niceTicks(0, maxX, 5),
      xTitle: "Infection rate λ, as a multiple of the predicted threshold λc",
      yTitle: "Share still infected"
    });

    // the prediction under test
    root.appendChild(svg("line", {
      class: "ref-line", x1: xScale(1), y1: box.y, x2: xScale(1), y2: box.y + box.h
    }));
    root.appendChild(svg("text", {
      class: "axis-title", x: xScale(1) + 6, y: box.y + 12, text: "λ = λc (predicted)"
    }));

    names.forEach(function (name, index) {
      var sweep = sweeps[name];
      var colour = token(NET_SLOT[name]);
      var points = sweep.x_ratio_over_threshold.map(function (x, i) {
        return [xScale(x), yScale(sweep.y_prevalence[i])];
      });

      root.appendChild(svg("path", {
        class: "mark",
        d: points.map(function (p, i) { return (i ? "L" : "M") + p[0] + " " + p[1]; }).join(" "),
        fill: "none", stroke: colour, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round"
      }));

      // direct-label the line at its end rather than relying on the legend alone
      var last = points[points.length - 1];
      root.appendChild(svg("circle", {
        cx: last[0], cy: last[1], r: 4.5, fill: colour, stroke: token("--surface"), "stroke-width": 2
      }));
      root.appendChild(svg("text", {
        class: "series-label", x: last[0] - 6, y: last[1] + (index ? 16 : -10), "text-anchor": "end",
        text: NET_LABEL[name]
      }));

      points.forEach(function (point, i) {
        root.appendChild(svg("circle", {
          class: "hit", cx: point[0], cy: point[1], r: 12,
          onpointermove: function (event) {
            showTip(event, NET_LABEL[name], [
              ["λ / λc", fmt(sweep.x_ratio_over_threshold[i], 2)],
              ["Still infected", pct(sweep.y_prevalence[i], 1)]
            ], null, colour);
          },
          onpointerleave: hideTip
        }));
      });

      legendHost.appendChild(el("span", { class: "legend__item" }, [
        el("span", { class: "legend__key", style: { background: colour } }),
        NET_LABEL[name] + " network"
      ]));
    });

    var head = ["λ / λc"].concat(names.map(function (n) { return NET_LABEL[n] + " prevalence"; }));
    var first = sweeps[names[0]];
    var ratio = DATA.dynamics.epidemic.sweeps.overall.measured_threshold_over_predicted;
    $("sis-note").textContent =
      "Both curves stay at zero well past the predicted threshold. Infection only takes hold around " +
      fmt(ratio, 2) + "× λc. The threshold is a lower bound. It tells you outbreaks are impossible below it, " +
      "but does not promise one will happen right above it. With only 87 people and a connected core of about 50, " +
      "the infection randomly dies out before it can spread, even at rates above the threshold.";
  }

  // ---- threshold sensitivity --------------------------------------------

  function renderSensitivity() {
    var root = clear($("sens-chart"));
    var legendHost = clear($("sens-legend"));
    var sweeps = DATA.curves.threshold_sweep;
    var names = DATA.meta.networks.filter(function (name) { return sweeps[name]; });

    var labels = {
      y_giant_fraction: "Share of class in the giant component",
      y_n_isolates: "Respondents with no edge",
      y_avg_clustering: "Average clustering coefficient",
      y_n_edges: "Edges kept"
    };

    var W = 980, H = 320;
    var box = { x: 58, y: 24, w: W - 58 - 130, h: H - 24 - 52 };

    var maxY = 0;
    names.forEach(function (name) {
      maxY = Math.max(maxY, Math.max.apply(null, sweeps[name][state.sensMeasure]));
    });
    var yTicks = niceTicks(0, maxY, 5);
    var yMax = yTicks[yTicks.length - 1] || 1;
    var xs = sweeps[names[0]].x_quantile;
    var xScale = function (q) { return box.x + (q - xs[0]) / (xs[xs.length - 1] - xs[0]) * box.w; };
    var yScale = function (v) { return box.y + box.h - (v / yMax) * box.h; };

    var percentage = state.sensMeasure === "y_giant_fraction" || state.sensMeasure === "y_avg_clustering";

    axisFrame(root, box, {
      yScale: yScale, yTicks: yTicks,
      yFormat: state.sensMeasure === "y_giant_fraction"
        ? function (t) { return Math.round(t * 100) + "%"; }
        : function (t) { return String(Math.round(t * 1000) / 1000); },
      xScale: xScale, xTicks: [0.5, 0.6, 0.7, 0.8, 0.9, 0.99],
      xFormat: function (t) { return "q = " + fmt(t, 2); },
      xTitle: "Similarity quantile kept as edges (higher = stricter)",
      yTitle: labels[state.sensMeasure]
    });

    var baseline = DATA.curves.baseline_quantile;
    root.appendChild(svg("line", {
      class: "ref-line", x1: xScale(baseline), y1: box.y, x2: xScale(baseline), y2: box.y + box.h
    }));
    root.appendChild(svg("text", {
      class: "axis-title", x: xScale(baseline) - 7, y: box.y + 12, "text-anchor": "end",
      text: "the cut this study uses"
    }));

    names.forEach(function (name) {
      var sweep = sweeps[name];
      var colour = token(NET_SLOT[name]);
      var current = name === state.network;
      var points = sweep.x_quantile.map(function (q, i) {
        return [xScale(q), yScale(sweep[state.sensMeasure][i])];
      });

      root.appendChild(svg("path", {
        class: "mark",
        d: points.map(function (p, i) { return (i ? "L" : "M") + p[0] + " " + p[1]; }).join(" "),
        fill: "none", stroke: colour, "stroke-width": current ? 2.4 : 1.6,
        "stroke-linejoin": "round", "stroke-linecap": "round",
        opacity: current ? 1 : 0.62
      }));

      var last = points[points.length - 1];
      root.appendChild(svg("circle", {
        cx: last[0], cy: last[1], r: 4.5, fill: colour, stroke: token("--surface"), "stroke-width": 2
      }));
      // the five lines converge at the right edge, so only the selected one is
      // direct-labelled; nudging five labels apart would detach them from their
      // lines. The legend and the crosshair carry the other four.
      if (current) {
        root.appendChild(svg("text", {
          class: "series-label", x: last[0] + 9, y: last[1] + 4,
          text: NET_LABEL[name], "font-weight": 700
        }));
      }

      legendHost.appendChild(el("span", { class: "legend__item" }, [
        el("span", { class: "legend__key", style: { background: colour } }),
        NET_LABEL[name]
      ]));
    });

    // one crosshair for the whole chart: every series reads off the same x
    var crosshair = svg("line", { class: "ref-line", y1: box.y, y2: box.y + box.h, opacity: 0 });
    root.appendChild(crosshair);
    root.appendChild(svg("rect", {
      class: "hit", x: box.x, y: box.y, width: box.w, height: box.h,
      onpointermove: function (event) {
        var svgBox = root.getBoundingClientRect();
        var localX = (event.clientX - svgBox.left) / svgBox.width * W;
        var index = clamp(Math.round((localX - box.x) / box.w * (xs.length - 1)), 0, xs.length - 1);
        crosshair.setAttribute("x1", xScale(xs[index]));
        crosshair.setAttribute("x2", xScale(xs[index]));
        crosshair.setAttribute("opacity", 1);
        showTip(event, "Quantile " + fmt(xs[index], 2), names.map(function (name) {
          var value = sweeps[name][state.sensMeasure][index];
          return [NET_LABEL[name], percentage && state.sensMeasure === "y_giant_fraction"
            ? pct(value) : fmt(value, state.sensMeasure === "y_n_edges" || state.sensMeasure === "y_n_isolates" ? 0 : 3)];
        }), labels[state.sensMeasure]);
      },
      onpointerleave: function () { crosshair.setAttribute("opacity", 0); hideTip(); }
    }));

    var ordering = DATA.dynamics.thresholdSensitivity.topic_ordering_holds_at_every_cut;
    var holds = Object.keys(ordering).every(function (key) { return ordering[key]; });
    $("sens-note").textContent =
      "Changing the cut-off changes the numbers but not the pattern. " +
      (holds
        ? "Technology always has a more connected network than Environment, and Education more than Ethics, at every cut-off from 0.50 to 0.99."
        : "The topic ordering does not hold at every cut-off. See report/VARUN.md for details.") +
      " No matter where you set the cut-off, some people stay isolated. That is a real feature of these opinions, not something the threshold creates.";
  }

  // ---- null models -------------------------------------------------------

  function renderNull() {
    var root = clear($("null-chart"));
    var legendHost = clear($("null-legend"));
    var nulls = DATA.dynamics.nullmodels;

    var stats = [
      { key: "avg_clustering", label: "Clustering" },
      { key: "giant_fraction", label: "Giant component" },
      { key: "avg_path_length", label: "Path length" },
      { key: "modularity", label: "Modularity" }
    ];
    var models = [
      { key: "vs_erdos_renyi", label: "vs Erdős–Rényi", slot: "--s2" },
      { key: "vs_configuration_model", label: "vs configuration model", slot: "--s3" }
    ];

    var W = 700, H = 300;
    var box = { x: 118, y: 22, w: W - 118 - 46, h: H - 22 - 50 };

    // z spans 0.04 to 362, so the axis is symmetric-log; ticks are labelled
    // in real z units so nothing has to be decoded
    var squash = function (z) { return Math.sign(z) * Math.log10(1 + Math.abs(z)); };
    var limit = squash(400);
    var xScale = function (z) { return box.x + box.w / 2 + (squash(z) / limit) * (box.w / 2); };

    [-100, -10, -2, 0, 2, 10, 100].forEach(function (tick) {
      var x = xScale(tick);
      root.appendChild(svg("line", { class: "grid-line", x1: x, x2: x, y1: box.y, y2: box.y + box.h }));
      root.appendChild(svg("text", { class: "tick", x: x, y: box.y + box.h + 16, "text-anchor": "middle", text: String(tick) }));
    });

    // the band inside which the null model reproduces the real value
    root.appendChild(svg("rect", {
      x: xScale(-2), y: box.y, width: xScale(2) - xScale(-2), height: box.h,
      fill: token("--ink-3"), opacity: 0.09
    }));
    root.appendChild(svg("text", {
      class: "axis-title", x: xScale(0), y: box.y - 6, "text-anchor": "middle", text: "looks random (|z| < 2)"
    }));

    var rows = stats.length * models.length;
    var band = box.h / rows;
    var tableRows = [];
    var index = 0;

    stats.forEach(function (stat) {
      models.forEach(function (model) {
        var entry = nulls[model.key][stat.key];
        var y = box.y + band * index + band / 2;
        var colour = token(model.slot);
        var x = xScale(clamp(entry.z_score, -400, 400));
        var zero = xScale(0);

        root.appendChild(svg("line", {
          class: "mark", x1: zero, y1: y, x2: x, y2: y, stroke: colour, "stroke-width": 2, "stroke-linecap": "round"
        }));
        root.appendChild(svg("circle", {
          class: "mark", cx: x, cy: y, r: 5, fill: colour, stroke: token("--surface"), "stroke-width": 2
        }));

        if (index % 2 === 0) {
          root.appendChild(svg("text", {
            class: "series-label", x: box.x - 12, y: y + band / 2 + 4, "text-anchor": "end", text: stat.label
          }));
        }

        root.appendChild(svg("rect", {
          class: "hit", x: box.x, y: box.y + band * index, width: box.w, height: band,
          onpointermove: function (event) {
            showTip(event, stat.label + " " + model.label, [
              ["Real network", fmt(entry.real, 3)],
              ["Null mean", fmt(entry.null_mean, 3)],
              ["Null s.d.", fmt(entry.null_sd, 4)],
              ["z", fmt(entry.z_score, 2)],
              ["p (two-sided)", entry.p_two_sided === 0 ? "< 0.002" : fmt(entry.p_two_sided, 3)]
            ], "500 random graphs", colour);
          },
          onpointerleave: hideTip
        }));

        tableRows.push([
          stat.label + " " + model.label, fmt(entry.real, 3), fmt(entry.null_mean, 3),
          fmt(entry.null_sd, 4), fmt(entry.z_score, 2),
          entry.p_two_sided === 0 ? "< 0.002" : fmt(entry.p_two_sided, 3)
        ]);
        index += 1;
      });
    });

    root.appendChild(svg("line", { class: "axis-line", x1: xScale(0), y1: box.y, x2: xScale(0), y2: box.y + box.h }));
    root.appendChild(svg("text", {
      class: "axis-title", x: box.x + box.w / 2, y: H - 8, "text-anchor": "middle",
      text: "z-score of the real value against 500 null graphs (log-spaced axis)"
    }));

    models.forEach(function (model) {
      legendHost.appendChild(el("span", { class: "legend__item" }, [
        el("span", { class: "legend__key", style: { background: "var(" + model.slot + ")" } }),
        model.label
      ]));
    });

    $("null-note").textContent =
      "Compared to a plain random graph (Erdos-Renyi), everything looks different. But that just means our network is not random, which we already knew. " +
      "The useful comparison is the configuration model. It keeps each person's exact number of connections but rewires them randomly. " +
      "Against that, clustering, the giant component, and modularity all look normal. " +
      "Once you know how many connections each person has, the rest of the structure is what you would expect by chance.";
  }

  // ---- findings ------------------------------------------------------

  function renderFindings() {
    var host = clear($("findings-grid"));
    var net = currentNetwork();
    var degroot = DATA.dynamics.degroot[state.network];
    var top = net.nodes.slice().sort(function (a, b) { return b.degree - a.degree; })[0];
    var conf = DATA.dynamics.nullmodels.vs_configuration_model;

    var cards = [
      {
        // the lead reading: full width and larger, so the section has a shape
        // rather than four interchangeable boxes
        lead: true,
        // scoped to the overall network on purpose: the isolated-vs-connected
        // test behind this claim was run on all 60 questions, not per topic
        title: "The connected group shares a habit, not a belief",
        text: "In the overall network the " +
          Math.round(DATA.networkStats.overall.giant_fraction * DATA.networkStats.overall.n_nodes) +
          " connected people are not a random slice of the class. They are the ones who tend to agree or strongly " +
          "agree on most questions. That pattern of similar answers is what creates their connections. The " +
          DATA.networkStats.overall.n_isolated +
          " people with no connections gave more mixed or neutral answers. They are not extreme, they are just less predictable."
      },
      {
        title: "More agreement does not mean more connections",
        text: "Ethics and Environment have the highest average agreement among the four topics, but they produce " +
          "the most disconnected networks. Our similarity measure looks at the pattern of answers, not how strongly " +
          "people agree. Topics where people answer in many different ways lose connections, even if most people lean the same direction."
      },
      {
        title: "The whole class never agrees",
        text: "When connected people average opinions with their neighbours, they settle on " + fmt(degroot.consensus_giant, 2) + " in " +
          degroot.steps_to_converge_giant + " steps. But " + degroot.n_isolated +
          " people have no connections and never change their opinion. " +
          "The connected majority reaching agreement is not the same as the whole class reaching agreement."
      },
      {
        title: "The number of connections explains everything else",
        text: "We built 500 random networks that keep each person's exact number of connections but rewire them randomly. " +
          "Clustering (z = " +
          fmt(conf.avg_clustering.z_score, 2) + "), the giant component (z = " +
          fmt(conf.giant_fraction.z_score, 2) + "), and modularity (z = " +
          fmt(conf.modularity.z_score, 2) + ") all look normal compared to those random networks. " +
          "Once you know how many connections each person has, the rest of the structure is what you would expect by chance."
      }
    ];

    var colours = ["finding--blue", "finding--orange", "finding--green", "finding--pink"];
    cards.forEach(function (card, i) {
      host.appendChild(el("article", {
        class: "finding " + (colours[i] || "finding--blue")
      }, [
        el("h3", { text: card.title }),
        el("p", { text: card.text })
      ]));
    });

    // keep the top-degree respondent reachable from the summary
    if (top) {
      host.firstChild.appendChild(el("p", {
        class: "note",
        style: { marginTop: "8px" }
      }, [
        "Most connected in the " + NET_LABEL[state.network].toLowerCase() + " network: ",
        el("button", {
          class: "btn btn--ghost",
          type: "button",
          style: { padding: "1px 6px" },
          text: "respondent " + top.id + " (" + top.degree + " links)",
          onclick: function () {
            select(top.id);
            $("explorer").scrollIntoView({ behavior: "smooth", block: "start" });
          }
        })
      ]));
    }
  }

  /* ---------------------------------------------------------------
   * 8  boot
   * --------------------------------------------------------------- */

  function renderAll() {
    graph.invalidate();
    renderHero();
    renderTiles();
    renderLegend();
    renderInspector();
    renderProfile();
    renderDegree();
    renderCentrality();
    renderCompare();
    renderDeGroot();
    renderSIS();
    renderSensitivity();
    renderNull();
    renderFindings();
    graph.draw();
  }

  function boot() {
    $("stamp").textContent = DATA.meta.generated;
    initTheme();
    initNetworkPicker();
    initSegments();
    initSearch();
    initSectionNav();
    graph.init();
    renderAll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
