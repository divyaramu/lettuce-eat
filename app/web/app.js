// All dynamic text goes through textContent / createTextNode (no innerHTML) => no XSS from scraped content.
const RESTRICTIONS = ["peanut_free","tree_nut_free","shellfish_free","dairy_free","egg_free","soy_free","sesame_free","gluten_free","vegan","vegetarian","halal","kosher"];
const TIER = {official_verified:"Official source", community_verified:"Community verified", questionable:"Questionable: call to check", reported_unsafe:"Warning reported"};
const STORAGE_KEY = "lettuce-eat-saved-groups";
const $ = (t, props = {}, ...kids) => { const e = document.createElement(t); Object.assign(e, props); kids.forEach(k => e.append(k)); return e; };
const root = document.getElementById("app");
const m = location.pathname.match(/^\/g\/([\w-]+)/);
const gid = m && m[1], tok = new URLSearchParams(location.search).get("t");
const api = (p, o) => fetch(p, o).then(async r => { if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.status); return r.json(); });
const label = s => s.replace(/_/g, " ");
const safeHref = u => /^https?:\/\//i.test(u) ? u : "#";

function normalizeCustomRestrictions(raw) {
  return (raw || "")
    .split(/[\n,]/)
    .map(s => s.trim())
    .filter(Boolean)
    .filter(s => s.length <= 40);
}

function loadSavedGroups() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); }
  catch { return []; }
}

