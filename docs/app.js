/*
 * docs/index.html 的交互：读文件 / 示例 → 转码判定 + 时频图 + 长时间频谱，英日双语。
 * 算法都在 analysis.js（globalThis.SPF），这里只管界面。
 */
(function () {
"use strict";

const S = globalThis.SPF, I18N = globalThis.SPF_I18N;
const $ = id => document.getElementById(id);
const store = {
  get(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } },
  set(k,v){ try{ localStorage.setItem(k,v); }catch(e){ /* 隐私模式等 */ } },
};

const MAX_SECONDS = 120;
const LOSSLESS = /\.(flac|wav|aiff?|alac|wv|ape)$/i;

// 与 spectral_forensics/render.py 的 PALETTES 相同
const PALETTES = {
  ember: ["#05070d","#1b1035","#5c1d5c","#b83355","#f2813c","#ffe6a7"],
  abyss: ["#03050a","#0a2540","#136f8c","#3fbfa0","#c9f2c7"],
  mono:  ["#000000","#2a2a2a","#666666","#b0b0b0","#ffffff"],
  bloom: ["#0a0510","#2d1b4e","#6b3fa0","#c264a8","#ffb3c6","#fff0f3"],
};

const SAMPLES = {
  genuine: { url:"samples/demo-genuine.flac", name:"demo-genuine.flac", lossless:true },
  mp3:     { url:"samples/demo-128k.mp3", name:"demo-128k.mp3 → .flac", lossless:true },
};

/* ---------------------------- 语言 ---------------------------- */

function pickLang(){
  const q = new URLSearchParams(location.search).get("lang");
  if(q==="en" || q==="ja") return q;
  const s = store.get("spf.lang");
  if(s==="en" || s==="ja") return s;
  return (navigator.language||"").toLowerCase().startsWith("ja") ? "ja" : "en";
}
let lang = pickLang();

function t(key, ...args){
  const v = key in I18N[lang] ? I18N[lang][key] : I18N.en[key];
  return typeof v==="function" ? v(...args) : v;
}

function applyLang(){
  document.documentElement.lang = lang;
  document.title = t("meta.title");
  for(const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for(const el of document.querySelectorAll("[data-i18n-html]")) el.innerHTML = t(el.dataset.i18nHtml);
  $("langBtn").textContent = t("lang.switch");
  $("langBtn").lang = lang==="en" ? "ja" : "en";
  $("drop").setAttribute("aria-label", t("drop.title"));
  if(state.file){ renderVerdict(); drawSpectrogram(); drawOverlay(); drawChart(); }
  updateTransport();
  updateResLabel();
}

/* ---------------------------- 状态 ---------------------------- */

const state = {
  file: null,      // {name, kind, buffer, sr, n, mono, verdict…}
  spec: {
    mode: "stft", nFft: 2048, logFreq: true, range: 80,
    palette: PALETTES[store.get("spf.palette")] ? store.get("spf.palette") : "ember",
    showCutoff: true,
  },
  rasters: new Map(),   // 已算好的时频图，按设置缓存
  raster: null,         // 当前显示的
  image: null,          // raster 上色后的离屏 canvas
  job: 0,
  hover: null,
};

let ctx = null;
function audioCtx(){
  if(!ctx) ctx = new (window.AudioContext||window.webkitAudioContext)();
  return ctx;
}

function say(msg, isErr){
  $("status").textContent = msg || "";
  $("status").className = isErr ? "err" : "";
}
const nextFrame = () => new Promise(r => setTimeout(r, 16));

/* ---------------------------- 读入 ---------------------------- */

async function openFile(file){
  say(t("status.decoding", file.name));
  await nextFrame();
  let buf;
  try{
    buf = await audioCtx().decodeAudioData(await file.arrayBuffer());
  }catch(err){
    say(t("status.decodeFail"), true);
    return;
  }
  analyse(buf, file.name, "file", LOSSLESS.test(file.name));
}

async function openSample(key){
  if(key==="synth"){ analyse(synthBuffer(), "sweep-tones-clicks.wav", "synth", true); return; }
  const s = SAMPLES[key];
  say(t("status.decoding", s.name));
  try{
    const res = await fetch(s.url);
    if(!res.ok) throw new Error(res.status);
    const buf = await audioCtx().decodeAudioData(await res.arrayBuffer());
    analyse(buf, s.name, key, s.lossless);
  }catch(err){
    say(t("status.sampleFail"), true);
  }
}

/** 合成测试信号：对数扫频、带谐波的定常音、颤音、每 0.75 s 一个脉冲。 */
function synthBuffer(){
  const sr = 44100, T = 8, n = T*sr, y = new Float32Array(n);
  const f0 = 60, f1 = 16000, K = Math.log(f1/f0);
  const gate = (t, a, b) => t<a || t>b ? 0 : Math.min(1, (t-a)/0.03, (b-t)/0.03);
  let vib = 0;
  for(let i=0;i<n;i++){
    const tt = i/sr;
    let v = 0.2*Math.sin(2*Math.PI*f0*T/K*(Math.exp(K*tt/T)-1)) * gate(tt, 0, T);
    const g1 = gate(tt, 1, 7);
    if(g1) for(let h=1;h<=6;h++) v += 0.09/h*Math.sin(2*Math.PI*220*h*tt)*g1;
    vib += 2*Math.PI*(3000 + 250*Math.sin(2*Math.PI*5.5*tt))/sr;
    v += 0.08*Math.sin(vib)*gate(tt, 2, 6);
    y[i] = v;
  }
  for(let c=0.375; c<T; c+=0.75){ const i = Math.round(c*sr); y[i] += 0.8; y[i+1] -= 0.3; }
  let peak = 0;
  for(const v of y) peak = Math.max(peak, Math.abs(v));
  for(let i=0;i<n;i++) y[i] *= 0.9/peak;
  const buf = audioCtx().createBuffer(2, n, sr);
  buf.copyToChannel(y, 0); buf.copyToChannel(y, 1);
  return buf;
}

async function analyse(buf, name, kind, isLossless){
  const sr = buf.sampleRate;
  const n = Math.min(buf.length, Math.floor(MAX_SECONDS*sr));
  if(n < 16384){ say(t("status.tooShort"), true); return; }
  stopPlayback(true);

  const ch0 = buf.getChannelData(0).subarray(0,n);
  const ch1 = buf.numberOfChannels>1 ? buf.getChannelData(1).subarray(0,n) : null;
  let mono = ch0;
  if(ch1){
    mono = new Float32Array(n);
    for(let i=0;i<n;i++) mono[i] = (ch0[i]+ch1[i])/2;
  }

  const f = { name, kind, buffer:buf, sr, n, mono, isLossless };
  if(kind!=="synth"){
    say(t("status.analysing"));
    await nextFrame();
    const { freqs, db } = S.longTermSpectrum(mono, sr);
    f.freqs = freqs;
    f.cut = S.findCutoff(freqs, db);
    f.stereoHz = ch1 ? S.intensityStereoCutoff(ch0, ch1, sr) : null;
    f.v = S.verdict(f.cut, f.stereoHz, isLossless);
  }
  state.file = f;
  state.rasters.clear();
  state.raster = null;
  state.image = null;
  state.hover = null;

  $("verdictCard").hidden = kind==="synth";
  $("chartCard").hidden = kind==="synth";
  $("synthCard").hidden = kind!=="synth";
  $("result").hidden = false;
  say("");
  renderVerdict();
  drawChart();
  updateTransport();
  updateResLabel();
  computeSpectrogram();
}

/* ---------------------------- 判定卡片 ---------------------------- */

function renderVerdict(){
  const f = state.file;
  if(!f || !f.v) return;
  const { v, cut, stereoHz, isLossless, sr, n } = f;
  $("badge").textContent = t("tier."+v.tier);
  $("badge").className = "badge "+v.tier;
  $("fname").textContent = f.name;
  $("headline").textContent = t("headline."+v.tier);

  const khz = cut.cutoffHz===null ? null : cut.cutoffHz/1000;
  $("s-cut").textContent = khz===null ? "—" : (khz>=S.FULL_BAND_KHZ ? t("stat.fullBand") : khz.toFixed(1)+" kHz");
  $("s-steep").textContent = cut.steepness===null ? "—" : "−"+cut.steepness.toFixed(0)+" dB";
  $("s-stereo").textContent = stereoHz===null ? t("stat.none") : (stereoHz/1000).toFixed(1)+" kHz";
  $("s-dur").textContent = (n/sr).toFixed(0)+" s";

  const notes = v.notes.map(x => t("note."+x.code, x));
  if(khz!==null && khz<S.FULL_BAND_KHZ && (v.tier==="suspect"||v.tier==="likely"||v.tier==="lossy")){
    const src = S.guessSource(khz);
    notes.push(t("note.consistent", src==="an unknown lossy encoder" ? t("note.unknownEncoder") : src));
  }
  if(!isLossless) notes.push(t("note.lossyName"));
  if(f.kind==="genuine") notes.push(t("note.genuineSample"));
  if(f.kind==="mp3") notes.push(t("note.mp3Sample"));
  notes.push(t("note.decoded", (sr/1000).toFixed(1), (n/sr).toFixed(0)));

  const ul = $("notes");
  ul.replaceChildren(...notes.map(s => { const li = document.createElement("li"); li.textContent = s; return li; }));
}

/* ---------------------------- 时频图 ---------------------------- */

const PAD = { l:50, r:12, t:10, b:28 };   // CSS 像素

function specGeometry(){
  const dpr = Math.min(window.devicePixelRatio||1, 2);
  const cssW = $("specWrap").clientWidth || 900;
  const cssH = Math.round(Math.max(250, Math.min(460, cssW*0.46)));
  const plot = { x:PAD.l, y:PAD.t, w:cssW-PAD.l-PAD.r, h:cssH-PAD.t-PAD.b };
  return { dpr, cssW, cssH, plot };
}

function specKey(){ const s = state.spec; return `${s.mode}|${s.nFft}|${s.logFreq}`; }

async function computeSpectrogram(){
  const f = state.file;
  if(!f) return;
  const key = specKey();
  if(state.rasters.has(key)){
    state.raster = state.rasters.get(key);
    paintRaster(); drawSpectrogram(); drawOverlay();
    return;
  }
  const job = ++state.job;
  const { dpr, plot } = specGeometry();
  const width = Math.min(2000, Math.round(plot.w*dpr)), height = Math.min(900, Math.round(plot.h*dpr));
  const { mode, nFft, logFreq } = state.spec;
  const hop = S.displayHop(f.mono.length, nFft, width);
  const gen = S.spectrogramRaster(f.mono, f.sr, {
    nFft, hop, width, height, logFreq, mode,
    fmin: logFreq ? 20 : 0, fmax: f.sr/2, topDb: 120,
  });
  const busy = $("specBusy");
  busy.hidden = false;
  busy.textContent = t("spec.computing", 0);
  if(!state.raster) drawSpectrogram();

  let r, last = performance.now();
  while(!(r = gen.next()).done){
    if(performance.now()-last > 40){
      busy.textContent = t("spec.computing", Math.round(100*r.value));
      await new Promise(res => setTimeout(res, 0));
      if(job!==state.job) return;
      last = performance.now();
    }
  }
  if(job!==state.job) return;
  busy.hidden = true;
  state.rasters.set(key, r.value);
  state.raster = r.value;
  paintRaster(); drawSpectrogram(); drawOverlay();
}

function lut(name){
  const stops = PALETTES[name].map(h => [1,3,5].map(i => parseInt(h.slice(i,i+2),16)));
  const out = new Uint8ClampedArray(256*3);
  for(let i=0;i<256;i++){
    const x = i/255*(stops.length-1), j = Math.min(stops.length-2, Math.floor(x)), a = x-j;
    for(let c=0;c<3;c++) out[i*3+c] = stops[j][c]*(1-a) + stops[j+1][c]*a;
  }
  return out;
}

/** 把 dB 栅格按当前配色和动态范围上色，存进离屏 canvas。 */
function paintRaster(){
  const R = state.raster;
  if(!R) return;
  const L = lut(state.spec.palette), range = state.spec.range;
  const c = state.image || (state.image = document.createElement("canvas"));
  c.width = R.width; c.height = R.height;
  const g = c.getContext("2d"), im = g.createImageData(R.width, R.height), d = im.data;
  for(let r=0;r<R.height;r++){
    const src = r*R.width, dst = (R.height-1-r)*R.width;   // 行 0 是最低频，画在最下面
    for(let x=0;x<R.width;x++){
      let v = (R.db[src+x]+range)/range;
      v = v<0 ? 0 : v>1 ? 1 : v;
      const li = (v*255|0)*3, o = (dst+x)*4;
      d[o] = L[li]; d[o+1] = L[li+1]; d[o+2] = L[li+2]; d[o+3] = 255;
    }
  }
  g.putImageData(im, 0, 0);
}

function yOfFreq(axis, plot, f){
  const frac = axis.logFreq
    ? (Math.log10(f)-Math.log10(Math.max(axis.fmin,1)))/(Math.log10(axis.fmax)-Math.log10(Math.max(axis.fmin,1)))
    : (f-axis.fmin)/(axis.fmax-axis.fmin);
  return plot.y + plot.h*(1-frac);
}
function freqOfY(axis, plot, y){
  const frac = 1-(y-plot.y)/plot.h;
  if(axis.logFreq){
    const a = Math.log10(Math.max(axis.fmin,1)), b = Math.log10(axis.fmax);
    return Math.pow(10, a+(b-a)*frac);
  }
  return axis.fmin + (axis.fmax-axis.fmin)*frac;
}
const fmtHz = f => f>=1000 ? (f/1000).toFixed(f>=10000 ? 1 : 2)+" kHz" : f.toFixed(0)+" Hz";
const fmtTick = f => f>=1000 ? (f/1000)+"k" : String(f);
function fmtClock(s){
  const m = Math.floor(s/60), r = s-60*m;
  return `${m}:${r<10?"0":""}${r.toFixed(1)}`;
}

function sizeCanvas(c, g){
  const w = Math.round(g.cssW*g.dpr), h = Math.round(g.cssH*g.dpr);
  if(c.width!==w || c.height!==h){ c.width = w; c.height = h; }
  c.style.height = g.cssH+"px";
}

function drawSpectrogram(){
  const f = state.file, R = state.raster;
  const c = $("spec"), G = specGeometry();
  sizeCanvas(c, G); sizeCanvas($("specOverlay"), G);
  const g = c.getContext("2d"), { plot } = G;
  g.setTransform(G.dpr,0,0,G.dpr,0,0);
  g.fillStyle = "#03050a"; g.fillRect(0,0,G.cssW,G.cssH);
  if(!f) return;
  const axis = R ? R.axis : { logFreq: state.spec.logFreq, fmin: state.spec.logFreq?20:0, fmax: f.sr/2 };
  const dur = f.n/f.sr;

  if(state.image){
    g.imageSmoothingEnabled = true;
    g.drawImage(state.image, plot.x, plot.y, plot.w, plot.h);
  }

  // 坐标轴
  g.font = "11px ui-monospace,SFMono-Regular,Menlo,monospace";
  g.fillStyle = "#8b93a7"; g.strokeStyle = "rgba(240,242,248,.10)"; g.lineWidth = 1;
  g.textAlign = "right"; g.textBaseline = "middle";
  const ticks = axis.logFreq
    ? [20,50,100,200,500,1000,2000,5000,10000,20000]
    : Array.from({length:30}, (_,i) => i*(plot.h<260 ? 4000 : 2000));
  for(const hz of ticks){
    if(hz<axis.fmin || hz>axis.fmax) continue;
    const y = Math.round(yOfFreq(axis, plot, hz))+0.5;
    g.beginPath(); g.moveTo(plot.x-4, y); g.lineTo(plot.x, y); g.stroke();
    g.fillText(fmtTick(hz), plot.x-7, y);
  }
  const steps = [0.1,0.2,0.5,1,2,5,10,15,30,60];
  const step = steps.find(s => dur/s <= plot.w/70) || 60;
  const unitW = g.measureText(t("spec.time")).width;
  g.textAlign = "center"; g.textBaseline = "top";
  for(let s=0; s<=dur+1e-9; s+=step){
    const x = Math.round(plot.x + plot.w*s/dur)+0.5;
    g.beginPath(); g.moveTo(x, plot.y+plot.h); g.lineTo(x, plot.y+plot.h+4); g.stroke();
    if(x < plot.x+plot.w-unitW-18) g.fillText(step<1 ? s.toFixed(1) : String(Math.round(s)), x, plot.y+plot.h+7);
  }
  g.textAlign = "right"; g.fillStyle = "#5a6175";
  g.fillText(t("spec.time"), plot.x+plot.w, plot.y+plot.h+7);

  // 截止频率
  const cut = f.cut && f.cut.cutoffHz;
  if(state.spec.showCutoff && cut && cut/1000 < S.FULL_BAND_KHZ && cut<=axis.fmax){
    const y = Math.round(yOfFreq(axis, plot, cut))+0.5;
    g.strokeStyle = "#ff5d7e"; g.lineWidth = 1.5; g.setLineDash([7,5]);
    g.beginPath(); g.moveTo(plot.x, y); g.lineTo(plot.x+plot.w, y); g.stroke();
    g.setLineDash([]);
    const label = t("spec.cutoffLabel", (cut/1000).toFixed(1));
    g.font = "600 12px ui-sans-serif,-apple-system,sans-serif";
    const w = g.measureText(label).width;
    g.fillStyle = "rgba(5,7,13,.78)"; g.fillRect(plot.x+plot.w-w-14, y-22, w+10, 18);
    g.fillStyle = "#ff8fa6"; g.textAlign = "left"; g.textBaseline = "middle";
    g.fillText(label, plot.x+plot.w-w-9, y-13);
  }
}

/** 覆盖层：播放游标 + 鼠标读数。单独一层，播放时每帧只重画这一层。 */
function drawOverlay(){
  const c = $("specOverlay"), f = state.file, R = state.raster;
  const G = specGeometry(), { plot } = G;
  sizeCanvas(c, G);
  const g = c.getContext("2d");
  g.setTransform(G.dpr,0,0,G.dpr,0,0);
  g.clearRect(0,0,G.cssW,G.cssH);
  if(!f) return;
  const dur = f.n/f.sr, pos = position();

  if(player.playing || pos>0){
    const x = plot.x + plot.w*Math.min(pos,dur)/dur;
    g.fillStyle = "rgba(255,230,167,.9)";
    g.fillRect(Math.round(x)-1, plot.y, 2, plot.h);
  }

  const h = state.hover;
  if(h && R && h.x>=plot.x && h.x<=plot.x+plot.w && h.y>=plot.y && h.y<=plot.y+plot.h){
    g.strokeStyle = "rgba(240,242,248,.35)"; g.lineWidth = 1;
    g.beginPath();
    g.moveTo(h.x+0.5, plot.y); g.lineTo(h.x+0.5, plot.y+plot.h);
    g.moveTo(plot.x, h.y+0.5); g.lineTo(plot.x+plot.w, h.y+0.5);
    g.stroke();
    const tSec = (h.x-plot.x)/plot.w*dur;
    const hz = freqOfY(R.axis, plot, h.y);
    const col = Math.min(R.width-1, Math.floor((h.x-plot.x)/plot.w*R.width));
    const row = Math.min(R.height-1, Math.max(0, Math.floor((plot.y+plot.h-h.y)/plot.h*R.height)));
    const db = R.db[row*R.width+col];
    const text = `${tSec.toFixed(2)} s · ${fmtHz(hz)} · ${db<=-120 ? "≤ −120" : db.toFixed(0).replace("-","−")} dB`;
    g.font = "12px ui-monospace,SFMono-Regular,Menlo,monospace";
    const w = g.measureText(text).width + 12;
    let bx = h.x+12, by = h.y-28;
    if(bx+w > plot.x+plot.w) bx = h.x-12-w;
    if(by < plot.y) by = h.y+10;
    g.fillStyle = "rgba(5,7,13,.85)"; g.fillRect(bx, by, w, 20);
    g.fillStyle = "#f0f2f8"; g.textAlign = "left"; g.textBaseline = "middle";
    g.fillText(text, bx+6, by+10);
  }
}

function updateResLabel(){
  const sr = state.file ? state.file.sr : 44100, n = state.spec.nFft;
  const ms = n/sr*1000;
  $("resLabel").textContent = t("spec.res", ms<20 ? ms.toFixed(1) : ms.toFixed(0), (sr/n).toFixed(1));
}

/* ---------------------------- 播放 ---------------------------- */

const player = { src:null, startedAt:0, offset:0, playing:false };

function position(){
  return player.playing ? audioCtx().currentTime-player.startedAt : player.offset;
}

function play(from){
  const f = state.file;
  if(!f) return;
  stopPlayback(false);
  const ac = audioCtx();
  if(ac.state==="suspended") ac.resume();
  const dur = f.n/f.sr;
  from = Math.max(0, Math.min(from, dur-0.05));
  const src = ac.createBufferSource();
  src.buffer = f.buffer;
  src.connect(ac.destination);
  src.start(0, from, dur-from);
  src.onended = () => {
    if(player.src!==src) return;
    player.src = null; player.playing = false; player.offset = 0;
    updateTransport(); drawOverlay();
  };
  Object.assign(player, { src, startedAt: ac.currentTime-from, playing:true });
  updateTransport();
  requestAnimationFrame(tick);
}

function stopPlayback(reset){
  if(player.playing) player.offset = position();
  if(player.src){ const s = player.src; player.src = null; try{ s.stop(); }catch(e){ /* 已停止 */ } }
  player.playing = false;
  if(reset) player.offset = 0;
  updateTransport();
}

function tick(){
  if(!player.playing) return;
  drawOverlay();
  updateClock();
  requestAnimationFrame(tick);
}

function updateClock(){
  const f = state.file;
  $("clock").textContent = f ? `${fmtClock(Math.min(position(), f.n/f.sr))} / ${fmtClock(f.n/f.sr)}` : "";
}
function updateTransport(){
  $("playBtn").textContent = player.playing ? "❚❚ "+t("spec.pause") : "▶ "+t("spec.play");
  updateClock();
}
function togglePlay(){
  if(!state.file) return;
  if(player.playing){ stopPlayback(false); drawOverlay(); }
  else play(player.offset);
}

/* ---------------------------- 长时间频谱 ---------------------------- */

function drawChart(){
  const f = state.file;
  if(!f || !f.cut) return;
  const c = $("chart");
  const dpr = Math.min(window.devicePixelRatio||1, 2);
  const W = c.clientWidth || 900, H = Math.round(Math.max(220, Math.min(360, W*0.4)));
  c.width = Math.round(W*dpr); c.height = Math.round(H*dpr); c.style.height = H+"px";
  const g = c.getContext("2d");
  g.setTransform(dpr,0,0,dpr,0,0);
  const L = 58, R = 14, T = 14, B = 44;
  const fMin = 40, fMax = f.sr/2, dbMin = -100, dbMax = 6;
  const X = hz => L+(Math.log10(Math.max(hz,fMin))-Math.log10(fMin))/(Math.log10(fMax)-Math.log10(fMin))*(W-L-R);
  const Y = d => T+(dbMax-d)/(dbMax-dbMin)*(H-T-B);

  g.clearRect(0,0,W,H);
  g.strokeStyle = "#161b2b"; g.lineWidth = 1; g.font = "11px ui-monospace,SFMono-Regular,Menlo,monospace";
  g.fillStyle = "#5a6175"; g.textAlign = "center"; g.textBaseline = "top";
  for(const hz of [50,100,200,500,1000,2000,5000,10000,20000]){
    if(hz<fMin || hz>fMax) continue;
    g.beginPath(); g.moveTo(X(hz)+0.5,T); g.lineTo(X(hz)+0.5,H-B); g.stroke();
    g.fillText(fmtTick(hz), X(hz), H-B+6);
  }
  g.textAlign = "right"; g.textBaseline = "middle";
  for(let d=0; d>=dbMin; d-=20){
    g.beginPath(); g.moveTo(L,Y(d)+0.5); g.lineTo(W-R,Y(d)+0.5); g.stroke();
    g.fillText(String(d).replace("-","−")+" dB", L-8, Y(d));
  }

  const cut = f.cut.cutoffHz;
  if(cut!==null && cut/1000 < S.FULL_BAND_KHZ){
    g.strokeStyle = "#b83355"; g.lineWidth = 1.5; g.setLineDash([6,5]);
    g.beginPath(); g.moveTo(X(cut),T); g.lineTo(X(cut),H-B); g.stroke();
    g.setLineDash([]);
    g.fillStyle = "#ff8fa6"; g.textAlign = "right"; g.textBaseline = "top";
    g.fillText((cut/1000).toFixed(1)+" kHz", X(cut)-8, T+6);
  }

  g.strokeStyle = "#f2813c"; g.lineWidth = 1.8; g.lineJoin = "round"; g.beginPath();
  let started = false;
  const { freqs } = f, rel = f.cut.rel;
  for(let i=1;i<freqs.length;i++){
    if(freqs[i]<fMin) continue;
    const x = X(freqs[i]), y = Y(Math.max(rel[i], dbMin));
    if(started) g.lineTo(x,y); else { g.moveTo(x,y); started = true; }
  }
  g.stroke();

  g.fillStyle = "#5a6175"; g.textAlign = "left"; g.textBaseline = "bottom";
  g.font = "12px ui-sans-serif,-apple-system,sans-serif";
  g.fillText(t("chart.caption"), L, H-4);
}

/* ---------------------------- 控件 ---------------------------- */

function syncControls(){
  const s = state.spec;
  const press = (id, v) => { for(const b of $(id).children) b.setAttribute("aria-pressed", String(b.dataset.v===String(v))); };
  press("modeSeg", s.mode);
  press("nfftSeg", s.nFft);
  press("axisSeg", s.logFreq ? "log" : "linear");
  press("paletteSeg", s.palette);
  $("range").value = s.range;
  $("rangeVal").textContent = s.range+" dB";
  $("showCutoff").checked = s.showCutoff;
}

function bindSeg(id, apply){
  $(id).addEventListener("click", e => {
    const b = e.target.closest("button[data-v]");
    if(!b) return;
    apply(b.dataset.v);
    syncControls();
  });
}

function setup(){
  // 调色板按钮：直接用渐变当样本
  for(const [name, stops] of Object.entries(PALETTES)){
    const b = document.createElement("button");
    b.type = "button"; b.dataset.v = name; b.title = name; b.setAttribute("aria-label", name);
    b.style.background = `linear-gradient(90deg, ${stops.join(",")})`;
    $("paletteSeg").appendChild(b);
  }

  bindSeg("modeSeg", v => { state.spec.mode = v; computeSpectrogram(); });
  bindSeg("nfftSeg", v => { state.spec.nFft = +v; updateResLabel(); computeSpectrogram(); });
  bindSeg("axisSeg", v => { state.spec.logFreq = v==="log"; computeSpectrogram(); });
  bindSeg("paletteSeg", v => {
    state.spec.palette = v; store.set("spf.palette", v);
    paintRaster(); drawSpectrogram();
  });
  $("range").addEventListener("input", () => {
    state.spec.range = +$("range").value;
    $("rangeVal").textContent = state.spec.range+" dB";
    paintRaster(); drawSpectrogram();
  });
  $("showCutoff").addEventListener("change", () => { state.spec.showCutoff = $("showCutoff").checked; drawSpectrogram(); });

  $("playBtn").addEventListener("click", togglePlay);
  $("pngBtn").addEventListener("click", () => {
    const f = state.file;
    if(!f) return;
    // 把游标之外的画面合成一张图
    $("spec").toBlob(blob => {
      if(!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${f.name.replace(/[^\w.-]+/g,"_").replace(/\.\w+$/,"")}-${state.spec.mode}-${state.spec.nFft}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
  });

  const ov = $("specOverlay");
  const local = e => { const r = ov.getBoundingClientRect(); return { x:e.clientX-r.left, y:e.clientY-r.top }; };
  ov.addEventListener("pointermove", e => { state.hover = local(e); drawOverlay(); });
  ov.addEventListener("pointerleave", () => { state.hover = null; drawOverlay(); });
  ov.addEventListener("click", e => {
    const f = state.file;
    if(!f) return;
    const { plot } = specGeometry(), p = local(e);
    const tSec = Math.max(0, Math.min(1, (p.x-plot.x)/plot.w))*f.n/f.sr;
    play(tSec);
  });

  document.addEventListener("keydown", e => {
    if(e.code!=="Space" || !state.file) return;
    if(e.target.closest("button, input, textarea, select, [role=button]")) return;
    e.preventDefault();
    togglePlay();
  });

  // 文件：拖进页面任何地方都可以
  const drop = $("drop"), picker = $("file");
  drop.addEventListener("click", () => picker.click());
  drop.addEventListener("keydown", e => { if(e.key==="Enter" || e.key===" "){ e.preventDefault(); picker.click(); } });
  picker.addEventListener("change", () => { if(picker.files[0]) openFile(picker.files[0]); picker.value = ""; });
  let depth = 0;
  window.addEventListener("dragenter", e => { e.preventDefault(); depth++; drop.classList.add("hot"); });
  window.addEventListener("dragover", e => e.preventDefault());
  window.addEventListener("dragleave", () => { if(--depth<=0){ depth = 0; drop.classList.remove("hot"); } });
  window.addEventListener("drop", e => {
    e.preventDefault(); depth = 0; drop.classList.remove("hot");
    const file = e.dataTransfer && e.dataTransfer.files[0];
    if(file) openFile(file);
  });

  for(const b of document.querySelectorAll("[data-sample]")) b.addEventListener("click", () => openSample(b.dataset.sample));

  $("langBtn").addEventListener("click", () => {
    lang = lang==="en" ? "ja" : "en";
    store.set("spf.lang", lang);
    applyLang();
  });

  let resizeTimer = 0, lastW = 0;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const w = $("specWrap").clientWidth;
      if(w===lastW) return;
      lastW = w;
      drawSpectrogram(); drawOverlay(); drawChart();
    }, 120);
  });

  syncControls();
  applyLang();

  // ?sample=genuine|mp3|synth 直接打开示例，README 可以链接到具体的一个
  const sample = new URLSearchParams(location.search).get("sample");
  if(sample==="synth" || Object.hasOwn(SAMPLES, sample||"")) openSample(sample);
}

setup();
})();
