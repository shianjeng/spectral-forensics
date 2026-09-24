/*
 * spectral-forensics in the browser: the algorithms behind docs/index.html.
 *
 *  - transcode check: longTermSpectrum / findCutoff / intensityStereoCutoff / verdict,
 *    one-to-one with spectral_forensics/audit.py (tests/test_web_parity.py compares them)
 *  - spectrogram: STFT exactly like librosa.stft(center=True, pad_mode="constant", periodic Hann)
 *  - reassigned spectrogram: the same corrections as librosa.reassigned_spectrogram
 *    (Flandrin, Auger & Chassande-Mottin 2002, eqs. 5.20 / 5.23), as used by spf reassign
 *
 * Plain script, no modules: it defines globalThis.SPF, so the page works from file:// too,
 * and Node can load it for the tests.
 */
(function (root) {
"use strict";

/* ---------- 核心算法：与 spectral_forensics/audit.py 一一对应 ---------- */

function fftRadix2(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { const a=re[i];re[i]=re[j];re[j]=a; const b=im[i];im[i]=im[j];im[j]=b; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2*Math.PI)/len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len/2; k++) {
        const ur = re[i+k], ui = im[i+k];
        const vr = re[i+k+len/2]*cr - im[i+k+len/2]*ci;
        const vi = re[i+k+len/2]*ci + im[i+k+len/2]*cr;
        re[i+k] = ur+vr; im[i+k] = ui+vi;
        re[i+k+len/2] = ur-vr; im[i+k+len/2] = ui-vi;
        const ncr = cr*wr - ci*wi; ci = cr*wi + ci*wr; cr = ncr;
      }
    }
  }
}

function hann(n){ const w=new Float64Array(n);
  for(let i=0;i<n;i++) w[i]=0.5-0.5*Math.cos((2*Math.PI*i)/n); return w; }

function longTermSpectrum(y, sr, nFft=8192, percentile=95){
  const hop=nFft/2, w=hann(nFft), nBins=nFft/2+1;
  const nFrames=Math.max(1, Math.floor((y.length-nFft)/hop)+1);
  const cols=Array.from({length:nBins},()=>new Float64Array(nFrames));
  const re=new Float64Array(nFft), im=new Float64Array(nFft);
  for(let f=0;f<nFrames;f++){
    const off=f*hop;
    for(let i=0;i<nFft;i++){ re[i]=(y[off+i]||0)*w[i]; im[i]=0; }
    fftRadix2(re,im);
    for(let k=0;k<nBins;k++) cols[k][f]=re[k]*re[k]+im[k]*im[k];
  }
  const db=new Float64Array(nBins);
  for(let k=0;k<nBins;k++){
    const s=Array.from(cols[k]).sort((a,b)=>a-b);
    const pos=(percentile/100)*(s.length-1), lo=Math.floor(pos), hi=Math.ceil(pos);
    db[k]=10*Math.log10(s[lo]+(s[hi]-s[lo])*(pos-lo)+1e-20);
  }
  const freqs=new Float64Array(nBins);
  for(let k=0;k<nBins;k++) freqs[k]=(k*sr)/nFft;
  return {freqs, db};
}

function smooth(x,width=9){
  const out=new Float64Array(x.length), half=(width-1)/2;
  for(let i=0;i<x.length;i++){
    let sum=0;
    for(let j=-half;j<=half;j++){ const k=i+j; sum += (k>=0&&k<x.length)?x[k]:0; }
    out[i]=sum/width;
  }
  return out;
}

