/* Dashboard IGAE — todo corre en el navegador a partir de data/data.json */
(function () {
  "use strict";

  var MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"];
  var COLORS = { Primarias: "#E41A1C", Secundarias: "#4DAF4A", Terciarias: "#377EB8" };

  var $ = function (id) { return document.getElementById(id); };
  var css = function (n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); };
  var esc = function (s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  var fmt = function (v, d) {
    if (d === undefined) d = 1;
    return v == null ? "–" : v.toLocaleString("es-MX", { minimumFractionDigits: d, maximumFractionDigits: d });
  };
  var pct = function (v, d) { return v == null ? "–" : (v > 0 ? "+" : "") + fmt(v, d) + "%"; };
  var sign = function (v) { return v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : ""; };
  var lbl = function (ym) { return MESES[+ym.slice(5) - 1] + " de " + ym.slice(0, 4); };
  var cap = function (s) { return s.charAt(0).toUpperCase() + s.slice(1); };
  var abbr = function (ym) { return MESES[+ym.slice(5) - 1].slice(0, 3) + " " + ym.slice(0, 4); };
  var shorten = function (s, n) { return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s; };

  var state = { idx: 0, rango: 60, sortKey: "contrib", sortDir: -1, act: "" };
  var D, byId, subs, reportes, estado, reporteDe = {};
  var charts = {};
  var MIN_IDX = 12; // antes de 12 meses no existe variación anual

  function getJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(url + " → HTTP " + r.status);
      return r.json();
    });
  }

  function showError(e) {
    var box = $("error");
    box.hidden = false;
    var local = location.protocol === "file:";
    box.innerHTML = "<strong>No se pudieron cargar los datos.</strong> " +
      (local ? "Estás abriendo el archivo directamente; el navegador bloquea la lectura de los datos. " +
               "Sirve la carpeta con <code>python -m http.server</code> o abre la página publicada en GitHub Pages."
             : esc(e.message || e));
    if (window.console) console.error(e);
  }

  /* ---------------- KPIs ---------------- */
  function renderKpis() {
    var T = byId.total, i = state.idx, P = D.periodos;
    var max = -Infinity, maxI = 0;
    for (var k = 0; k <= i; k++) { if (T.valor[k] != null && T.valor[k] > max) { max = T.valor[k]; maxI = k; } }
    var esMax = maxI === i;
    var anio = +P[i].slice(0, 4), mesN = MESES[+P[i].slice(5) - 1];
    var items = [
      { l: "Nivel del índice", v: fmt(T.valor[i]), c: "",
        n: esMax ? "Máximo histórico de la serie" : "Máx. histórico: " + fmt(max) + " (" + lbl(P[maxI]) + ")", badge: esMax ? "máx." : "" },
      { l: "Variación mensual", v: pct(T.var_mensual[i]), c: sign(T.var_mensual[i]), n: "vs. " + lbl(P[i - 1]) },
      { l: "Variación anual", v: pct(T.var_anual[i]), c: sign(T.var_anual[i]), n: "vs. " + lbl(P[i - 12]) },
      { l: "Variación acumulada", v: pct(T.var_acum[i]), c: sign(T.var_acum[i]),
        n: "ene–" + mesN.slice(0, 3) + " " + anio + " vs. mismo periodo " + (anio - 1) }
    ];
    $("kpis").innerHTML = items.map(function (x) {
      return '<div class="kpi"><div class="k-label">' + x.l + (x.badge ? '<span class="badge">' + x.badge + "</span>" : "") +
             '</div><div class="k-value ' + x.c + '">' + x.v + '</div><div class="k-note">' + esc(x.n) + "</div></div>";
    }).join("");
  }

  /* ---------------- Gráficas ---------------- */
  function baseOptions() {
    return {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false } }
    };
  }
  function lineScales() {
    return {
      x: { grid: { display: false }, ticks: { maxTicksLimit: 7, maxRotation: 0,
            callback: function (v) { return abbr(this.getLabelForValue(v)); } } },
      y: { grid: { color: css("--grid") }, ticks: { callback: function (v) { return fmt(v, 0); } } }
    };
  }
  function range() {
    var i = state.idx, n = state.rango;
    return [n === 0 ? 0 : Math.max(0, i - n + 1), i + 1];
  }
  function replaceChart(key, canvasId, cfg) {
    if (charts[key]) charts[key].destroy();
    charts[key] = new Chart($(canvasId), cfg);
  }

  function renderCharts() {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = css("--muted");
    var r = range(), labels = D.periodos.slice(r[0], r[1]);
    var tick = function (items) { return lbl(items[0].label); };

    // Total
    var T = byId.total, data = T.valor.slice(r[0], r[1]);
    var o1 = baseOptions();
    o1.scales = lineScales();
    o1.plugins.tooltip = { callbacks: { title: tick, label: function (c) { return fmt(c.parsed.y) + " puntos"; } } };
    replaceChart("total", "ch-total", {
      type: "line",
      data: { labels: labels, datasets: [{
        label: "IGAE total", data: data, borderColor: css("--blue"), backgroundColor: "rgba(79,129,189,.14)",
        borderWidth: 2, fill: true, tension: 0.15,
        pointRadius: data.map(function (_, k) { return k === data.length - 1 ? 4 : 0; }), pointHoverRadius: 4
      }] },
      options: o1
    });

    // Por actividad
    var o2 = baseOptions();
    o2.scales = lineScales();
    o2.plugins.legend = { display: true, position: "bottom", labels: { boxWidth: 12 } };
    o2.plugins.tooltip = { callbacks: { title: tick, label: function (c) { return c.dataset.label + ": " + fmt(c.parsed.y); } } };
    replaceChart("act", "ch-act", {
      type: "line",
      data: { labels: labels, datasets: ["Primarias", "Secundarias", "Terciarias"].map(function (n) {
        return { label: n, data: byId[n.toLowerCase()].valor.slice(r[0], r[1]), borderColor: COLORS[n],
                 borderWidth: 1.6, pointRadius: 0, pointHoverRadius: 3, tension: 0.15 };
      }) },
      options: o2
    });

    // Contribución por subsector (mes seleccionado)
    var rows = subs.map(function (s) { return { s: s, c: s.contrib[state.idx], va: s.var_anual[state.idx] }; })
                   .filter(function (x) { return x.c != null; })
                   .sort(function (a, b) { return b.c - a.c; });
    var o3 = baseOptions();
    o3.indexAxis = "y";
    o3.interaction = { mode: "nearest", intersect: true, axis: "y" };
    o3.scales = {
      x: { grid: { color: css("--grid") }, title: { display: true, text: "puntos porcentuales (pp)" } },
      y: { grid: { display: false }, ticks: { autoSkip: false, font: { size: 11 },
            callback: function (v) { return shorten(this.getLabelForValue(v), window.innerWidth < 520 ? 22 : 46); } } }
    };
    o3.plugins.tooltip = { callbacks: {
      title: function (items) { return rows[items[0].dataIndex].s.nombre; },
      label: function (c) { var x = rows[c.dataIndex]; return fmt(x.c, 2) + " pp · var. anual " + pct(x.va); }
    } };
    replaceChart("contrib", "ch-contrib", {
      type: "bar",
      data: { labels: rows.map(function (x) { return x.s.nombre; }), datasets: [{
        data: rows.map(function (x) { return x.c; }),
        backgroundColor: rows.map(function (x) { return x.c >= 0 ? css("--pos") : css("--neg"); }),
        borderRadius: 3, barPercentage: 0.8
      }] },
      options: o3
    });
  }

  /* ---------------- Tabla de subsectores ---------------- */
  function renderTable() {
    var i = state.idx;
    var rows = subs.filter(function (s) { return !state.act || s.actividad === state.act; }).map(function (s) {
      return { actividad: s.actividad, codigo: s.codigo, nombre: s.nombre,
               var_anual: s.var_anual[i], var_acum: s.var_acum[i], contrib: s.contrib[i] };
    });
    var k = state.sortKey, d = state.sortDir;
    rows.sort(function (a, b) {
      var x = a[k], y = b[k];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      if (typeof x === "string") return x.localeCompare(y, "es") * d;
      return (x - y) * d;
    });
    document.querySelector("#tbl-sub tbody").innerHTML = rows.map(function (r) {
      return "<tr><td>" + esc(r.actividad) + '</td><td><span class="cod">' + esc(r.codigo) + "</span>" + esc(r.nombre) + "</td>" +
        '<td class="num ' + sign(r.var_anual) + '">' + pct(r.var_anual) + "</td>" +
        '<td class="num ' + sign(r.var_acum) + '">' + pct(r.var_acum) + "</td>" +
        '<td class="num ' + sign(r.contrib) + '">' + fmt(r.contrib, 2) + "</td></tr>";
    }).join("");
    document.querySelectorAll("#tbl-sub th.sortable").forEach(function (th) {
      th.setAttribute("aria-sort", th.dataset.k === k ? (d > 0 ? "ascending" : "descending") : "none");
    });
  }

  /* ---------------- Botón de descarga y lista de reportes ---------------- */
  function renderDownload() {
    var ym = D.periodos[state.idx], a = $("btn-reporte"), rep = reporteDe[ym];
    if (rep) {
      a.hidden = false;
      a.href = rep.archivo;
      a.textContent = "⬇ Descargar reporte de " + lbl(ym);
    } else {
      a.hidden = true;
    }
  }

  function renderReportes() {
    var tb = document.querySelector("#tbl-rep tbody");
    if (!reportes.length) {
      tb.innerHTML = '<tr><td colspan="4">Todavía no hay reportes generados.</td></tr>';
      return;
    }
    tb.innerHTML = reportes.map(function (r, k) {
      return "<tr><td><strong>" + esc(cap(r.label)) + "</strong>" + (k === 0 ? '<span class="badge">más reciente</span>' : "") +
        "</td><td>" + esc(r.archivo.split("/").pop()) + '</td><td class="num">' + esc(r.kb) + ' KB</td>' +
        '<td class="num"><a class="btn" href="' + esc(r.archivo) + '" download>⬇ Descargar</a></td></tr>';
    }).join("");
  }

  /* ---------------- Navegación y eventos ---------------- */
  function showTab(name) {
    ["dashboard", "reportes"].forEach(function (t) {
      var on = t === name;
      $("panel-" + t).hidden = !on;
      $("tab-" + t).setAttribute("aria-selected", on ? "true" : "false");
    });
    if (name === "dashboard") renderCharts(); // los canvas ocultos miden 0: se redibujan al mostrarse
  }

  function renderAll() {
    renderKpis(); renderCharts(); renderTable(); renderDownload();
  }

  function init() {
    byId = {};
    D.series.forEach(function (s) { byId[s.id] = s; });
    subs = D.series.filter(function (s) { return s.tipo === "subsector"; });
    reportes.forEach(function (r) { reporteDe[r.periodo] = r; });

    var last = D.periodos.length - 1;
    state.idx = last;
    var sel = $("sel-mes"), opts = "";
    for (var i = last; i >= MIN_IDX; i--) {
      opts += '<option value="' + i + '">' + esc(cap(lbl(D.periodos[i]))) + (i === last ? " (más reciente)" : "") + "</option>";
    }
    sel.innerHTML = opts;
    sel.addEventListener("change", function () { state.idx = +sel.value; renderAll(); });

    document.querySelectorAll("#rango button").forEach(function (b) {
      b.addEventListener("click", function () {
        state.rango = +b.dataset.m;
        document.querySelectorAll("#rango button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        renderCharts();
      });
    });
    $("f-act").addEventListener("change", function (e) { state.act = e.target.value; renderTable(); });
    document.querySelectorAll("#tbl-sub th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var k = th.dataset.k;
        state.sortDir = state.sortKey === k ? -state.sortDir : (k === "nombre" || k === "actividad" ? 1 : -1);
        state.sortKey = k;
        renderTable();
      });
    });
    $("tab-dashboard").addEventListener("click", function () { history.replaceState(null, "", "#dashboard"); showTab("dashboard"); });
    $("tab-reportes").addEventListener("click", function () { history.replaceState(null, "", "#reportes"); showTab("reportes"); });
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      var rerender = function () { if (!$("panel-dashboard").hidden) renderCharts(); };
      if (mq.addEventListener) mq.addEventListener("change", rerender);
    }

    renderReportes();
    renderAll();
    showTab(location.hash === "#reportes" ? "reportes" : "dashboard");

    var fecha = estado.generado_en ? new Date(estado.generado_en).toLocaleDateString("es-MX", { dateStyle: "long" }) : "";
    $("pie").innerHTML = "Fuente: INEGI, Indicador Global de la Actividad Económica (IGAE). Último dato: <strong>" +
      esc(estado.ultimo_periodo_label || lbl(D.periodos[last])) + "</strong>" + (fecha ? " · Actualizado el " + esc(fecha) : "") + ".";
  }

  Promise.all([getJSON("data/data.json"), getJSON("data/reportes.json"), getJSON("data/estado.json")])
    .then(function (r) { D = r[0]; reportes = r[1]; estado = r[2]; init(); })
    .catch(showError);
})();
