const POLL_MS = 5000;
let worldState = null;
let activePlayerId = "";

const el = {
  syncStatus: document.getElementById("syncStatus"),
  syncInfo: document.getElementById("syncInfo"),
  worldVersion: document.getElementById("worldVersion"),
  worldUpdated: document.getElementById("worldUpdated"),
  cityGrid: document.getElementById("cityGrid"),
  routeList: document.getElementById("routeList"),
  goodsTableBody: document.querySelector("#goodsTable tbody"),
  eventFeed: document.getElementById("eventFeed"),
  tradeForm: document.getElementById("tradeForm"),
  guildForm: document.getElementById("guildForm"),
  createPlayerForm: document.getElementById("createPlayerForm"),
  membershipForm: document.getElementById("membershipForm"),
  tradeCity: document.getElementById("tradeCity"),
  tradeGood: document.getElementById("tradeGood"),
  tradeRoute: document.getElementById("tradeRoute"),
  tradeGuild: document.getElementById("tradeGuild"),
  guildActionGuild: document.getElementById("guildActionGuild"),
  createCity: document.getElementById("createCity"),
  createGuild: document.getElementById("createGuild"),
  membershipGuild: document.getElementById("membershipGuild"),
  playerIdsList: document.getElementById("playerIdsList"),
  tradePlayerId: document.getElementById("tradePlayerId"),
  guildActionPlayerId: document.getElementById("guildActionPlayerId"),
  membershipPlayerId: document.getElementById("membershipPlayerId"),
  createPlayerId: document.getElementById("createPlayerId"),
  activePlayerSelect: document.getElementById("activePlayerSelect"),
  playerSummary: document.getElementById("playerSummary"),
  playerInfo: document.getElementById("playerInfo"),
  playerInventoryBody: document.querySelector("#playerInventoryTable tbody"),
  barDopamine: document.getElementById("barDopamine"),
  barOxytocin: document.getElementById("barOxytocin"),
  barResonance: document.getElementById("barResonance"),
  barImmunity: document.getElementById("barImmunity"),
  txtDopamine: document.getElementById("txtDopamine"),
  txtOxytocin: document.getElementById("txtOxytocin"),
  txtResonance: document.getElementById("txtResonance"),
  txtImmunity: document.getElementById("txtImmunity"),
};

async function api(path, method = "GET", payload = undefined) {
  const response = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.error || `HTTP ${response.status}`);
  }
  return data;
}

function toFixedNumber(value, digits = 2) {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n.toFixed(digits) : "0.00";
}

function setSyncStatus(message, isError = false) {
  el.syncStatus.textContent = message;
  el.syncStatus.style.color = isError ? "#ff6d7a" : "#4fe4c3";
}

function setBar(barElement, value) {
  const safe = Math.max(0, Math.min(1, Number(value) || 0));
  barElement.style.width = `${safe * 100}%`;
}

function setSelectValue(selectElement, value) {
  if (!selectElement) {
    return;
  }
  const normalized = String(value ?? "");
  const optionExists = [...selectElement.options].some((opt) => opt.value === normalized);
  if (optionExists) {
    selectElement.value = normalized;
  }
}

function patchSelectOptions(selectElement, values, includeEmpty = false, emptyLabel = "(keine)") {
  if (!selectElement) {
    return;
  }
  const previous = selectElement.value;
  selectElement.innerHTML = "";
  if (includeEmpty) {
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = emptyLabel;
    selectElement.appendChild(emptyOption);
  }
  for (const item of values) {
    const value = typeof item === "string" ? item : String(item.value ?? "");
    const label = typeof item === "string" ? item : String(item.label ?? value);
    if (!value) {
      continue;
    }
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    selectElement.appendChild(option);
  }
  setSelectValue(selectElement, previous);
  if (!selectElement.value && selectElement.options.length > 0) {
    selectElement.selectedIndex = 0;
  }
}

function patchDataList(dataListElement, values) {
  if (!dataListElement) {
    return;
  }
  dataListElement.innerHTML = "";
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    dataListElement.appendChild(option);
  }
}

