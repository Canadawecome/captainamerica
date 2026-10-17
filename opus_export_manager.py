#!/usr/bin/env python3
"""OpusClip Get Clips loader, safe export downloader and source-range provenance.

GET /api/exportable-clips?q=findByProjectId&projectId=... is documented.
No live request without explicit --execute. No invented project ID or URL.
"""
from __future__ import annotations
import argparse,json,os,urllib.request,urllib.parse,shutil,ipaddress,socket
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass
from opus_expert_core import sha256, windows_overlap

BASE='https://api.opus.pro/api/exportable-clips'


def normalize_clip(row:dict)->dict:
    """Fail closed if project id, export URL or original timeRanges is missing."""
    if not isinstance(row,dict) or not row.get('projectId') or not row.get('id'):
        raise ValueError('EXPORT_METADATA_MISSING_PROJECT_OR_ID')
    intervals=row.get('timeRanges')
    if not isinstance(intervals,list) or not intervals:
        raise ValueError('EXPORT_SOURCE_RANGES_MISSING')
    ranges=[]
    for pair in intervals:
        if not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(x,(int,float)) for x in pair):
            raise ValueError('INVALID_TIME_RANGE')
        a,b=map(float,pair)
        if a<0 or b<=a:raise ValueError('INVALID_TIME_RANGE')
        ranges.append([a/1000,b/1000]) # Opus sample timeRanges in milliseconds
    url=row.get('uriForExport')
    if not url or not isinstance(url,str):raise ValueError('MISSING_EXPORT_URL')
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or not (parsed.hostname=='opus.pro' or parsed.hostname.endswith('.opus.pro')):
        raise ValueError('UNTRUSTED_EXPORT_DOMAIN')
    return {'id':row['id'],'project_id':row['projectId'],'ranges_sec':ranges,'export_url':url,
            'duration_provider_sec':row.get('durationMs',0)/1000 if isinstance(row.get('durationMs'),(int,float)) else None}


def match_group(clip:dict,opus_jobs:dict,min_overlap=.75):
    """Resolve exact project from a persisted submission ledger, then overlap source time ranges.

    Ambiguous grouped jobs are NOT assigned a candidate automatically.
    """
    entries=opus_jobs.get('jobs',[])
    matching=[g for g in entries if g.get('project_id')==clip['project_id']]
    if len(matching)!=1:
        return {'status':'HOLD','reason':'UNMAPPED_PROJECT_ID'}
    entry=matching[0];a,b=entry['source_window']
    duration=sum(y-x for x,y in clip['ranges_sec'])
    aligned=sum(windows_overlap((x,y),(a,b)) for x,y in clip['ranges_sec'])
    if not duration or aligned/duration<min_overlap:
        return {'status':'HOLD','reason':'TIME_RANGES_OUTSIDE_GPT_WINDOW'}
    return {'status':'SOURCE_GROUP_VERIFIED','group_id':entry.get('group_id'),
            'candidate_ids':entry['candidate_ids'],'source_ranges_sec':clip['ranges_sec'],
            'overlap_ratio':round(aligned/duration,4), 'provider_project_id':clip['project_id'],
            'requires_per_candidate_review':len(entry['candidate_ids'])>1}


def get_clips(project_id:str,*,execute=False,org_id=None):
    if not execute:return {'status':'DRY_RUN','method':'GET','url':BASE,
                            'query':{'q':'findByProjectId','projectId':project_id}}
    token=os.getenv('OPUSCLIP_API_KEY')
    if not token:raise ValueError('Missing OPUSCLIP_API_KEY')
    url=BASE+'?'+urllib.parse.urlencode({'q':'findByProjectId','projectId':project_id})
    headers={'Authorization':'Bearer '+token,'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    if org_id:headers['x-opus-org-id']=org_id
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=45) as resp:data=json.loads(resp.read())
    raw_list = data if isinstance(data,list) else data.get('data',[]) if isinstance(data,dict) else None
    if raw_list is None:raise ValueError('UNEXPECTED_GET_CLIPS_SCHEMA: inspect provider response')
    return [normalize_clip(x) for x in raw_list]


