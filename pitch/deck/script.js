(() => {
  const SLIDE_W = 1280;
  const SLIDE_H = 720;

  const wrappers = Array.from(document.querySelectorAll('.slide-wrapper'));
  let current = 0;
  let busy = false;

  /* ─────────────────────────────────────
     Scale slides to fit viewport
  ───────────────────────────────────── */
  let _ox = 0, _oy = 0, _sc = 1;

  function scaleSlides() {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    _sc = Math.min(vw / SLIDE_W, vh / SLIDE_H);
    _ox = (vw - SLIDE_W * _sc) / 2;
    _oy = (vh - SLIDE_H * _sc) / 2;

    wrappers.forEach(w => {
      const s = w.querySelector('.slide');
      s.style.width  = SLIDE_W + 'px';
      s.style.height = SLIDE_H + 'px';
      s.style.transform = `translate(${_ox}px, ${_oy}px) scale(${_sc})`;
      s.style.transformOrigin = 'top left';
    });
  }

  /* ─────────────────────────────────────
     Animate content blocks on enter
     Each slide has data-animate children
     or we select known block selectors
  ───────────────────────────────────── */
  function animateContent(wrapper) {
    const slide = wrapper.querySelector('.slide');

    const selectors = [
      '.sh', '.s1-top', '.s1-body',
      '.s2-body', '.s3-body', '.s4-body',
      '.s5-body', '.s6-body', '.s7-body',
      '.s-road-body', '.s9-body', '.s-end',
    ];

    const blocks = slide.querySelectorAll(selectors.join(','));

    // сначала сбрасываем всё в видимое состояние (на случай если transition не сработает)
    blocks.forEach(el => {
      el.style.opacity    = '1';
      el.style.transform  = 'translateY(0)';
      el.style.transition = 'none';
    });

    // потом анимируем
    blocks.forEach((el, i) => {
      el.style.opacity   = '0';
      el.style.transform = 'translateY(12px)';

      const delay = 60 + i * 80;
      setTimeout(() => {
        el.style.transition = 'opacity 0.5s cubic-bezier(.22,1,.36,1), transform 0.5s cubic-bezier(.22,1,.36,1)';
        el.style.opacity    = '1';
        el.style.transform  = 'translateY(0)';
      }, delay);
    });

    // fallback — через 1.5с гарантируем что всё видимо
    setTimeout(() => {
      blocks.forEach(el => {
        el.style.opacity   = '1';
        el.style.transform = 'translateY(0)';
      });
    }, 1500);
  }

  /* ─────────────────────────────────────
     Slide transition
     out: fade + slight push in exit dir
     in:  arrives from opposite side
  ───────────────────────────────────── */
  function goTo(idx) {
    if (busy || idx < 0 || idx >= wrappers.length || idx === current) return;
    busy = true;

    const dir = idx > current ? 1 : -1;
    const outW = wrappers[current];
    const inW  = wrappers[idx];
    const outS = outW.querySelector('.slide');
    const inS  = inW.querySelector('.slide');

    const T = 'translate(' + _ox + 'px,' + _oy + 'px) scale(' + _sc + ')';
    const push = 28; // px inside scaled space

    // --- OUT slide ---
    outS.style.transition = 'none';
    outS.style.transform  = T;
    outS.style.opacity    = '1';

    requestAnimationFrame(() => {
      outS.style.transition = `opacity 380ms ease-in, transform 380ms cubic-bezier(.4,0,1,1)`;
      outS.style.opacity    = '0';
      outS.style.transform  = `translate(${_ox}px,${_oy}px) scale(${_sc}) translateX(${dir * -push}px)`;
    });

    // --- IN slide: prepare off-screen ---
    inW.style.display    = 'block';
    inW.style.zIndex     = '10';
    inS.style.transition = 'none';
    inS.style.opacity    = '0';
    inS.style.transform  = `translate(${_ox}px,${_oy}px) scale(${_sc}) translateX(${dir * push}px)`;

    // start IN after a brief paint frame
    requestAnimationFrame(() => requestAnimationFrame(() => {
      inS.style.transition = `opacity 460ms cubic-bezier(.22,1,.36,1), transform 460ms cubic-bezier(.22,1,.36,1)`;
      inS.style.opacity    = '1';
      inS.style.transform  = `translate(${_ox}px,${_oy}px) scale(${_sc}) translateX(0px)`;
    }));

    // cleanup
    setTimeout(() => {
      outW.classList.remove('active');
      outW.style.display = '';
      outW.style.zIndex  = '';
      outS.style.transition = '';
      outS.style.opacity    = '';
      outS.style.transform  = T;

      inW.classList.add('active');
      inW.style.zIndex = '';
      inS.style.transition = '';
      inS.style.opacity    = '';
      inS.style.transform  = T;

      current = idx;
      busy = false;

      animateContent(inW);
    }, 500);
  }

  /* ─────────────────────────────────────
     Animated background — canvas orbs
  ───────────────────────────────────── */
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:0;pointer-events:none;';
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d');
  let CW, CH;

  function resizeCv() {
    CW = canvas.width  = window.innerWidth;
    CH = canvas.height = window.innerHeight;
  }
  resizeCv();
  window.addEventListener('resize', resizeCv);

  // three soft orbs with independent drift
  const ORBS = [
    { bx:0.78, by:0.08, r:0.58, rgb:[26,140,78],  sx:0.000155, sy:0.000110, px:0.00, py:1.40 },
    { bx:0.10, by:0.90, r:0.50, rgb:[13,155,110], sx:0.000125, sy:0.000160, px:2.10, py:0.60 },
    { bx:0.52, by:0.52, r:0.34, rgb:[15,168,102], sx:0.000200, sy:0.000180, px:4.20, py:3.10 },
  ];

  function drawBg(ts) {
    ctx.clearRect(0, 0, CW, CH);
    ctx.fillStyle = '#F4F8F5';
    ctx.fillRect(0, 0, CW, CH);

    ORBS.forEach(o => {
      const cx = (o.bx + Math.sin(ts * o.sx + o.px) * 0.085) * CW;
      const cy = (o.by + Math.cos(ts * o.sy + o.py) * 0.065) * CH;
      const r  = o.r * Math.min(CW, CH);
      const [rr,gg,bb] = o.rgb;

      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      g.addColorStop(0,    `rgba(${rr},${gg},${bb},0.092)`);
      g.addColorStop(0.42, `rgba(${rr},${gg},${bb},0.038)`);
      g.addColorStop(1,    `rgba(${rr},${gg},${bb},0)`);

      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    });

    requestAnimationFrame(drawBg);
  }
  requestAnimationFrame(drawBg);

  /* ─────────────────────────────────────
     Input
  ───────────────────────────────────── */
  document.addEventListener('keydown', e => {
    if (['ArrowRight', 'ArrowDown', ' ', 'PageDown'].includes(e.key)) { e.preventDefault(); goTo(current + 1); }
    else if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(e.key))      { e.preventDefault(); goTo(current - 1); }
  });

  document.addEventListener('click', e => {
    if (e.clientX < window.innerWidth / 2) goTo(current - 1);
    else goTo(current + 1);
  });

  document.addEventListener('mousemove', e => {
    document.body.style.cursor = e.clientX < window.innerWidth / 2 ? 'w-resize' : 'e-resize';
  });

  /* ─────────────────────────────────────
     Init
  ───────────────────────────────────── */
  window.addEventListener('resize', scaleSlides);
  wrappers[0].classList.add('active');
  scaleSlides();

  // animate first slide with slight delay
  setTimeout(() => animateContent(wrappers[0]), 200);
})();