function renderNeuro(neuro) {
  const dopamine = Number(neuro?.dopamine ?? 0);
  const oxytocin = Number(neuro?.oxytocin ?? 0);
  const resonance = Number(neuro?.decoq_resonance ?? 0);
  const immunity = Number(neuro?.immunity_level ?? 0);

  setBar(el.barDopamine, dopamine);
  setBar(el.barOxytocin, oxytocin);
  setBar(el.barResonance, resonance);
  setBar(el.barImmunity, immunity);

  el.txtDopamine.textContent = toFixedNumber(dopamine, 3);
  el.txtOxytocin.textContent = toFixedNumber(oxytocin, 3);
  el.txtResonance.textContent = toFixedNumber(resonance, 3);
  el.txtImmunity.textContent = toFixedNumber(immunity, 3);
}

function renderCities(cities) {
  el.cityGrid.innerHTML = "";
  for (const [cityName, city] of Object.entries(cities || {})) {
    const card = document.createElement("article");
    card.className = "city-card";
    card.innerHTML = `
      <h3>${cityName}</h3>
      <div class="city-meta">
        <span>Wohlstand: ${toFixedNumber(city.wealth, 3)}</span>
        <span>Stabilitaet: ${toFixedNumber(city.stability, 3)}</span>
        <span>Gilden-Einfluss: ${toFixedNumber(city.guild_influence, 3)}</span>
        <span>Steuersatz: ${toFixedNumber(city.tax_rate, 3)}</span>
      </div>
    `;
    el.cityGrid.appendChild(card);
  }
}

function renderGoods(globalGoods) {
  el.goodsTableBody.innerHTML = "";
  for (const [goodName, good] of Object.entries(globalGoods || {})) {
    const tr = document.createElement("tr");
    const momentum = Number(good.momentum ?? 0);
    const momentumClass = momentum >= 0 ? "momentum-pos" : "momentum-neg";
    tr.innerHTML = `
      <td>${goodName}</td>
      <td>${toFixedNumber(good.price, 2)}</td>
      <td class="${momentumClass}">${toFixedNumber(momentum, 4)}</td>
      <td>${toFixedNumber(good.supply, 1)}</td>
      <td>${toFixedNumber(good.demand, 1)}</td>
    `;
    el.goodsTableBody.appendChild(tr);
  }
}

function renderRoutes(routes) {
  el.routeList.innerHTML = "";
  for (const route of routes || []) {
    const item = document.createElement("div");
    item.className = "route-item";
    item.innerHTML = `
      <strong>${route.from_city}</strong> → <strong>${route.to_city}</strong><br>
      Distanz ${toFixedNumber(route.distance, 1)} | Risiko ${toFixedNumber(route.risk, 2)}
      | Kapazitaet ${toFixedNumber(route.capacity, 0)} | Verkehr ${toFixedNumber(route.traffic, 0)}
    `;
    el.routeList.appendChild(item);
  }
}

function renderEvents(events) {
  el.eventFeed.innerHTML = "";
  const list = [...(events || [])].slice(-24).reverse();
  for (const event of list) {
    const node = document.createElement("div");
    node.className = "event-item";
    node.innerHTML = `
      <div><strong>${event.kind || "event"}</strong></div>
      <div class="event-meta">#${event.id ?? "-"} | ${event.actor_id ?? "-"} | ${event.at ?? "-"}</div>
      <div class="event-meta">${JSON.stringify(event.payload || {})}</div>
    `;
    el.eventFeed.appendChild(node);
  }
}

function syncPlayerInputs() {
  if (!activePlayerId) {
    return;
  }
  for (const input of [el.tradePlayerId, el.guildActionPlayerId, el.membershipPlayerId]) {
    if (input) {
      input.value = activePlayerId;
    }
  }
}

