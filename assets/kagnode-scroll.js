/*! KagNode scrolling. Source and license are retained in each project. */
(() => {
  if (window.KagNodeScroll) return;
  const root = document.scrollingElement;
  const regions = new Map();
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const forced = matchMedia('(forced-colors: active)');
  let mode = 'custom', frame = 0, scanTimer = 0, serial = 0, pan = null, suppressClickUntil = 0;
  const touches = new Set();
  try { mode = localStorage.getItem('kagnode.scrollMode') === 'native' ? 'native' : 'custom'; } catch {}
  const active = () => mode === 'custom' && !forced.matches;
  const clamp = (n, max) => Math.max(0, Math.min(max, n));
  const axes = ['x', 'y'];
  const dimensions = (element, axis) => {
    const vertical = axis === 'y';
    const length = element === root ? (vertical ? innerHeight : innerWidth) : (vertical ? element.clientHeight : element.clientWidth);
    const total = vertical ? element.scrollHeight : element.scrollWidth;
    return { length, total, max: Math.max(0, total - length), value: vertical ? element.scrollTop : element.scrollLeft };
  };
  const setPosition = (state, axis, value) => {
    const d = dimensions(state.element, axis);
    state.written[axis] = clamp(value, d.max);
    state.element[axis === 'y' ? 'scrollTop' : 'scrollLeft'] = state.written[axis];
  };
  function stop(state) {
    cancelAnimationFrame(state.animation); state.animation = 0;
    for (const axis of axes) state.target[axis] = dimensions(state.element, axis).value;
  }
  function move(state, axis, delta, immediate = false) {
    const d = dimensions(state.element, axis);
    if (!state.animation) state.target[axis] = d.value;
    state.target[axis] = clamp(state.target[axis] + delta, d.max);
    if (immediate || reduce.matches) { stop(state); setPosition(state, axis, d.value + delta); update(); return; }
    if (state.animation) return;
    let previous = performance.now();
    const tick = now => {
      const blend = 1 - Math.exp(-Math.min(40, now - previous) / 45); previous = now;
      let unfinished = false;
      for (const a of axes) {
        const current = dimensions(state.element, a), target = clamp(state.target[a], current.max), gap = target - current.value;
        setPosition(state, a, Math.abs(gap) < .6 ? target : current.value + gap * blend);
        unfinished ||= Math.abs(gap) > .6;
      }
      update(); state.animation = unfinished ? requestAnimationFrame(tick) : 0;
    };
    state.animation = requestAnimationFrame(tick);
  }
  function eligible(element, axis) {
    if (element === root) return dimensions(root, axis).max > 1;
    if (!(element instanceof HTMLElement) || element.closest('.kn-scroll-rail,[data-native-scroll]')) return false;
    const d = dimensions(element, axis);
    if (d.max < 2 || d.length < 16) return false;
    return /auto|scroll/.test(getComputedStyle(element)[axis === 'y' ? 'overflowY' : 'overflowX']);
  }
  function mount(element) {
    let state = regions.get(element); if (state) return state;
    state = {element, bars: {}, animation: 0, target: {}, written: {}};
    for (const axis of axes) state.target[axis] = dimensions(element, axis).value;
    regions.set(element, state); resize.observe(element); element.classList.add(element === root ? 'kn-scroll-root' : 'kn-scroll-region');
    return state;
  }
  function choose(target, axis, delta) {
    let element = target instanceof Element ? target : document.activeElement;
    while (element && element !== document.documentElement) {
      if (eligible(element, axis)) {
        const d = dimensions(element, axis), contain = /contain|none/.test(getComputedStyle(element)[axis === 'y' ? 'overscrollBehaviorY' : 'overscrollBehaviorX']);
        if (delta < 0 && d.value > .5 || delta > 0 && d.value < d.max - .5 || contain) return mount(element);
      }
      element = element.parentElement;
    }
    return eligible(root, axis) ? mount(root) : null;
  }
  function bar(state, axis) {
    if (state.bars[axis]) return state.bars[axis];
    const rail = document.createElement('div'), thumb = document.createElement('span');
    rail.className = 'kn-scroll-rail kn-scroll-' + axis; thumb.className = 'kn-scroll-thumb'; rail.append(thumb);
    rail.tabIndex = 0; rail.setAttribute('role', 'scrollbar'); rail.setAttribute('aria-orientation', axis === 'y' ? 'vertical' : 'horizontal');
    if (!state.element.id) state.element.id = 'kn-scroll-region-' + ++serial;
    rail.setAttribute('aria-controls', state.element.id);
    rail.setAttribute('aria-label', (state.element === root ? 'Page' : state.element.getAttribute('aria-label') || 'Content') + (axis === 'y' ? ' vertical scroll' : ' horizontal scroll'));
    rail.setAttribute('aria-valuemin', '0');
    const host = state.element.closest('dialog[open]') || document.body;
    host.append(rail);
    rail.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault(); event.stopPropagation(); stop(state); rail.focus({preventScroll: true}); rail.setPointerCapture(event.pointerId);
      const start = axis === 'y' ? event.clientY : event.clientX, d = dimensions(state.element, axis), box = rail.getBoundingClientRect(), length = axis === 'y' ? box.height : box.width;
      const thumbLength = Math.min(length, Math.max(28, length * d.length / d.total)), travel = Math.max(1, length - thumbLength);
      if (event.target !== thumb) move(state, axis, ((start - (axis === 'y' ? box.top : box.left)) < d.value / Math.max(1,d.max) * travel ? -1 : 1) * d.length * .85, true);
      const initial = dimensions(state.element, axis).value;
      const drag = e => { e.preventDefault(); const point = axis === 'y' ? e.clientY : e.clientX; setPosition(state, axis, initial + (point - start) * d.max / travel); update(); };
      const end = () => { rail.removeEventListener('pointermove', drag); rail.removeEventListener('pointerup', end); rail.removeEventListener('pointercancel', end); rail.removeEventListener('lostpointercapture', end); };
      rail.addEventListener('pointermove', drag); rail.addEventListener('pointerup', end); rail.addEventListener('pointercancel', end); rail.addEventListener('lostpointercapture', end);
    });
    rail.addEventListener('keydown', event => {
      const d = dimensions(state.element, axis), commands = {ArrowDown: 48, ArrowRight: 48, ArrowUp: -48, ArrowLeft: -48, PageDown: d.length * .85, PageUp: -d.length * .85, Home: -d.max, End: d.max};
      if (!(event.key in commands)) return; event.preventDefault(); event.stopPropagation(); stop(state); move(state, axis, commands[event.key], true);
    });
    return state.bars[axis] = {rail, thumb};
  }
  function update() { if (!frame) frame = requestAnimationFrame(paint); }
  function paint() {
    frame = 0;
    for (const state of regions.values()) {
      if (!state.element.isConnected || !active()) continue;
      const element = state.element, rectangle = element === root ? {top: 0,left: 0,right: innerWidth,bottom: innerHeight,width: innerWidth,height: innerHeight} : element.getBoundingClientRect();
      const visible = rectangle.width > 0 && rectangle.height > 0 && rectangle.bottom > 0 && rectangle.top < innerHeight;
      for (const axis of axes) {
        const d = dimensions(element, axis);
        if (!eligible(element, axis) || !visible) { if (state.bars[axis]) state.bars[axis].rail.hidden = true; continue; }
        const {rail, thumb} = bar(state, axis); rail.hidden = false;
        let clip={top:0,left:0,right:innerWidth,bottom:innerHeight};for(let parent=element.parentElement;parent&&parent!==document.body&&parent!==document.documentElement;parent=parent.parentElement){const style=getComputedStyle(parent),box=parent.getBoundingClientRect();if(/auto|scroll|hidden|clip/.test(style.overflowY)){clip.top=Math.max(clip.top,box.top);clip.bottom=Math.min(clip.bottom,box.bottom);}if(/auto|scroll|hidden|clip/.test(style.overflowX)){clip.left=Math.max(clip.left,box.left);clip.right=Math.min(clip.right,box.right);}}
        const top = Math.max(clip.top+4, rectangle.top + 4), left = Math.max(clip.left+4, rectangle.left + 4), bottom = Math.min(clip.bottom - 4, rectangle.bottom - 4), right = Math.min(clip.right - 4, rectangle.right - 4);
        const host=rail.parentElement,hostStyle=getComputedStyle(host),offset=host!==document.body&&(hostStyle.transform!=='none'||hostStyle.perspective!=='none'||/paint|layout|strict|content/.test(hostStyle.contain))?host.getBoundingClientRect():{top:0,left:0};
        rail.style.top = ((axis === 'y' ? top : bottom - 9)-offset.top-host.clientTop) + 'px'; rail.style.left = ((axis === 'y' ? right - 9 : left)-offset.left-host.clientLeft) + 'px';
        const length = Math.max(0, axis === 'y' ? bottom - top : right - left);
        rail.style[axis === 'y' ? 'height' : 'width'] = length + 'px';
        const size = Math.min(length, Math.max(28, length * d.length / d.total)), position = d.value / Math.max(1,d.max) * (length - size);
        thumb.style[axis === 'y' ? 'height' : 'width'] = size + 'px'; thumb.style.transform = axis === 'y' ? 'translateY(' + position + 'px)' : 'translateX(' + position + 'px)';
        rail.setAttribute('aria-valuemax', String(Math.round(d.max))); rail.setAttribute('aria-valuenow', String(Math.round(d.value)));
        rail.setAttribute('aria-valuetext', Math.round(d.value / Math.max(1,d.max) * 100) + '%');
      }
    }
  }
  function scan() {
    clearTimeout(scanTimer);
    for (const [element,state] of regions) if (!element.isConnected || !active()) {
      stop(state); resize.unobserve(element); for (const b of Object.values(state.bars)) b.rail.remove(); element.classList.remove('kn-scroll-root','kn-scroll-region'); regions.delete(element);
    }
    if (active()) {
      mount(root);
      for (const element of document.querySelectorAll('body *')) if (!element.closest('.kn-scroll-rail') && (eligible(element,'y') || eligible(element,'x'))) mount(element);
    }
    update(); preference();
  }
  function scheduleScan() { clearTimeout(scanTimer); scanTimer = setTimeout(scan, 100); }
  const resize = new ResizeObserver(update);
  document.addEventListener('wheel', event => {
    if (!active() || event.defaultPrevented || event.ctrlKey || event.metaKey || event.target.closest('[data-native-scroll],video,audio,iframe,[role=slider]')) return;
    const dx = event.shiftKey ? event.deltaX || event.deltaY : event.deltaX, dy = event.shiftKey ? 0 : event.deltaY;
    const axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y', raw = axis === 'x' ? dx : dy;
    if (!raw) return; const state = choose(event.target,axis,raw); if (!state) return;
    event.preventDefault(); const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? dimensions(state.element,axis).length : 1; move(state,axis,raw * unit);
  }, {passive: false});
  document.addEventListener('keydown', event => {
    if (!active() || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input,textarea,select,button,[contenteditable],[role=combobox],[role=listbox],[role=menu],[role=slider],.kn-scroll-rail,video,audio')) return;
    const keys = ['ArrowDown','ArrowUp','ArrowLeft','ArrowRight','PageDown','PageUp','Home','End',' ']; if (!keys.includes(event.key)) return;
    const axis = ['ArrowLeft','ArrowRight'].includes(event.key) ? 'x' : 'y', sign = ['ArrowUp','ArrowLeft','PageUp','Home'].includes(event.key) || event.key === ' ' && event.shiftKey ? -1 : 1;
    const state = choose(event.target,axis,sign); if (!state) return; const d = dimensions(state.element,axis);
    const distance = ['Home','End'].includes(event.key) ? d.max : ['PageDown','PageUp',' '].includes(event.key) ? d.length * .85 : 48;
    event.preventDefault(); stop(state); move(state,axis,sign * distance,true);
  });
  document.addEventListener('pointerdown', event => {
    if (!active()) return;
    for (const state of regions.values()) stop(state);
    if (event.pointerType !== 'touch') return; touches.add(event.pointerId);
    if (touches.size !== 1 || event.target.closest('input,select,[contenteditable],video,audio,iframe,[role=slider],.kn-scroll-rail')) { pan = null; return; }
    pan = {id: event.pointerId,target: event.target,x: event.clientX,y: event.clientY,time: performance.now(),vx: 0,vy: 0,state: null,axis: null};
  }, {passive: true});
  document.addEventListener('pointermove', event => {
    if (!pan || event.pointerId !== pan.id || touches.size !== 1 || !active()) return;
    const dx = pan.x - event.clientX, dy = pan.y - event.clientY, time = performance.now();
    if (!pan.axis && Math.max(Math.abs(dx),Math.abs(dy)) < 6) return;
    if (!pan.axis) pan.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
    const delta = pan.axis === 'y' ? dy : dx, state = choose(pan.target,pan.axis,delta); if (!state) return;
    event.preventDefault(); pan.state = state; pan.vx = dx / Math.max(8,time-pan.time) * 16; pan.vy = dy / Math.max(8,time-pan.time) * 16;
    move(state,pan.axis,delta,true); pan.x = event.clientX; pan.y = event.clientY; pan.time = time;
  }, {passive: false});
  function endTouch(event) {
    touches.delete(event.pointerId); if (!pan || event.pointerId !== pan.id) return;
    const current = pan; pan = null; if(current.state)suppressClickUntil=Date.now()+350;
    if (event.type === 'pointercancel' || reduce.matches || !current.state || performance.now() - current.time > 100) return;
    let velocity = Math.max(-65,Math.min(65,current.axis === 'y' ? current.vy : current.vx));
    const step = () => { const state = current.state; if (!active() || !state.element.isConnected) return; const before = dimensions(state.element,current.axis).value; setPosition(state,current.axis,before+velocity); update(); velocity *= .9; state.animation = Math.abs(velocity) > .6 && Math.abs(dimensions(state.element,current.axis).value-before) > .1 ? requestAnimationFrame(step) : 0; };
    current.state.animation = requestAnimationFrame(step);
  }
  document.addEventListener('pointerup',endTouch); document.addEventListener('pointercancel',endTouch);
  document.addEventListener('focusin',()=>{for(const state of regions.values())stop(state);});
  document.addEventListener('click',event=>{if(event.target.closest('a[href]'))for(const state of regions.values())stop(state);},true);
  document.addEventListener('scroll', update, {passive: true,capture: true});
  addEventListener('resize',scheduleScan); window.visualViewport?.addEventListener('resize',scheduleScan);
  document.addEventListener('transitionend',scheduleScan,{passive:true});
  document.addEventListener('load',scheduleScan,{capture:true,passive:true});
  document.addEventListener('click',event=>{if(Date.now()<suppressClickUntil){suppressClickUntil=0;event.preventDefault();event.stopImmediatePropagation();}},true);
  new MutationObserver(records => { if (records.some(r => !r.target.closest?.('.kn-scroll-rail,.kn-scroll-preference') && (r.type === 'childList' || r.attributeName === 'open' || r.attributeName === 'hidden' || r.attributeName === 'class'))) scheduleScan(); }).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['open','hidden','class']});
  let preferenceButton;
  function preference() {
    if (!preferenceButton?.isConnected) {
      preferenceButton = document.createElement('button'); preferenceButton.type = 'button'; preferenceButton.className = 'kn-scroll-preference';

      preferenceButton.onclick = () => setMode(mode === 'custom' ? 'native' : 'custom');
    }
    const host=[...document.querySelectorAll('.kn-product-signature,.portal-footer,.site-footer,.mail-footer,.main-footer,.sidebar-bottom,.auth-footer,.sim-footer')].find(element=>element.getClientRects().length&&!element.closest('[hidden],.hidden,[aria-hidden=true]'))||document.body;if(preferenceButton.parentElement!==host)host.append(preferenceButton);
    preferenceButton.textContent = mode === 'custom' ? 'Use native scrolling' : 'Use KagNode scrolling';
    preferenceButton.setAttribute('aria-pressed',String(mode === 'native'));
  }
  function setMode(value) { mode = value === 'native' ? 'native' : 'custom'; try { localStorage.setItem('kagnode.scrollMode',mode); } catch {} scan(); }
  forced.addEventListener('change',scan); reduce.addEventListener('change',() => { for (const state of regions.values()) stop(state); });
  addEventListener('storage',event=>{if(event.key==='kagnode.scrollMode')setMode(event.newValue);});
  window.KagNodeScroll = {setMode,refresh: scheduleScan,get mode(){return mode;}};
  scan();
})();
