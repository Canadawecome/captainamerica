#!/usr/bin/env python3
"""Extract time-stamped still frames from an actual source or exported podcast MP4."""
import argparse,json
from pathlib import Path
from podcast_media import evidence

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--media',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--interval',type=float,default=5)
    p.add_argument('--max-frames',type=int,default=60);a=p.parse_args()
    r=evidence(a.media,a.output,a.interval,a.max_frames)
    print(json.dumps({'duration':r['duration'],'frames':len(r['frames']),'media_sha256':r['media_sha256']},indent=2))
