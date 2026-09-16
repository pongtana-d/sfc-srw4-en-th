"""Repair table-rooted FA selectors in the restored v1.3 artifact.

Uses JP only as the structural reference, matches existing authored Thai bytes
uniquely inside each relocated block, and never substitutes Japanese text.
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from srw4.en_dialogue_streams import compile_text

def repair(base, jp, source, translations, layout):
    image=bytearray(base); changes=[];seen=set()
    master=0x280000
    tables=[int.from_bytes(base[master+3*i:master+3*i+3],'little') for i in range(52)]
    for block in source['summary']['blocks']:
        if block['kind']!='record': continue
        slot=block['slot'];jpbase=int(block['pc'],0);table=tables[slot];bank=table>>16
        lo=table&0xffff
        hi=min([t&0xffff for t in tables if t>>16==bank and (t&0xffff)>lo]+[0x10000])
        begin=(bank&0x3f)*65536+lo;end=(bank&0x3f)*65536+hi
        rows={int(x['offset'],0):x for x in source['messages'] if x['block']==slot}
        for index in range(block['pointers']):
            ja=int.from_bytes(jp[jpbase+index*2:jpbase+index*2+2],'little');jo=(jpbase&0xff0000)|ja
            if jp[jo]!=0xfa:continue
            address=int.from_bytes(base[begin+index*2:begin+index*2+2],'little');at=(bank&0x3f)*65536+address
            if at in seen:continue
            seen.add(at)
            count=jp[jo+1]
            assert base[at:at+2]==bytes((0xfa,count)),(slot,index,'selector mismatch')
            for n in range(count):
                old_jp=int.from_bytes(jp[jo+2+2*n:jo+4+2*n],'little');row=rows[old_jp]
                text=translations[row['id']]
                # This first-stage tool locates the immutable v1.3 Thai-name payloads.
                for en,th in [('Shingo','ชินโง'),('Remy','เรมี่'),('Killy','คิลลี่')]:
                    text=text.replace(f'<EN:{en}>',th)
                payload=compile_text(text,layout)
                found=base.find(payload,begin,end)
                assert found>=0 and base.find(payload,found+1,end)<0,(row['id'],'payload not unique')
                field=at+2+2*n;before=int.from_bytes(base[field:field+2],'little');after=found&0xffff
                # A correct target must retain the explicit speaker selector.
                assert payload[0]==0xfe and len(payload)>3,row['id']
                image[field:field+2]=after.to_bytes(2,'little')
                changes.append(dict(block=slot,index=index,choice=n,field_pc=field,before=before,after=after,id=row['id'],text=text))
    assert len(changes)==30 and len(seen)==5,(len(changes),len(seen))
    # Four checksum bytes always total 510, independent of checksum value.
    image[0xffdc:0xffe0]=b'\xff\xff\x00\x00'
    checksum=sum(image)&0xffff
    image[0xffdc:0xffe0]=(checksum^0xffff).to_bytes(2,'little')+checksum.to_bytes(2,'little')
    assert sum(image)&0xffff==checksum
    return bytes(image),changes

def ips(base,out):
    patch=bytearray(b'PATCH');i=0
    while i<len(base):
        if base[i]==out[i]:i+=1;continue
        start=i
        while i<len(base) and base[i]!=out[i] and i-start<65535:i+=1
        patch+=start.to_bytes(3,'big')+(i-start).to_bytes(2,'big')+out[start:i]
    return bytes(patch+b'EOF')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--jp',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    base=args.base.read_bytes();jp=args.jp.read_bytes()
    source=json.loads((ROOT/'data/translations/script.source.json').read_text());th=json.loads((ROOT/'data/translations/script.th.json').read_text())['messages'];layout=json.loads((ROOT/'data/font/encoding.json').read_text())
    result,changes=repair(base,jp,source,th,layout)
    assert result==repair(base,jp,source,th,layout)[0]
    # Source v1.3 objectives remain byte-identical.
    from srw4.en_ff_router import STOCK_OBJECTIVE_SPAN
    bank,start,end=STOCK_OBJECTIVE_SPAN;t=(bank<<16)|start;n=(bank<<16)|end
    assert int.from_bytes(base[0x280003:0x280006],'little')==t
    assert result[t&0x3fffff:n&0x3fffff]==base[t&0x3fffff:n&0x3fffff]
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(result);args.output.with_suffix('.ips').write_bytes(ips(base,result))
    report={'base_sha256':hashlib.sha256(base).hexdigest(),'output_sha256':hashlib.sha256(result).hexdigest(),'changed_bytes':sum(a!=b for a,b in zip(base,result)),'changes':changes,'note':'Delta repair of v1.3; original English combo baseline is absent, so full rebuild was not run.'}
    args.output.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='changes'},indent=2))
