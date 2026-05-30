/* ════════════════════════════════════════════════════════════════════════
   cinematic.js — engines for the cinematic design system.

   Refactored from sample-apple.html's two auto-running <script> blocks into
   SCOPED, DISPOSABLE factories so they can mount/unmount cleanly inside the
   hash-routed SPA (no leaked rAF loops / timers / observers / listeners when
   navigating between routes), and also auto-init on standalone connector pages.

   Public API:
     window.Cinematic.initHome(root)   — mount all home engines under `root`
     window.Cinematic.teardownHome()   — dispose everything from the last initHome
   Standalone pages: add class "cin-static" to <body> → auto-inits on load.
   ════════════════════════════════════════════════════════════════════════ */
(function(){
  'use strict';

  var BF = function(d){ return 'https://cdn.brandfetch.io/' + d + '?c=1idiVFVAawYfs0vBpzR'; };
  var GS = function(f){ return 'https://www.gstatic.com/images/branding/product/1x/' + f; };

  /* ── nav solidify on scroll (idempotent; returns a teardown fn) ───────── */
  function initNavSolidify(){
    var nav = document.querySelector('.cin-nav');
    if (!nav) return function(){};
    if (nav.__cinNavBound) return nav.__cinNavTeardown || function(){};
    var onScroll = function(){ nav.classList.toggle('solid', (window.scrollY || window.pageYOffset || 0) > 40); };
    window.addEventListener('scroll', onScroll, { passive:true });
    onScroll();
    nav.__cinNavBound = true;
    var teardown = function(){ window.removeEventListener('scroll', onScroll); nav.__cinNavBound = false; nav.__cinNavTeardown = null; };
    nav.__cinNavTeardown = teardown;
    return teardown;
  }

  /* ── rise-in reveals + count-up + bars/flow staggered reveal (scoped) ─── */
  function initRise(root){
    root = root || document;
    var observers = [];
    var io = new IntersectionObserver(function(es){
      es.forEach(function(e){ if (e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { threshold:.2 });
    root.querySelectorAll('.rise').forEach(function(el){ io.observe(el); });
    observers.push(io);

    var cio = new IntersectionObserver(function(es){
      es.forEach(function(e){
        if (!e.isIntersecting) return;
        var el = e.target, t = +el.dataset.count, t0 = performance.now();
        (function step(n){
          var p = Math.min((n - t0) / 1400, 1);
          el.textContent = Math.round(t * (1 - Math.pow(1 - p, 3))).toLocaleString();
          if (p < 1) requestAnimationFrame(step);
        })(t0);
        cio.unobserve(el);
      });
    }, { threshold:.6 });
    root.querySelectorAll('[data-count]').forEach(function(el){ cio.observe(el); });
    observers.push(cio);

    var fio = new IntersectionObserver(function(es){
      es.forEach(function(e){ if (e.isIntersecting){ e.target.classList.add('in'); fio.unobserve(e.target); } });
    }, { threshold:.3 });
    root.querySelectorAll('.bars, .flow').forEach(function(el){ fio.observe(el); });
    observers.push(fio);

    return { destroy:function(){ observers.forEach(function(o){ try{ o.disconnect(); }catch(e){} }); } };
  }

  /* ── pinned scroll-telling (scoped + disposable) ──────────────────────── */
  var STAGES = [
    {sub:'01 — Install', cap:'Pick the tools you need.', title:'~/your-project — bash',
     desc:'One <code>pip install</code> — just the connectors you want. The core stays tiny (pydantic, httpx, docstring-parser); no vendor SDK ever lands in your environment.',
     chips:['Python 3.9+','0 hosted deps','pip extras'],
     code:`<span class="c"># one package, just the connectors you want</span>\n<span class="f">$</span> pip install <span class="s">"toolsconnector[slack,github,stripe]"</span>\n<span class="ok">✔</span> <span class="c">installed toolsconnector 0.3.11</span>`},
    {sub:'02 — Call', cap:'Use any API in one line.', title:'python',
     desc:'Every connector speaks the same shape — <code>kit.execute(name, params)</code>. Typed parameters in, structured results out, identical across all 68. Sync for your views, async for your workers.',
     chips:['Typed params','Structured errors','sync + async'],
     code:`<span class="k">from</span> toolsconnector.serve <span class="k">import</span> ToolKit\n\nkit = ToolKit([<span class="s">"slack"</span>,<span class="s">"github"</span>], credentials=creds)\nkit.<span class="f">execute</span>(<span class="s">"slack_send_message"</span>, {<span class="s">"channel"</span>:<span class="s">"#eng"</span>, <span class="s">"text"</span>:<span class="s">"Shipped 🚀"</span>})`},
    {sub:'03 — Empower', cap:'Hand it all to your LLM.', title:'python',
     desc:'One method exports native tool schemas. The model decides which tool to call; you execute its choice with the very same one-liner. No hand-written JSON Schema, no glue code.',
     chips:['OpenAI','Anthropic','Gemini'],
     code:`tools = kit.<span class="f">to_openai_tools</span>()    <span class="c"># native schemas, auto-generated</span>\n<span class="c"># …or Anthropic, or Gemini — same kit</span>\nresp = openai.chat.completions.create(model=<span class="s">"gpt-4o"</span>, tools=tools, messages=msgs)`},
    {sub:'04 — Serve', cap:'Or expose it over MCP.', title:'bash',
     desc:'<code>kit.serve_mcp()</code> — or a single CLI command — turns any set of connectors into an MCP server your assistant can use directly. Zero extra wiring.',
     chips:['Claude Desktop','Cursor','Windsurf'],
     code:`<span class="f">$</span> tc serve mcp slack github --transport stdio\n<span class="ok">✔</span> <span class="c">live in Claude Desktop, Cursor, Windsurf</span>\n<span class="c"># 88 tools, zero glue code</span>`},
  ];
  function createPinned(root){
    root = root || document;
    var pintext = root.querySelector('#pintext'), dots = root.querySelector('#dots'),
        scr = root.querySelector('#scr'), scrT = root.querySelector('#scr-title'),
        screen = root.querySelector('.screen'), pinglow = root.querySelector('#pinglow'),
        pinwrap = root.querySelector('#pinwrap');
    if (!pinwrap || !scr || !pintext || !dots) return { destroy:function(){} };

    dots.innerHTML = STAGES.map(function(_, i){ return '<div class="cin-dot" data-i="' + i + '"></div>'; }).join('');
    var dotEls = [].slice.call(dots.querySelectorAll('.cin-dot'));
    var renderText = function(s){
      return '<div class="num">' + s.sub + '</div><h3>' + s.cap + '</h3><p>' + s.desc + '</p>' +
             '<div class="chips">' + s.chips.map(function(c){ return '<span class="chip">' + c + '</span>'; }).join('') + '</div>';
    };
    var lastStage = -1, raf = 0, swapT = 0, typeTimer = 0, alive = true;
    var prefersReduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    // ── typewriter: reveal the console code char-by-char, preserving the syntax spans ──
    function escHtml(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
    function charsOf(html){
      var tmp = document.createElement('div'); tmp.innerHTML = html; var a = [];
      [].forEach.call(tmp.childNodes, function(n){
        var cls = n.nodeType === 1 ? n.getAttribute('class') : null;
        var t = n.nodeType === 1 ? n.textContent : n.nodeValue;
        Array.from(t).forEach(function(ch){ a.push([ch, cls]); });   // code-point safe (emoji ok)
      });
      return a;
    }
    function htmlUpTo(chars, n){
      var out = '', curCls, buf = '', have = false;
      function flush(){ if (have){ out += (curCls != null) ? '<span class="' + curCls + '">' + escHtml(buf) + '</span>' : escHtml(buf); buf = ''; have = false; } }
      for (var k = 0; k < n; k++){ var c = chars[k]; if (have && c[1] !== curCls) flush(); curCls = c[1]; buf += c[0]; have = true; }
      flush(); return out;
    }
    function typeInto(el, html){
      clearTimeout(typeTimer);
      if (prefersReduced){ el.innerHTML = html; return; }
      var chars = charsOf(html), len = chars.length, stepN = Math.max(1, Math.ceil(len / 50)), i = 0;
      (function go(){
        if (!alive) return;
        i = Math.min(i + stepN, len);
        el.innerHTML = htmlUpTo(chars, i) + '<span class="cin-cursor">▋</span>';
        if (i < len) typeTimer = setTimeout(go, 20);
      })();
    }
    scr.innerHTML = STAGES[0].code; pintext.innerHTML = renderText(STAGES[0]); lastStage = 0;

    function tick(){
      if (!alive) return;
      var r = pinwrap.getBoundingClientRect();
      var total = pinwrap.offsetHeight - window.innerHeight;
      var prog = Math.min(Math.max(-r.top / (total || 1), 0), 1);
      var N = STAGES.length, stage = Math.min(Math.floor(prog * N), N - 1);
      dotEls.forEach(function(el, i){ el.classList.toggle('on', i === stage); });
      if (stage !== lastStage){
        lastStage = stage;
        scr.style.opacity = 0; pintext.style.opacity = 0; scrT.textContent = STAGES[stage].title;
        clearTimeout(swapT);
        swapT = setTimeout(function(){
          if (!alive) return;
          typeInto(scr, STAGES[stage].code);
          pintext.innerHTML = renderText(STAGES[stage]);
          scr.style.opacity = 1; pintext.style.opacity = 1;
        }, 170);
      }
      if (screen) screen.style.transform = 'scale(' + (1 + prog * 0.04) + ')';
      if (pinglow) pinglow.style.transform = 'translateX(' + ((prog - 0.5) * 150) + 'px) scale(' + (1 + prog * 0.3) + ')';
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return { destroy:function(){ alive = false; cancelAnimationFrame(raf); clearTimeout(swapT); clearTimeout(typeTimer); } };
  }

  /* ── connector marquee builder ────────────────────────────────────────── */
  var MARQ = [
    [GS('gmail_2020q4_32dp.png'),BF('slack.com'),BF('github.com'),BF('stripe.com'),BF('notion.so'),BF('linear.app'),BF('atlassian.com'),BF('salesforce.com'),BF('hubspot.com'),BF('openai.com'),BF('anthropic.com'),BF('aws.amazon.com'),BF('shopify.com')],
    [GS('drive_2020q4_32dp.png'),BF('twilio.com'),BF('discord.com'),BF('airtable.com'),BF('mongodb.com'),BF('figma.com'),BF('cloudflare.com'),BF('datadoghq.com'),BF('vercel.com'),BF('zendesk.com'),BF('gitlab.com'),BF('okta.com'),BF('plaid.com')],
    [GS('calendar_2020q4_32dp.png'),BF('supabase.com'),BF('asana.com'),BF('trello.com'),BF('clickup.com'),BF('intercom.com'),BF('sendgrid.com'),BF('mailchimp.com'),BF('pagerduty.com'),BF('sentry.io'),BF('dropbox.com'),BF('segment.com'),BF('calendly.com')]
  ];
  function buildMarquee(root){
    root = root || document;
    var tile = function(u){ return '<div class="gi"><img src="' + u + '" alt="" loading="lazy" onerror="this.parentElement.style.opacity=.25"></div>'; };
    root.querySelectorAll('.marq-row').forEach(function(row, i){ var set = (MARQ[i] || []).map(tile).join(''); row.innerHTML = set + set; });
  }

  /* ── live-execution workflow engine (scoped + disposable) ─────────────── */
  function createWorkflow(root){
    root = root || document;
    var disposed = false;
    var listeners = [];                      // {target,type,fn}
    var timeouts = [];                        // kickstart timers
    var vio = null, controllers = [], mqHandler = null, mqRef = null;
    function on(target, type, fn, opts){ target.addEventListener(type, fn, opts); listeners.push({ target:target, type:type, fn:fn }); }

    try {
      var pipes = [].slice.call(root.querySelectorAll('.wf-pipe'));
      if (!pipes.length) return { destroy:function(){} };

      var mq = (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)')) || null;
      mqRef = mq;
      var reduced = function(){ return !!(mq && mq.matches); };

      controllers = pipes.map(function(pipe){ return makePipe(pipe); }).filter(Boolean);
      if (!controllers.length) return { destroy:function(){} };

      function makePipe(pipe){
        var rail = pipe.querySelector('.wf-rail');
        if (!rail) return null;
        var stages = [].slice.call(rail.querySelectorAll('.wf-stage'));
        var links  = [].slice.call(rail.querySelectorAll('.wf-link'));
        var chip   = pipe.querySelector('.wf-chip');
        var term   = pipe.querySelector('.wf-term');
        var termLines = term ? [].slice.call(term.querySelectorAll('.wf-line')) : [];
        if (stages.length < 2) return null;

        stages.forEach(function(s){ if (s.hasAttribute('data-hub') || s.querySelector('.wf-hub')) s.classList.add('wf-hub-stage'); });
        stages.forEach(function(s){
          var d = s.getAttribute('data-tick');
          if (d){ var tt = s.querySelector('.wf-tick-txt'); if (tt && !tt.textContent) tt.textContent = d; }
        });

        var WAKE = 460, HOP = 620, START_HOLD = 520, END_HOLD = 2100, GAP_HOLD = 1400;
        var state = { running:false, timers:[], visible:false };
        function clearTimers(){ for (var i=0;i<state.timers.length;i++){ clearTimeout(state.timers[i]); } state.timers = []; }

        function chipTextOf(s){ return s.getAttribute('data-payload') || ''; }
        function chipTypeOf(s){ return s.getAttribute('data-payload-type') || 'msg'; }
        function isMono(s){ var t = chipTypeOf(s); return t==='tool'||t==='http'||t==='ok'; }
        function setChip(stage){
          if (!chip) return;
          var t = chip.querySelector('.wf-txt');
          if (t) t.textContent = chipTextOf(stage);
          chip.className = 'wf-chip is-on t-' + chipTypeOf(stage) + (isMono(stage)?' mono':'');
        }
        function anchorChip(stage, opts){
          if (!chip) return;
          var box = stage.querySelector('.wf-box') || stage;
          var rb = box.getBoundingClientRect();
          var rr = rail.getBoundingClientRect();
          var mobile = window.matchMedia && window.matchMedia('(max-width:760px)').matches;
          var cx, cy;
          if (mobile){
            cx = (rb.right - rr.left) + 12;
            cy = (rb.top - rr.top) + rb.height/2;
            cx = Math.max(8, Math.min(cx, Math.max(8, rr.width - 12)));
            chip.style.transform = 'translate(0,-50%)';
          } else {
            cx = (rb.left - rr.left) + rb.width/2;
            cy = (rb.top - rr.top) - 16;
            chip.style.transform = 'translate(-50%,-100%)';
          }
          chip.style.left = cx + 'px';
          chip.style.top  = cy + 'px';
          if (opts && opts.land) chip.classList.add('landed'); else chip.classList.remove('landed');
        }
        function litTermLine(i){ if (!termLines.length) return; termLines.forEach(function(l, j){ l.classList.toggle('lit', j <= i); }); }
        function clearAll(){
          stages.forEach(function(s){ s.classList.remove('is-active','is-warm','show-tick'); });
          links.forEach(function(l){ l.classList.remove('is-firing','is-done'); l.style.removeProperty('--d'); });
          termLines.forEach(function(l){ l.classList.remove('lit'); });
          pipe.classList.remove('is-done');
          if (chip) chip.classList.remove('is-on','landed');
        }
        function wake(stage){
          stage.classList.add('is-active');
          setTimeout(function(){ if (!state.running) return; stage.classList.remove('is-active'); stage.classList.add('is-warm'); }, WAKE);
        }
        function fireLink(link){
          link.style.setProperty('--d', (HOP/1000) + 's');
          link.classList.remove('is-firing');
          void link.offsetWidth;
          link.classList.add('is-firing');
          setTimeout(function(){ if (!state.running) return; link.classList.add('is-done'); }, HOP*0.92);
        }
        function buildSequence(){
          var steps = [];
          steps.push({ at:0, fn:function(){ setChip(stages[0]); anchorChip(stages[0], {land:true}); wake(stages[0]); litTermLine(0); }});
          var clock = START_HOLD;
          for (var i=0; i<links.length; i++){
            (function(i, clk){
              steps.push({ at:clk, fn:function(){ fireLink(links[i]); if (stages[i+1]) anchorChip(stages[i+1], {land:false}); }});
              steps.push({ at:clk + HOP, fn:function(){
                var nx = stages[i+1];
                if (!nx) return;
                wake(nx); setChip(nx); anchorChip(nx, {land:true}); litTermLine(i+1);
                if (nx.getAttribute('data-tick')){ setTimeout(function(){ if (state.running) nx.classList.add('show-tick'); }, 260); }
              }});
            })(i, clock);
            clock += HOP;
          }
          var endAt = clock + END_HOLD;
          steps.push({ at:clock + 80, fn:function(){ pipe.classList.add('is-done'); }});
          steps.push({ at:endAt, fn:function(){ if (chip) chip.classList.remove('is-on'); }});
          steps.push({ at:endAt + GAP_HOLD, fn:function(){ restart(); }});
          steps.sort(function(a,b){ return a.at - b.at; });
          return steps;
        }
        function restart(){
          if (!state.running) return;
          clearTimers(); clearAll();
          var seq = buildSequence();
          for (var i=0;i<seq.length;i++){
            (function(step){ state.timers.push(setTimeout(function(){ if (!state.running) return; try { step.fn(); } catch(e){} }, step.at)); })(seq[i]);
          }
        }
        function start(){
          if (state.running) return;
          state.running = true;
          if (reduced()){ renderStatic(); return; }
          pipe.classList.add('is-running');
          if (term) term.classList.add('is-in');
          restart();
        }
        function stop(){
          if (!state.running) return;
          state.running = false;
          pipe.classList.remove('is-running');
          clearTimers();
        }
        function renderStatic(){
          if (term) term.classList.add('is-in');
          pipe.classList.add('is-done');
          stages.forEach(function(s){ s.classList.add('is-warm'); if (s.getAttribute('data-tick')) s.classList.add('show-tick'); });
          links.forEach(function(l){ l.classList.add('is-done'); });
          termLines.forEach(function(l){ l.classList.add('lit'); });
          if (chip){
            var last = stages[stages.length-1];
            setChip(last);
            var prev = chip.style.transition;
            chip.style.transition = 'none';
            anchorChip(last, {land:true});
            setTimeout(function(){ chip.style.transition = prev || ''; }, 30);
          }
        }
        function lastWarm(){ for (var i=stages.length-1;i>=0;i--){ if (stages[i].classList.contains('is-warm')) return stages[i]; } return null; }
        function reanchor(){
          if (!chip) return;
          var target = pipe.querySelector('.wf-stage.is-active') || lastWarm() || stages[0];
          var prev = chip.style.transition;
          chip.style.transition = 'none';
          anchorChip(target, {land:chip.classList.contains('landed')});
          setTimeout(function(){ chip.style.transition = prev || ''; }, 30);
        }
        function setVisible(v){ state.visible = v; }
        function isVisible(){ return state.visible; }
        function kick(){ if (state.running && !reduced()) restart(); }

        return { el:pipe, start:start, stop:stop, kick:kick, reanchor:reanchor, reduced:reduced,
                 renderStatic:renderStatic, clearAll:clearAll, setVisible:setVisible,
                 isVisible:isVisible, isRunning:function(){ return state.running; } };
      }

      controllers.forEach(function(c, i){ c.el.setAttribute('data-wf-id', i); });

      function inView(el){
        var vh = window.innerHeight || document.documentElement.clientHeight || 0;
        if (vh <= 0) return true;
        var r = el.getBoundingClientRect();
        if (!r.height) return false;
        return r.top < vh * 0.85 && r.bottom > vh * 0.15;
      }
      function sweep(){
        if (disposed) return;
        controllers.forEach(function(c){
          var vis = inView(c.el);
          c.setVisible(vis);
          if (vis && !c.isRunning()) { try { c.start(); } catch(e){} }
          else if (!vis && c.isRunning()) { try { c.stop(); } catch(e){} }
        });
      }

      if ('IntersectionObserver' in window){
        vio = new IntersectionObserver(function(entries){
          entries.forEach(function(en){
            var c = controllers[+en.target.getAttribute('data-wf-id')];
            if (!c) return;
            c.setVisible(en.isIntersecting);
            if (en.isIntersecting) { try { c.start(); } catch(e){} }
            else { try { c.stop(); } catch(e){} }
          });
        }, { threshold: 0.3 });
        controllers.forEach(function(c){ vio.observe(c.el); });
      }
      on(window, 'scroll', sweep, { passive:true });
      [0, 300, 800, 1600].forEach(function(ms){ timeouts.push(setTimeout(sweep, ms)); });

      var onVis = function(){ if (document.visibilityState === 'visible'){ sweep(); controllers.forEach(function(c){ try{ c.kick(); }catch(e){} }); } };
      on(document, 'visibilitychange', onVis);

      var rt;
      var onResize = function(){ clearTimeout(rt); rt = setTimeout(function(){ controllers.forEach(function(c){ try{ c.reanchor(); }catch(e){} }); sweep(); }, 160); };
      on(window, 'resize', onResize, { passive:true });

      if (mq){
        mqHandler = function(){
          controllers.forEach(function(c){
            c.stop(); c.clearAll();
            if (c.reduced()) c.renderStatic();
            else if (c.isVisible()) c.start();
          });
        };
        if (mq.addEventListener) mq.addEventListener('change', mqHandler);
        else if (mq.addListener) mq.addListener(mqHandler);
      }
    } catch(e){ /* never throw into the page */ }

    return { destroy:function(){
      if (disposed) return;
      disposed = true;
      try { controllers.forEach(function(c){ try{ c.stop(); c.clearAll(); }catch(e){} }); } catch(e){}
      try { vio && vio.disconnect(); } catch(e){}
      timeouts.forEach(function(t){ clearTimeout(t); });
      listeners.forEach(function(l){ try{ l.target.removeEventListener(l.type, l.fn); }catch(e){} });
      listeners = [];
      if (mqRef && mqHandler){
        try { if (mqRef.removeEventListener) mqRef.removeEventListener('change', mqHandler); else if (mqRef.removeListener) mqRef.removeListener(mqHandler); } catch(e){}
      }
    }};
  }

  /* ── orchestrator: mount/unmount the whole home experience ────────────── */
  var homeState = null;
  function initHome(root){
    teardownHome();
    root = root || document;
    homeState = {
      nav:    initNavSolidify(),
      rise:   initRise(root),
      pinned: createPinned(root),
      wf:     createWorkflow(root)
    };
    buildMarquee(root);
    return homeState;
  }
  function teardownHome(){
    if (!homeState) return;
    try { if (typeof homeState.nav === 'function') homeState.nav(); } catch(e){}
    try { homeState.rise && homeState.rise.destroy(); } catch(e){}
    try { homeState.pinned && homeState.pinned.destroy(); } catch(e){}
    try { homeState.wf && homeState.wf.destroy(); } catch(e){}
    homeState = null;
  }

  window.Cinematic = {
    initHome: initHome,
    teardownHome: teardownHome,
    initRise: initRise,
    buildMarquee: buildMarquee,
    initNavSolidify: initNavSolidify,
    createWorkflow: createWorkflow,
    createPinned: createPinned
  };

  /* ── standalone-page auto-init (connector pages: <body class="cin-static">) ── */
  function autoInit(){
    if (!document.body || !document.body.classList.contains('cin-static')) return;
    initNavSolidify();
    initRise(document);
    buildMarquee(document);
    if (document.querySelector('.wf-pipe')) createWorkflow(document);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', autoInit, { once:true });
  else autoInit();
})();
