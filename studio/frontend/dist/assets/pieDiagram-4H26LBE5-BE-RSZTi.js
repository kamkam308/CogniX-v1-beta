import{n as e}from"./ordinal-Sf2A9frB.js";import{n as t}from"./path-04Iapt4k.js";import{p as n}from"./math-ClKh9N92.js";import{t as r}from"./arc-Dt-fKyYD.js";import{t as i}from"./array-Bycb6e-0.js";import{$n as a,$r as o,Ar as s,Br as c,Fr as l,Ir as u,Lr as d,Nr as f,Xr as p,Zr as m,di as h,fi as g,mn as _,yn as v,zr as y}from"./index-x9BSa6p8.js";import{t as b}from"./chunk-4BX2VUAB-BvFXTuwN.js";import{t as x}from"./mermaid-parser.core-DNMOePKy.js";function S(e,t){return t<e?-1:t>e?1:t>=e?0:NaN}function C(e){return e}function w(){var e=C,r=S,a=null,o=t(0),s=t(n),c=t(0);function l(t){var l,u=(t=i(t)).length,d,f,p=0,m=Array(u),h=Array(u),g=+o.apply(this,arguments),_=Math.min(n,Math.max(-n,s.apply(this,arguments)-g)),v,y=Math.min(Math.abs(_)/u,c.apply(this,arguments)),b=y*(_<0?-1:1),x;for(l=0;l<u;++l)(x=h[m[l]=l]=+e(t[l],l,t))>0&&(p+=x);for(r==null?a!=null&&m.sort(function(e,n){return a(t[e],t[n])}):m.sort(function(e,t){return r(h[e],h[t])}),l=0,f=p?(_-u*b)/p:0;l<u;++l,g=v)d=m[l],x=h[d],v=g+(x>0?x*f:0)+b,h[d]={data:t[d],index:l,value:x,startAngle:g,endAngle:v,padAngle:y};return h}return l.value=function(n){return arguments.length?(e=typeof n==`function`?n:t(+n),l):e},l.sortValues=function(e){return arguments.length?(r=e,a=null,l):r},l.sort=function(e){return arguments.length?(a=e,r=null,l):a},l.startAngle=function(e){return arguments.length?(o=typeof e==`function`?e:t(+e),l):o},l.endAngle=function(e){return arguments.length?(s=typeof e==`function`?e:t(+e),l):s},l.padAngle=function(e){return arguments.length?(c=typeof e==`function`?e:t(+e),l):c},l}var T=l.pie,E={sections:new Map,showData:!1,config:T},D=E.sections,O=E.showData,k=structuredClone(T),A={getConfig:h(()=>structuredClone(k),`getConfig`),clear:h(()=>{D=new Map,O=E.showData,s()},`clear`),setDiagramTitle:o,getDiagramTitle:c,setAccTitle:m,getAccTitle:d,setAccDescription:p,getAccDescription:u,addSection:h(({label:e,value:t})=>{if(t<0)throw Error(`"${e}" has invalid value: ${t}. Negative values are not allowed in pie charts. All slice values must be >= 0.`);D.has(e)||(D.set(e,t),g.debug(`added new section: ${e}, with value: ${t}`))},`addSection`),getSections:h(()=>D,`getSections`),setShowData:h(e=>{O=e},`setShowData`),getShowData:h(()=>O,`getShowData`)},j=h((e,t)=>{b(e,t),t.setShowData(e.showData),e.sections.map(t.addSection)},`populateDb`),M={parse:h(async e=>{let t=await x(`pie`,e);g.debug(t),j(t,A)},`parse`)},N=h(e=>`
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
`,`getStyles`),P=h(e=>{let t=[...e.values()].reduce((e,t)=>e+t,0),n=[...e.entries()].map(([e,t])=>({label:e,value:t})).filter(e=>e.value/t*100>=1);return w().value(e=>e.value).sort(null)(n)},`createPieArcs`),F={parser:M,db:A,renderer:{draw:h((t,n,i,o)=>{g.debug(`rendering pie chart
`+t);let s=o.db,c=y(),l=_(s.getConfig(),c.pie),u=a(n),d=u.append(`g`);d.attr(`transform`,`translate(225,225)`);let{themeVariables:p}=c,[m]=v(p.pieOuterStrokeWidth);m??=2;let h=l.textPosition,b=r().innerRadius(0).outerRadius(185),x=r().innerRadius(185*h).outerRadius(185*h);d.append(`circle`).attr(`cx`,0).attr(`cy`,0).attr(`r`,185+m/2).attr(`class`,`pieOuterCircle`);let S=s.getSections(),C=P(S),w=[p.pie1,p.pie2,p.pie3,p.pie4,p.pie5,p.pie6,p.pie7,p.pie8,p.pie9,p.pie10,p.pie11,p.pie12],T=0;S.forEach(e=>{T+=e});let E=C.filter(e=>(e.data.value/T*100).toFixed(0)!==`0`),D=e(w).domain([...S.keys()]);d.selectAll(`mySlices`).data(E).enter().append(`path`).attr(`d`,b).attr(`fill`,e=>D(e.data.label)).attr(`class`,`pieCircle`),d.selectAll(`mySlices`).data(E).enter().append(`text`).text(e=>(e.data.value/T*100).toFixed(0)+`%`).attr(`transform`,e=>`translate(`+x.centroid(e)+`)`).style(`text-anchor`,`middle`).attr(`class`,`slice`);let O=d.append(`text`).text(s.getDiagramTitle()).attr(`x`,0).attr(`y`,-400/2).attr(`class`,`pieTitleText`),k=[...S.entries()].map(([e,t])=>({label:e,value:t})),A=d.selectAll(`.legend`).data(k).enter().append(`g`).attr(`class`,`legend`).attr(`transform`,(e,t)=>{let n=22*k.length/2;return`translate(216,`+(t*22-n)+`)`});A.append(`rect`).attr(`width`,18).attr(`height`,18).style(`fill`,e=>D(e.label)).style(`stroke`,e=>D(e.label)),A.append(`text`).attr(`x`,22).attr(`y`,14).text(e=>s.getShowData()?`${e.label} [${e.value}]`:e.label);let j=512+Math.max(...A.selectAll(`text`).nodes().map(e=>e?.getBoundingClientRect().width??0)),M=O.node()?.getBoundingClientRect().width??0,N=450/2-M/2,F=450/2+M/2,I=Math.min(0,N),L=Math.max(j,F)-I;u.attr(`viewBox`,`${I} 0 ${L} 450`),f(u,450,L,l.useMaxWidth)},`draw`)},styles:N};export{F as diagram};