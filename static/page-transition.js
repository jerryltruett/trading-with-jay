/* Register pagereveal in the head, before the first rendering. */
(() => {
  const root=document.documentElement;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const transferKey='jay.page-transition',preferenceKey='jay.motion-choice';
  const rest={x:.66,y:.5};
  const pages=new Set(['/','/login/','/join/','/members/','/library/','/live/']);
  const mask=CSS.supports('mask-composite','exclude') || CSS.supports('-webkit-mask-composite','xor');
  const supported='onpagereveal' in window && 'onpageswap' in window && mask && CSS.supports('clip-path','polygon(0px 0px,1px 0px,1px 1px,0px 1px)');
  function read(key){try{return sessionStorage.getItem(key);}catch{return null;}}
  function write(key,value){try{sessionStorage.setItem(key,value);}catch{/* Keep normal navigation. */}}
  function remove(key){try{sessionStorage.removeItem(key);}catch{}}
  function takeTransfer(){
    const raw=read(transferKey);remove(transferKey);
    if(!raw)return null;
    try{
      const value=JSON.parse(raw),age=Date.now()-value.time;
      if(value.path!==location.pathname || !pages.has(value.path) || age<0 || age>4000 || !Number.isFinite(value.x) || !Number.isFinite(value.y) || value.x<0 || value.x>1 || value.y<0 || value.y>1)return null;
      return value;
    }catch{return null;}
  }
  const preference=read(preferenceKey);
  let initial=takeTransfer(),activeTransition=null,formNavigation=false;
  const state=window.JayPageTransition={
    point:initial?{x:initial.x,y:initial.y}:{...rest},
    motion:preference==='on' || (preference!=='off' && !reduced.matches),
    chosen:preference==='on' || preference==='off',holding:Boolean(initial && supported),pointer:null,
    setMotion(enabled,chosen=false){
      state.motion=enabled;
      if(chosen){state.chosen=true;write(preferenceKey,enabled?'on':'off');}
      root.classList.toggle('jay-motion-user-enabled',state.chosen && enabled);
      if(!enabled)activeTransition?.skipTransition();
    }
  };
  state.setMotion(state.motion);
  document.addEventListener('submit',event=>{if(!event.defaultPrevented)formNavigation=true;});
  window.addEventListener('pageshow',()=>{formNavigation=false;});
  window.addEventListener('pageswap',event=>{
    remove(transferKey);
    let path=null;
    try{const url=new URL(event.activation?.entry?.url);if(url.origin===location.origin)path=url.pathname;}catch{}
    if(!event.viewTransition || !supported || !state.motion || formNavigation || !pages.has(location.pathname) || !pages.has(path)){
      event.viewTransition?.skipTransition();return;
    }
    state.holding=true;state.pointer?.freeze();
    write(transferKey,JSON.stringify({x:state.point.x,y:state.point.y,path,time:Date.now()}));
  });
  window.addEventListener('pagereveal',event=>{
    const incoming=takeTransfer() || initial;initial=null;
    const choice=read(preferenceKey);
    state.chosen=choice==='on' || choice==='off';
    state.setMotion(choice==='on' || (choice!=='off' && !reduced.matches));
    if(incoming)state.point={x:incoming.x,y:incoming.y};
    state.pointer?.setPoint(state.point);
    const transition=event.viewTransition;
    if(!transition || !supported || !incoming || !state.motion || !pages.has(location.pathname)){
      transition?.skipTransition();state.holding=false;state.pointer?.resume();return;
    }
    activeTransition=transition;state.holding=true;state.pointer?.freeze();
    const width=root.clientWidth,height=window.innerHeight;
    if(!width || !height)transition.skipTransition();
    else{
      const x=state.point.x*width,y=state.point.y*height;
      const cover=Math.max((Math.max(x,width-x)+2)/(width/2),(Math.max(y,height-y)+2)/(height/2));
      const halfWidth=width/2*cover,halfHeight=height/2*cover;
      const values={x,y,left:x-halfWidth,right:x+halfWidth,top:y-halfHeight,bottom:y+halfHeight,width:halfWidth*2,height:halfHeight*2};
      Object.entries(values).forEach(([key,value])=>root.style.setProperty(`--jay-page-${key}`,`${value}px`));
      root.classList.add('jay-page-transition');
    }
    const complete=()=>{
      root.classList.remove('jay-page-transition');
      ['x','y','left','right','top','bottom','width','height'].forEach(key=>root.style.removeProperty(`--jay-page-${key}`));
      activeTransition=null;state.holding=false;state.pointer?.resume();
    };
    transition.ready.catch(()=>{});transition.finished.then(complete,complete);
  });
})();
