"""Encode CUA-captured screenshots as an explicitly labelled offline walkthrough."""
import json
from pathlib import Path
import subprocess
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parent.parent
folder=ROOT/'.local-data/recording'
frames=json.loads((folder/'frames.json').read_text())
lines=[]
for i,frame in enumerate(frames):
    duration=5 if i==len(frames)-1 else max(3,min(8,(frames[i+1]['time']-frame['time'])/1000))
    lines.extend(["file '"+frame['path'].replace("'", "'\\''")+"'",f'duration {duration:.3f}'])
lines.append("file '"+frames[-1]['path']+"'")
concat=folder/'concat.txt'
concat.write_text('\n'.join(lines))
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ffmpeg,'-y','-f','concat','-safe','0','-i',str(concat),'-vf',
    'scale=1440:-2,drawbox=x=0:y=ih-30:w=iw:h=30:color=black:t=fill,drawtext=text=OFFLINE ACCEPTANCE - Sampled desktop screenshots - No live LLM:fontcolor=white:fontsize=16:x=15:y=h-23',
    '-r','24','-c:v','libx264','-preset','fast','-crf','24','-pix_fmt','yuv420p','-movflags','+faststart',
    '-metadata','title=Little Cursor offline acceptance - sampled screenshot walkthrough',str(ROOT/'demo.mp4')],check=True)
