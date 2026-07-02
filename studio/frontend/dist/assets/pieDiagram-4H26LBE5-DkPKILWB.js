import{n as e}from"./ordinal-CHQ4joKP.js";import{n as t}from"./path-BN-NoVqN.js";import{p as n}from"./math-4cBtkbfL.js";import{t as r}from"./arc-B9uPU3jj.js";import{t as i}from"./array-Bda68fSV.js";import{Dn as a,Gr as o,Jr as s,Rr as c,Sn as l,Ur as u,Vr as d,Wr as f,ai as p,bi as m,ii as h,qr as g,si as _,sr as v,yi as y}from"./index-B_8xXQk4.js";import{t as b}from"./chunk-4BX2VUAB-CbPIcice.js";import{t as x}from"./mermaid-parser.core-CKzcoFMi.js";function S(e,t){return t<e?-1:t>e?1:t>=e?0:NaN}function C(e){return e}function w(){var e=C,r=S,a=null,o=t(0),s=t(n),c=t(0);function l(t){var l,u=(t=i(t)).length,d,f,p=0,m=Array(u),h=Array(u),g=+o.apply(this,arguments),_=Math.min(n,Math.max(-n,s.apply(this,arguments)-g)),v,y=Math.min(Math.abs(_)/u,c.apply(this,arguments)),b=y*(_<0?-1:1),x;for(l=0;l<u;++l)(x=h[m[l]=l]=+e(t[l],l,t))>0&&(p+=x);for(r==null?a!=null&&m.sort(function(e,n){return a(t[e],t[n])}):m.sort(function(e,t){return r(h[e],h[t])}),l=0,f=p?(_-u*b)/p:0;l<u;++l,g=v)d=m[l],x=h[d],v=g+(x>0?x*f:0)+b,h[d]={data:t[d],index:l,value:x,startAngle:g,endAngle:v,padAngle:y};return h}return l.value=function(n){return arguments.length?(e=typeof n==`function`?n:t(+n),l):e},l.sortValues=function(e){return arguments.length?(r=e,a=null,l):r},l.sort=function(e){return arguments.length?(a=e,r=null,l):a},l.startAngle=function(e){return arguments.length?(o=typeof e==`function`?e:t(+e),l):o},l.endAngle=function(e){return arguments.length?(s=typeof e==`function`?e:t(+e),l):s},l.padAngle=function(e){return arguments.length?(c=typeof e==`function`?e:t(+e),l):c},l}var T=u.pie,E={sections:new Map,showData:!1,config:T},D=E.sections,O=E.showData,k=structuredClone(T),A={getConfig:y(()=>structuredClone(k),`getConfig`),clear:y(()=>{D=new Map,O=E.showData,c()},`clear`),setDiagramTitle:_,getDiagramTitle:s,setAccTitle:p,getAccTitle:o,setAccDescription:h,getAccDescription:f,addSection:y(({label:e,value:t})=>{if(t<0)throw Error(`"${e}" has invalid value: ${t}. Negative values are not allowed in pie charts. All slice values must be >= 0.`);D.has(e)||(D.set(e,t),m.debug(`added new section: ${e}, with value: ${t}`))},`addSection`),getSections:y(()=>D,`getSections`),setShowData:y(e=>{O=e},`setShowData`),getShowData:y(()=>O,`getShowData`)},j=y((e,t)=>{b(e,t),t.setShowData(e.showData),e.sections.map(t.addSection)},`populateDb`),M={parse:y(async e=>{let t=await x(`pie`,e);m.debug(t),j(t,A)},`parse`)},N=y(e=>`
  .pieCircle{
    stroke: ${e.pieStrokeColor};
    stroke-width : ${e.pieStrokeWidth};
    opacity : ${e.pieOpacity};
  }
  .pieOuterCircle{
    stroke: ${e.pieOuterStrokeColor};
    stroke-width: ${e.pieOuterStrokeWidth};
    fill: none;
  }
  .pieTitleText {
    text-anchor: middle;
    font-size: ${e.pieTitleTextSize};
    fill: ${e.pieTitleTextColor};
    font-family: ${e.fontFamily};
  }
  .slice {
    font-family: ${e.fontFamily};
    fill: ${e.pieSectionTextColor};
    font-size:${e.pieSectionTextSize};
    // fill: white;
  }
  .legend text {
    fill: ${e.pieLegendTextColor};
    font-family: ${e.fontFamily};
    font-size: ${e.pieLegendTextSize};
  }
`,`getStyles`),P=y(e=>{let t=[...e.values()].reduce((e,t)=>e+t,0),n=[...e.entries()].map(([e,t])=>({label:e,value:t})).filter(e=>e.value/t*100>=1);return w().value(e=>e.value).sort(null)(n)},`createPieArcs`),F={parser:M,db:A,renderer:{draw:y((t,n,i,o)=>{m.debug(`rendering pie chart
`+t);let s=o.db,c=g(),u=l(s.getConfig(),c.pie),f=v(n),p=f.append(`g`);p.attr(`transform`,`translate(225,225)`);let{themeVariables:h}=c,[_]=a(h.pieOuterStrokeWidth);_??=2;let y=u.textPosition,b=r().innerRadius(0).outerRadius(185),x=r().innerRadius(185*y).outerRadius(185*y);p.append(`circle`).attr(`cx`,0).attr(`cy`,0).attr(`r`,185+_/2).attr(`class`,`pieOuterCircle`);let S=s.getSections(),C=P(S),w=[h.pie1,h.pie2,h.pie3,h.pie4,h.pie5,h.pie6,h.pie7,h.pie8,h.pie9,h.pie10,h.pie11,h.pie12],T=0;S.forEach(e=>{T+=e});let E=C.filter(e=>(e.data.value/T*100).toFixed(0)!==`0`),D=e(w).domain([...S.keys()]);p.selectAll(`mySlices`).data(E).enter().append(`path`).attr(`d`,b).attr(`fill`,e=>D(e.data.label)).attr(`class`,`pieCircle`),p.selectAll(`mySlices`).data(E).enter().append(`text`).text(e=>(e.data.value/T*100).toFixed(0)+`%`).attr(`transform`,e=>`translate(`+x.centroid(e)+`)`).style(`text-anchor`,`middle`).attr(`class`,`slice`);let O=p.append(`text`).text(s.getDiagramTitle()).attr(`x`,0).attr(`y`,-400/2).attr(`class`,`pieTitleText`),k=[...S.entries()].map(([e,t])=>({label:e,value:t})),A=p.selectAll(`.legend`).data(k).enter().append(`g`).attr(`class`,`legend`).attr(`transform`,(e,t)=>{let n=22*k.length/2;return`translate(216,`+(t*22-n)+`)`});A.append(`rect`).attr(`width`,18).attr(`height`,18).style(`fill`,e=>D(e.label)).style(`stroke`,e=>D(e.label)),A.append(`text`).attr(`x`,22).attr(`y`,14).text(e=>s.getShowData()?`${e.label} [${e.value}]`:e.label);let j=512+Math.max(...A.selectAll(`text`).nodes().map(e=>e?.getBoundingClientRect().width??0)),M=O.node()?.getBoundingClientRect().width??0,N=450/2-M/2,F=450/2+M/2,I=Math.min(0,N),L=Math.max(j,F)-I;f.attr(`viewBox`,`${I} 0 ${L} 450`),d(f,450,L,u.useMaxWidth)},`draw`)},styles:N};export{F as diagram};