"""Tests for shared expert modules. Copied into BOTH variant test directories."""
import json
import pytest
from opus_expert_core import phrase_present,bundle_candidates,make_opus_jobs,transcript_boundaries
from opus_export_manager import normalize_clip,match_group,ledger_from_submissions,download
from opus_transcript_manager import normalized
from opus_recut_engine import proposal,render


def test_false_one_word_hook_rejected():
    assert not phrase_present('The','The biggest surprise here is science')
    assert not phrase_present('This matters','This matters because the data tells another story')
    assert phrase_present('The data tells another story', 'Intro: the data tells another story and the guest explains why.')
    assert not phrase_present('The data tells another story','The data helps tell this interesting story.')

def test_group_nearby_candidates_but_not_distant():
    rows=[{'id':'a','start':20,'end':110,'score':95,'prompt':'talk about an unexpected insight'},
          {'id':'b','start':112,'end':205,'score':91,'prompt':'host responds to insight'},
          {'id':'c','start':1200,'end':1280,'score':88,'prompt':'totally different chapter'}]
    groups=bundle_candidates(rows,max_gap=15)
    assert len(groups)==2 and groups[0]['candidate_ids']==['a','b']
    jobs=make_opus_jobs(groups,'https://example.com/media','podcast')
    assert len(jobs['jobs'])==2
    assert jobs['jobs'][0]['request']['curationPref']['clipDurations']==[[70,100]]
    req=jobs['jobs'][0]['request']
    assert req['renderPref']['enableCaption'] is False
    assert req['renderPref']['enableEmoji'] is False
    assert req['renderPref']['quickstartConfig']['enableRemoveFillerWords'] is False
    assert 'portrait' not in req['curationPref']['customPrompt'].lower()
    assert 'caption' not in req['curationPref']['customPrompt'].lower()

def test_asmr_prompt_does_not_mention_dubbing_or_effects():
    rows=[{'id':'forge','start':0,'end':80,'prompt':'forging with bright sparks and repeated hammering','score':90}]
    j=make_opus_jobs(bundle_candidates(rows),'https://example.com/forge','asmr',90)['jobs'][0]
    assert j['request']['renderPref']['enableBroll'] is False
    assert 'elevenlabs' not in j['request']['curationPref']['customPrompt'].lower()

def test_get_clips_milliseconds_and_provenance_verification():
    c=normalize_clip({'id':'P1.C1','projectId':'P1','uriForExport':'https://ext.cdn.opus.pro/file.mp4',
                      'timeRanges':[[110000,181000]],'durationMs':71000})
    assert c['ranges_sec']==[[110,181]]
    assert match_group(c,{'jobs':[{'project_id':'P1','group_id':'g1','candidate_ids':['a','b'],
                     'source_window':[108,184]}]})['status']=='SOURCE_GROUP_VERIFIED'
    assert match_group(c,{'jobs':[{'project_id':'P2','group_id':'g2','candidate_ids':['x'],
                     'source_window':[108,184]}]})['status']=='HOLD'
    assert match_group(c,{'jobs':[{'project_id':'P1','group_id':'g1','candidate_ids':['x'],
                     'source_window':[1000,1100]}]})['status']=='HOLD'

def test_invalid_clip_url_and_range_fails_closed():
    with pytest.raises(ValueError,match='UNTRUSTED'):
        normalize_clip({'id':'P1.C1','projectId':'P1','uriForExport':'http://localhost/private.mp4',
            'timeRanges':[[0,70000]]})
    with pytest.raises(ValueError,match='INVALID_TIME_RANGE'):
        normalize_clip({'id':'P1.C1','projectId':'P1','uriForExport':'https://opus.pro/export.mp4',
            'timeRanges':[[5000,1000]]})

def test_transcript_requires_real_word_timestamps():
    data={'data':[[{'start':0,'end':3,'words':[{'start':.2,'end':.5,'word':'Really'},
           {'start':.5,'end':1.,'word':'interesting'}],'speaker':'SPEAKER_00'}]]}
    r=normalized(data)
    assert len(r['words'])==2
    assert r['timebase']=='OPUS_PROJECT_SOURCE_TIMELINE_NOT_EXPORTED_CLIP'
    with pytest.raises(ValueError):normalized({'data':[None]})
    with pytest.raises(ValueError):normalized({'data':[[{'words':[{'word':'oops'}]}]]})

def test_missing_punctuation_needs_audio_not_auto_reject():
    r=transcript_boundaries([{'start':.1,'end':69.97,'text':'complete'}],70)
    assert 'POSSIBLE_CUT_OFF_REVIEW_AUDIO' in r['risk']
    assert r['requires_semantic_review']

def test_recut_not_automatically_approved(tmp_path):
    p=proposal([20,90],'Podcast cut missed the last answer',attempt=1,source_total=200)
    assert p['status']=='NEEDS_EDITOR_OR_GPT_SOURCE_BOUNDARY_APPROVAL'
    with pytest.raises(ValueError,match='BOUNDARY_APPROVAL'):
        render(tmp_path/'src.mp4',p,tmp_path/'out.mp4')
    with pytest.raises(ValueError,match='LIMIT'):
        proposal([20,90],'reason',attempt=3)

def test_submission_ledger_stops_on_missing_project_id():
    jobs={'jobs':[{'group_id':'g1','candidate_ids':['c1'], 'source_window':[100,200]}]}
    ok=ledger_from_submissions(jobs,{'results':[{'group_id':'g1','status':'SUBMITTED',
        'result':{'data':{'projectId':'P1'}}}]})
    assert ok['jobs'][0]['project_id']=='P1'
    bad=ledger_from_submissions(jobs,{'results':[{'group_id':'g1','status':'SUBMITTED','result':{}}]})
    assert bad['jobs'][0]['status']=='HOLD_MISSING_PROJECT_ID'

def test_download_requires_execute_and_known_host(tmp_path):
    clip={'export_url':'https://ext.cdn.opus.pro/abc.mp4'}
    assert download(clip,tmp_path/'clip.mp4',execute=False)['status']=='DRY_RUN'
    with pytest.raises(ValueError,match='Untrusted'):
        download({'export_url':'https://example.org/clip.mp4'},tmp_path/'evil.mp4',execute=False)