function findCutoff(freqs, dbRaw, dropDb=50){
  const db=smooth(dbRaw);
  let ref=-Infinity;
  for(let i=0;i<freqs.length;i++) if(freqs[i]>=200&&freqs[i]<=4000) ref=Math.max(ref,db[i]);
  if(!isFinite(ref)) return {cutoffHz:null, steepness:null, rel:null};
  const rel=Array.from(db,v=>v-ref);
  let idx=-1;
  for(let i=rel.length-1;i>=0;i--) if(rel[i]>-dropDb){ idx=i; break; }
  if(idx<0) return {cutoffHz:null, steepness:null, rel};
  const fc=freqs[idx];
  if(idx>=freqs.length-1) return {cutoffHz:fc, steepness:null, rel};
  let j=freqs.length-1;
  for(let i=0;i<freqs.length;i++) if(freqs[i]>=fc+1000){ j=i; break; }
  return {cutoffHz:fc, steepness:rel[idx]-rel[j], rel};
}

/* 强度立体声：高频处边信号 (L−R)/2 相对中信号塌陷的起点。 */
function intensityStereoCutoff(L, R, sr){
  let peak=0;
  const n=Math.min(L.length,R.length);
  const mid=new Float32Array(n), side=new Float32Array(n);
  for(let i=0;i<n;i++){ mid[i]=(L[i]+R[i])/2; side[i]=(L[i]-R[i])/2; peak=Math.max(peak,Math.abs(side[i])); }
  if(peak<1e-5) return null;                       // 本来就是假立体声
  const M=longTermSpectrum(mid,sr,4096,50), S=longTermSpectrum(side,sr,4096,50);
  const ratio=smooth(Float64Array.from(S.db,(v,i)=>v-M.db[i]),7);
  let start=0;
  for(let i=0;i<M.freqs.length;i++) if(M.freqs[i]>=4000){ start=i; break; }
  for(let i=start;i<ratio.length;i++){
    let all=true;
    for(let k=i;k<ratio.length;k++) if(ratio[k]>=-40){ all=false; break; }
    if(all) return M.freqs[i];
  }
  return null;
}

const CUTOFF_TABLE=[[11,"mp3 ~64 kbps / AAC ~48 kbps"],[13,"mp3 ~96 kbps"],
  [15,"mp3 ~112 kbps / AAC ~96 kbps"],[16,"mp3 ~128 kbps / AAC ~128 kbps"],
  [17.5,"mp3 ~160 kbps"],[19,"mp3 ~192 kbps"],[20,"mp3 ~256–320 kbps"]];

function guessSource(khz){
  let best=Infinity, label="an unknown lossy encoder";
  for(const [f,name] of CUTOFF_TABLE){ const d=Math.abs(khz-f); if(d<best){best=d;label=name;} }
  return best<=1.2 ? label : "an unknown lossy encoder";
}

/* 浏览器 decodeAudioData 会重采样，真正的 44.1 kHz 无损在 48 kHz 下
   会在 22.05 kHz 露出一道假悬崖——那是源素材的奈奎斯特，不是编码器。 */
const FULL_BAND_KHZ = 21.6;

/* 19.8–21.6 kHz 是一条无法靠低通本身分辨的模糊带：母带处理和一部分 ADC
   抗混叠滤波器就切在这里，而 LAME 320 kbps 的截止也落在 20 kHz 附近。
   落在这一带时不给"编码器常用档位"的加分，且没有立体声佐证时判定封顶在 likely。 */
const AMBIGUOUS_LO_KHZ = 19.8;

