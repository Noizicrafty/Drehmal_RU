import struct,zlib,gzip
def nbt_strings(data,lists=None):
    pos=0
    def u16():
        nonlocal pos
        v=struct.unpack_from('>H',data,pos)[0];pos+=2;return v
    def skip(t):
        nonlocal pos
        if t in (1,2,3,4,5,6):pos+={1:1,2:2,3:4,4:8,5:4,6:8}[t]
        elif t==8:
            n=u16();pos+=n
        elif t in (7,11,12):
            n=struct.unpack_from('>i',data,pos)[0];pos+=4+n*{7:1,11:4,12:8}[t]
        elif t==9:
            sub=data[pos];n=struct.unpack_from('>i',data,pos+1)[0];pos+=5
            if sub in (1,2,3,4,5,6):pos+=n*{1:1,2:2,3:4,4:8,5:4,6:8}[sub]
            else:
                for _ in range(n):skip(sub)
        elif t==10:
            while True:
                sub=data[pos];pos+=1
                if not sub:break
                n=u16();pos+=n;skip(sub)
        else:raise ValueError(('skip',t,pos))
    def string(path,record=False):
        nonlocal pos
        start=pos;n=u16();b=data[pos:pos+n];pos+=n
        if record: yield start,pos,path,b.decode('utf-8',errors='surrogateescape')
    def payload(t,path):
        nonlocal pos
        if t in (1,2,3,4,5,6):pos+={1:1,2:2,3:4,4:8,5:4,6:8}[t]
        elif t in (7,11,12):
            n=struct.unpack_from('>i',data,pos)[0];pos+=4+n*{7:1,11:4,12:8}[t]
        elif t==8:yield from string(path,True)
        elif t==9:
            start=pos
            sub=data[pos];n=struct.unpack_from('>i',data,pos+1)[0];pos+=5
            if sub in (1,2,3,4,5,6):pos+=n*{1:1,2:2,3:4,4:8,5:4,6:8}[sub]
            else:
                for i in range(n):yield from payload(sub,path)
            if lists is not None and sub==8 and path and path[-1]=='pages':lists.append((start,pos,path))
        elif t==10:
            while True:
                sub=data[pos];pos+=1
                if not sub:break
                n=u16();name=data[pos:pos+n].decode('utf-8',errors='surrogateescape');pos+=n
                if name in {'sections','Heightmaps','structures','PostProcessing','CarvingMasks','block_ticks','fluid_ticks','Lights','ToBeTicked','LiquidsToBeTicked'}:skip(sub)
                else:yield from payload(sub,path+(name,))
        else:raise ValueError((t,pos,path))
    t=data[pos];pos+=1;n=u16();pos+=n
    yield from payload(t,())
    if pos!=len(data):raise ValueError(('NBT trailing bytes',pos,len(data)))

def region_chunks(path,indices=None):
    with open(path,'rb') as f:
        header=f.read(8192)
        for i in range(1024):
            if indices is not None and i not in indices:continue
            loc=int.from_bytes(header[i*4:i*4+4],'big');off=loc>>8
            if not off:continue
            f.seek(off*4096);n=struct.unpack('>I',f.read(4))[0];ctype=f.read(1)[0];raw=f.read(n-1)
            if ctype&128: raise ValueError('External chunk '+str(path))
            data= zlib.decompress(raw) if ctype==2 else gzip.decompress(raw) if ctype==1 else raw if ctype==3 else None
            if data is None:raise ValueError(('compression',ctype))
            yield i,data
