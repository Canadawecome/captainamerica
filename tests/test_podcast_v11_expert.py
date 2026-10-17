import json
import pytest
from podcast_director import validate_precut, opus_jobs
from podcast_semantic_recut_v11 import boundary_plan
from podcast_opus_submit import submit
from opus_audio_qc import audio_report
from test_podcast_v1 import fixture


def test_podcast_rejects_weak_nonliteral_hook(fixture):
    root,source,tx,plan,_=fixture
    old=json.loads(plan.read_text())
    try:
        old['candidates'][0]['hook_quote']='The facts are surprisingly different'
        plan.write_text(json.dumps(old))
        with pytest.raises(ValueError,match='HOOK_NOT_EVIDENCED'):
            validate_precut(source,tx,plan)
    finally:
        original=old;original['candidates'][0]['hook_quote']='This matters deeply today.'
        plan.write_text(json.dumps(original))


def test_podcast_opus_expert_job_has_correct_render_pref(fixture):
    _,source,tx,plan,_=fixture
    res=opus_jobs(source,tx,plan,'https://example.com/podcast')
    assert res['schema_version']=='podcast-v1.1'
    r=res['jobs'][0]['request']
    assert r['renderPref']['enableCaption'] is False
    assert r['renderPref']['enableSplitLayout'] is True
    assert r['curationPref']['clipDurations']==[[70,90]]
    assert res['credit_note']


def test_semantic_recut_requires_editor_gpt_approval(fixture):
    _,source,tx,plan,folder=fixture
    from podcast_director import review
    review(folder,source,tx,plan)
    rp=folder/'post_review.json'
    old=rp.read_text()
    try:
        obj=json.loads(old);obj['recut_instruction']='Restore guest completion of the thought'
        rp.write_text(json.dumps(obj))
        from podcast_semantic_recut_v11 import boundary_plan
        data=boundary_plan(folder)
        assert data['status']=='NEEDS_EDITOR_OR_GPT_SOURCE_BOUNDARY_APPROVAL'
        assert data['source_end_sec']-data['source_start_sec']>65
    finally:
        rp.write_text(old)
        review(folder,source,tx,plan)


def test_audio_diagnostics_do_not_certify_spoken_content(fixture):
    _,_,_,_,folder=fixture
    r=audio_report(folder/'clip.mp4')
    assert r['has_audio'] and r['requires_human_listening_for_speech_accuracy']
    assert r['channels']>=1


def test_cost_limit_enforced_before_network(tmp_path):
    j=tmp_path/'jobs.json'
    j.write_text(json.dumps({'schema_version':'podcast-v1.1','jobs':[{'candidate_id':str(i)} for i in range(9)]}))
    with pytest.raises(ValueError,match='BUDGET'):
        submit(j,tmp_path/'out.json',execute=True,max_projects=8)