function verdict(cut, stereoHz, isLossless){
  // 评分与判定和 Python 版一致；notes 只给代码和数值，文字由页面按语言生成。
  const notes=[]; let score=0;
  if(cut.cutoffHz!==null){
    const khz=cut.cutoffHz/1000;
    if(khz < FULL_BAND_KHZ){
      score+=0.45;
      if(cut.steepness!==null && cut.steepness>=20){
        score+=0.30;
        notes.push({code:"brickwall", db:cut.steepness});
      } else if(cut.steepness!==null){
        notes.push({code:"rolloff", db:cut.steepness});
      }
      const ambiguous = khz >= AMBIGUOUS_LO_KHZ;
      if(!ambiguous && Math.min(...CUTOFF_TABLE.map(([f])=>Math.abs(khz-f)))<=0.6){
        score+=0.15;
        notes.push({code:"commonCutoff"});
      }
    } else {
      notes.push({code:"fullBand"});
    }
  }
  if(stereoHz!==null){
    score+=0.25;
    notes.push({code:"stereoCollapse", khz:stereoHz/1000});
  }
  score=Math.min(score,1);
  let tier;
  if(!isLossless) tier="lossy";
  else if(score>=0.70) tier="suspect";
  else if(score>=0.45) tier="likely";
  else tier="clean";

  // 模糊带封顶：这一带的砖墙可能来自母带处理而非编码器。
  const khz = cut.cutoffHz===null ? null : cut.cutoffHz/1000;
  if(tier==="suspect" && stereoHz===null && khz!==null
     && khz>=AMBIGUOUS_LO_KHZ && khz<FULL_BAND_KHZ){
    tier="likely";
    notes.push({code:"ambiguousBand", lo:AMBIGUOUS_LO_KHZ, hi:FULL_BAND_KHZ});
  }
  return {tier, score, notes};
}

/* ---------- 时频图：STFT 与重分配谱 ---------- */

/** 两条实序列一次复数 FFT：z = a + i·b，再按共轭对称拆开。返回 a、b 的 0…n/2 频点。 */
function fftPair(a, b, re, im, outA, outB){
  const n=a.length;
  for(let i=0;i<n;i++){ re[i]=a[i]; im[i]=b[i]; }
  fftRadix2(re,im);
  const nb=n/2+1;
  for(let k=0;k<nb;k++){
    const j=(n-k)%n;
    // A[k] = (Z[k] + conj(Z[n-k]))/2,  B[k] = (Z[k] - conj(Z[n-k]))/(2i)
    outA.re[k]=0.5*(re[k]+re[j]); outA.im[k]=0.5*(im[k]-im[j]);
    outB.re[k]=0.5*(im[k]+im[j]); outB.im[k]=-0.5*(re[k]-re[j]);
  }
}

/** librosa 的 util.cyclic_gradient：周期窗口的中心差分，首尾按环绕处理。 */
function cyclicGradient(w){
  const n=w.length, g=new Float64Array(n);
  for(let i=0;i<n;i++) g[i]=0.5*(w[(i+1)%n]-w[(i-1+n)%n]);
  return g;
}

/** 按时间加权的窗：偶数长度时 t = -(n/2 - 0.5) … (n/2 - 0.5)，与 librosa 相同。 */
function timeWeightedWindow(w){
  const n=w.length, half=Math.floor(n/2), out=new Float64Array(n);
  for(let i=0;i<n;i++) out[i]=w[i]*((n%2 ? -half : 0.5-half)+i);
  return out;
}

/** 第 f 帧（center=True：两端各补 n/2 个零）乘上窗 w 写入 out。 */
function frameInto(y, f, hop, w, out){
  const n=w.length, start=f*hop-Math.floor(n/2);
  for(let i=0;i<n;i++){ const s=start+i; out[i]=(s>=0&&s<y.length ? y[s] : 0)*w[i]; }
}

function nFramesOf(len, hop){ return 1+Math.floor(len/hop); }

/** 功率谱矩阵（测试用，短信号）：power[f*nBins + k] = |X|²，与 librosa.stft 逐点一致。 */
function stftPower(y, nFft, hop){
  const w=hann(nFft), nBins=nFft/2+1, nFrames=nFramesOf(y.length,hop);
  const power=new Float64Array(nFrames*nBins), re=new Float64Array(nFft), im=new Float64Array(nFft);
  const fa=new Float64Array(nFft), fb=new Float64Array(nFft);
  const A={re:new Float64Array(nBins), im:new Float64Array(nBins)}, B={re:new Float64Array(nBins), im:new Float64Array(nBins)};
  for(let f=0;f<nFrames;f+=2){
    frameInto(y,f,hop,w,fa);
    if(f+1<nFrames) frameInto(y,f+1,hop,w,fb); else fb.fill(0);
    fftPair(fa,fb,re,im,A,B);
    for(let k=0;k<nBins;k++){
      power[f*nBins+k]=A.re[k]*A.re[k]+A.im[k]*A.im[k];
      if(f+1<nFrames) power[(f+1)*nBins+k]=B.re[k]*B.re[k]+B.im[k]*B.im[k];
    }
  }
  return {power, nFrames, nBins};
}

