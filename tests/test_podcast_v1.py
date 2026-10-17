import json,subprocess
from pathlib import Path
import pytest
from podcast_media import digest,probe,evidence
from podcast_transcript import from_words
from podcast_director import opus_jobs,review,require_approved
from podcast_render import render,cues


def make_video(file,seconds):
    file.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',
        '-f','lavfi','-i','color=c=navy:size=144x256:rate=2',
        '-f','lavfi','-i','sine=frequency=320:sample_rate=16000',
        '-t',str(seconds),'-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','64k','-shortest',str(file)],check=True)


def tx(file):
    length=probe(file)['duration'];rows=[]
    n=int(length)-1
    for s in range(n):
        rows.append({'start':float(s)+.05,'end':float(s)+.23,'text':'This','speaker':'host'})
        rows.append({'start':float(s)+.24,'end':float(s)+.42,'text':'matters','speaker':'host'})
        rows.append({'start':float(s)+.43,'end':float(s)+.61,'text':'deeply','speaker':'host'})
        rows.append({'start':float(s)+.62,'end':float(s)+.82,'text':'today.','speaker':'host'})
    return from_words(file,rows)


@pytest.fixture(scope='module')
def fixture(tmp_path_factory):
    root=tmp_path_factory.mktemp('podcast')
    source=root/'source.mp4';make_video(source,112)
    source_tx=root/'source_transcript.json';source_tx.write_text(tx(source).model_dump_json(indent=2))
    plan=root/'precut_plan.json'
    plan.write_text(json.dumps({'source_sha256':digest(source),'transcript_sha256':digest(source_tx),
        'rights_verified':True,'candidates':[{'id':'C01','start':0,'end':90,
           'hook_quote':'This matters deeply today.', 'payoff_quote':'This matters deeply today.',
           'transcript_evidence':'This matters deeply today. This matters deeply today.',
           'why_compelling':'A concise interview insight that may be clipped',
           'predicted_potential_score':94,'confidence':.92}]}))
    folder=root/'clip_1';folder.mkdir()
    clip=folder/'clip.mp4';make_video(clip,68)
    ctrans=folder/'clip_transcript.json';ctrans.write_text(tx(clip).model_dump_json(indent=2))
    review_file=folder/'post_review.json'
    review_file.write_text(json.dumps({'candidate_id':'C01','clip_sha256':digest(clip),
        'transcript_sha256':digest(ctrans),
        'scores':{'hook':96,'meaning':94,'audio_emotion':92,'framing':91,'pacing':91,'caption_readiness':94},
        'complete_thought':True,'meaning_not_distorted':True,'begins_at_natural_boundary':True,
        'ends_at_natural_boundary':True,'clear_english_dialogue':True,'speaker_framing_ok':True,
        'rights_verified':True,'source_mapping_verified':True,
        'review_confidence':.96,'evidence_note':'Frame and word times match checked export'}))
    (folder/'source_mapping.json').write_text(json.dumps({'candidate_id':'C01','verified_by':'HUMAN_EDITOR',
        'reviewer_or_project_id':'editor-1','source_ranges_sec':[[0,68]],'evidence_note':'Range inspected'}))
    return root,source,source_tx,plan,folder


def test_opus_podcast_prompt_and_bounds(fixture):
    _,source,source_tx,plan,_=fixture
    result=opus_jobs(source,source_tx,plan,'https://example.org/podcast.mp4')
    req=result['jobs'][0]['request']
    assert req['curationPref']['range']=={'startSec':0.0,'endSec':90.0}
    assert req['curationPref']['clipDurations']==[[70,90]]
    assert 'podcast' in req['curationPref']['customPrompt']
    assert 'hammer' not in req['curationPref']['customPrompt'].lower()


def test_approval_and_native_audio(fixture):
    _,source,source_tx,plan,folder=fixture
    a=review(folder,source,source_tx,plan)
    assert a.status=='APPROVED' and a.score>=85
    assert require_approved(folder).status=='APPROVED'


