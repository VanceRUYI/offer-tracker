/* Date fields keep their native values and validation; this only replaces their UI. */
import {dayKey, shiftDay, shiftMonth, pickerDays, dateValue} from './model.mjs';
import {closeSelectMenu} from './selects.mjs';

const controls = new WeakMap();
let opened = null;
const svg = path => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
const chevron = svg('m9 5 7 7-7 7');
const calendarIcon = svg('M8 3v4m8-4v4M4 10h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z');

export function closeDatePicker(focus = false) { opened?.close(focus); }
export function enhanceDates(root = document) {
  root.querySelectorAll('input[type="date"],input[type="datetime-local"]').forEach(input => {
    if(controls.has(input)){controls.get(input).sync();return;}
    const withTime = input.type==='datetime-local';
    const labels = [...input.labels];
    const label = labels.map(el=>el.textContent.trim()).join(' ') || '选择日期';
    const wrap = document.createElement('div');
    wrap.className = 'date-control';
    const button = document.createElement('button');
    button.type = 'button'; button.id = input.id+'-control'; button.className = 'date-trigger';
    button.setAttribute('aria-haspopup','dialog'); button.setAttribute('aria-expanded','false');
    input.before(wrap); wrap.append(input,button);
    input.hidden = true;
    labels.forEach(el=>el.htmlFor=button.id);
    const sync = () => {
      button.innerHTML = `<span>${input.value ? input.value.replaceAll('-',' / ').replace('T','　') : withTime?'选择日期与时间':'选择日期'}</span>${calendarIcon}`;
      button.classList.toggle('is-empty',!input.value); button.disabled=input.disabled;
      button.setAttribute('aria-label',`${label}：${input.value.replace('T',' ')||'未选择'}`);
    };
    const open = () => {
      closeDatePicker(); closeSelectMenu();
      let selected = input.value.slice(0,10) || dayKey();
      let month = selected.slice(0,7);
      let hour = input.value.slice(11,13) || '09', minute = input.value.slice(14,16) || '00';
      const min = input.min.slice(0,10)||'1900-01-01', max = input.max.slice(0,10)||'9999-12-31';
      const allowed = day => /^\d{4}-\d{2}-\d{2}$/.test(day)&&day>=min&&day<=max;
      const panel = document.createElement('div');
      panel.id=input.id+'-picker'; panel.className='date-picker';
      panel.setAttribute('role','dialog'); panel.setAttribute('aria-label',label); panel.setAttribute('popover','manual');
      const close = focus => {
        panel.remove(); button.setAttribute('aria-expanded','false'); button.removeAttribute('aria-controls');
        if(opened?.panel===panel)opened=null;
        if(focus&&button.isConnected)button.focus({preventScroll:true});
      };
      const position = () => {
        const rect=button.getBoundingClientRect(), width=Math.min(308,innerWidth-24);
        panel.style.width=width+'px'; panel.style.maxHeight=(innerHeight-24)+'px';
        const height=panel.getBoundingClientRect().height;
        panel.style.left=Math.max(12,Math.min(rect.left,innerWidth-width-12))+'px';
        panel.style.top=Math.max(12,Math.min(rect.bottom+8+height<=innerHeight-12?rect.bottom+8:rect.top-height-8,innerHeight-height-12))+'px';
      };
      const commit = value => {
        input.value=value; sync(); close(true);
        input.dispatchEvent(new Event('input',{bubbles:true}));
        input.dispatchEvent(new Event('change',{bubbles:true}));
      };
      const rememberTime = () => {
        if(withTime){hour=panel.querySelector('[data-hour]').value;minute=panel.querySelector('[data-minute]').value;}
      };
      const draw = (focusDay = '') => {
        const year=Number(month.slice(0,4)), monthNumber=Number(month.slice(5));
        if(!panel.firstElementChild)panel.innerHTML=`<header class="date-picker-heading"><span>${withTime?'安排日期与时间':'选择日期'}</span><button type="button" class="date-picker-icon" data-close aria-label="关闭日期选择">${svg('m6 6 12 12M6 18 18 6')}</button></header>
          <div class="date-picker-navigation"><button type="button" class="date-picker-icon date-picker-prev" data-month-offset="-1" aria-label="上个月" ${month<=min.slice(0,7)?'disabled':''}>${chevron}</button><div class="date-picker-month"><label><input type="number" value="${year}" min="${Number(min.slice(0,4))}" max="${Number(max.slice(0,4))}" data-year aria-label="年份"><span>年</span></label><label><input type="number" value="${monthNumber}" min="1" max="12" data-month aria-label="月份"><span>月</span></label></div><button type="button" class="date-picker-icon" data-month-offset="1" aria-label="下个月" ${month>=max.slice(0,7)?'disabled':''}>${chevron}</button></div>
          <div class="date-picker-weekdays" aria-hidden="true">${['一','二','三','四','五','六','日'].map(d=>`<span>${d}</span>`).join('')}</div>
          <div class="date-picker-grid" role="group" aria-label="日期"></div>
          ${withTime?`<div class="date-picker-time"><span>时间 <small>24 小时制</small></span><div><input type="number" data-hour min="0" max="23" value="${hour}" aria-label="小时"><span>:</span><input type="number" data-minute min="0" max="59" value="${minute}" aria-label="分钟"></div></div>`:''}
          <footer class="date-picker-footer"><div><button type="button" data-today>今天</button>${!input.required?'<button type="button" data-clear>清空</button>':''}</div>${withTime?'<button type="button" class="date-picker-done" data-done>确定</button>':''}</footer>`;
        // Keep navigation nodes alive while an input blur and button click are in flight.
        panel.querySelector('[data-year]').value=String(year);
        panel.querySelector('[data-month]').value=String(monthNumber);
        panel.querySelector('[data-month-offset="-1"]').disabled=month<=min.slice(0,7);
        panel.querySelector('[data-month-offset="1"]').disabled=month>=max.slice(0,7);
        panel.querySelector('.date-picker-grid').innerHTML=pickerDays(month).map(day=>`<button type="button" data-date="${day}" class="date-picker-day ${day.slice(0,7)!==month?'is-outside':''} ${day===selected?'is-selected':''} ${day===dayKey()?'is-today':''}" aria-label="${day}" aria-pressed="${day===selected}" ${day===dayKey()?'aria-current="date"':''} ${allowed(day)?'':'disabled'} tabindex="${day===(focusDay||selected)?'0':'-1'}">${Number(day.slice(8))}</button>`).join('');
        if(!panel.querySelector('.date-picker-day[tabindex="0"]'))panel.querySelector('.date-picker-day:not(.is-outside):not(:disabled)')?.setAttribute('tabindex','0');
        position();
        if(focusDay)panel.querySelector(`[data-date="${focusDay}"]`)?.focus({preventScroll:true});
      };
      panel.addEventListener('click',event=>{
        const target=event.target.closest('button');if(!target||target.disabled)return;
        if(target.hasAttribute('data-close'))return close(true);
        if(target.hasAttribute('data-clear'))return commit('');
        if(target.hasAttribute('data-month-offset')){
          rememberTime();month=shiftMonth(month,Number(target.dataset.monthOffset));draw();
          panel.querySelector(`[data-month-offset="${target.dataset.monthOffset}"]`)?.focus({preventScroll:true});return;
        }
        if(target.dataset.date||target.hasAttribute('data-today')){
          const day=target.dataset.date||dayKey();if(!allowed(day))return;
          if(!withTime)return commit(day);
          rememberTime();selected=day;month=day.slice(0,7);draw(day);return;
        }
        if(target.hasAttribute('data-done')){
          const inputs=[...panel.querySelectorAll('input')];
          const invalid=inputs.find(el=>!el.value||!el.checkValidity());
          if(invalid){invalid.focus();invalid.reportValidity();return;}
          rememberTime();const value=dateValue(selected,hour,minute,true);if(value)commit(value);
        }
      });
      panel.addEventListener('change',event=>{
        if(!event.target.matches('[data-year],[data-month]'))return;
        const y=panel.querySelector('[data-year]'),m=panel.querySelector('[data-month]');
        if(!y.value||!m.value||!y.checkValidity()||!m.checkValidity())return;
        rememberTime();month=`${y.value.padStart(4,'0')}-${m.value.padStart(2,'0')}`;
        draw();
      });
      panel.addEventListener('keydown',event=>{
        if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close(true);return;}
        if(event.key==='Enter'&&event.target.matches('input')){
          event.preventDefault();event.target.dispatchEvent(new Event('change',{bubbles:true}));return;
        }
        const offsets={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7};
        if(event.target.dataset.date&&event.key in offsets){
          event.preventDefault();const day=shiftDay(event.target.dataset.date,offsets[event.key]);
          if(allowed(day)){rememberTime();month=day.slice(0,7);draw(day);}
        }
      });
      (input.closest('dialog')||document.body).append(panel);
      if(typeof panel.showPopover==='function')panel.showPopover();else panel.removeAttribute('popover');
      opened={panel,button,close};button.setAttribute('aria-expanded','true');button.setAttribute('aria-controls',panel.id);
      draw();panel.querySelector('.date-picker-day[tabindex="0"]')?.focus({preventScroll:true});
    };
    button.addEventListener('click',()=>opened?.button===button?closeDatePicker():open());
    input.addEventListener('change',sync);
    input.addEventListener('invalid',event=>{event.preventDefault();open();});
    controls.set(input,{sync});sync();
  });
}

document.addEventListener('pointerdown',event=>{
  if(opened&&!opened.panel.contains(event.target)&&!opened.button.contains(event.target))closeDatePicker();
},true);
document.addEventListener('focusin',event=>{
  if(opened&&!opened.panel.contains(event.target)&&!opened.button.contains(event.target))closeDatePicker();
});
document.addEventListener('scroll',event=>{
  if(opened&&!opened.panel.contains(event.target))closeDatePicker();
},true);
document.addEventListener('close',()=>closeDatePicker(),true);
window.addEventListener('resize',()=>closeDatePicker());