/** librosa.power_to_db(S, ref=np.max, amin=1e-10, top_db)。 */
function powerToDb(power, topDb=80){
  let ref=0;
  for(const v of power) if(v>ref) ref=v;
  const refDb=10*Math.log10(Math.max(ref,1e-10)), out=new Float64Array(power.length);
  for(let i=0;i<power.length;i++){
    const d=10*Math.log10(Math.max(power[i],1e-10))-refDb;
    out[i]=topDb===null ? d : Math.max(d,-topDb);
  }
  return out;
}

/**
 * 重分配：对第 f 帧第 k 个频点，
 *   f̂ = f_k − Im(S_dh / S_h) · sr/2π      （瞬时频率）
 *   t̂ = t_f + Re(S_th / S_h) / sr         （群延迟）
 * 与 spf reassign 相同的取舍：
 *   - 功率不高于 (最大功率 − magTopDb) 的格点相位不可靠，丢弃；
 *   - |S|² < 1e-6 的格点（librosa 的 ref_power）不做修正，留在格点中心（fill_nan=True）；
 *   - 结果裁到 [0, sr/2] × [0, 时长]（clip=True）。
 * 回调 emit(t̂, f̂, power, f, k) 收下每个保留的点。
 */
const REF_POWER = 1e-6;

function reassignFrames(y, sr, nFft, hop, maxPower, magTopDb, emit, f0=0, f1=Infinity){
  const w=hann(nFft), dw=cyclicGradient(w), tw=timeWeightedWindow(w);
  const nBins=nFft/2+1, nFrames=nFramesOf(y.length,hop), thr=maxPower*Math.pow(10,-magTopDb/10);
  const re=new Float64Array(nFft), im=new Float64Array(nFft), fa=new Float64Array(nFft), fb=new Float64Array(nFft);
  const H={re:new Float64Array(nBins), im:new Float64Array(nBins)}, D={re:new Float64Array(nBins), im:new Float64Array(nBins)};
  const T={re:new Float64Array(nBins), im:new Float64Array(nBins)}, Z={re:new Float64Array(nBins), im:new Float64Array(nBins)};
  const zero=new Float64Array(nFft), dur=y.length/sr, fNyq=sr/2;
  for(let f=f0; f<Math.min(f1,nFrames); f++){
    frameInto(y,f,hop,w,fa); frameInto(y,f,hop,dw,fb);
    fftPair(fa,fb,re,im,H,D);
    frameInto(y,f,hop,tw,fa);
    fftPair(fa,zero,re,im,T,Z);
    const tf=f*hop/sr;
    for(let k=0;k<nBins;k++){
      const hr=H.re[k], hi=H.im[k], p=hr*hr+hi*hi;
      if(!(p>thr)) continue;
      const fk=k*sr/nFft;
      if(p<REF_POWER){ emit(Math.min(tf,dur),fk,p,f,k); continue; }
      const imDh=(D.im[k]*hr-D.re[k]*hi)/p;            // Im(S_dh / S_h)
      const reTh=(T.re[k]*hr+T.im[k]*hi)/p;            // Re(S_th / S_h)
      const fh=Math.min(Math.max(fk-imDh*sr/(2*Math.PI),0),fNyq);
      const th=Math.min(Math.max(tf+reTh/sr,0),dur);
      emit(th,fh,p,f,k);
    }
  }
}

