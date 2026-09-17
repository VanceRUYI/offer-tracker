/* Local company icon cache, discovery preview, and user-controlled replacement. */
const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const key = name => String(name||'').trim().toLowerCase();
const building = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 21V5h11v16M15 10h5v11M2 21h20M7 8h1m3 0h1M7 12h1m3 0h1M7 16h1m3 0h1M8 21v-2h3v2"/></svg>';

export function createCompanyLogos({request,notify}) {
  let saved={}, catalog=[], current='', candidate=null, revision=0, busy=false;
  const attempted=new Set(), pending=new Set(), versions=new Map(), previews=new Map();
  const dialog=document.createElement('dialog');
  dialog.className='editor company-logo-dialog';dialog.setAttribute('aria-labelledby','companyLogoTitle');
  document.body.append(dialog);
  const lookup=company=>saved[key(company)];
  const known=company=>catalog.find(c=>c.aliases.includes(key(company)));
  const content=company=>lookup(company)?.data_url?`<img src="${escape(lookup(company).data_url)}" alt="" decoding="async">`:building;
  const markup=(company,large=false)=>`<span class="company-logo${large?' large':''}${lookup(company)?' has-image':''}" data-company-logo="${escape(company)}" aria-hidden="true">${content(company)}</span>`;
  function refresh(){
    document.querySelectorAll('[data-company-logo]').forEach(el=>{
      el.innerHTML=content(el.dataset.companyLogo);el.classList.toggle('has-image',!!lookup(el.dataset.companyLogo));
    });
  }
  document.addEventListener('error',event=>{
    if(event.target.matches?.('[data-company-logo] img'))event.target.parentElement.innerHTML=building;
  },true);
  async function load(){const data=await request('/api/company-logos');saved=data.logos;catalog=data.catalog;refresh();}
  function remember(candidate){
    if(candidate?.company&&candidate.application_url&&(candidate.logo?.data_url||candidate.logo?.icon_url))
      previews.set(JSON.stringify([key(candidate.company),candidate.application_url]),candidate.logo);
  }
  async function ensure(records){
    // Retry a new link, but never loop on a failed link during subsequent renders.
    const groups=new Map();
    for(const record of records){
      const id=key(record.company);
      if(!groups.has(id))groups.set(id,{company:record.company,urls:new Set()});
      if(record.url?.trim())groups.get(id).urls.add(record.url.trim());
    }
    for(const [id,{company,urls}] of groups){
      if(lookup(company)||pending.has(id))continue;
      const preview=[...urls].map(url=>previews.get(JSON.stringify([id,url]))).find(Boolean);
      const websites=preview?['']:known(company)?['']:[...urls];
      pending.add(id);
      try{for(const website of websites){
        const attempt=JSON.stringify([id,website]);
        if(attempted.has(attempt)&&!preview)continue;
        attempted.add(attempt);
        const version=versions.get(id);
        try{
          const logo=preview?.data_url?preview:await request('/api/company-logo/discover','POST',{company,website:preview?.website||website,automatic:true,...(preview?.icon_url?{icon_url:preview.icon_url}:{})});
          // Do not replace an uploaded image or explicit default while fetching.
          if(lookup(company)||versions.get(id)!==version)break;
          saved[id]=await request('/api/company-logo','POST',{company,logo});refresh();break;
        }catch{/* Missing icons never interrupt recording an application. */}
      }}finally{pending.delete(id);}
    }
  }
  function preview(){
    const box=dialog.querySelector('.logo-preview');
    box.innerHTML=candidate?`<img src="${escape(candidate.data_url)}" alt="图标预览">`:building;
    dialog.querySelector('[data-logo-save]').disabled=busy||!candidate;
    const source=dialog.querySelector('.logo-source');
    source.textContent=candidate?.source_url?'来源：'+new URL(candidate.source_url).hostname:candidate?'自选图片，保存到本机':'没有图标时显示企业图标';
  }
  function open(company){
    revision++;current=company;candidate=lookup(company)?.data_url?lookup(company):null;busy=false;
    const website=candidate?.website||known(company)?.website||'';
    dialog.innerHTML=`<div class="dialog-heading"><div><h2 id="companyLogoTitle">公司图标</h2><p>${escape(company)} · 同公司岗位共用</p></div><button class="icon-button" data-logo-close aria-label="关闭图标设置">×</button></div><div class="form-content"><div class="logo-preview"></div><p class="logo-source"></p><div class="field"><label for="logoWebsite">公司官网</label><input id="logoWebsite" type="url" value="${escape(website)}" placeholder="https://公司官网"><small class="muted">请使用公司官网，避免获取到招聘平台的图标。</small></div><div class="logo-editor-actions"><button class="button" data-logo-fetch>从官网获取</button><button class="button" data-logo-upload>上传图片</button><input type="file" data-logo-file accept="image/png,image/jpeg,image/webp" hidden></div><p class="field-hint">支持 PNG、JPG、WebP；图片会自动缩小，保留原比例。</p><p class="form-error" data-logo-error role="alert" hidden></p></div><div class="dialog-footer"><button class="text-button" data-logo-remove>使用默认图标</button><div class="actions"><button class="button" data-logo-close>取消</button><button class="button primary" data-logo-save>保存图标</button></div></div>`;
    preview();dialog.showModal();
  }
  function setBusy(value){busy=value;dialog.querySelectorAll('[data-logo-fetch],[data-logo-upload],[data-logo-save],[data-logo-remove]').forEach(el=>el.disabled=value);preview();}
  function failure(error){const box=dialog.querySelector('[data-logo-error]');box.textContent=error.message;box.hidden=false;}
  dialog.addEventListener('click',async event=>{
    const b=event.target.closest('button');if(!b)return;
    if(b.hasAttribute('data-logo-close')){dialog.close();return;}
    if(b.hasAttribute('data-logo-upload')){dialog.querySelector('[data-logo-file]').click();return;}
    if(busy)return;
    const token=revision,company=current;
    dialog.querySelector('[data-logo-error]').hidden=true;
    try{
      if(b.hasAttribute('data-logo-fetch')){
        setBusy(true);const logo=await request('/api/company-logo/discover','POST',{company,website:dialog.querySelector('#logoWebsite').value.trim()});
        if(token===revision&&dialog.open){candidate=logo;preview();}
      }else if(b.hasAttribute('data-logo-save')||b.hasAttribute('data-logo-remove')){
        setBusy(true);const logo=b.hasAttribute('data-logo-remove')?{disabled:true}:candidate;
        versions.set(key(company),(versions.get(key(company))||0)+1);
        await request('/api/company-logo','POST',{company,logo});
        saved[key(company)]=logo;
        refresh();if(token===revision)dialog.close();
      }
    }catch(error){if(token===revision&&dialog.open)failure(error);else notify(error.message,true);}
    finally{if(token===revision&&dialog.open)setBusy(false);}
  });
  dialog.addEventListener('close',()=>{revision++;});
  dialog.addEventListener('change',async event=>{
    if(!event.target.hasAttribute('data-logo-file'))return;
    const file=event.target.files[0];event.target.value='';if(!file)return;
    const token=revision;let bitmap;
    try{
      if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5*1024*1024)throw new Error('请选择 5 MB 以内的 PNG、JPG 或 WebP 图片');
      setBusy(true);bitmap=await createImageBitmap(file);
      const scale=Math.min(1,256/Math.max(bitmap.width,bitmap.height));
      const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
      canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);
      if(token===revision&&dialog.open){candidate={data_url:canvas.toDataURL('image/png'),website:'',source_url:''};dialog.querySelector('[data-logo-error]').hidden=true;preview();}
    }catch(error){if(token===revision&&dialog.open)failure(error);}
    finally{bitmap?.close();if(token===revision&&dialog.open)setBusy(false);}
  });
  return {load,ensure,markup,open,remember};
}
