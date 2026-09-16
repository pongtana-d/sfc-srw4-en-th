import sys,json,re
from pathlib import Path
import argparse,hashlib
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'src'))
from srw4.en_dialogue_streams import compile_text
import srw4.en_th_renderer as renderer
parser=argparse.ArgumentParser(description='Keep GoShogun battle speaker names in English on the repaired v1.3 ROM.')
parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
parser.add_argument('--report',type=Path,default=root/'build/reports/srw4-en-th-v1.3-dialogue-fix.json')
args=parser.parse_args()
original=args.input.read_bytes()
assert hashlib.sha256(original).hexdigest()=='322da6bca95f83a18643b361bad46949ac3c09ce5c13e72037f668edc0c724a7','Expected pointer-repaired v1.3 baseline'
layout=json.loads((root/'data/font/encoding.json').read_text());r=bytearray(original);report=json.loads(args.report.read_text());changes=[]
free={}
for bank in (0x34,0x35):
 m=max(re.finditer(b'\xff{80,}',r[bank*65536:(bank+1)*65536]),key=lambda x:len(x.group()));free[bank]=[[bank*65536+m.start()+1,bank*65536+m.end()]]
for block in sorted({x['block'] for x in report['changes']}):
 rows=[x for x in report['changes'] if x['block']==block];start=(rows[0]['field_pc']&0xff0000)|rows[0]['after'];end=start;data=bytearray()
 for row in rows:
  text=row['text'];idx=text.index(':');prefix=text[:len('<FE><0C><00>')];name={'0C':'Shingo','0D':'Remy','0E':'Killy'}[prefix[5:7]]
  new=prefix+'<EN:'+name+'>'+text[idx:]
  old=compile_text(text,layout);payload=compile_text(new,layout);at=(row['field_pc']&0xff0000)|row['after'];assert at==end;assert r[at:at+len(old)]==old;end+=len(old)
  newat=start+len(data)
  spanend=(rows[-1]['field_pc']&0xff0000)|rows[-1]['after'];spanend+=len(compile_text(rows[-1]['text'],layout))
  if newat+len(payload)>spanend:
   region=next(x for x in free[start>>16] if x[1]-x[0]>=len(payload));newat=region[0];assert newat+len(payload)<=region[1];assert all(x==255 for x in r[newat:newat+len(payload)]);r[newat:newat+len(payload)]=payload;region[0]+=len(payload)
  else:data+=payload
  r[row['field_pc']:row['field_pc']+2]=(newat&65535).to_bytes(2,'little')
  changes.append({'id':row['id'],'old':text,'new':new,'name':name,'new_pc':newat})
 print(block,len(data),end-start);assert len(data)<=end-start
 r[start:end]=data+b'\xff'*(end-start-len(data))
 free[start>>16].append([start+len(data),end])
# Assemble both versions and check every original byte before replacing the adapters.
src=(root/'src/srw4/en_th_renderer.py').read_text()
new='private:\n  lda.l ${ROUTER_PAGE_STATE:06X}\n  cmp #$0005\n  beq stock\n  cmp #$0002'
old='private:\n  lda.l ${ROUTER_PAGE_STATE:06X}\n  cmp #$0002'
assert src.count(new)==2
ns=dict(renderer.__dict__);exec(compile(src.replace(new,old),renderer.__file__,'exec'),ns)
for fn,pc in [('_entry',renderer.ENTRY_PC),('_width_entry',renderer.WIDTH_ENTRY_PC)]:
 a=ns[fn](renderer.DEFAULT_STORY_BANKS);b=getattr(renderer,fn)(renderer.DEFAULT_STORY_BANKS)
 assert r[pc:pc+len(a)]==a
 assert all(v==255 for v in r[pc+len(a):pc+len(b)])
 r[pc:pc+len(b)]=b
# Reserve state 5 for explicit English runs; state 1 retains old Thai recovery.
import srw4.en_ff_router as router
src=Path(router.__file__).read_text()
new='  inc a\n  cmp #$0001\n  bne page_selected\n  lda #$0005\npage_selected:\n  sta.l ${ROUTER_PAGE_STATE:06X}'
old='  inc a\n  sta.l ${ROUTER_PAGE_STATE:06X}'
assert src.count(new)==1
ns=dict(router.__dict__);exec(compile(src.replace(new,old),router.__file__,'exec'),ns)
pc=router.ORIGIN+len(router.TRAMPOLINE)
a=ns['_story_dispatch'](router.DEFAULT_STORY_BANKS);b=router._story_dispatch(router.DEFAULT_STORY_BANKS)
a+=ns['_glyph_width'](pc+len(a));b+=router._glyph_width(pc+len(b))
assert r[pc:pc+len(a)]==a
assert all(v==255 for v in r[pc+len(a):pc+len(b)])
r[pc:pc+len(b)]=b
h=router.ORIGIN+router.ENTRY['glyph_width'];r[h:h+5]=router._jml(pc+len(router._story_dispatch(router.DEFAULT_STORY_BANKS)))+b'\xea'
r[0xffdc:0xffe0]=b'\xff\xff\0\0';checksum=sum(r)&65535
r[0xffdc:0xffe0]=(checksum^65535).to_bytes(2,'little')+checksum.to_bytes(2,'little')
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(r)
args.output.with_suffix('.json').write_text(json.dumps({'input_sha256':hashlib.sha256(original).hexdigest(),'output_sha256':hashlib.sha256(r).hexdigest(),'changes':changes},ensure_ascii=False,indent=2)+'\n')
print(args.output)
