// Run with: node --test tests/test_title_logo_picker.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../tools/title_logo_editor.html'), 'utf8');
const paint = html.slice(html.indexOf('function paint(event)'), html.indexOf('\nfunction nudge('));

function setup() {
  const S = {state:{width:2,height:1}, pixels:[[4,9]], color:6, tool:'pick',
    painting:false, strokeSaved:false, undo:[], dirty:false};
  const context = {S, $:()=>({textContent:''}), point:e=>[e.x,0],
    renderPalette(){}, renderTools(){}, renderGrid(){},
    snapshot:()=>S.pixels.map(r=>r.slice()), markDirty:()=>{S.dirty=true}};
  vm.createContext(context); vm.runInContext(paint,context);
  return {S,move:(x,extra={})=>context.paint({x,buttons:0,altKey:false,...extra})};
}

test('hover leaves eyedropper armed; click picks without changing pixels or undo',()=>{
  const {S,move}=setup(); move(0);
  assert.equal(S.tool,'pick'); assert.equal(S.color,6);
  S.painting=true; move(1,{buttons:1});
  assert.equal(S.color,9); assert.equal(S.tool,'draw');
  move(0,{buttons:1});
  assert.deepEqual(S.pixels,[[4,9]]); assert.equal(S.undo.length,0); assert.equal(S.dirty,false);
  S.painting=true; move(0,{buttons:1});
  assert.deepEqual(S.pixels,[[9,9]]); assert.equal(S.undo.length,1);
});

test('Option hover does not pick; Option click picks and cannot draw during drag',()=>{
  const {S,move}=setup(); S.tool='draw'; move(0,{altKey:true});
  assert.equal(S.color,6);
  S.painting=true; move(1,{buttons:1,altKey:true}); move(0,{buttons:1});
  assert.equal(S.color,9); assert.deepEqual(S.pixels,[[4,9]]); assert.equal(S.dirty,false);
});
