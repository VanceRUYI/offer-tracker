export async function readRecognition(response, onProgress=()=>{}){
  if(!response.ok){
    const error=await response.json().catch(()=>({}));
    throw new Error(error.error||'识别请求失败，请重试');
  }
  if(!response.body)throw new Error('识别连接已中断，请重试');
  const reader=response.body.getReader(),decoder=new TextDecoder();
  let buffer='',result;
  const consume=line=>{
    if(!line.trim())return;
    const event=JSON.parse(line);
    if(event.type==='error')throw new Error(event.error||'识别未完成，请重试');
    if(event.type==='progress')onProgress(event);
    if(event.type==='result')result=event.result;
  };
  try{
    while(true){
      const {done,value}=await reader.read();
      buffer+=done?decoder.decode():decoder.decode(value,{stream:true});
      let end;
      while((end=buffer.indexOf('\n'))>=0){consume(buffer.slice(0,end));buffer=buffer.slice(end+1);}
      if(done){consume(buffer);break;}
    }
    if(!result)throw new Error('识别连接已中断，请重试');
    return result;
  }finally{
    await reader.cancel().catch(()=>{});
    reader.releaseLock();
  }
}
