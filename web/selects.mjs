/* Styled single-choice controls; the native select remains the form's source of truth. */
let opened = null;
let serial = 0;
const enhanced = new WeakMap();

export function enhanceSelects(root = document) {
  root.querySelectorAll('select').forEach(select => {
    let control = enhanced.get(select);
    if (control) { control.sync(); return; }
    if (select.multiple) return;
    const id = select.id || (select.id = `choice-${++serial}`);
    const labels = [...select.labels];
    const label = select.getAttribute('aria-label') || labels.map(el => el.textContent.trim()).join(' ') || select.name || '选择';
    const wrap = document.createElement('span');
    wrap.className = 'choice-control';
    const button = document.createElement('button');
    button.type = 'button';
    button.id = id + '-control';
    button.className = select.className + ' choice-trigger';
    button.setAttribute('role', 'combobox');
    button.setAttribute('aria-label', label);
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    const text = document.createElement('span');
    const arrow = document.createElement('span');
    arrow.className = 'choice-chevron';
    arrow.setAttribute('aria-hidden', 'true');
    button.append(text, arrow);
    select.before(wrap);
    wrap.append(select, button);
    select.hidden = true;
    labels.forEach(el => el.htmlFor = button.id);
    let active = -1;
    let panel = null;
    let rows = [];
    let typed = '', typedAt = 0;
    const sync = () => {
      text.textContent = select.selectedOptions[0]?.textContent || '请选择';
      button.disabled = select.disabled;
      button.className = select.className + ' choice-trigger';
    };
    const close = (focus = false) => {
      if (!panel) return;
      panel.remove(); panel = null; rows = [];
      button.setAttribute('aria-expanded', 'false');
      button.removeAttribute('aria-activedescendant');
      button.removeAttribute('aria-controls');
      if (opened?.button === button) opened = null;
      if (focus && button.isConnected) button.focus();
    };
    const enabled = () => [...select.options].map((o,i) => (!o.disabled && !o.hidden && !o.parentElement.disabled) ? i : -1).filter(i => i >= 0);
    const highlight = index => {
      active = index;
      rows.forEach((row,i) => row.classList.toggle('is-active', i === active));
      if (rows[active]) {
        button.setAttribute('aria-activedescendant', rows[active].id);
        rows[active].scrollIntoView({block:'nearest'});
      }
    };
    const choose = index => {
      if (!enabled().includes(index)) return;
      const changed = select.selectedIndex !== index;
      select.selectedIndex = index;
      sync(); close(true);
      if (changed) {
        select.dispatchEvent(new Event('input', {bubbles:true}));
        select.dispatchEvent(new Event('change', {bubbles:true}));
        document.getElementById(button.id)?.focus();
      }
    };
    const open = () => {
      if (button.disabled) return;
      opened?.close();
      panel = document.createElement('div');
      panel.className = 'choice-menu';
      panel.id = id + '-listbox';
      panel.setAttribute('role', 'listbox');
      panel.setAttribute('aria-label', label);
      panel.setAttribute('popover', 'manual');
      rows = [...select.options].map((option,i) => {
        const row = document.createElement('div');
        row.id = id + '-option-' + i;
        row.className = 'choice-option';
        row.setAttribute('role','option');
        row.setAttribute('aria-selected', String(select.selectedIndex === i));
        row.setAttribute('aria-disabled', String(!enabled().includes(i)));
        row.hidden = option.hidden;
        const tick = document.createElement('span');
        tick.className = 'choice-tick';
        tick.textContent = select.selectedIndex === i ? '✓' : '';
        tick.setAttribute('aria-hidden','true');
        const value = document.createElement('span');
        value.textContent = option.textContent;
        row.append(tick, value);
        row.addEventListener('pointerdown', event => event.preventDefault());
        row.addEventListener('click', () => choose(i));
        row.addEventListener('pointermove', () => { if (enabled().includes(i)) highlight(i); });
        panel.append(row);
        return row;
      });
      // Inside the dialog subtree for focus/inert rules; the popover top layer avoids clipping.
      (select.closest('dialog') || document.body).append(panel);
      if (typeof panel.showPopover === 'function') panel.showPopover();
      else panel.removeAttribute('popover');
      const rect = button.getBoundingClientRect();
      const width = Math.min(Math.max(rect.width, 182), innerWidth - 24);
      const below = innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const up = below < 200 && above > below;
      const maxHeight = Math.max(60, Math.min(304, up ? above : below));
      panel.style.width = width + 'px';
      panel.style.maxHeight = maxHeight + 'px';
      panel.style.left = Math.max(12, Math.min(rect.left, innerWidth - width - 12)) + 'px';
      panel.style.top = (up ? Math.max(12, rect.top - Math.min(panel.scrollHeight, maxHeight) - 6) : rect.bottom + 6) + 'px';
      button.setAttribute('aria-expanded','true');
      button.setAttribute('aria-controls', panel.id);
      opened = {button,panel,close};
      highlight(enabled().includes(select.selectedIndex) ? select.selectedIndex : enabled()[0]);
      button.focus();
    };
    button.addEventListener('click', () => panel ? close() : open());
    button.addEventListener('keydown', event => {
      const keys = ['ArrowDown','ArrowUp','Home','End','Enter',' ','Escape'];
      if (event.key === 'Tab') { close(); return; }
      if (event.key === 'Escape' && panel) { event.preventDefault(); event.stopPropagation(); close(true); return; }
      if (event.key === 'Escape') return;
      if (keys.includes(event.key)) {
        event.preventDefault(); event.stopPropagation();
        if (!panel) { open(); if (event.key === 'Home') highlight(enabled()[0]); if (event.key === 'End') highlight(enabled().at(-1)); return; }
        if (event.key === 'Enter' || event.key === ' ') { choose(active); return; }
        const items = enabled(), index = items.indexOf(active);
        if (event.key === 'Home') highlight(items[0]);
        else if (event.key === 'End') highlight(items.at(-1));
        else highlight(items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]);
      } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault(); event.stopPropagation();
        if (!panel) open();
        typed = Date.now() - typedAt > 700 ? event.key : typed + event.key;
        typedAt = Date.now();
        const match = enabled().find(i => select.options[i].textContent.toLocaleLowerCase().startsWith(typed.toLocaleLowerCase()));
        if (match !== undefined) highlight(match);
      }
    });
    select.addEventListener('change', sync);
    enhanced.set(select, {sync});
    sync();
  });
}
export function closeSelectMenu() { opened?.close(); }
document.addEventListener('pointerdown', event => {
  if (opened && !opened.button.contains(event.target) && !opened.panel.contains(event.target)) opened.close();
}, true);
document.addEventListener('focusin', event => {
  if (opened && !opened.button.contains(event.target) && !opened.panel.contains(event.target)) opened.close();
});
document.addEventListener('scroll', event => {
  if (opened && event.target !== opened.panel && !opened.panel.contains(event.target)) opened.close();
}, true);
window.addEventListener('resize', closeSelectMenu);
document.addEventListener('close', closeSelectMenu, true);
