(() => {
  const scene=document.querySelector('[data-motion-scene]') || document.querySelector('.city-page');
  const cross=document.querySelector('.pointer-cross');
  const toggles=document.querySelectorAll('[data-motion-toggle]');
  if(!scene || !cross || !toggles.length)return;
  const first=cross.querySelector('.cross-one'),second=cross.querySelector('.cross-two'),dot=cross.querySelector('circle');
  const rest={x:.66,y:.5};
  const transition=window.JayPageTransition || {point:{...rest},motion:true,chosen:false,holding:false};
  let current={...transition.point},target={...(transition.target || current)},frame=0,lastTime=0,running=true;
  const lag=150;
  const cursorHalfBox=9.5; // Half the visible 19px arrow height.
  function paint(){
    const width=cross.clientWidth,height=cross.clientHeight;
    if(!width || !height)return;
    const x=current.x*width,y=current.y*height,slope=.55;
    cross.setAttribute('viewBox',`0 0 ${width} ${height}`);
    first.setAttribute('d',`M 0 ${y-slope*x} L ${width} ${y+slope*(width-x)}`);
    second.setAttribute('d',`M 0 ${y+slope*x} L ${width} ${y-slope*(width-x)}`);
    dot.setAttribute('cx',x);dot.setAttribute('cy',y);
    transition.point={...current};
    scene.style.setProperty('--pointer-x',`${((current.x-.5)*14).toFixed(2)}px`);
    scene.style.setProperty('--pointer-y',`${((current.y-.5)*10).toFixed(2)}px`);
    scene.style.setProperty('--type-turn',`${((current.x-.5)*12).toFixed(2)}deg`);
  }
  function stop(){cancelAnimationFrame(frame);frame=0;lastTime=0;}
  function step(now){
    frame=0;
    if(!running || document.hidden || !transition.motion || transition.holding){lastTime=0;return;}
    const elapsed=lastTime?Math.max(1,Math.min(40,now-lastTime)):16.67;lastTime=now;
    const amount=1-Math.exp(-elapsed/lag);
    current.x+=(target.x-current.x)*amount;current.y+=(target.y-current.y)*amount;
    const distance=Math.hypot((target.x-current.x)*cross.clientWidth,(target.y-current.y)*cross.clientHeight);
    if(distance<=.2){current={...target};lastTime=0;}
    paint();if(distance>.2)frame=requestAnimationFrame(step);
  }
  function requestPaint(){if(!frame && running && !document.hidden && transition.motion && !transition.holding)frame=requestAnimationFrame(step);}
  function setMotion(enabled,chosen=false){
    if(transition.setMotion)transition.setMotion(enabled,chosen);
    else{transition.motion=enabled;if(chosen)transition.chosen=true;}
    scene.classList.toggle('motion-enabled',enabled);
    toggles.forEach(toggle=>{toggle.textContent=enabled?'Motion: on':'Motion: off';toggle.setAttribute('aria-pressed',String(enabled));});
    if(!enabled){stop();current={...rest};target={...rest};}
    paint();
  }
  transition.pointer={freeze:stop,getTarget:()=>({...target}),setPoint(point,nextTarget=point){stop();current={...point};target={...nextTarget};paint();},resume:requestPaint};
  toggles.forEach(toggle=>toggle.addEventListener('click',()=>setMotion(!transition.motion,true)));
  function rememberPointer(event){
    if(!transition.motion || event.pointerType==='touch')return;
    const bounds=cross.getBoundingClientRect();
    const x=Math.max(0,Math.min(1,(event.clientX-bounds.left+cursorHalfBox)/bounds.width));
    const y=Math.max(0,Math.min(1,(event.clientY-bounds.top-cursorHalfBox)/bounds.height));
    target={x,y};requestPaint();
  }
  document.addEventListener('pointermove',rememberPointer);
  document.addEventListener('pointerdown',rememberPointer);
  document.addEventListener('pointerleave',()=>{if(transition.motion){target={...rest};requestPaint();}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else requestPaint();});
  window.addEventListener('resize',paint);
  window.addEventListener('pagehide',()=>{running=false;stop();});
  window.addEventListener('pageshow',()=>{running=true;setMotion(transition.motion);requestPaint();});
  setMotion(transition.motion);
})();
