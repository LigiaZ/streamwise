// StreamWise front end. Everything the user logs lives in localStorage on their device;
// the Python API only looks up titles (TMDB) and computes the report from what we send it.
(function () {
  "use strict";

  var KEY = "streamwise:v1";
  var $ = function (sel) { return document.querySelector(sel); };
  var state = load();
  var catalog = null;          // { services: [...], countries: [...], currency, prices_as_of }
  var picked = null;           // title chosen in the add sheet
  var searchTimer = null, searchSeq = 0;

  // ---------------------------------------------------------------- storage
  function blank() { return { country: "NL", services: {}, log: [], demo: false, started: false }; }
  function load() {
    try {
      var s = JSON.parse(localStorage.getItem(KEY));
      if (s && typeof s === "object" && Array.isArray(s.log)) return Object.assign(blank(), s);
    } catch (e) {}
    return blank();
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }
  function activeServices() {
    return Object.keys(state.services).filter(function (id) { return state.services[id].on; });
  }

  // ---------------------------------------------------------------- helpers
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function iso(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function today() { return iso(new Date()); }
  function daysAgo(n) { var d = new Date(); d.setDate(d.getDate() - n); return iso(d); }
  function money(x, digits) {
    if (x == null) return "–";
    var cur = (catalog && catalog.currency) || "EUR";
    return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, maximumFractionDigits: digits == null ? 2 : digits, minimumFractionDigits: digits == null ? 2 : digits }).format(x);
  }
  function hours(min) {
    if (!min) return "0 h";
    var h = min / 60;
    return (h < 10 ? Math.round(h * 10) / 10 : Math.round(h)) + " h";
  }
  function fmtDate(s, opts) {
    var d = new Date(s + "T00:00:00");
    return d.toLocaleDateString(undefined, opts || { day: "numeric", month: "short" });
  }
  function svcInfo(id) {
    var found = catalog && catalog.services.filter(function (s) { return s.id === id; })[0];
    var known = catalog && catalog.all && catalog.all[id];
    return found || (known ? { id: id, name: known.name, color: known.color } : { id: id, name: id, color: "#888" });
  }
  function initials(name) {
    return name.replace(/[^A-Za-z0-9 ]/g, "").split(" ").map(function (w) { return w[0]; }).join("").slice(0, 2).toUpperCase();
  }
  function logo(id) {
    var s = svcInfo(id);
    return '<span class="logo" style="background:' + esc(s.color) + '">' + esc(initials(s.name)) + "</span>";
  }
  var toastTimer;
  function toast(msg) {
    var t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove("show"); }, 2600);
  }
  function api(path, body) {
    var opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch("/api/" + path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) { var e = new Error(data.error || "Something went wrong."); e.status = r.status; throw e; }
        return data;
      });
    });
  }
  function loadCatalog() {
    return api("catalog?country=" + encodeURIComponent(state.country)).then(function (c) { catalog = c; });
  }

  // ---------------------------------------------------------------- navigation
  var current = "overview";
  function show(view) {
    current = view;
    var welcome = !state.started && !activeServices().length && !state.log.length;
    $("#view-welcome").hidden = !welcome;
    ["overview", "log", "services"].forEach(function (v) {
      $("#view-" + v).hidden = welcome || v !== view;
    });
    $("#tabs").hidden = welcome;
    $("#fab").hidden = welcome || view === "services";
    $("#demo-pill").hidden = !state.demo;
    document.querySelectorAll(".tabs button").forEach(function (b) {
      if (b.dataset.tab === view) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    if (welcome) return;
    if (view === "overview") renderOverview();
    if (view === "log") renderLog();
    if (view === "services") renderServices();
    window.scrollTo(0, 0);
  }

  // ---------------------------------------------------------------- overview
  function renderOverview() {
    var ids = activeServices();
    if (!ids.length) {
      $("#summary").innerHTML = '<p style="margin:0">Pick the services you pay for to see what they’re worth.</p><div class="stack"><button class="btn primary" data-goto="services">Choose services</button></div>';
      $("#cards").innerHTML = "";
      $("#report-meta").textContent = "";
      return;
    }
    $("#summary").innerHTML = '<p class="status">Crunching the numbers…</p>';
    var services = ids.map(function (id) {
      var s = state.services[id];
      return { id: id, name: svcInfo(id).name, price: Number(s.price) || 0, since: s.since || null };
    });
    api("report", { country: state.country, today: today(), services: services, log: state.log })
      .then(drawReport)
      .catch(function (e) {
        $("#summary").innerHTML = '<p style="margin:0">Couldn’t build your report: ' + esc(e.message) + "</p>";
      });
  }

  function drawReport(r) {
    var save = r.yearly_savings > 0;
    $("#summary").innerHTML =
      '<div class="big">' + money(r.monthly_total) + " <small>a month · " + money(r.yearly_total, 0) + " a year</small></div>" +
      '<div class="stats">' +
        "<div><b>" + r.hours_30d + " h</b><span>watched in 30 days</span></div>" +
        "<div><b>" + (r.cost_per_hour == null ? "–" : money(r.cost_per_hour)) + "</b><span>per hour overall</span></div>" +
        "<div><b>" + (save ? money(r.yearly_savings, 0) : "–") + "</b><span>a year on unused services</span></div>" +
      "</div>" +
      '<p class="says' + (save ? " save" : "") + '">' + esc(r.summary) + "</p>";

    $("#cards").innerHTML = r.services.map(function (s) {
      var max = Math.max.apply(null, s.monthly.map(function (m) { return m.minutes; }).concat([60]));
      var bars = s.monthly.map(function (m) {
        var h = Math.round((m.minutes / max) * 100);
        return '<div class="' + (m.minutes ? "on" : "") + '" style="height:' + Math.max(h, 6) + '%" title="' + esc(m.month + ": " + hours(m.minutes)) + '"></div>';
      }).join("");
      var labels = s.monthly.map(function (m) {
        return "<span>" + new Date(m.month + "-01T00:00:00").toLocaleDateString(undefined, { month: "short" }) + "</span>";
      }).join("");
      return '<article class="card">' +
        '<div class="card-top">' + logo(s.id) +
          '<div><div class="name">' + esc(s.name) + '</div><div class="price">' + money(s.price) + " / month</div></div>" +
          '<span class="chip ' + s.verdict + '">' + esc(s.verdict_label) + "</span></div>" +
        '<div class="card-stats">' +
          "<div><b>" + s.hours_30d + " h</b><span>last 30 days</span></div>" +
          "<div><b>" + (s.cost_per_hour == null ? "–" : money(s.cost_per_hour)) + "</b><span>per hour</span></div>" +
          "<div><b>" + (s.last_watched ? fmtDate(s.last_watched) : "Never") + "</b><span>last watched</span></div>" +
        "</div>" +
        '<p class="reason">' + esc(s.reason) + "</p>" +
        (s.top_titles.length ? '<p class="titles">Recently: ' + esc(s.top_titles.join(" · ")) + "</p>" : "") +
        '<div class="bars" aria-label="Hours watched per month">' + bars + "</div>" +
        '<div class="bar-labels">' + labels + "</div>" +
      "</article>";
    }).join("");
    $("#report-meta").textContent = "Poor value means renting what you watched would have cost less (about " + money(2.5) + " per hour).";
  }

  // ---------------------------------------------------------------- log
  function renderLog() {
    if (!state.log.length) {
      $("#log-list").innerHTML = '<p class="empty">Nothing yet. Tap <b>+</b> to add a film or some episodes you watched.</p>';
      return;
    }
    var sorted = state.log.slice().sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; });
    var html = "", lastMonth = "";
    sorted.forEach(function (e) {
      var month = e.date.slice(0, 7);
      if (month !== lastMonth) {
        html += '<div class="month">' + esc(new Date(month + "-01T00:00:00").toLocaleDateString(undefined, { month: "long", year: "numeric" })) + "</div>";
        lastMonth = month;
      }
      html += '<div class="entry">' +
        (e.poster ? '<img src="' + esc(e.poster) + '" alt="" loading="lazy">' : '<span class="ph"></span>') +
        '<div class="t"><b>' + esc(e.title) + "</b><span>" + esc(svcInfo(e.service).name) + " · " + hours(e.minutes) +
          (e.episodes > 1 ? " · " + e.episodes + " episodes" : "") + " · " + fmtDate(e.date) + "</span></div>" +
        '<button data-delete="' + esc(e.id) + '" aria-label="Delete ' + esc(e.title) + '">✕</button></div>';
    });
    $("#log-list").innerHTML = html;
  }

  // ---------------------------------------------------------------- services
  var OTHER = "__other";

  function plansFor(id) {
    var s = catalog.services.filter(function (x) { return x.id === id; })[0];
    return s ? s.plans : [];
  }
  // Which plan is this subscription on? By saved name, else by matching price, else "Other amount".
  function currentPlan(id) {
    var mine = state.services[id] || {}, plans = plansFor(id);
    if (mine.plan === OTHER) return OTHER;
    var byName = plans.filter(function (p) { return p.name === mine.plan; })[0];
    if (byName) return byName.name;
    var byPrice = plans.filter(function (p) { return p.price === Number(mine.price); })[0];
    return byPrice ? byPrice.name : OTHER;
  }

  function renderServices() {
    $("#country").innerHTML = catalog.countries.map(function (c) {
      return '<option value="' + c.code + '"' + (c.code === state.country ? " selected" : "") + ">" + esc(c.name) + "</option>";
    }).join("");
    $("#price-note").textContent = "Plans and prices as of " +
      new Date(catalog.prices_as_of + "-01T00:00:00").toLocaleDateString(undefined, { month: "long", year: "numeric" }) +
      ". Pick “Other amount” if you pay something different, like a bundle or a yearly deal.";

    // Services sold in this country, plus any you still have switched on from elsewhere.
    var listed = catalog.services.map(function (s) { return s.id; });
    var extra = activeServices().filter(function (id) { return listed.indexOf(id) < 0; });
    $("#service-list").innerHTML = listed.concat(extra).map(function (id) {
      var s = svcInfo(id), mine = state.services[id] || {}, on = !!mine.on, plans = plansFor(id);
      var plan = on ? currentPlan(id) : null;
      var price = on ? Number(mine.price) : (s.default ? s.default.price : null);
      var sub = on
        ? (plan === OTHER ? "Other amount" : esc(plan)) + " · " + (isNaN(price) ? "–" : money(price)) + " / month"
        : (plans.length > 1 ? plans.length + " plans · from " + money(plans[0].price) : plans.length ? money(plans[0].price) + " / month" : "Not listed in this country");
      var options = plans.map(function (p) {
        return '<option value="' + esc(p.name) + '"' + (p.name === plan ? " selected" : "") + ">" + esc(p.name) + " · " + money(p.price) + "</option>";
      }).join("") + '<option value="' + OTHER + '"' + (plan === OTHER ? " selected" : "") + ">Other amount…</option>";
      return '<div class="svc">' + logo(id) +
        '<div><div class="name">' + esc(s.name) + '</div><div class="fine" style="margin:0">' + sub + "</div></div>" +
        '<label class="switch"><input type="checkbox" data-svc="' + id + '"' + (on ? " checked" : "") + ' aria-label="I pay for ' + esc(s.name) + '"><span></span></label>' +
        (on ? '<div class="detail">' +
          '<label class="grow">Plan<select data-plan="' + id + '">' + options + "</select></label>" +
          (plan === OTHER ? '<label>Amount per month<input type="number" step="0.01" min="0" inputmode="decimal" data-price="' + id + '" value="' + esc(isNaN(price) ? "" : price) + '"></label>' : "") +
          '<label>Subscribed since<input type="date" data-since="' + id + '" value="' + esc(mine.since || "") + '"></label>' +
        "</div>" : "") +
      "</div>";
    }).join("");
  }

  // After switching country, move each subscription to the same-named plan there (if any).
  function remapPlans() {
    activeServices().forEach(function (id) {
      var mine = state.services[id], p = plansFor(id).filter(function (x) { return x.name === mine.plan; })[0];
      if (p) mine.price = p.price;
      else if (mine.plan !== OTHER) { var d = svcInfo(id).default; if (d) { mine.plan = d.name; mine.price = d.price; } else mine.plan = OTHER; }
    });
  }

  document.addEventListener("change", function (ev) {
    var t = ev.target;
    if (t.id === "country") {
      state.country = t.value;
      loadCatalog().then(function () { remapPlans(); save(); renderServices(); });
    } else if (t.dataset.svc) {
      var id = t.dataset.svc, d = svcInfo(id).default;
      var mine = state.services[id] || { since: today() };
      mine.on = t.checked;
      if (t.checked && mine.price == null) {
        if (d) { mine.plan = d.name; mine.price = d.price; } else { mine.plan = OTHER; mine.price = null; }
      }
      state.services[id] = mine; save(); renderServices();
    } else if (t.dataset.plan) {
      var sid = t.dataset.plan, chosen = plansFor(sid).filter(function (p) { return p.name === t.value; })[0];
      state.services[sid].plan = t.value;
      if (chosen) state.services[sid].price = chosen.price;
      save(); renderServices();
      if (t.value === OTHER) { var inp = document.querySelector('[data-price="' + sid + '"]'); if (inp) inp.focus(); }
    } else if (t.dataset.price) {
      state.services[t.dataset.price].price = t.value === "" ? null : Number(t.value); save(); renderServices();
    } else if (t.dataset.since) {
      state.services[t.dataset.since].since = t.value || null; save();
    } else if (t.id === "import") {
      importBackup(t.files[0]); t.value = "";
    }
  });

  // ---------------------------------------------------------------- add sheet
  var sheet = $("#add-sheet");

  function openAdd() {
    if (!activeServices().length) { toast("Choose your services first."); show("services"); return; }
    picked = null;
    $("#q").value = "";
    $("#results").innerHTML = "";
    $("#step-search").hidden = false;
    $("#step-details").hidden = true;
    sheet.showModal();
    setTimeout(function () { $("#q").focus(); }, 50);
  }

  $("#q").addEventListener("input", function () {
    clearTimeout(searchTimer);
    var q = this.value.trim();
    if (q.length < 2) { $("#results").innerHTML = ""; return; }
    searchTimer = setTimeout(function () { runSearch(q); }, 300);
  });

  function runSearch(q) {
    var seq = ++searchSeq;
    $("#results").innerHTML = '<p class="status">Searching…</p>';
    api("search?q=" + encodeURIComponent(q)).then(function (data) {
      if (seq !== searchSeq) return;
      if (!data.results.length) { $("#results").innerHTML = '<p class="status">No matches. Try another spelling, or add it manually.</p>'; return; }
      $("#results").innerHTML = data.results.map(function (r, i) {
        return '<button type="button" class="result" data-pick="' + i + '">' +
          (r.poster ? '<img src="' + esc(r.poster) + '" alt="" loading="lazy">' : '<span class="ph"></span>') +
          "<div><b>" + esc(r.title) + "</b><span>" + (r.kind === "tv" ? "Series" : "Film") + (r.year ? " · " + r.year : "") + "</span></div></button>";
      }).join("");
      $("#results").dataset.items = JSON.stringify(data.results);
    }).catch(function (e) {
      if (seq !== searchSeq) return;
      $("#results").innerHTML = '<p class="status">' + esc(e.message) + "</p>";
    });
  }

  function serviceOptions(preferred) {
    var ids = activeServices();
    var pick = ids.indexOf(preferred) >= 0 ? preferred : ids[0];
    $("#service").innerHTML = ids.map(function (id) {
      return '<option value="' + id + '"' + (id === pick ? " selected" : "") + ">" + esc(svcInfo(id).name) + "</option>";
    }).join("");
  }

  function pickTitle(r) {
    $("#step-search").hidden = true;
    $("#step-details").hidden = false;
    $("#title-field").hidden = true;
    $("#picked").innerHTML = (r.poster ? '<img src="' + esc(r.poster) + '" alt="">' : "") +
      "<div><b>" + esc(r.title) + "</b><span>" + (r.kind === "tv" ? "Series" : "Film") + (r.year ? " · " + r.year : "") + "</span></div>";
    $("#where").innerHTML = '<span class="status" style="padding:0">Looking up runtime and where it streams…</span>';
    $("#episodes-field").hidden = r.kind !== "tv";
    $("#episodes").value = 1;
    $("#minutes").value = "";
    $("#date").value = today();
    serviceOptions(null);
    picked = { title: r.title, kind: r.kind, tmdbId: r.id, poster: r.poster };

    api("title?kind=" + r.kind + "&id=" + r.id + "&country=" + state.country).then(function (t) {
      if (!picked || picked.tmdbId !== t.id) return;
      picked.episodeMinutes = t.episode_minutes || null;
      $("#minutes").value = r.kind === "tv" ? t.episode_minutes : (t.minutes || "");
      var mine = activeServices();
      var ownedMatch = t.providers.filter(function (p) { return p.service && mine.indexOf(p.service) >= 0; })[0];
      serviceOptions(ownedMatch && ownedMatch.service);
      var countryName = (catalog.countries.filter(function (c) { return c.code === state.country; })[0] || {}).name || state.country;
      var where = t.providers.length
        ? "Streaming in " + esc(countryName) + " on " + t.providers.map(function (p) { return "<b>" + esc(p.name) + "</b>"; }).join(", ") + "."
        : "Not on a subscription service in " + esc(countryName) + " right now.";
      if (t.next_episode && t.next_episode.air_date) {
        where += '<span class="next">Next: season ' + t.next_episode.season + ", episode " + t.next_episode.episode + " on " +
          esc(fmtDate(t.next_episode.air_date, { day: "numeric", month: "long", year: "numeric" })) + "</span>";
      }
      $("#where").innerHTML = where;
    }).catch(function (e) {
      $("#where").textContent = e.message + " Enter the minutes yourself.";
    });
  }

  $("#episodes").addEventListener("input", function () {
    if (picked && picked.episodeMinutes) $("#minutes").value = Math.max(1, Number(this.value) || 1) * picked.episodeMinutes;
  });

  function manual() {
    picked = { title: "", kind: "manual" };
    $("#step-search").hidden = true;
    $("#step-details").hidden = false;
    $("#picked").innerHTML = "";
    $("#where").innerHTML = "";
    $("#episodes-field").hidden = true;
    $("#title-field").hidden = false;
    $("#manual-title").value = $("#q").value;
    $("#minutes").value = "";
    $("#date").value = today();
    serviceOptions(null);
    $("#manual-title").focus();
  }

  $("#add-form").addEventListener("submit", function (ev) {
    if (ev.submitter && ev.submitter.value !== "save") return;
    ev.preventDefault();
    var title = picked.kind === "manual" ? $("#manual-title").value.trim() : picked.title;
    var minutes = Math.round(Number($("#minutes").value));
    if (!title) { $("#manual-title").focus(); return; }
    if (!minutes || minutes < 1) { $("#minutes").focus(); return; }
    var episodes = picked.kind === "tv" ? Math.max(1, Number($("#episodes").value) || 1) : null;
    state.log.push({
      id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      title: title, minutes: minutes, service: $("#service").value, date: $("#date").value || today(),
      kind: picked.kind, tmdbId: picked.tmdbId || null, poster: picked.poster || null, episodes: episodes,
    });
    save();
    sheet.close();
    toast("Added " + title + " (" + hours(minutes) + ")");
    show(current === "services" ? "overview" : current);
  });

  // ---------------------------------------------------------------- backup / sample data / reset
  function exportBackup() {
    var blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "streamwise-backup-" + today() + ".json";
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }
  function importBackup(file) {
    if (!file) return;
    file.text().then(function (text) {
      var data = JSON.parse(text);
      if (!data || !Array.isArray(data.log) || typeof data.services !== "object") throw new Error("bad file");
      state = Object.assign(blank(), data, { demo: false, started: true });
      save();
      return loadCatalog();
    }).then(function () { toast("Backup restored."); show("overview"); })
      .catch(function () { toast("That doesn’t look like a StreamWise backup."); });
  }

  function demo() {
    // A believable three months for someone in the Netherlands. Made-up, not real viewing data.
    var ep = function (title, min, n, service, ago) { return { title: title, minutes: min * n, episodes: n, service: service, date: daysAgo(ago), kind: "tv" }; };
    var film = function (title, min, service, ago) { return { title: title, minutes: min, service: service, date: daysAgo(ago), kind: "movie" }; };
    var log = [
      film("The Lord of the Rings: The Fellowship of the Ring", 179, "prime", 3),
      film("The Lord of the Rings: The Two Towers", 179, "prime", 10),
      film("The Lord of the Rings: The Return of the King", 201, "prime", 17),
      ep("Wednesday", 50, 4, "netflix", 2), ep("Wednesday", 50, 3, "netflix", 6),
      ep("The Crown", 55, 2, "netflix", 12), film("Glass Onion", 139, "netflix", 20),
      ep("Squid Game", 55, 3, "netflix", 26), ep("Squid Game", 55, 3, "netflix", 40),
      ep("Bridgerton", 60, 4, "netflix", 55), ep("Bridgerton", 60, 4, "netflix", 70),
      ep("The Last of Us", 55, 1, "hbo", 9),
      ep("Andor", 45, 3, "disney", 52), ep("Andor", 45, 4, "disney", 80),
      film("Dune", 155, "hbo", 95), ep("The Bear", 30, 6, "disney", 110),
    ];
    state = {
      country: "NL", demo: true, started: true, log: log.map(function (e, i) { e.id = "demo" + i; return e; }),
      services: {
        netflix: { on: true, plan: "Standard", price: 15.99, since: daysAgo(400) },
        prime: { on: true, plan: "Prime Video", price: 4.99, since: daysAgo(400) },
        disney: { on: true, plan: "Standard", price: 10.99, since: daysAgo(300) },
        hbo: { on: true, plan: "Standard", price: 11.99, since: daysAgo(200) },
      },
    };
    save();
    loadCatalog().then(function () { show("overview"); });
  }

  function reset() {
    if (!confirm("Delete all your services and everything you’ve logged on this device?")) return;
    state = blank(); save();
    loadCatalog().then(function () { show("overview"); });
  }

  // ---------------------------------------------------------------- clicks
  document.addEventListener("click", function (ev) {
    var el = ev.target.closest("[data-action], [data-tab], [data-goto], [data-delete], [data-pick]");
    if (!el) return;
    if (el.dataset.tab) return show(el.dataset.tab);
    if (el.dataset.goto) return show(el.dataset.goto);
    if (el.dataset.delete) {
      var gone = state.log.filter(function (e) { return e.id === el.dataset.delete; })[0];
      state.log = state.log.filter(function (e) { return e.id !== el.dataset.delete; });
      save(); renderLog();
      if (gone) toast("Removed " + gone.title);
      return;
    }
    if (el.dataset.pick) {
      var items = JSON.parse($("#results").dataset.items || "[]");
      return pickTitle(items[Number(el.dataset.pick)]);
    }
    switch (el.dataset.action) {
      case "start": state.started = true; save(); show("services"); break;
      case "demo": demo(); break;
      case "add": openAdd(); break;
      case "manual": manual(); break;
      case "back": $("#step-details").hidden = true; $("#step-search").hidden = false; picked = null; break;
      case "export": exportBackup(); break;
      case "reset": reset(); break;
    }
  });

  // ---------------------------------------------------------------- start
  loadCatalog().then(function () { show("overview"); }).catch(function () {
    document.querySelector("main").innerHTML = '<p class="empty">StreamWise couldn’t start. Check your connection and reload.</p>';
  });
})();