function saveGroupForLater(title, url) {
  const arr = loadSavedGroups();
  const next = [{title, url, savedAt: Date.now()}, ...arr.filter(v => v.url !== url)].slice(0, 5);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

function renderSavedGroups() {
  const saved = loadSavedGroups();
  const tray = $("div", {className: "saved-groups"});
  if (!saved.length) {
    tray.append($("div", {className: "saved-empty", textContent: "No saved groups yet."}));
    return tray;
  }
  saved.forEach(item => {
    const card = $("button", {className: "saved-group", type: "button", onclick: () => window.location.href = item.url});
    card.append($("strong", {textContent: item.title}), $("small", {textContent: "Open group"}));
    tray.append(card);
  });
  return tray;
}

function mapPreview(venues = []) {
  const wrap = $("div", {className: "map-preview"});
  const map = $("div", {className: "map-surface"});
  const points = venues.slice(0, 5);
  if (points.length) {
    points.forEach((v, i) => {
      const pin = $("div", {className: "map-pin", style: `left:${12 + i * 18}%`},
        $("span", {className: "map-dot"}),
        $("span", {className: "map-tag", textContent: v.name.split(" ")[0] || "Spot"})
      );
      map.append(pin);
    });
  }
  wrap.append(map);
  return wrap;
}

function loadingCard(label = "Checking official sites, blogs, Reddit and reviews...") {
  return $("div", {className: "card loading-card"},
    $("div", {className: "loading-head"},
      $("span", {className: "kicker", textContent: "Scanning"}),
      $("strong", {textContent: label})
    ),
    mapPreview(),
    $("div", {className: "progress-bar"}, $("span", {className: "progress-fill"}))
  );
}

function reverseGeocode(lat, lon) {
  const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&zoom=12&addressdetails=1`;
  return fetch(url, {headers: {"Accept-Language": "en"}})
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data) return "Selected location";
      const addr = data.address || {};
      const parts = [
        addr.city || addr.town || addr.village || addr.municipality,
        addr.state || addr.county,
        addr.country
      ].filter(Boolean);
      return parts.slice(0, 3).join(", ") || data.display_name?.split(",").slice(0, 3).join(", ") || "Selected location";
    })
    .catch(() => "Selected location");
}

function createGeoSelector() {
  const state = {lat: 47.6062, lon: -122.3321, radius: 5};
  const label = $("span", {className: "radius-chip", textContent: "5 km"});
  const slider = $("input", {id: "radius-range", type: "range", min: "1", max: "15", value: "5"});
  slider.addEventListener("input", () => {
    state.radius = Number(slider.value);
    label.textContent = `${state.radius} km`;
    if (window.L && window.__lettuceMapCircle) {
      window.__lettuceMapCircle.setRadius(state.radius * 1000);
    }
  });

  const mapEl = $("div", {id: "location-map", className: "location-map"});
  setTimeout(() => {
    if (!window.L) return;
    const map = window.L.map(mapEl).setView([state.lat, state.lon], 11);
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(map);
    const marker = window.L.marker([state.lat, state.lon]).addTo(map);
    const circle = window.L.circle([state.lat, state.lon], {radius: state.radius * 1000, color: "#2f7d4a", fillOpacity: 0.12}).addTo(map);
    window.__lettuceMapCircle = circle;
    map.on("click", (evt) => {
      state.lat = evt.latlng.lat;
      state.lon = evt.latlng.lng;
      marker.setLatLng([state.lat, state.lon]);
      circle.setLatLng([state.lat, state.lon]);
      const field = document.getElementById("area-input");
      if (field) {
        reverseGeocode(state.lat, state.lon).then(value => {
          field.value = value;
        });
      }
    });
  }, 0);

  return {state, slider, label, mapEl};
}

function home() {
  const geo = createGeoSelector();
  root.replaceChildren(
    $("div", {className: "card hero"},
      $("span", {className: "kicker", textContent: "Dining, made safer"}),
      $("h1", {textContent: "Lettuce Eat"}),
      $("p", {className: "mute", textContent: "Find places where everyone in your group can actually eat."}),
      $("div", {className: "stack"},
        $("label", {className: "field-label", textContent: "Area"}),
        $("input", {type: "text", id: "area-input", value: "Seattle, WA", maxLength: 80}),
        geo.mapEl,
        $("div", {className: "radius-row"},
          $("span", {className: "field-label", textContent: "Radius"}),
          geo.slider,
          geo.label
        ),
        $("div", {className: "button-row"},
          $("button", {textContent: "Start a group", onclick: async () => {
            const areaInput = document.getElementById("area-input");
            const area = areaInput ? areaInput.value.trim() || "Seattle, WA" : "Seattle, WA";
            const g = await api("/api/groups", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({
              area,
              lat: geo.state.lat,
              lon: geo.state.lon,
              radius_km: geo.state.radius
            })});
            location.href = `/g/${g.id}?t=${encodeURIComponent(g.token)}`;
          }}),
          $("button", {className: "secondary", textContent: "Clear", onclick: () => {
            const field = document.getElementById("area-input");
            if (field) field.value = "Seattle, WA";
            geo.state.lat = 47.6062;
            geo.state.lon = -122.3321;
            geo.state.radius = 5;
            geo.slider.value = "5";
            geo.label.textContent = "5 km";
            if (window.L && window.__lettuceMapCircle) {
              window.__lettuceMapCircle.setLatLng([geo.state.lat, geo.state.lon]);
              window.__lettuceMapCircle.setRadius(5000);
            }
          }})
        )
      )
    ),
    $("div", {className: "card"},
      $("h2", {textContent: "Saved groups"}),
      renderSavedGroups()
    )
  );
}

async function group() {
  const g = await api(`/api/groups/${gid}?t=${encodeURIComponent(tok)}`).catch(() => null);
  if (!g) return root.replaceChildren($("p", {textContent: "This link is invalid or expired."}));

  root.replaceChildren(
    $("div", {className: "card hero"},
      $("span", {className: "kicker", textContent: "Your group"}),
      $("h1", {textContent: g.area}),
      $("p", {className: "mute", textContent: "Share the link with friends and add each person’s restrictions."}),
      $("div", {className: "button-row"},
        $("button", {className: "secondary", textContent: "Save group", onclick: function() {
          const url = `${location.origin}/g/${g.id}?t=${encodeURIComponent(tok)}`;
          const next = saveGroupForLater(g.area, url);
          const btn = this;
          btn.textContent = next.length ? "Saved" : "Save group";
          btn.disabled = true;
        }}),
        $("button", {className: "secondary danger", textContent: "Clear", onclick: () => {
          location.href = "/";
        }})
      )
    )
  );

  const nick = $("input", {type: "text", placeholder: "Your nickname", maxLength: 30});
  const custom = $("input", {type: "text", placeholder: "Custom restriction (e.g. low FODMAP, no cilantro)", maxLength: 80});
  const boxes = RESTRICTIONS.map(r => { const c = $("input", {type: "checkbox", value: r}); return [c, $("label", {className: "chip"}, c, " " + label(r))]; });
  const add = $("button", {className: "secondary", textContent: "Add me", onclick: async () => {
    const chosen = boxes.filter(([c]) => c.checked).map(([c]) => c.value);
    const extras = normalizeCustomRestrictions(custom.value);
    await api(`/api/groups/${gid}/join`, {method: "POST", headers: {"content-type": "application/json"},
      body: JSON.stringify({token: tok, nickname: nick.value, restrictions: [...chosen, ...extras]})});
    group();
  }});

  root.append($("div", {className: "card"},
    $("div", {className: "stack"},
      $("h2", {textContent: "Add person"}),
      nick,
      $("h3", {textContent: "Dietary restrictions"}),
      $("div", {className: "wrap"}, ...boxes.map(b => b[1])),
      custom,
      add
    )
  ));

  const list = $("div", {className: "card"},
    $("div", {className: "result-header"}, $("h2", {textContent: `Members (${g.members.length})`}))
  );
  g.members.forEach(mm => list.append($("div", {className: "member-line"},
    $("strong", {textContent: mm.nickname}),
    $("span", {className: "mute", textContent: mm.restrictions.map(label).join(", ") || "no restrictions"})
  )));
  root.append(list);

  const status = $("p", {className: "mute"});
  root.append($("div", {className: "card"},
    $("div", {className: "button-row"},
      $("button", {textContent: "Find places", onclick: async () => {
        const loading = loadingCard();
        const existing = document.getElementById("report");
        if (existing) existing.remove();
        root.append(loading);
        status.textContent = "";
        try {
          const rep = await api(`/api/groups/${gid}/report?t=${encodeURIComponent(tok)}`, {method: "POST"});
          loading.remove();
          render(rep);
        }
        catch (e) {
          loading.remove();
          status.textContent = String(e.message);
        }
      }}),
      $("button", {className: "secondary", textContent: "Reset", onclick: () => { location.href = "/"; }})
    ),
    status
  ));
}

function render(rep) {
  document.getElementById("report")?.remove();
  const box = $("div", {id: "report", className: "card"},
    $("div", {className: "result-header"},
      $("span", {className: "kicker", textContent: "Results"}),
      $("h2", {textContent: `Top picks for your group`})
    ),
    mapPreview(rep.venues.map(v => ({name: v.venue.name, score: v.score})))
  );

  rep.venues.forEach(v => {
    const c = $("div", {className: "card result-card"},
      $("div", {className: "row"},
        $("div", {}, $("b", {textContent: v.venue.name}), $("small", {textContent: [v.venue.address, v.venue.phone].filter(Boolean).join(" · ")})),
        $("span", {className: "badge", textContent: `score ${v.score}`})
      ),
      $("p", {className: "mute", textContent: v.summary})
    );

    v.results.forEach(r => {
      const d = $("details", {}, $("summary", {},
        $("span", {textContent: label(r.restriction) + " "}),
        $("span", {className: `badge ${r.tier}`, textContent: TIER[r.tier]})
      ));
      d.append($("p", {className: "mute", textContent: r.note}));
      r.evidence.slice(0, 4).forEach(e => d.append($("blockquote", {}, `"${e.quote}" `, $("a", {href: safeHref(e.url), target: "_blank", rel: "noopener noreferrer", textContent: `[${e.source_kind}]`}))));
      c.append(d);
    });
    box.append(c);
  });

  box.append($("small", {className: "mute", textContent: rep.disclaimer}));
  root.append(box);
}

gid && tok ? group() : home();