function renderPlayerPanel(world) {
  const players = world?.players || {};
  const playerIds = Object.keys(players);
  patchDataList(el.playerIdsList, playerIds);

  if (playerIds.length === 0) {
    activePlayerId = "";
    patchSelectOptions(el.activePlayerSelect, []);
    el.playerInfo.textContent = "Keine Spieler";
    el.playerSummary.innerHTML = "<span>Noch kein Spieler angelegt. Nutze rechts \"Spieler erstellen\".</span>";
    el.playerInventoryBody.innerHTML = "";
    return;
  }

  if (!activePlayerId || !players[activePlayerId]) {
    activePlayerId = playerIds[0];
  }

  const playerOptions = playerIds.map((id) => {
    const p = players[id] || {};
    const display = p.display_name || id;
    return { value: id, label: `${id} (${display})` };
  });
  patchSelectOptions(el.activePlayerSelect, playerOptions);
  setSelectValue(el.activePlayerSelect, activePlayerId);
  activePlayerId = el.activePlayerSelect.value || activePlayerId;
  syncPlayerInputs();

  const player = players[activePlayerId] || {};
  const city = String(player.home_city || "-");
  const guild = String(player.guild_id || "-");
  const inventory = player.inventory || {};
  const cityPrices = world?.market_view?.city_prices?.[city] || {};
  const cash = Number(player.cash || 0);
  const debt = Number(player.debt || 0);

  el.playerInfo.textContent = `${playerIds.length} Spieler`;
  let totalValue = 0;
  for (const [goodName, rawQty] of Object.entries(inventory)) {
    const qty = Number(rawQty || 0);
    const unitPrice = Number(cityPrices[goodName] || 0);
    totalValue += qty * unitPrice;
  }
  const netWorth = cash + totalValue - debt;

  el.playerSummary.innerHTML = `
    <span>Name: <strong>${player.display_name || activePlayerId}</strong></span>
    <span>ID: <strong>${activePlayerId}</strong></span>
    <span>Stadt: <strong>${city}</strong></span>
    <span>Gilde: <strong>${guild}</strong></span>
    <span>Bargeld: <strong>${toFixedNumber(cash, 2)}</strong></span>
    <span>Schulden: <strong>${toFixedNumber(debt, 2)}</strong></span>
    <span>Warenwert: <strong>${toFixedNumber(totalValue, 2)}</strong></span>
    <span>Gesamtwert: <strong>${toFixedNumber(netWorth, 2)}</strong></span>
    <span>Ruf: <strong>${toFixedNumber(player.reputation, 3)}</strong></span>
    <span>Letzte Aktion: <strong>${player.last_action_at || "-"}</strong></span>
  `;

  el.playerInventoryBody.innerHTML = "";
  for (const [goodName, rawQty] of Object.entries(inventory)) {
    const qty = Number(rawQty || 0);
    const unitPrice = Number(cityPrices[goodName] || 0);
    const value = qty * unitPrice;
    totalValue += value;
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${goodName}</td>
      <td>${toFixedNumber(qty, 1)}</td>
      <td>${toFixedNumber(unitPrice, 2)}</td>
      <td>${toFixedNumber(value, 2)}</td>
    `;
    el.playerInventoryBody.appendChild(row);
  }
  const totalRow = document.createElement("tr");
  totalRow.innerHTML = `
    <td><strong>Gesamtwarenwert</strong></td>
    <td>-</td>
    <td>-</td>
    <td><strong>${toFixedNumber(totalValue, 2)}</strong></td>
  `;
  el.playerInventoryBody.appendChild(totalRow);
}

function hydrateActionSelectors(world) {
  const cities = Object.keys(world?.economy?.cities || {});
  const goods = Object.keys(world?.economy?.goods || {});
  const guildSet = new Set(Object.keys(world?.guilds || {}));
  guildSet.add("free_merchants");
  const guilds = [...guildSet];
  const routes = (world?.economy?.trade_routes || []).map((route) => route.id).filter(Boolean);

  patchSelectOptions(el.tradeCity, cities);
  patchSelectOptions(el.createCity, cities);
  patchSelectOptions(el.tradeGood, goods);
  patchSelectOptions(el.tradeRoute, routes, true, "(keine Route)");
  patchSelectOptions(el.tradeGuild, guilds);
  patchSelectOptions(el.guildActionGuild, guilds);
  patchSelectOptions(el.createGuild, guilds);
  patchSelectOptions(el.membershipGuild, guilds);
}

function renderWorld(world) {
  if (!world) {
    return;
  }
  const version = world?.meta?.version ?? "-";
  const updated = world?.meta?.updated_at ?? "-";
  const syncError = world?.sync?.last_error;
  const marketView = world?.market_view || {};
  const playerCount = Object.keys(world?.players || {}).length;
  const phase = String(world?.system?.market_phase || "-");
  const aiCycleCount = Number(world?.sync?.ai_cycle_count || 0);
  const aiTradePerCycle = Number(world?.sync?.ai_last_cycle_trade_count || 0);

  el.worldVersion.textContent = `Version ${version}`;
  el.worldUpdated.textContent = `Stand ${updated}`;
  el.syncInfo.textContent = `Polling ${POLL_MS / 1000}s | Spieler ${playerCount} | Phase ${phase} | KI-Zyklen ${aiCycleCount} | KI-Trades/Zyklus ${aiTradePerCycle}`;

  renderNeuro(world.neuro_state || {});
  renderCities(world?.economy?.cities || {});
  renderGoods(marketView.global_goods || {});
  renderRoutes(marketView.routes || []);
  renderEvents(world.events || []);
  hydrateActionSelectors(world);
  renderPlayerPanel(world);

  if (syncError) {
    setSyncStatus(`Sync-Warnung: ${syncError}`, true);
  } else {
    setSyncStatus("Synchronisiert");
  }
}

async function refreshWorld() {
  try {
    const world = await api("/api/world");
    worldState = world;
    renderWorld(world);
  } catch (error) {
    setSyncStatus(`Fehler: ${error.message}`, true);
  }
}

function formToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function submitCreatePlayer(event) {
  event.preventDefault();
  const payload = formToObject(el.createPlayerForm);
  payload.action_type = "create";
  payload.starting_cash = Number(payload.starting_cash || 6000);
  payload.starting_debt = Number(payload.starting_debt || 1800);
  try {
    const world = await api("/api/action/player", "POST", payload);
    activePlayerId = payload.player_id;
    worldState = world;
    renderWorld(world);
    setSyncStatus(`Spieler ${payload.player_id} angelegt`);
  } catch (error) {
    setSyncStatus(`Spieler erstellen fehlgeschlagen: ${error.message}`, true);
  }
}

async function submitMembership(event) {
  event.preventDefault();
  const form = formToObject(el.membershipForm);
  let payload;
  if (String(form.action_type) === "leave_guild") {
    payload = {
      action_type: "leave_guild",
      player_id: form.player_id,
      fallback_guild: form.guild_id,
    };
  } else {
    payload = {
      action_type: "join_guild",
      player_id: form.player_id,
      guild_id: form.guild_id,
    };
  }
  try {
    const world = await api("/api/action/player", "POST", payload);
    activePlayerId = form.player_id;
    worldState = world;
    renderWorld(world);
    setSyncStatus("Gildenmitgliedschaft aktualisiert");
  } catch (error) {
    setSyncStatus(`Mitgliedschaft fehlgeschlagen: ${error.message}`, true);
  }
}

async function submitTrade(event) {
  event.preventDefault();
  const payload = formToObject(el.tradeForm);
  payload.quantity = Number(payload.quantity || 0);
  if (!payload.route_id) {
    delete payload.route_id;
  }
  try {
    const world = await api("/api/action/trade", "POST", payload);
    activePlayerId = payload.player_id;
    worldState = world;
    renderWorld(world);
    setSyncStatus("Handel global synchronisiert");
  } catch (error) {
    setSyncStatus(`Handel fehlgeschlagen: ${error.message}`, true);
  }
}

async function submitGuildAction(event) {
  event.preventDefault();
  const payload = formToObject(el.guildForm);
  payload.intensity = Number(payload.intensity || 0.2);
  try {
    const world = await api("/api/action/guild", "POST", payload);
    activePlayerId = payload.player_id;
    worldState = world;
    renderWorld(world);
    setSyncStatus("Gildenaktion global synchronisiert");
  } catch (error) {
    setSyncStatus(`Gildenaktion fehlgeschlagen: ${error.message}`, true);
  }
}

function onActivePlayerChanged() {
  activePlayerId = el.activePlayerSelect.value || "";
  syncPlayerInputs();
  if (worldState) {
    renderPlayerPanel(worldState);
  }
}

function boot() {
  el.createPlayerForm.addEventListener("submit", submitCreatePlayer);
  el.membershipForm.addEventListener("submit", submitMembership);
  el.tradeForm.addEventListener("submit", submitTrade);
  el.guildForm.addEventListener("submit", submitGuildAction);
  el.activePlayerSelect.addEventListener("change", onActivePlayerChanged);
  refreshWorld();
  setInterval(refreshWorld, POLL_MS);
}

boot();