/** 全部重分配点（测试用，短信号）。 */
function reassignedPoints(y, sr, nFft, hop, magTopDb=60){
  let maxPower=0;
  const {power}=stftPower(y,nFft,hop);
  for(const v of power) if(v>maxPower) maxPower=v;
  const times=[], freqs=[], weights=[], frames=[], bins=[];
  reassignFrames(y,sr,nFft,hop,maxPower,magTopDb,(t,f,p,fr,k)=>{ times.push(t); freqs.push(f); weights.push(p); frames.push(fr); bins.push(k); });
  return {times, freqs, weights, frames, bins};
}

/** 频率 → 行号（0 = 最低频）。log 轴按对数等分，和 spectral_forensics.reassign.rasterize 相同。 */
function freqAxis(height, fmin, fmax, logFreq){
  const lmin=Math.log10(Math.max(fmin,1)), lmax=Math.log10(fmax);
  const edge=r=> logFreq ? Math.pow(10, lmin+(lmax-lmin)*r/height) : fmin+(fmax-fmin)*r/height;
  const rowOf=f=>{
    if(!(f>=fmin && f<=fmax)) return -1;               // 与 histogram2d 一样，最后一格含右端点
    const x = logFreq ? (Math.log10(f)-lmin)/(lmax-lmin) : (f-fmin)/(fmax-fmin);
    return Math.min(height-1, Math.floor(x*height));
  };
  return {edge, rowOf, fmin, fmax, logFreq, height};
}

/**
 * 逐步计算一张时频图（生成器，每处理一批帧 yield 一次进度 0…1，最后 return 结果），
 * 这样页面在算两分钟的音频时也不会卡住。
 *   mode "stft"：每个像素取落在其中的帧与频点的最大功率（细线不会被平均掉）；
 *                一个像素比频点还窄时（对数轴的低频端），在相邻频点间线性插值。
 *   mode "reassigned"：重分配点的功率按像素累加，与 rasterize() 里的 histogram2d 一样。
 * 返回 {db: Float32Array(width*height)（行 0 = 最低频，已转 dB 并裁到 -topDb），width, height, duration, axis}。
 */