def test_caption_groups_srt_and_render(fixture):
    _,source,source_tx,plan,folder=fixture
    if not (folder/'approval.json').exists():review(folder,source,source_tx,plan)
    report=render(folder,'preserve')
    assert report['original_dialogue_kept'] is True
    assert report['elevenlabs_used'] is False
    assert report['duration_sec']>65
    assert (folder/'captions_en.srt').is_file()
    assert (folder/'captions_en.ass').is_file()
    assert (folder/'final.mp4').is_file()
    assert probe(folder/'final.mp4')['has_audio']
    assert 'This matters' in (folder/'captions_en.srt').read_text()


def test_metadata_tamper_blocks_render(fixture):
    _,_,_,_,folder=fixture
    path=folder/'clip_transcript.json'
    old=path.read_text()
    try:
        path.write_text(old+' ')
        with pytest.raises(ValueError,match='STALE_PODCAST_APPROVAL'):require_approved(folder)
    finally:path.write_text(old)


def test_65_seconds_rejected(tmp_path,fixture):
    root,source,source_tx,plan,folder=fixture
    short=tmp_path/'clip_short';short.mkdir();make_video(short/'clip.mp4',65)
    (short/'clip_transcript.json').write_text(tx(short/'clip.mp4').model_dump_json())
    with pytest.raises(ValueError,match='DURATION_RECUT'):
        review(short,source,source_tx,plan)


def test_context_guard_even_for_high_score(fixture):
    _,source,source_tx,plan,folder=fixture
    p=folder/'post_review.json';old=p.read_text()
    try:
        x=json.loads(old);x['meaning_not_distorted']=False;p.write_text(json.dumps(x))
        a=review(folder,source,source_tx,plan)
        assert a.status=='RECUT' and 'MEANING_NOT_DISTORTED_FAILED' in a.blockers
    finally:
        p.write_text(old)
        review(folder,source,source_tx,plan)


def test_approve_requires_real_mapping(fixture):
    _,source,source_tx,plan,folder=fixture
    m=folder/'source_mapping.json';old=m.read_text()
    try:
        m.unlink()
        a=review(folder,source,source_tx,plan)
        assert a.status=='HOLD'
    finally:
        m.write_text(old)
        review(folder,source,source_tx,plan)


def test_no_english_dub_tts_modules_imported():
    from podcast_render import render as fn
    assert 'elevenlabs' not in fn.__code__.co_names


def test_cues_speaker_change():
    from podcast_contracts import Word
    ws=[Word(start=0,end=.4,text='Hello',speaker='host'),Word(start=.41,end=.8,text='there.',speaker='host'),
        Word(start=.82,end=1.1,text='Hi!',speaker='guest')]
    cs=cues(ws)
    assert len(cs)==2 and cs[-1]['speaker']=='guest'


def test_transcript_windows_cover_long_sources():
    from podcast_gpt import chunks
    from podcast_contracts import Word,Transcript
    dummy=Transcript(media_sha256='0'*64,words=[Word(start=i*2,end=i*2+.5,text='word.') for i in range(1800)])
    windows=chunks(dummy,3600)
    assert len(windows)>10
    assert any(a<=2800<=b for a,b,_ in windows)
    assert windows[-1][1]>=3600
    # Consecutive windows overlap by at least 100s.
    assert all(windows[i][1]-windows[i+1][0]>=100 for i in range(len(windows)-1))


def test_original_aac_bitstream_retained(fixture):
    _,_,_,_,folder=fixture
    from hashlib import sha256
    def audio_md5(file):
        r=subprocess.run(['ffmpeg','-v','error','-i',str(file),'-map','0:a:0','-c:a','copy','-f','md5','-'],check=True,text=True,capture_output=True)
        return r.stdout.strip()
    assert (folder/'final.mp4').exists()
    assert audio_md5(folder/'final.mp4')==audio_md5(folder/'clip.mp4')


def test_metadata_is_optional_and_uses_only_export_transcript(fixture,monkeypatch):
    from podcast_metadata import generate
    import podcast_metadata
    _,_,_,_,folder=fixture
    monkeypatch.setattr(podcast_metadata,'ask',lambda *args,**kwargs:{'title':'Why this matters',
        'description':'A guest explains why this matters.','hashtags':['#podcast','#interview','#ideas','#conversation']})
    r=generate(folder,'offline-test')
    assert r['status']=='DRAFT_NEEDS_EDITOR_REVIEW'
    assert '#podcast' in (folder/'hashtags.txt').read_text()
