"""Small libretro frontend; the unmodified Snes9x core runs the actual ROM."""
import ctypes as C
import pathlib, struct, zlib, os, subprocess, csv, hashlib, json
ROOT = pathlib.Path(__file__).resolve().parents[1]
class Game(C.Structure):
    _fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]
class Emulator:
    def __init__(self, rom='build/lantern.sfc'):
        import sys
        extension='dylib' if sys.platform=='darwin' else 'so'
        self.lib=C.CDLL(str(ROOT/f'tools/vendor/snes9x-1.63/libretro/snes9x_libretro.{extension}'))
        self.capture_path=os.environ.pop('MYDQ_CAPTURE',None)
        self.video_process=None;self.capture_audio=None;self.capture_trace=None;self.capture_frames=0
        self.record_audio=False; self.audio_pcm=bytearray()
        self.frame_observer=None;self.mask=0; self.frame=None; self.audio_energy=0; self.pixel_format=0
        self.directory=C.c_char_p(str(ROOT/'build').encode())
        ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
        VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
        AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16)
        BATCH=C.CFUNCTYPE(C.c_size_t,C.POINTER(C.c_int16),C.c_size_t)
        POLL=C.CFUNCTYPE(None)
        INPUT=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
        def env(cmd,p):
            if cmd in (9,31): C.cast(p,C.POINTER(C.c_char_p))[0]=self.directory; return True
            if cmd==10: self.pixel_format=C.cast(p,C.POINTER(C.c_int))[0]; return True
            if cmd==16: C.cast(p,C.POINTER(C.c_bool))[0]=False; return True
            if cmd in (18,35,36,37): return True
            return False
        def video(p,w,h,pitch):
            if p:self.frame=(w,h,pitch,C.string_at(p,pitch*h))
            if self.capture_path and self.frame:self.capture_frame()
        def batch(p,n):
            self.audio_energy+=sum(abs(p[i]) for i in range(n*2))
            if self.record_audio:self.audio_pcm.extend(C.string_at(p,n*4))
            if self.capture_audio:self.capture_audio.write(C.string_at(p,n*4))
            return n
        def inp(port,device,index,id):
            return bool(self.mask&(1<<id)) if port==0 and id<16 else 0
        self.callbacks=[ENV(env),VIDEO(video),AUDIO(lambda a,b:None),BATCH(batch),POLL(lambda:None),INPUT(inp)]
        for name, cb in zip(('environment','video_refresh','audio_sample','audio_sample_batch','input_poll','input_state'),self.callbacks):
            getattr(self.lib,'retro_set_'+name)(cb)
        self.lib.retro_init()
        self.lib.retro_load_game.argtypes=[C.POINTER(Game)]; self.lib.retro_load_game.restype=C.c_bool
        content=(ROOT/rom).read_bytes();self.rom_sha256=hashlib.sha256(content).hexdigest(); self.rom=C.create_string_buffer(content)
        assert self.lib.retro_load_game(C.byref(Game(None,C.cast(self.rom,C.c_void_p),len(content),None)))
        self.lib.retro_get_memory_data.argtypes=[C.c_uint]; self.lib.retro_get_memory_data.restype=C.c_void_p
        self.lib.retro_get_memory_size.argtypes=[C.c_uint]; self.lib.retro_get_memory_size.restype=C.c_size_t
        self.vram=(C.c_ubyte*0x10000).from_address(self.lib.retro_get_memory_data(3))
        self.ram=(C.c_ubyte*0x20000).from_address(self.lib.retro_get_memory_data(2))
        self.sram=(C.c_ubyte*self.lib.retro_get_memory_size(0)).from_address(self.lib.retro_get_memory_data(0)) if self.lib.retro_get_memory_size(0) else None
    def run(self,n=1,buttons=()):
        ids={'B':0,'Y':1,'SELECT':2,'START':3,'UP':4,'DOWN':5,'LEFT':6,'RIGHT':7,'A':8,'X':9,'L':10,'R':11}
        self.mask=sum(1<<ids[x] for x in buttons)
        for _ in range(n):
            self.lib.retro_run()
            if self.frame_observer:self.frame_observer()
    def press(self,key,n=1): self.run(n,(key,)); self.run(2)
    def word(self,addr): return self.ram[addr]|self.ram[addr+1]<<8
    def screenshot(self,name):
        w,h,pitch,data=self.frame; rows=[]
        for y in range(h):
            row=bytearray([0])
            for x in range(w):
                if self.pixel_format==1:
                    b,g,r,_=data[y*pitch+x*4:y*pitch+x*4+4]
                else:
                    p=struct.unpack_from('<H',data,y*pitch+x*2)[0]
                    if self.pixel_format==2: r=((p>>11)&31)*255//31; g=((p>>5)&63)*255//63; b=(p&31)*255//31
                    else: r=((p>>10)&31)*255//31; g=((p>>5)&31)*255//31; b=(p&31)*255//31
                row.extend((r,g,b))
            rows.append(row)
        def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d))
        path=ROOT/'build'/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))
    def save_audio(self,name):
        import wave
        with wave.open(str(ROOT/'build'/name),'wb') as f:
            f.setnchannels(2);f.setsampwidth(2);f.setframerate(32040);f.writeframes(self.audio_pcm)
    def capture_frame(self):
        w,h,pitch,data=self.frame
        bpp=4 if self.pixel_format==1 else 2
        if self.video_process is None:
            path=ROOT/self.capture_path;path.parent.mkdir(parents=True,exist_ok=True)
            fmt='bgra' if self.pixel_format==1 else 'rgb565le' if self.pixel_format==2 else 'rgb555le'
            self.video_process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format',fmt,'-video_size',f'{w}x{h}','-framerate','60.0988','-i','pipe:0','-vf','scale=1024:896:flags=neighbor','-c:v','libx264','-preset','veryfast','-crf','14','-pix_fmt','yuv420p',str(path.with_suffix('.silent.mp4'))],stdin=subprocess.PIPE)
            self.capture_audio=open(path.with_suffix('.pcm'),'wb')
            self.capture_trace=open(path.with_suffix('.csv'),'w');self.trace_writer=csv.writer(self.capture_trace);self.trace_writer.writerow(['frame','mode','x','y','camx','camy','brightness','moving','map','actor','choose','enemies','phase','round','fading'])
            labels={p[2].lstrip('.'):int(p[1],16) for l in (ROOT/'build/labels.txt').read_text().splitlines() if len(p:=l.split())>=3}
            self.trace_labels=labels
        self.video_process.stdin.write(b''.join(data[y*pitch:y*pitch+w*bpp] for y in range(h)))
        self.trace_writer.writerow([self.capture_frames]+[self.word(self.trace_labels[n]) for n in ('mode',)]+[self.word(0x202),self.word(0x204)]+[self.word(self.trace_labels[n]) for n in ('camx','camy','brightness','moving')]+[self.word(0x200)]+[self.word(self.trace_labels[n]) for n in ('p_actor','p_choose','p_count','battle_phase','p_round','p_fade_in')])
        self.capture_frames+=1
    def close(self):
        if self.video_process:
            self.video_process.stdin.close();assert self.video_process.wait()==0
            self.capture_audio.close();self.capture_trace.close();path=ROOT/self.capture_path
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(path.with_suffix('.silent.mp4')),'-f','s16le','-ar','32040','-ac','2','-i',str(path.with_suffix('.pcm')),'-c:v','copy','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(path)],check=True)
            path.with_suffix('.json').write_text(json.dumps(dict(rom_sha256=self.rom_sha256,frames=self.capture_frames,fps=60.0988,source='unmodified Snes9x1.63 libretro video/audio callbacks',scale='4x nearest-neighbor',duration=self.capture_frames/60.0988),indent=2)+'\n')
        self.lib.retro_unload_game();self.lib.retro_deinit()
if __name__=='__main__':
    import sys
    e=Emulator(sys.argv[1] if len(sys.argv)>1 else 'build/lantern.sfc'); e.run(120); e.screenshot('boot.png'); print('video',e.frame[:3], 'audio energy',e.audio_energy); e.close()
