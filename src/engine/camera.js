(() => {
  const BLUR_K = 14.0;
  const DEPTH_MAP = { bg: -320, mid: -120, fg: 0, ui: 40 };

  function mulberry32(seed) {
    let a = seed >>> 0;
    return () => {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function remapTime(p, curve) {
    const t = Math.max(0, Math.min(1, p));
    switch (curve) {
      case "linear":
        return t;
      case "slow_then_fast":
        return t * t * t;
      case "fast_then_slow":
        return 1 - Math.pow(1 - t, 3);
      case "hold_end":
        return t < 0.78 ? (t / 0.78) * 0.96 : 0.96 + ((t - 0.78) / 0.22) * 0.04;
      case "ease_in_out":
      default:
        return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }
  }

  function evaluateMove(move, u, seed) {
    let tx = 0;
    let ty = 0;
    let tz = 0;
    let rx = 0;
    let ry = 0;
    let rz = 0;

    switch (move) {
      case "dolly_in":
        tz = 160 * u;
        break;
      case "dolly_out":
        tz = 160 * (1 - u);
        break;
      case "truck_left":
        tx = 140 * u;
        break;
      case "truck_right":
        tx = -140 * u;
        break;
      case "pan_left":
        ry = 14 * u;
        tx = 95 * u;
        break;
      case "pan_right":
        ry = -14 * u;
        tx = -95 * u;
        break;
      case "tilt_up":
        rx = -10 * u;
        ty = 95 * u;
        break;
      case "tilt_down":
        rx = 10 * u;
        ty = -95 * u;
        break;
      case "orbit":
        ry = -16 + 32 * u;
        tx = Math.sin((u - 0.5) * Math.PI) * 70;
        tz = 45 * Math.sin(u * Math.PI);
        break;
      case "crane_up":
        ty = 130 * u;
        rx = -8 * u;
        tz = -40 * u;
        break;
      case "crane_down":
        ty = -130 * (1 - u);
        rx = 8 * (1 - u);
        break;
      case "push_through":
        tz = 260 * u;
        rz = 3 * u;
        break;
      case "whip_pan": {
        const burst = u < 0.25 ? u / 0.25 : 1;
        tx = -220 * (1 - burst);
        ry = -22 * (1 - burst);
        break;
      }
      case "handheld_drift": {
        const rng = mulberry32(seed || 42);
        const f1 = 1.7 + rng() * 1.5;
        const f2 = 2.3 + rng() * 1.5;
        tx = Math.sin(u * Math.PI * 2 * f1) * 22;
        ty = Math.cos(u * Math.PI * 2 * f2) * 18;
        rz = Math.sin(u * Math.PI * 2 * 1.3) * 1.4;
        tz = 30 * u;
        break;
      }
      default:
        tz = 100 * u;
    }
    return { tx, ty, tz, rx, ry, rz };
  }

  window.computeCameraFrame = function computeCameraFrame(cameraCfg, p, viewportWidth, seed) {
    const lensMm = Number(cameraCfg.lens_mm || 35);
    const aperture = Number(cameraCfg.aperture || 2.8);
    const focusKey = cameraCfg.focus || "fg";
    const focusZ = DEPTH_MAP[focusKey] ?? 0;
    const u = remapTime(p, cameraCfg.speed || "ease_in_out");
    const pose = evaluateMove(cameraCfg.move || "dolly_in", u, seed);
    const perspectivePx = Math.round((viewportWidth * lensMm) / 36);

    const layers = {};
    for (const [layerName, baseZ] of Object.entries(DEPTH_MAP)) {
      const parallax = layerName === "bg" ? 0.35 : layerName === "mid" ? 0.68 : 1.0;
      const distFromFocus = Math.abs(baseZ - focusZ);
      const blurPx = Number(((BLUR_K * (distFromFocus / 160)) / aperture).toFixed(2));
      const tx = (pose.tx * parallax).toFixed(2);
      const ty = (pose.ty * parallax).toFixed(2);
      const tz = (baseZ + pose.tz * parallax).toFixed(2);
      layers[layerName] = {
        transform: `translate3d(${tx}px, ${ty}px, ${tz}px) rotateX(${pose.rx.toFixed(2)}deg) rotateY(${pose.ry.toFixed(2)}deg) rotateZ(${pose.rz.toFixed(2)}deg)`,
        blurPx,
      };
    }

    return { u, perspectivePx, layers };
  };
})();
