/* Browser port of simulate.py. MT19937 integer seeding and rejection sampling
   match Python random.Random so that the same integer seed replays identically. */
const NzothEngine = (() => {
  const [ICE,KOBOLD,NZOTH,STEP,PREP,COIN,SWINDLE,SHROUD,DIG,FISH,MAP,BLADE,PICK,BONE,SHADOW,EVASION,SCHEME,TRANSFORM,FUEL,DEJA] = Array.from({length:20},(_,i)=>i);
  const COST=[1,5,15,0,0,0,2,3,1,1,2,1,2,2,0,2,1,1,1,1];
  const COPIES=[1,1,1,2,2,2,2,2,2,2,2,2,1,1,1,2,1,1,1,1];
  const minions=new Set([ICE,KOBOLD,NZOTH]), weapons=new Set([BLADE,PICK]);
  const spells=new Set(Array.from({length:20},(_,i)=>i).filter(i=>!minions.has(i)&&!weapons.has(i)));
  const drawSpells=new Set([SWINDLE,SHROUD,DIG,FISH,MAP]);
  const tacticalKinds=new Set([ICE,KOBOLD,NZOTH,STEP,PREP,COIN,BONE]);
  const names=['碎冰蹒跚者','狗头人幻术师','恩佐斯，梦境之末','暗影步','伺机待发','伪造的幸运币','行骗','潜伏帷幕','挖掘宝藏','垂钓时光','异教地图','黑水弯刀','疾速矿锄','锯齿骨刺','殒命暗影','闪避','托瓦格尔的阴谋','美味变异鱼','梦魇供能','似曾相识'];
  const card=(uid,kind,delta=0,shadow=false)=>({uid,kind,delta,shadow});
  const compare=(a,b)=>a[0]-b[0]||a[1]-b[1]||Number(a[2])-Number(b[2]);
  const cardName=c=>c.uid===999?'幸运币（后手）':names[c.kind];

  class Random {
    constructor(seed) {
      let n=BigInt(seed); if(n<0n)n=-n;
      const words=[]; do {words.push(Number(n&0xffffffffn));n>>=32n;} while(n);
      this.mt=new Uint32Array(624); this.mt[0]=19650218;
      for(let i=1;i<624;i++)this.mt[i]=(Math.imul(1812433253,this.mt[i-1]^(this.mt[i-1]>>>30))+i)>>>0;
      let i=1,j=0;
      for(let k=Math.max(624,words.length);k;k--){
        this.mt[i]=((this.mt[i]^Math.imul(this.mt[i-1]^(this.mt[i-1]>>>30),1664525))+words[j]+j)>>>0;
        i++;j++;if(i>=624){this.mt[0]=this.mt[623];i=1;}if(j>=words.length)j=0;
      }
      for(let k=623;k;k--){
        this.mt[i]=((this.mt[i]^Math.imul(this.mt[i-1]^(this.mt[i-1]>>>30),1566083941))-i)>>>0;
        i++;if(i>=624){this.mt[0]=this.mt[623];i=1;}
      }
      this.mt[0]=0x80000000;this.index=624;
    }
    uint32(){
      if(this.index>=624){
        for(let i=0;i<624;i++){
          const y=(this.mt[i]&0x80000000)|(this.mt[(i+1)%624]&0x7fffffff);
          this.mt[i]=(this.mt[(i+397)%624]^(y>>>1)^((y&1)?0x9908b0df:0))>>>0;
        }this.index=0;
      }
      let y=this.mt[this.index++];y^=y>>>11;y^=(y<<7)&0x9d2c5680;y^=(y<<15)&0xefc60000;y^=y>>>18;return y>>>0;
    }
    below(n){
      if(n<=0)throw Error('empty random pool');
      const bits=Math.floor(Math.log2(n))+1;let r;
      do{r=this.uint32()>>>(32-bits);}while(r>=n);return r;
    }
    choice(a){return a[this.below(a.length)];}
    shuffle(a){for(let i=a.length-1;i>0;i--){const j=this.below(i+1);[a[i],a[j]]=[a[j],a[i]];}}
    random(){return ((this.uint32()>>>5)*67108864+(this.uint32()>>>6))/9007199254740992;}
  }
  const clone=s=>({...s,deck:s.deck.slice(),hand:s.hand.slice()});
  const counts=s=>{const m=new Map();for(const c of s.deck)m.set(c.kind,(m.get(c.kind)||0)+1);return m;};
  const cost=(s,c)=>Math.max(0,COST[c.kind]+c.delta-s.next_discount-(spells.has(c.kind)?s.prep:0)-(c.kind===KOBOLD?s.ice_discount:0)-(c.kind===NZOTH?s.deathrattle_summons:0));
  function missing(s){
    const kinds=new Set(s.hand.map(c=>c.kind));
    return [!(s.ice_discount||kinds.has(ICE)),!(kinds.has(KOBOLD)||s.board_kobold),!kinds.has(NZOTH)];
  }
  function value(s,k){
    const need=missing(s),any=need.some(Boolean);
    if(minions.has(k))return need[k]?[32,37,38][k]:(k===ICE?2:0);
    if(k===SHADOW)return 7;
    if(k===STEP)return s.board_ice||s.hand.some(c=>c.kind===ICE)?16:6;
    if(k===COIN)return any?9:13;
    if(k===PREP)return s.hand.some(c=>drawSpells.has(c.kind))?12:6;
    if(k===DIG||k===SHROUD)return any?19:1;
    if(k===SWINDLE)return any?17:5;
    if(k===FISH||k===MAP||k===BLADE)return any?12:7;
    if(k===PICK)return Math.max(1,13-2*s.turn);
    if(k===BONE)return s.board_ice||s.enemy_target||s.board_kobold?10:2;
    return 0;
  }
  function add(s,c){if(s.hand.length===10){s.burned++;return false;}s.hand.push(c);return true;}
  function draw(s,rng,filter=null,selected=null,details=null){
    if(!s.deck.length)return null;
    const indices=[];
    if(selected!==null||filter!==null){s.deck.forEach((c,i)=>{if(selected!==null?c.kind===selected:filter.has(c.kind))indices.push(i);});}
    else indices.push(0);
    if(!indices.length)return null;
    const i=rng.choice(indices),c=s.deck.splice(i,1)[0];if(i===0)s.known_top=-1;
    const ok=add(s,c);if(details)details.push((ok?'抽到：':'手牌已满，烧掉：')+cardName(c));return c;
  }
  function shadow(s,cast){s.hand=s.hand.map(c=>c.shadow?card(c.uid,cast.kind,cast.delta,true):c);}
  function chooseOption(s,options,bonus=false){
    if(!options.length)return null;
    const score=k=>{
      let result=value(s,k);
      if(bonus){
        const c=Math.max(0,COST[k]-s.next_discount-(spells.has(k)?s.prep:0)-(k===KOBOLD?s.ice_discount:0));
        let playable=new Set([ICE,COIN,PREP,DIG,SWINDLE,SHROUD,FISH,MAP,BLADE,PICK]).has(k);
        if(k===STEP)playable=s.board_ice||s.board_kobold;
        if(k===BONE)playable=s.board_ice||s.board_kobold||s.enemy_target;
        if(playable&&c<=s.mana)result+=0.65*Math.max(0,...options.filter(x=>x!==k).map(x=>value(s,x)));
      }return [result,-COST[k],-k];
    };
    return options.reduce((best,k)=>{const a=score(k),b=score(best);return a[0]>b[0]||(a[0]===b[0]&&(a[1]>b[1]||(a[1]===b[1]&&a[2]>b[2])))?k:best;});
  }
  function discover(s,rng){
    const pool=Array.from(counts(s).keys()).sort((a,b)=>a-b),out=[];
    for(let i=0,n=Math.min(3,pool.length);i<n;i++){const k=rng.choice(pool);out.push(k);pool.splice(pool.indexOf(k),1);}return out;
  }
  function rewards(s,uid,rng,details){
    const active=s.rewards.filter(r=>r[0]===uid&&r[1]===s.turn);s.rewards=s.rewards.filter(r=>r[0]!==uid);
    for(const r of active){
      const available=new Set(s.deck.map(c=>c.kind)),valid=r[2].filter(k=>available.has(k)),k=chooseOption(s,valid);
      if(k!==null){const c=draw(s,rng,null,k);if(details)details.push('地图第二次选择：'+cardName(c));}
    }
  }
  const onlyNzoth=s=>{const a=s.hand.filter(c=>minions.has(c.kind));return a.length===1&&a[0].kind===NZOTH;};
  function apply(s,a,rng,details=null){
    const [op,uid,target]=a;
    if(op==='attack'){
      s.attacked=true;if(s.weapon===PICK)draw(s,rng,null,null,details);s.durability--;if(!s.durability)s.weapon=-1;return;
    }
    const c=s.hand.find(c=>c.uid===uid);if(!c)throw Error('card not in hand');
    if(op==='trade'){
      s.mana--;s.hand.splice(s.hand.indexOf(c),1);draw(s,rng,null,null,details);
      const at=rng.below(s.deck.length+1);s.deck.splice(at,0,c);if(at===0)s.known_top=-1;
      const indices=s.hand.map((c,i)=>spells.has(c.kind)?i:-1).filter(i=>i>=0);
      if(indices.length){const i=rng.choice(indices);s.hand[i]={...s.hand[i],delta:s.hand[i].delta-1};if(details)details.push(cardName(s.hand[i])+'永久减 1 费');}
      if(details)details.push('交易不触发连击，不消耗待发或骨刺效果');return;
    }
    const paid=cost(s,c);if(paid>s.mana)throw Error('insufficient mana');
    const combo=s.combo;s.mana-=paid;s.next_discount=0;if(spells.has(c.kind))s.prep=0;
    s.hand.splice(s.hand.indexOf(c),1);s.combo=true;if(spells.has(c.kind))shadow(s,c);
    switch(c.kind){
      case ICE:s.board_ice=true;s.ice_discount++;if(details)details.push('下一个亡语随从累计减 '+s.ice_discount+' 费，使用后立即死亡');break;
      case KOBOLD:
        s.deathrattle_summons++;
        if(s.ice_discount){s.ice_discount=0;s.started=onlyNzoth(s);if(details)details.push('幻术师立即死亡 → 亡语定向拉出恩佐斯');}
        else{s.board_kobold=true;if(details)details.push('幻术师留在场上，仍需主动触发死亡');}break;
      case STEP:
        if(target==='ice'){s.board_ice=false;add(s,card(76259,ICE,-2));}
        else{s.board_kobold=false;add(s,card(45936,KOBOLD,-2));}
        if(details)details.push('回手'+(target==='ice'?'碎冰者':'幻术师')+'，其费用减少 2');break;
      case PREP:s.prep+=2;if(details)details.push('下一张法术减 2 费，仅本回合有效');break;
      case COIN:s.mana=Math.min(10,s.mana+1);if(details)details.push('本回合增加 1 法力；连击已开启');break;
      case BONE:
        if(target==='ice')s.board_ice=false;
        else if(target==='kobold'){s.board_kobold=false;s.started=onlyNzoth(s);}
        else s.enemy_target=false;
        s.next_discount+=2;if(details)details.push('击杀'+({ice:'自己的碎冰者',kobold:'自己的幻术师',enemy:'对手的随从'}[target])+'；下一张牌减 2 费');break;
      case DIG:draw(s,rng,minions,null,details);break;
      case SWINDLE:
        if(details)details.push(combo?'已连击：先抽法术，再抽随从':'未连击：只能抽法术');
        draw(s,rng,spells,null,details);if(combo)draw(s,rng,minions,null,details);break;
      case SHROUD:draw(s,rng,minions,null,details);draw(s,rng,minions,null,details);break;
      case FISH:{
        const bottom=s.deck.slice(-3);
        if(bottom.length){
          const chosen=bottom.reduce((best,c)=>value(s,c.kind)>value(s,best.kind)||(value(s,c.kind)===value(s,best.kind)&&COST[c.kind]<COST[best.kind])?c:best);
          s.deck.splice(s.deck.indexOf(chosen),1);s.deck.unshift(chosen);s.known_top=chosen.uid;
          if(details)details.push('探底 ['+bottom.map(cardName).join(' / ')+'] → '+cardName(chosen));
          if(combo)draw(s,rng,null,null,details);else if(details)details.push('未连击：所选牌仅放到牌库顶，不立即抽');
        }break;
      }
      case MAP:{
        const options=discover(s,rng),selected=chooseOption(s,options,true);
        if(selected!==null){
          const h=draw(s,rng,null,selected);
          if(s.hand.includes(h))s.rewards=[...s.rewards,[h.uid,s.turn,options.filter(k=>k!==selected)]];
          if(details)details.push('发现 ['+options.map(k=>names[k]).join(' / ')+'] → '+names[selected]);
          if(details)details.push('本回合打出首选牌，才能从其余选项再选一张');
        }break;
      }
      case BLADE:case PICK:s.weapon=c.kind;s.durability=2;if(details)details.push('装备武器，2 耐久'+(c.kind===PICK?'；英雄攻击后抽牌':''));break;
      case EVASION:s.evasion=true;break;
      default:throw Error('unsupported play');
    }
    if(!s.started)rewards(s,uid,rng,details);
  }

  const tacCache=new Map();
  const tacArgs=s=>[s.hand.filter(c=>tacticalKinds.has(c.kind)||c.shadow).map(c=>[c.kind,c.delta,c.shadow]).sort(compare),s.mana,s.prep,s.next_discount,s.ice_discount,s.board_ice,s.board_kobold,s.enemy_target];
  function tactical(hand,mana,prep,nxt,ice,bi,bk,enemy){
    const key=JSON.stringify([hand,mana,prep,nxt,ice,bi,bk,enemy]);if(tacCache.has(key))return tacCache.get(key);
    const remember=result=>{tacCache.set(key,result);return result;};
    const kinds=hand.map(c=>c[0]);if(!kinds.includes(NZOTH)||(!kinds.includes(KOBOLD)&&!bk))return remember(null);
    for(let i=0;i<hand.length;i++){
      const [kind,delta,sh]=hand[i];if(!tacticalKinds.has(kind)||kind===NZOTH)continue;
      const paid=Math.max(0,COST[kind]+delta-nxt-(spells.has(kind)?prep:0)-(kind===KOBOLD?ice:0));
      if(paid>mana||(kind===ICE&&bi))continue;
      let targets=[''];if(kind===STEP)targets=[...(bi?['ice']:[]),...(bk?['kobold']:[])];
      if(kind===BONE)targets=[...(bk?['kobold']:[]),...(enemy?['enemy']:[]),...(bi?['ice']:[])];
      for(const target of targets){
        let rest=[...hand.slice(0,i),...hand.slice(i+1)];if(spells.has(kind))rest=rest.map(c=>c[2]?[kind,delta,true]:c);
        let m=mana-paid,p=spells.has(kind)?0:prep,n=0,a=ice,b=bi,k=bk,e=enemy,success=false;
        const clean=()=>{const h=rest.filter(c=>minions.has(c[0]));return h.length===1&&h[0][0]===NZOTH;};
        if(kind===KOBOLD){if(a){success=clean();a=0;if(!success)continue;}else if(!k)k=true;else continue;}
        else if(kind===ICE){a++;b=true;}
        else if(kind===STEP){rest.push([target==='ice'?ICE:KOBOLD,-2,false]);if(target==='ice')b=false;else k=false;}
        else if(kind===COIN)m=Math.min(10,m+1);
        else if(kind===PREP)p+=2;
        else if(kind===BONE){n+=2;if(target==='ice')b=false;else if(target==='kobold'){k=false;success=clean();if(!success)continue;}else e=false;}
        const selector=[kind,delta,sh,target];if(success)return remember([selector]);
        const tail=tactical(rest.sort(compare),m,p,n,a,b,k,e);if(tail!==null)return remember([selector,...tail]);
      }
    }return remember(null);
  }
  function actual(s,selector){const [k,d,sh,target]=selector;const c=s.hand.find(c=>c.kind===k&&c.delta===d&&c.shadow===sh);return ['play',c.uid,target];}
  function deterministic(s){
    const seen=new Set(),actions=[];
    for(const c of s.hand){
      const sig=JSON.stringify([c.kind,c.delta,c.shadow]);if(seen.has(sig)||cost(s,c)>s.mana)continue;seen.add(sig);
      let targets=[];
      if(c.kind===ICE&&!s.board_ice)targets=[''];
      else if(c.kind===COIN||c.kind===PREP)targets=[''];
      else if(c.kind===STEP&&s.board_ice)targets=['ice'];
      else if(c.kind===BONE){if(s.enemy_target)targets.push('enemy');if(s.board_ice)targets.push('ice');}
      else if(c.kind===BLADE&&s.weapon!==PICK&&(!s.combo||s.rewards.some(r=>r[0]===c.uid)))targets=[''];
      else if(c.kind===EVASION&&!s.evasion&&(!s.combo||s.rewards.some(r=>r[0]===c.uid)))targets=[''];
      for(const target of targets)actions.push(['play',c.uid,target]);
    }return actions;
  }
  function comb(n,r){if(r>n)return 0;let a=1;for(let i=1;i<=r;i++)a=a*(n-i+1)/i;return a;}
  function expectedMax(s,counts,sample,unique=false){
    if(unique)counts=new Map(Array.from(counts.keys(),k=>[k,1]));
    const n=Array.from(counts.values()).reduce((a,b)=>a+b,0);if(!n)return 0;
    const r=Math.min(sample,n),denom=comb(n,r),groups=new Map();
    for(const [k,count]of counts){const v=value(s,k);groups.set(v,(groups.get(v)||0)+count);}
    let cumulative=0,previous=0,result=0;
    for(const [v,count]of Array.from(groups).sort((a,b)=>a[0]-b[0])){cumulative+=count;const cdf=comb(cumulative,r)/denom;result+=v*(cdf-previous);previous=cdf;}return result;
  }
  function drawValue(s,c,counts){
    const nMin=Array.from(minions).reduce((a,k)=>a+(counts.get(k)||0),0);
    const minValue=nMin?Array.from(minions).reduce((a,k)=>a+(counts.get(k)||0)*value(s,k),0)/nMin:0;
    const nSpell=Array.from(spells).reduce((a,k)=>a+(counts.get(k)||0),0);
    const spellValue=nSpell?Array.from(spells).reduce((a,k)=>a+(counts.get(k)||0)*value(s,k),0)/nSpell:0;
    const mean=()=>Array.from(counts).reduce((a,[k,n])=>a+n*value(s,k),0)/Math.max(1,Array.from(counts.values()).reduce((a,b)=>a+b,0));
    switch(c.kind){
      case DIG:return minValue;
      case SHROUD:return Math.min(2,nMin)*minValue;
      case SWINDLE:return spellValue+(s.combo?minValue:0);
      case FISH:return expectedMax(s,counts,3)*(s.combo?1:0.43);
      case MAP:return expectedMax(s,counts,3,true)+(s.mana-cost(s,c)>=1?5:0);
      case BLADE:return (s.known_top>=0?value(s,s.deck.find(h=>h.uid===s.known_top).kind):mean())+(s.hand.some(h=>drawSpells.has(h.kind))?2.5:1);
      case PICK:return s.weapon!==PICK?mean()*(1+(s.turn<5?0.8:0)):0;
      default:return 0;
    }
  }
  const setup=s=>(s.ice_discount?9:0)+3*Math.min(3,Math.max(0,s.ice_discount-1))+(s.board_ice?1:0)+(s.hand.some(c=>c.kind===ICE&&COST[ICE]+c.delta<=0)?0.5:0);
  const penalty=k=>({[COIN]:5,[PREP]:2,[STEP]:2,[BONE]:2,[EVASION]:0,[BLADE]:1}[k]||0);
  function choose(s,rng){
    const win=tactical(...tacArgs(s));if(win)return actual(s,win[0]);
    const remaining=counts(s),initial=setup(s),frontier=[[s,[],0,0]],visited=new Set();let bestScore=0,best=null;
    while(frontier.length){
      const [node,prefix,used,paid]=frontier.pop();
      const key=JSON.stringify([node.hand.map(c=>[c.kind,c.delta,c.shadow]).sort(compare),node.mana,node.combo,node.prep,node.next_discount,node.ice_discount,node.board_ice,node.enemy_target,node.weapon,node.evasion]);
      if(visited.has(key))continue;visited.add(key);
      const progress=setup(node)-initial,endScore=progress-used-3*paid;
      if(prefix.length&&endScore>bestScore){bestScore=endScore;best=prefix[0];}
      const seen=new Set();
      for(const c of node.hand){
        const sig=JSON.stringify([c.kind,c.delta,c.shadow]);if(seen.has(sig))continue;seen.add(sig);
        let expense,action;
        if(drawSpells.has(c.kind)||c.kind===PICK){expense=cost(node,c);if(expense>node.mana||(c.kind===PICK&&node.attacked))continue;action=['play',c.uid,''];}
        else if(c.kind===BLADE&&node.mana>=1&&node.deck.length){expense=1;action=['trade',c.uid,''];}
        else continue;
        let benefit=drawValue(node,c,remaining);
        if(action[0]==='play')for(const [uid,turn,options]of node.rewards)if(uid===c.uid&&turn===node.turn)benefit+=Math.max(0,...options.map(k=>value(node,k)));
        let score=benefit+progress-used-3*(paid+expense);if(c.kind===SWINDLE&&!node.combo)score-=5;
        if(score>bestScore){bestScore=score;best=prefix.length?prefix[0]:action;}
      }
      if(prefix.length===2)continue;
      for(const a of deterministic(node)){
        const c=node.hand.find(c=>c.uid===a[1]);if(node.rewards.some(r=>r[0]===c.uid))continue;
        const child=clone(node),spent=cost(node,c);apply(child,a,rng);frontier.push([child,[...prefix,a],used+penalty(c.kind),paid+spent]);
      }
    }
    for(const [uid,turn,options]of s.rewards){
      if(turn!==s.turn)continue;const c=s.hand.find(c=>c.uid===uid);if(!c)continue;
      const eligible=deterministic(s).find(a=>a[1]===uid);
      if(eligible){let score=Math.max(0,...options.map(k=>value(s,k)))-3*cost(s,c);if(c.kind===ICE)score+=s.ice_discount?3:9;if(score>bestScore){bestScore=score;best=eligible;}}
    }return best;
  }
  function mulligan(rng,second,policy){
    let deck=[];for(let k=0;k<20;k++)for(let j=0;j<COPIES[k];j++)deck.push(card(100+k*3+j,k,0,k===SHADOW));rng.shuffle(deck);
    const n=second?4:3,opening=deck.slice(0,n);deck=deck.slice(n);
    let keep=new Set([...minions,DIG,SWINDLE,SHROUD]);
    if(policy==='cheap'){
      keep=new Set([...minions,DIG,SHROUD]);if(opening.some(c=>[DIG,SHROUD,SWINDLE,MAP].includes(c.kind)))keep.add(PREP);if(opening.some(c=>c.kind===ICE))keep.add(STEP);
    }
    const held=opening.filter(c=>keep.has(c.kind)),rejected=opening.filter(c=>!keep.has(c.kind)),replacement=deck.slice(0,rejected.length);
    deck=[...deck.slice(rejected.length),...rejected];rng.shuffle(deck);const hand=[...held,...replacement];if(second)hand.push(card(999,COIN));
    return [{deck,hand,turn:0,mana:0,combo:false,prep:0,next_discount:0,ice_discount:0,board_ice:false,board_kobold:false,enemy_target:false,weapon:-1,durability:0,attacked:false,evasion:false,known_top:-1,rewards:[],started:false,burned:0,deathrattle_summons:0},opening,rejected,replacement];
  }
  function snapshot(s){
    return {turn:s.turn,mana:s.mana,combo:s.combo,prep:s.prep,next_discount:s.next_discount,ice_discount:s.ice_discount,board_ice:s.board_ice,board_kobold:s.board_kobold,enemy_target:s.enemy_target,weapon:s.weapon,durability:s.durability,attacked:s.attacked,started:s.started,burned:s.burned,
      deckCount:s.deck.length,remaining:Array.from(counts(s)).sort((a,b)=>a[0]-b[0]),hand:s.hand.map(c=>({...c,cost:cost(s,c)}))};
  }
  function simulate(seed,{second=false,enemy=false,policy='guide',naturalOnly=false}={}){
    tacCache.clear();const rng=new Random(seed),[s,opening,rejected,replacement]=mulligan(rng,second,policy),events=[];
    const emit=(type,title,details=[],extra={})=>events.push({type,title,details,...extra,state:snapshot(s)});
    emit('mulligan','起手与换牌',['原始起手：'+opening.map(cardName).join(' / '),'换掉：'+(rejected.map(cardName).join(' / ')||'无'),'替换抽到：'+(replacement.map(cardName).join(' / ')||'无'),...(second?['换牌结束后获得后手幸运币']:[])],{opening,rejected,replacement});
    for(let turn=1;turn<=5;turn++){
      s.turn=turn;s.mana=turn;s.combo=false;s.prep=0;s.next_discount=0;s.attacked=false;s.rewards=[];s.enemy_target=enemy&&turn>=2;
      const c=draw(s,rng);emit('natural','第 '+turn+' 回合 · 自然抽牌',c?[cardName(c)]:['牌库为空'],{card:c});
      for(let step=0;step<60;step++){
        let action;
        if(s.weapon===PICK&&s.durability&&!s.attacked)action=['attack',-1,''];
        else if(naturalOnly){
          const plan=tactical(...tacArgs(s));action=plan?actual(s,plan[0]):null;
          if(!action){const c=s.hand.find(c=>c.kind===ICE&&cost(s,c)<=s.mana);action=c&&!s.board_ice?['play',c.uid,'']:null;}
        }else action=choose(s,rng);
        if(!action)break;
        const [op,uid,target]=action,c=s.hand.find(c=>c.uid===uid),paid=op==='play'?cost(s,c):(op==='trade'?1:0),details=[],combo=s.combo;
        apply(s,action,rng,details);
        const title=op==='attack'?'矿锄攻击 · 抽牌':(op==='trade'?'交易黑水弯刀':'打出 '+cardName(c)+(c.shadow?'（殒命暗影复制）':''));
        emit(op,title,details,{card:c,paid,target,comboBefore:combo});
        if(s.started){emit('success','第 '+turn+' 回合启动成功',['幻术师亡语的手牌随从池只剩恩佐斯，定向召唤其 1/1 复制。','判定在第一只恩佐斯入场时结束；不继续模拟随机亡语池和斩杀。']);return {seed:String(seed),turn,burned:s.burned,events};}
        if(step===59)throw Error('action cap reached');
      }
      emit('end','第 '+turn+' 回合结束',['剩余 '+s.mana+' 法力；等待下一次自然抽牌。']);
    }
    emit('failure','五费内未启动',['截至第五回合，未找到可支付费用并定向拉出恩佐斯的路线。']);return {seed:String(seed),turn:0,burned:s.burned,events};
  }
  return {Random,simulate,names,COST,COPIES,cardName,minions,weapons,spells};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=NzothEngine;
