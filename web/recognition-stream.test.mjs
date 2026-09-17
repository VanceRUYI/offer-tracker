import test from 'node:test';
import assert from 'node:assert/strict';
import {readRecognition} from './recognition-stream.mjs';

function response(text, cut=3){
  const data=new TextEncoder().encode(text);
  return new Response(new ReadableStream({start(c){
    for(let i=0;i<data.length;i+=cut)c.enqueue(data.slice(i,i+cut));
    c.close();
  }}));
}
test('recognition handles split UTF-8 chunks and progress before result',async()=>{
  const events=[];
  const result=await readRecognition(response('{"type":"progress","message":"正在读取"}\n{"type":"result","result":{"fields":{"company":"测试公司"}}}\n'), e=>events.push(e.message));
  assert.deepEqual(events,['正在读取']);
  assert.equal(result.fields.company,'测试公司');
});
test('recognition reports terminal error and premature disconnect',async()=>{
  await assert.rejects(readRecognition(response('{"type":"error","error":"读取失败"}\n')),/读取失败/);
  await assert.rejects(readRecognition(response('{"type":"progress","message":"读取中"}\n')),/中断/);
});
