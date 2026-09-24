// Keyboard + mouse (pointer lock) and touch controls.
export class Input {
  constructor(canvas) {
    this.canvas = canvas;
    this.keys = new Set();
    this.lookDX = 0;
    this.lookDY = 0;
    this.fire = false;
    this.aim = false;
    this.aimToggle = false;
    this.pressed = new Set(); // edge-triggered actions this frame
    this.move = { x: 0, y: 0 }; // touch joystick
    this.touch = matchMedia("(pointer: coarse)").matches || "ontouchstart" in window;
    this.sensitivity = 1;
    this.locked = false;
    this.enabled = false;

    addEventListener("keydown", (e) => {
      if (!this.enabled) return;
      if (e.code === "Tab") e.preventDefault();
      if (!this.keys.has(e.code)) this.pressed.add(e.code);
      this.keys.add(e.code);
    });
    addEventListener("keyup", (e) => this.keys.delete(e.code));
    addEventListener("blur", () => {
      this.keys.clear();
      this.fire = false;
    });
    canvas.addEventListener("mousedown", (e) => {
      if (!this.enabled) return;
      if (!this.locked && !this.touch) {
        canvas.requestPointerLock();
        return;
      }
      if (e.button === 0) this.fire = true;
      if (e.button === 2) this.aim = true;
    });
    addEventListener("mouseup", (e) => {
      if (e.button === 0) this.fire = false;
      if (e.button === 2) this.aim = false;
    });
    addEventListener("contextmenu", (e) => e.preventDefault());
    addEventListener("mousemove", (e) => {
      if (!this.locked) return;
      this.lookDX += e.movementX * 0.0022 * this.sensitivity;
      this.lookDY += e.movementY * 0.0022 * this.sensitivity;
    });
    addEventListener("wheel", (e) => {
      if (this.locked) this.pressed.add(e.deltaY > 0 ? "WheelDown" : "WheelUp");
    });
    document.addEventListener("pointerlockchange", () => {
      this.locked = document.pointerLockElement === canvas;
      if (!this.locked) {
        this.fire = false;
        this.aim = false;
        this.onUnlock && this.onUnlock();
      }
    });
    if (this.touch) this._setupTouch();
  }

  down(code) {
    return this.keys.has(code);
  }

  consume(code) {
    const had = this.pressed.has(code);
    this.pressed.delete(code);
    return had;
  }

  endFrame() {
    this.lookDX = 0;
    this.lookDY = 0;
    this.pressed.clear();
  }

  axis() {
    let x = 0;
    let y = 0;
    if (this.down("KeyW") || this.down("ArrowUp")) y += 1;
    if (this.down("KeyS") || this.down("ArrowDown")) y -= 1;
    if (this.down("KeyD") || this.down("ArrowRight")) x += 1;
    if (this.down("KeyA") || this.down("ArrowLeft")) x -= 1;
    if (this.touch) {
      x += this.move.x;
      y += this.move.y;
    }
    const l = Math.hypot(x, y);
    if (l > 1) {
      x /= l;
      y /= l;
    }
    return { x, y };
  }

  _setupTouch() {
    const stick = document.getElementById("tStick");
    const knob = document.getElementById("tKnob");
    const lookTouches = new Map();
    let stickId = null;
    let center = { x: 0, y: 0 };
    const R = 55;
    const stickMove = (t) => {
      let dx = t.clientX - center.x;
      let dy = t.clientY - center.y;
      const l = Math.hypot(dx, dy);
      if (l > R) {
        dx = (dx / l) * R;
        dy = (dy / l) * R;
      }
      knob.style.transform = `translate(${dx}px, ${dy}px)`;
      this.move.x = dx / R;
      this.move.y = -dy / R;
      // pushing the stick all the way forward sprints
      this.touchSprint = -dy / R > 0.92;
    };
    stick.addEventListener("touchstart", (e) => {
      e.preventDefault();
      const t = e.changedTouches[0];
      stickId = t.identifier;
      const r = stick.getBoundingClientRect();
      center = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      stickMove(t);
    }, { passive: false });

    const btn = (id, down, up) => {
      const el = document.getElementById(id);
      el.addEventListener("touchstart", (e) => {
        e.preventDefault();
        el.classList.add("on");
        down();
        // buttons double as look areas so you can aim while firing
        for (const t of e.changedTouches) lookTouches.set(t.identifier, { x: t.clientX, y: t.clientY, btn: el, up });
      }, { passive: false });
    };
    btn("tFire", () => (this.fire = true), () => (this.fire = false));
    btn("tAim", () => (this.aimToggle = !this.aimToggle), () => {});
    btn("tReload", () => this.pressed.add("KeyR"), () => {});
    btn("tJump", () => this.pressed.add("Space"), () => {});
    btn("tCrouch", () => this.pressed.add("KeyC"), () => {});
    btn("tSwap", () => this.pressed.add("Swap"), () => {});

    const zone = document.getElementById("tLook");
    zone.addEventListener("touchstart", (e) => {
      e.preventDefault();
      for (const t of e.changedTouches) lookTouches.set(t.identifier, { x: t.clientX, y: t.clientY });
    }, { passive: false });

    addEventListener("touchmove", (e) => {
      for (const t of e.changedTouches) {
        if (t.identifier === stickId) stickMove(t);
        const lt = lookTouches.get(t.identifier);
        if (lt) {
          const k = 0.0055 * this.sensitivity * (this.aimToggle ? 0.6 : 1);
          this.lookDX += (t.clientX - lt.x) * k;
          this.lookDY += (t.clientY - lt.y) * k;
          lt.x = t.clientX;
          lt.y = t.clientY;
        }
      }
    }, { passive: false });
    const end = (e) => {
      for (const t of e.changedTouches) {
        if (t.identifier === stickId) {
          stickId = null;
          this.move.x = this.move.y = 0;
          this.touchSprint = false;
          knob.style.transform = "translate(0,0)";
        }
        const lt = lookTouches.get(t.identifier);
        if (lt) {
          if (lt.btn) {
            lt.btn.classList.remove("on");
            lt.up();
          }
          lookTouches.delete(t.identifier);
        }
      }
    };
    addEventListener("touchend", end);
    addEventListener("touchcancel", end);
  }
}