function* spectrogramRaster(y, sr, opt){
  const {nFft=2048, hop=nFft/4, width=1200, height=480, fmin=20, fmax=sr/2, logFreq=true,
         mode="stft", topDb=80, magTopDb=60} = opt||{};
  const nBins=nFft/2+1, nFrames=nFramesOf(y.length,hop), dur=y.length/sr, df=sr/nFft;
  const axis=freqAxis(height,fmin,fmax,logFreq), raster=new Float64Array(width*height);
  const colOf=t=>Math.min(width-1, Math.max(0, Math.floor(t/dur*width)));
  const BATCH=Math.max(8, Math.floor(65536/nFft));

  // 每一行对应的频点：一段 [k0, k1]（取最大），或两个相邻频点之间的插值位置
  const rows=[];
  for(let r=0;r<height;r++){
    const lo=axis.edge(r), hi=axis.edge(r+1), k0=Math.ceil(lo/df), k1=Math.min(nBins-1, Math.floor(hi/df));
    if(k1>=k0) rows.push({k0, k1, x:-1});
    else rows.push({k0:0, k1:-1, x:Math.min(nBins-1.000001, Math.sqrt(lo*hi)/df)});
  }

  if(mode==="stft"){
    const w=hann(nFft), re=new Float64Array(nFft), im=new Float64Array(nFft), fa=new Float64Array(nFft), fb=new Float64Array(nFft);
    const A={re:new Float64Array(nBins), im:new Float64Array(nBins)}, B={re:new Float64Array(nBins), im:new Float64Array(nBins)};
    const pw=new Float64Array(nBins);
    const put=(f,S)=>{
      for(let k=0;k<nBins;k++) pw[k]=S.re[k]*S.re[k]+S.im[k]*S.im[k];
      // 帧比像素列少时，一帧覆盖它两侧各半个 hop 的所有列，免得图上出现空白竖条
      const c0=colOf((f-0.5)*hop/sr), c1=colOf((f+0.5)*hop/sr);
      for(let r=0;r<height;r++){
        const row=rows[r]; let v;
        if(row.x>=0){ const i=Math.floor(row.x), a=row.x-i; v=pw[i]*(1-a)+pw[i+1]*a; }
        else { v=0; for(let k=row.k0;k<=row.k1;k++) if(pw[k]>v) v=pw[k]; }
        for(let c=c0;c<=c1;c++){ const idx=r*width+c; if(v>raster[idx]) raster[idx]=v; }
      }
    };
    for(let f=0;f<nFrames;f+=2){
      frameInto(y,f,hop,w,fa);
      if(f+1<nFrames) frameInto(y,f+1,hop,w,fb); else fb.fill(0);
      fftPair(fa,fb,re,im,A,B);
      put(f,A); if(f+1<nFrames) put(f+1,B);
      if(f % BATCH < 2) yield f/nFrames;
    }
  } else {
    // 两遍：先找全局最大功率（门限相对它），再做重分配
    let maxPower=0;
    const w=hann(nFft), re=new Float64Array(nFft), im=new Float64Array(nFft), fa=new Float64Array(nFft), fb=new Float64Array(nFft);
    const A={re:new Float64Array(nBins), im:new Float64Array(nBins)}, B={re:new Float64Array(nBins), im:new Float64Array(nBins)};
    for(let f=0;f<nFrames;f+=2){
      frameInto(y,f,hop,w,fa);
      if(f+1<nFrames) frameInto(y,f+1,hop,w,fb); else fb.fill(0);
      fftPair(fa,fb,re,im,A,B);
      for(let k=0;k<nBins;k++){
        maxPower=Math.max(maxPower, A.re[k]*A.re[k]+A.im[k]*A.im[k], B.re[k]*B.re[k]+B.im[k]*B.im[k]);
      }
      if(f % (2*BATCH) < 2) yield 0.25*f/nFrames;
    }
    const emit=(t,fh,p)=>{ const r=axis.rowOf(fh); if(r>=0) raster[r*width+colOf(t)]+=p; };
    for(let f0=0; f0<nFrames; f0+=BATCH){
      reassignFrames(y,sr,nFft,hop,maxPower,magTopDb,emit,f0,f0+BATCH);
      yield 0.25+0.75*f0/nFrames;
    }
  }

  // power_to_db(S + 1e-12, ref=np.max, amin=1e-10, top_db)，与 rasterize() 相同
  let ref=0;
  for(let i=0;i<raster.length;i++){ raster[i]+=1e-12; if(raster[i]>ref) ref=raster[i]; }
  const refDb=10*Math.log10(Math.max(ref,1e-10)), db=new Float32Array(width*height);
  for(let i=0;i<raster.length;i++) db[i]=Math.max(10*Math.log10(Math.max(raster[i],1e-10))-refDb, -topDb);
  return {db, width, height, duration:dur, axis, nFft, hop, mode, sr};
}

/** 页面用的 hop：帧数至少是像素列的 1.5 倍（重分配谱不留空列），但不超过 nFft/4、不小于 32。 */
function displayHop(nSamples, nFft, width){
  let hop=nFft/4;
  while(hop>32 && nSamples/hop < 1.5*width) hop/=2;
  return hop;
}

const API = {
  fftRadix2, hann, longTermSpectrum, smooth, findCutoff, intensityStereoCutoff,
  CUTOFF_TABLE, guessSource, FULL_BAND_KHZ, AMBIGUOUS_LO_KHZ, verdict,
  fftPair, cyclicGradient, timeWeightedWindow, stftPower, powerToDb, reassignedPoints,
  freqAxis, spectrogramRaster, displayHop,
};
root.SPF = API;
if (typeof module !== "undefined" && module.exports) module.exports = API;
})(globalThis);