def _ensure_public_host(url):
    """Block obvious SSRF/redirect abuse; explicit trusted opus.pro HTTPS only."""
    parts=urllib.parse.urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or not (parts.hostname=='opus.pro' or parts.hostname.endswith('.opus.pro')):
        raise ValueError('Untrusted Opus export URL')
    # No accepting redirected destinations, see redirect policy below.
    return url

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('REDIRECT_BLOCKED_FOR_EXPORT_SECURITY')


def download(clip_meta:dict,out:Path,*,execute=False,max_bytes:int=500_000_000):
    url=_ensure_public_host(clip_meta['export_url'])
    if not execute:return {'status':'DRY_RUN','destination':str(out),'url_host':urllib.parse.urlsplit(url).hostname}
    if out.exists():raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_name(out.name+'.partial')
    tmp.unlink(missing_ok=True)
    opener=urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}),timeout=90) as resp, tmp.open('wb') as file:
            total=0
            while chunk:=resp.read(1<<20):
                total+=len(chunk)
                if total>max_bytes:raise ValueError('EXPORT_TOO_LARGE')
                file.write(chunk)
        if total<1024:raise ValueError('EMPTY_EXPORT')
        tmp.replace(out)
        return {'status':'DOWNLOADED','bytes':total,'file':str(out),'sha256':sha256(out)}
    finally:tmp.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('get-clips');a.add_argument('--project-id',required=True);a.add_argument('--org-id');a.add_argument('--execute',action='store_true');a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('normalize');a.add_argument('--response-json',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('download');a.add_argument('--clip-json',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--execute',action='store_true')
    a=sub.add_parser('ledger');a.add_argument('--jobs',type=Path,required=True);a.add_argument('--submissions',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('match');a.add_argument('--clip-json',type=Path,required=True);a.add_argument('--ledger',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    x=p.parse_args()
    if x.cmd=='get-clips':value=get_clips(x.project_id,execute=x.execute,org_id=x.org_id)
    elif x.cmd=='normalize':
        payload=json.loads(x.response_json.read_text(encoding='utf8'))
        value=[normalize_clip(row) for row in payload]
    elif x.cmd=='ledger':value=ledger_from_submissions(json.loads(x.jobs.read_text()),json.loads(x.submissions.read_text()))
    elif x.cmd=='match':value=match_group(json.loads(x.clip_json.read_text()),json.loads(x.ledger.read_text()))
    else:value=download(json.loads(x.clip_json.read_text(encoding='utf8')),x.output,execute=x.execute)
    if x.cmd!='download':x.output.parent.mkdir(parents=True,exist_ok=True);x.output.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'status':'READY','result':value if isinstance(value,dict) else {'clips':len(value)}},ensure_ascii=False,indent=2))


def ledger_from_submissions(jobs_data:dict,results_data:dict)->dict:
    """Link provider project IDs to saved GPT groups; reject unknown response shapes."""
    groups={row.get('group_id'):row for row in jobs_data.get('jobs',[])}
    ledger=[]
    for item in results_data.get('results',[]):
        group=groups.get(item.get('group_id'))
        if group is None or item.get('status') not in ('SUBMITTED','SUCCESS'):
            continue
        result=item.get('result',item.get('provider_response',{}))
        payload=result.get('data',result) if isinstance(result,dict) else {}
        pid=payload.get('projectId') or payload.get('project_id') or payload.get('id')
        if not isinstance(pid,str) or not pid:
            ledger.append({'group_id':item.get('group_id'),'status':'HOLD_MISSING_PROJECT_ID'})
            continue
        ledger.append({'project_id':pid,'group_id':item.get('group_id'),
                       'candidate_ids':group['candidate_ids'],
                       'source_window':group['source_window']})
    return {'schema_version':'opus-expert-ledger-v1','jobs':ledger}

if __name__=='__main__':main()
