// DOM heads-up display.
const $ = (id) => document.getElementById(id);

export class HUD {
  constructor() {
    this.el = {
      hud: $("hud"), ammo: $("ammoNum"), reserve: $("ammoRes"), mode: $("fireMode"), hp: $("hpFill"), hpNum: $("hpNum"),
      cross: $("cross"), hit: $("hitmark"), compass: $("compassStrip"), hostiles: $("hostiles"), dmg: $("dmgRing"),
      blood: $("bloodOverlay"), note: $("notify"), feed: $("killfeed"), reload: $("reloadHint"), heading: $("heading"),
      wname: $("weaponName"), wlist: $("weaponList"), scope: $("scope"), squad: $("squad"), squadRow: $("squadRow"),
    };
    this._wl = "";
    this._buildCompass();
    this.hitT = 0;
    this.indicators = [];
  }

  _buildCompass() {
    const strip = this.el.compass;
    const names = { 0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW" };
    let html = "";
    for (let d = -180; d <= 540; d += 15) {
      const n = ((d % 360) + 360) % 360;
      const label = names[n];
      html += `<div class="tick${label ? " major" : ""}" style="left:${(d + 180) * 4}px">${label || (n % 45 === 0 ? "" : "|")}</div>`;
    }
    strip.innerHTML = html;
  }

  update(dt, player, weapon, enemies) {
    const e = this.el;
    e.ammo.textContent = weapon.ammo;
    e.ammo.classList.toggle("low", weapon.ammo <= 8);
    e.reserve.textContent = weapon.reserve;
    e.mode.textContent = weapon.mode.toUpperCase();
    e.wname.textContent = weapon.def.name;
    // weapon slots: key number, short name, rounds loaded
    const wl = ["M4", "DMR", "SG", "PST"].map((k) => {
      const on = k === (weapon.pending || weapon.current);
      const st = weapon.state[k];
      return `<span class="${on ? "on" : ""}"><b>${["M4", "DMR", "SG", "PST"].indexOf(k) + 1}</b>${k} ${st.ammo}</span>`;
    }).join("");
    if (wl !== this._wl) {
      this._wl = wl;
      e.wlist.innerHTML = wl;
    }
    e.scope.classList.toggle("on", weapon.scoped);
    const allies = enemies.alliesAlive;
    e.squadRow.style.display = enemies.mode === "squad" ? "" : "none";
    e.squad.textContent = allies;
    const hp = Math.max(0, player.health);
    e.hp.style.width = hp + "%";
    e.hp.classList.toggle("crit", hp < 35);
    e.hpNum.textContent = Math.ceil(hp);
    e.hostiles.textContent = enemies.aliveCount;
    e.reload.style.opacity = weapon.ammo === 0 && !weapon.reloading ? 1 : weapon.ammo <= 5 && !weapon.reloading ? 0.7 : 0;
    e.reload.textContent = weapon.reserve > 0 ? (weapon.ammo === 0 ? "RELOAD [R]" : "LOW AMMO") : "NO AMMO";
    // crosshair gap follows weapon spread; hidden when aiming through the optic
    const gap = 6 + weapon.spread(player) * 520;
    e.cross.style.setProperty("--gap", gap.toFixed(1) + "px");
    e.cross.style.opacity = (1 - weapon.adsT * 1.6).toFixed(2);
    // compass
    let heading = ((-player.yaw * 180) / Math.PI) % 360;
    if (heading < 0) heading += 360;
    e.compass.style.transform = `translateX(${-(heading + 180) * 4}px)`;
    e.heading.textContent = String(Math.round(heading) % 360).padStart(3, "0");
    // hit marker
    this.hitT -= dt;
    e.hit.style.opacity = Math.max(0, this.hitT * 4).toFixed(2);
    // blood overlay from low health
    const hurt = 1 - hp / 100;
    e.blood.style.opacity = (hurt * hurt * 0.9).toFixed(2);
    // damage direction indicators
    for (const ind of this.indicators) {
      ind.t -= dt;
      const dx = ind.from.x - player.pos.x;
      const dz = ind.from.z - player.pos.z;
      const ang = Math.atan2(dx, -dz) + player.yaw; // relative to view
      ind.el.style.transform = `rotate(${ang}rad)`;
      ind.el.style.opacity = Math.max(0, Math.min(1, ind.t)).toFixed(2);
    }
    this.indicators = this.indicators.filter((i) => {
      if (i.t > 0) return true;
      i.el.remove();
      return false;
    });
  }

  hitmarker(kill) {
    this.hitT = kill ? 0.45 : 0.25;
    this.el.hit.classList.toggle("kill", !!kill);
  }

  damageFrom(from, player) {
    const el = document.createElement("div");
    el.className = "dmgArc";
    this.el.dmg.appendChild(el);
    this.indicators.push({ el, from: from.clone(), t: 1.6 });
  }

  notify(text) {
    const n = this.el.note;
    n.textContent = text;
    n.classList.remove("show");
    void n.offsetWidth;
    n.classList.add("show");
  }

  feed(text, head) {
    const d = document.createElement("div");
    d.className = "feedItem" + (head ? " head" : "");
    d.textContent = text;
    this.el.feed.prepend(d);
    setTimeout(() => d.remove(), 3500);
  }
}
