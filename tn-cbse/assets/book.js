
(function(){
  // theme toggle (per-viewer convenience only)
  var root=document.documentElement;
  try{var t=localStorage.getItem('lb-theme'); if(t){root.setAttribute('data-theme',t);}}catch(e){}
  document.addEventListener('click',function(e){
    var b=e.target.closest('[data-theme-toggle]'); if(!b)return;
    var cur=root.getAttribute('data-theme');
    if(!cur){cur=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';}
    var nx=cur==='dark'?'light':'dark';
    root.setAttribute('data-theme',nx);
    try{localStorage.setItem('lb-theme',nx);}catch(e){}
  });
  // keyboard paging
  document.addEventListener('keydown',function(e){
    if(e.metaKey||e.ctrlKey||e.altKey)return;
    var tag=(e.target.tagName||'').toLowerCase();
    if(tag==='input'||tag==='textarea')return;
    var sel=e.key==='ArrowLeft'?'[data-nav="prev"]':e.key==='ArrowRight'?'[data-nav="next"]':null;
    if(!sel)return;
    var a=document.querySelector('a'+sel);
    if(a&&a.getAttribute('href')){e.preventDefault();location.href=a.getAttribute('href');}
  });
  // close the drawer on outside click / escape
  document.addEventListener('click',function(e){
    document.querySelectorAll('details.drawer[open]').forEach(function(d){
      if(!d.contains(e.target))d.removeAttribute('open');
    });
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape')document.querySelectorAll('details.drawer[open]').forEach(function(d){d.removeAttribute('open');});
  });
})();
