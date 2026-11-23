"""Compact Lovelace dashboard card for the X728 UPS."""

class X728UpsCard extends HTMLElement {
  setConfig(config) { this.config = config || {}; }
  set hass(hass) { this._hass = hass; this.render(); }
  getCardSize() { return 3; }
  _state(key) { return this._hass?.states?.[`sensor.x728_${key}`]?.state ?? "—"; }
  _entity(domain, key) { return this._hass?.states?.[`${domain}.x728_${key}`]; }
  _call(domain, service, key) {
    const entity = this._entity(domain, key);
    if (entity) this._hass.callService(domain, service, { entity_id: entity.entity_id });
  }
  render() {
    if (!this._hass) return;
    const s = this._hass.states;
    const find = (id) => s[id]?.state ?? "—";
    const battery = Number(find("sensor.x728_capacity"));
    const voltage = find("sensor.x728_voltage");
    const status = find("sensor.x728_ups_status");
    const runtime = find("sensor.x728_runtime_estimate");
    const batteryPct = Number.isFinite(battery) ? Math.max(0, Math.min(100, battery)) : 0;
    const charging = s["switch.x728_charging"];
    const shutdown = s["switch.x728_auto_shutdown"];
    const btn = (entity, label) => entity ? `<button data-entity="${entity.entity_id}" data-domain="switch" data-service="${entity.state === "on" ? "turn_off" : "turn_on"}">${label}: ${entity.state === "on" ? "On" : "Off"}</button>` : "";
    this.innerHTML = `<ha-card><style>
      ha-card{padding:16px;font-family:var(--primary-font-family);color:var(--primary-text-color)}
      .head{display:flex;justify-content:space-between;align-items:center;font-size:1.15em;font-weight:600}
      .status{color:var(--secondary-text-color);font-size:.9em;text-transform:capitalize}
      .bar{height:12px;background:var(--disabled-color);border-radius:8px;margin:14px 0;overflow:hidden}
      .fill{height:100%;width:${batteryPct}%;background:${batteryPct < 15 ? "var(--error-color)" : "var(--success-color, #4caf50)"};transition:width .4s}
      .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;text-align:center}.value{font-size:1.25em;font-weight:600}.label{font-size:.8em;color:var(--secondary-text-color)}
      .actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}button{border:0;border-radius:8px;padding:8px 12px;background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer}
    </style><div class="head"><span>${this.config.name || "X728 UPS"}</span><span class="status">${status.replaceAll("_", " ")}</span></div>
      <div class="bar"><div class="fill"></div></div><div class="grid">
      <div><div class="value">${Number.isFinite(battery) ? `${battery.toFixed(0)}%` : "—"}</div><div class="label">Battery</div></div>
      <div><div class="value">${voltage === "—" ? voltage : `${voltage} V`}</div><div class="label">Voltage</div></div>
      <div><div class="value">${runtime === "unknown" ? "—" : `${runtime} min`}</div><div class="label">Runtime estimate</div></div></div>
      <div class="actions">${btn(charging, "Charging")}${btn(shutdown, "Auto shutdown")}</div></ha-card>`;
    this.querySelectorAll("button[data-entity]").forEach((button) => button.addEventListener("click", () => this._hass.callService(button.dataset.domain, button.dataset.service, { entity_id: button.dataset.entity })));
  }
}
if (!customElements.get("x728-ups-card")) customElements.define("x728-ups-card", X728UpsCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "x728-ups-card", name: "Geekworm X728 UPS", description: "Battery status and controls for the X728" });
