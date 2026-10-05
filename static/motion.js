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
  const cursorPriorityMs=250,tapDistance=10,tapDuration=600;
  let lastCursorAt=-Infinity,tap=null;
  const touches=new Set();
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
    if(!enabled){stop();tap=null;touches.clear();current={...rest};target={...rest};}
    paint();
  }
  transition.pointer={freeze:stop,getTarget:()=>({...target}),setPoint(point,nextTarget=point){stop();current={...point};target={...nextTarget};paint();},resume:requestPaint};
  toggles.forEach(toggle=>toggle.addEventListener('click',()=>setMotion(!transition.motion,true)));
  function cursorHasPriority(){return performance.now()-lastCursorAt<cursorPriorityMs;}
  function aim(event,offset=0){
    const bounds=cross.getBoundingClientRect();
    if(!bounds.width || !bounds.height)return;
    const x=Math.max(0,Math.min(1,(event.clientX-bounds.left+offset)/bounds.width));
    const y=Math.max(0,Math.min(1,(event.clientY-bounds.top-offset)/bounds.height));
    target={x,y};requestPaint();
  }
  function rememberPointer(event){
    if(!transition.motion || event.pointerType==='touch')return;
    lastCursorAt=performance.now();transition.inputMode='cursor';tap=null;
    aim(event,cursorHalfBox);
  }
  function startPointer(event){
    if(event.pointerType!=='touch'){rememberPointer(event);return;}
    touches.add(event.pointerId);
    if(!transition.motion || !event.isPrimary || touches.size!==1 || cursorHasPriority()){tap=null;return;}
    tap={id:event.pointerId,x:event.clientX,y:event.clientY,time:performance.now()};
  }
  function movePointer(event){
    if(event.pointerType!=='touch'){rememberPointer(event);return;}
    if(tap?.id===event.pointerId && Math.hypot(event.clientX-tap.x,event.clientY-tap.y)>tapDistance)tap=null;
  }
  function endPointer(event){
    if(event.pointerType!=='touch')return;
    touches.delete(event.pointerId);
    if(tap?.id!==event.pointerId)return;
    const candidate=tap;tap=null;
    if(!transition.motion || touches.size || cursorHasPriority() || performance.now()-candidate.time>tapDuration || Math.hypot(event.clientX-candidate.x,event.clientY-candidate.y)>tapDistance)return;
    transition.inputMode='touch';aim(event);
  }
  function cancelPointer(event){
    if(event.pointerType!=='touch')return;
    touches.delete(event.pointerId);tap=null;
  }
  // Observe taps without capturing the pointer or interfering with native scrolling.
  document.addEventListener('pointermove',movePointer,{passive:true});
  document.addEventListener('pointerdown',startPointer,{passive:true});
  document.addEventListener('pointerup',endPointer,{passive:true});
  document.addEventListener('pointercancel',cancelPointer,{passive:true});
  document.addEventListener('contextmenu',()=>{tap=null;},{passive:true});
  document.addEventListener('pointerleave',event=>{
    if(event.pointerType==='touch')return;
    lastCursorAt=-Infinity;
    if(transition.motion && transition.inputMode==='cursor'){transition.inputMode=null;target={...rest};requestPaint();}
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden){tap=null;touches.clear();stop();}else requestPaint();});
  window.addEventListener('resize',paint);
  window.addEventListener('pagehide',()=>{running=false;tap=null;touches.clear();stop();});
  window.addEventListener('pageshow',()=>{running=true;setMotion(transition.motion);requestPaint();});
  setMotion(transition.motion);
})();
