/* Zero Latency VR Richmond — booking flow (vanilla JS, no build step). */
(function () {
  "use strict";

  var state = {
    config: null,
    experience: null,
    date: null,      // YYYY-MM-DD
    time: null,      // HH:MM
    timeLabel: null,
    players: 1,
    name: "",
    email: "",
    phone: "",
  };

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function money(cents) { return "$" + (cents / 100).toFixed(cents % 100 === 0 ? 0 : 2); }

  function banner(msg, kind) {
    var b = $("#banner");
    if (!msg) { b.hidden = true; return; }
    b.hidden = false;
    b.className = "banner " + (kind || "info");
    b.textContent = msg;
  }

  function gotoStep(n) {
    $$(".step").forEach(function (s) { s.hidden = parseInt(s.dataset.step, 10) !== n; });
    $$("#stepbar li").forEach(function (li) {
      var st = parseInt(li.dataset.step, 10);
      li.classList.toggle("active", st === n);
      li.classList.toggle("done", st < n);
    });
    banner("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* ---- Step 1: experiences ---- */
  function renderExperiences() {
    var grid = $("#experienceGrid");
    grid.innerHTML = "";
    state.config.experiences.forEach(function (e) {
      var card = document.createElement("div");
      card.className = "exp-card";
      card.innerHTML =
        '<div class="exp-poster" style="background:linear-gradient(150deg,' + e.accent + '33,#0c0c16 70%)">' +
          '<span class="badge">' + e.tag + '</span>' + e.emoji +
        '</div>' +
        '<div class="exp-info">' +
          '<h3>' + e.name + '</h3>' +
          '<p>' + e.summary + '</p>' +
          '<div class="exp-meta">' +
            '<span>⏱ <b>' + e.duration_min + ' min</b></span>' +
            '<span>👥 <b>' + e.min_players + '–' + e.max_players + '</b></span>' +
            '<span>🔥 <b>' + e.intensity + '</b></span>' +
          '</div>' +
          '<div class="exp-foot">' +
            '<div class="exp-price">' + e.price_display + ' <small>/ player</small></div>' +
            '<button class="pick">Select →</button>' +
          '</div>' +
        '</div>';
      card.addEventListener("click", function () { selectExperience(e); });
      grid.appendChild(card);
    });
  }

  function selectExperience(e) {
    state.experience = e;
    state.players = e.min_players;
    state.date = null; state.time = null;
    renderDates();
    $("#dateSub").textContent = e.name + " · " + e.duration_min + " min · up to " + e.max_players + " players";
    gotoStep(2);
  }

  /* ---- Step 2: dates ---- */
  function renderDates() {
    var grid = $("#dateGrid");
    grid.innerHTML = "";
    var horizon = state.config.venue.horizon_days || 30;
    var today = new Date(state.config.today + "T00:00:00");
    var dows = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    var mons = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    for (var i = 0; i < horizon; i++) {
      var d = new Date(today.getTime() + i * 86400000);
      var iso = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
      var cell = document.createElement("div");
      cell.className = "date-cell";
      cell.dataset.date = iso;
      cell.innerHTML =
        '<div class="dow">' + (i === 0 ? "Today" : dows[d.getDay()]) + '</div>' +
        '<div class="day">' + d.getDate() + '</div>' +
        '<div class="mon">' + mons[d.getMonth()] + '</div>';
      (function (isoDate) {
        cell.addEventListener("click", function () { selectDate(isoDate); });
      })(iso);
      grid.appendChild(cell);
    }
  }

  function selectDate(iso) {
    state.date = iso;
    state.time = null;
    $$("#dateGrid .date-cell").forEach(function (c) { c.classList.toggle("sel", c.dataset.date === iso); });
    loadTimes();
    gotoStep(3);
  }

  /* ---- Step 3: times ---- */
  function loadTimes() {
    var grid = $("#timeGrid");
    grid.innerHTML = '<div class="empty">Loading sessions…</div>';
    var prettyDate = new Date(state.date + "T00:00:00").toLocaleDateString(undefined,
      { weekday: "long", month: "long", day: "numeric" });
    $("#timeSub").textContent = state.experience.name + " · " + prettyDate;
    fetch("/api/vr/availability?experience_id=" + encodeURIComponent(state.experience.id) +
          "&date=" + encodeURIComponent(state.date))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        grid.innerHTML = "";
        if (!data.slots || !data.slots.length) {
          grid.innerHTML = '<div class="empty">No sessions available on this date — try another day.</div>';
          return;
        }
        data.slots.forEach(function (s) {
          var cell = document.createElement("div");
          cell.className = "time-cell" + (s.soldout ? " soldout" : "");
          cell.innerHTML = '<div class="t">' + s.label + '</div>' +
            '<div class="left">' + (s.soldout ? "Sold out" : s.remaining + " spots left") + '</div>';
          if (!s.soldout) {
            cell.addEventListener("click", function () { selectTime(s); });
          }
          grid.appendChild(cell);
        });
      })
      .catch(function () { grid.innerHTML = '<div class="empty">Could not load sessions. Please retry.</div>'; });
  }

  function selectTime(s) {
    state.time = s.time;
    state.timeLabel = s.label;
    state.maxRemaining = s.remaining;
    if (state.players > s.remaining) state.players = Math.max(state.experience.min_players, s.remaining);
    renderPlayers();
    gotoStep(4);
  }

  /* ---- Step 4: players ---- */
  function renderPlayers() {
    var e = state.experience;
    var cap = Math.min(e.max_players, state.maxRemaining || e.max_players);
    if (state.players < e.min_players) state.players = e.min_players;
    if (state.players > cap) state.players = cap;
    $("#playerCount").textContent = state.players;
    $("#playersTotal").textContent = money(e.price * state.players);
    $("#playersSub").textContent = e.name + " · " + state.timeLabel + " · " + e.price_display + " per player";
    $("#minusBtn").disabled = state.players <= e.min_players;
    $("#plusBtn").disabled = state.players >= cap;
  }

  /* ---- Step 6: summary ---- */
  function renderSummary() {
    var e = state.experience;
    var prettyDate = new Date(state.date + "T00:00:00").toLocaleDateString(undefined,
      { weekday: "short", month: "short", day: "numeric" });
    $("#sumPoster").textContent = e.emoji;
    $("#sumPoster").style.background = "linear-gradient(150deg," + e.accent + "44,#0c0c16 70%)";
    $("#sumExp").textContent = e.name;
    $("#sumWhen").textContent = prettyDate + " · " + state.timeLabel;
    $("#sumPlayers").textContent = state.players + " × " + e.price_display;
    $("#sumName").textContent = state.name;
    $("#sumEmail").textContent = state.email;
    $("#sumTotal").textContent = money(e.price * state.players);
    $("#payNote").textContent = state.config.stripe_enabled
      ? "You'll be redirected to Stripe's secure checkout to pay " + money(e.price * state.players) + "."
      : "Demo mode: Stripe isn't configured, so this reservation will be confirmed without a real charge.";
    $("#payBtn").textContent = state.config.stripe_enabled ? "Pay " + money(e.price * state.players) + " →" : "Confirm reservation →";
  }

  /* ---- Pay ---- */
  function pay() {
    var btn = $("#payBtn");
    btn.disabled = true;
    btn.textContent = "Starting checkout…";
    fetch("/api/vr/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        experience_id: state.experience.id,
        date: state.date,
        time: state.time,
        players: state.players,
        name: state.name,
        email: state.email,
        phone: state.phone,
      }),
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          banner(res.body.detail || "Could not start checkout.", "warn");
          renderSummary(); btn.disabled = false;
          return;
        }
        window.location.href = res.body.checkout_url;
      })
      .catch(function () {
        banner("Network error — please try again.", "warn");
        renderSummary(); btn.disabled = false;
      });
  }

  /* ---- Wire up ---- */
  function init() {
    // Cancelled-return notice.
    var params = new URLSearchParams(window.location.search);
    if (params.get("cancelled")) {
      banner("Payment cancelled — your spot wasn't booked. You can pick another time.", "warn");
    }

    $$("[data-goto]").forEach(function (b) {
      b.addEventListener("click", function () { gotoStep(parseInt(b.dataset.goto, 10)); });
    });
    $("#minusBtn").addEventListener("click", function () { state.players--; renderPlayers(); });
    $("#plusBtn").addEventListener("click", function () { state.players++; renderPlayers(); });
    $("#toDetails").addEventListener("click", function () {
      // prefill if returning
      $("#fName").value = state.name; $("#fEmail").value = state.email; $("#fPhone").value = state.phone;
      gotoStep(5);
    });
    $("#detailsForm").addEventListener("submit", function (ev) {
      ev.preventDefault();
      state.name = $("#fName").value.trim();
      state.email = $("#fEmail").value.trim();
      state.phone = $("#fPhone").value.trim();
      if (!state.name || state.email.indexOf("@") < 0) {
        banner("Please enter your name and a valid email.", "warn");
        return;
      }
      renderSummary();
      gotoStep(6);
    });
    $("#payBtn").addEventListener("click", pay);

    fetch("/api/vr/config")
      .then(function (r) { return r.json(); })
      .then(function (cfg) {
        state.config = cfg;
        $("#brandName").textContent = cfg.venue.brand;
        $("#venuePill").textContent = cfg.venue.name;
        $("#tagline").textContent = cfg.venue.tagline;
        $("#footAddr").textContent = cfg.venue.brand + " · " + cfg.venue.address;
        renderExperiences();
        gotoStep(1);
      })
      .catch(function () { banner("Could not load the booking system. Please refresh.", "warn"); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();
