"""Small deterministic RGBA PNG decoder and RGB encoder for native game assets."""
import struct,zlib,pathlib

def read(path):
 data=pathlib.Path(path).read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n';p=8;packed=bytearray();pal=None;alpha=None
 while p<len(data):
  n=struct.unpack_from('>I',data,p)[0];tag=data[p+4:p+8];v=data[p+8:p+8+n];p+=n+12
  if tag==b'IHDR':w,h,bits,kind,_,_,interlace=struct.unpack('>IIBBBBB',v);assert bits==8 and interlace==0
  if tag==b'IDAT':packed+=v
  if tag==b'PLTE':pal=[tuple(v[i:i+3]) for i in range(0,len(v),3)]
  if tag==b'tRNS':alpha=v
 channels={0:1,2:3,3:1,4:2,6:4}[kind];stride=w*channels;raw=zlib.decompress(packed);prev=bytearray(stride);rows=[];p=0
 for _ in range(h):
  f=raw[p];p+=1;line=bytearray(raw[p:p+stride]);p+=stride
  for i in range(stride):
   a=line[i-channels] if i>=channels else 0;b=prev[i];c=prev[i-channels] if i>=channels else 0
   if f==1:line[i]=(line[i]+a)&255
   elif f==2:line[i]=(line[i]+b)&255
   elif f==3:line[i]=(line[i]+((a+b)//2))&255
   elif f==4:
    q=a+b-c;da=abs(q-a);db=abs(q-b);dc=abs(q-c);line[i]=(line[i]+(a if da<=db and da<=dc else b if db<=dc else c))&255
   else:assert f==0
  row=[]
  for x in range(w):
   v=line[x*channels:(x+1)*channels]
   if kind==6:row.append(tuple(v))
   elif kind==2:row.append((*v,255))
   elif kind==3:row.append((*pal[v[0]],alpha[v[0]] if alpha and v[0]<len(alpha) else 255))
   elif kind==0:row.append((v[0],v[0],v[0],255))
   else:row.append((v[0],v[0],v[0],v[1]))
  rows.append(row);prev=line
 return rows

def write(path,rows):
 h=len(rows);w=len(rows[0]);channels=len(rows[0][0]);assert channels in (3,4)
 def chunk(t,d):return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d))
 raw=b''.join(b'\0'+bytes(c for v in row for c in v) for row in rows)
 pathlib.Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6 if channels==4 else 2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))
