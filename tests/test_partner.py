"""Synthetic vertical tests of controller-bound Herdr partner lifecycle."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(sys.argv.pop()).resolve() if len(sys.argv) > 1 and Path(sys.argv[-1]).is_dir() else Path(__file__).resolve().parents[1] / 'skills/crew/scripts'
sys.path.insert(0, str(SCRIPTS))
import partner


class PartnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crew-controller-', dir='/var/tmp')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.cwd = self.base / 'workspace'
        self.cwd.mkdir()
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith('HERDR_') or key in ('CODEX_THREAD_ID', 'CREW_DIALOG_RECEIPT_SHA256'):
                self.env.pop(key)
        self.env.update(CREW_STATE_DIR=str(self.base/'state'), CREW_CONTROLLER_ID='lead-session',
                        HERDR_STUB_FIXTURE=str(self.base/'fixture.json'),
                        HERDR_STUB_CALL_LOG=str(self.base/'calls.jsonl'),
                        HERDR_STUB_STATE=str(self.base/'stub-state.json'),
                        PATH=str(Path(__file__).parent/'bin')+os.pathsep+self.env['PATH'])
        context = json.loads(subprocess.check_output([str(SCRIPTS/'state-root.sh')], cwd=self.cwd, env=self.env))
        self.root = Path(context['state_root'])
        self.root.mkdir(parents=True)
        self.name = context['partner_name']
        self.path = self.root/'worker.json'
        self.pointer = self.root/'.current'
        self.pointer.write_text('run-1\n')
        (self.cwd/'.crew/run-1').mkdir(parents=True)
        self.receipt = dict(version=2, controller_id='lead-session', lead_kind='codex', session='work',
                            worker_name=self.name, worker_kind='claude', worker_pane_id='w1:p2')
        self.live = dict(name=self.name, agent='claude', pane_id='w1:p2')
        self.responses = []

    def add(self, args, *results, repeat=False):
        self.responses.append(dict(argv=['--session', 'work']+args, results=list(results), repeat_last=repeat))

    def run_helper(self, helper, args=()):
        (self.base/'fixture.json').write_text(json.dumps({'responses':self.responses}))
        return subprocess.run([str(SCRIPTS/helper), *args], cwd=self.cwd, env=self.env,
                              text=True, capture_output=True, timeout=15)

    def start(self, *extra):
        return self.run_helper('worker-start.sh', ['--controller','lead-session','--lead-kind','codex',
                        '--session','work',*extra,'claude'])

    def store(self, receipt=None):
        self.path.write_text(json.dumps(receipt or self.receipt)+'\n')

    def calls(self):
        path=self.base/'calls.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def refused_unchanged(self, result, before):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.path.read_bytes(), before)

    def launch(self, fail_marker=False, workspace=False, kind="claude"):
        self.add(['agent','get',self.name], {'error':'agent_not_found'}, {'agent':self.live}, repeat=True)
        create=['tab','create','--workspace','w1'] if workspace else ['workspace','create']
        self.add(create+['--cwd',str(self.cwd),'--label',self.name,'--no-focus'],
                 {'stdout_json':{'result':{'root_pane':{'pane_id':'w1:p2'}}}})
        self.add(['pane','wait-output','w1:p2','--regex','[#$%>❯] ?$','--source','detection','--lines','5','--timeout','60000'], {'stdout_json':{'result':{}}})
        edit='//'+str(self.root).lstrip('/')
        settings={'permissions':{'deny':[f'Edit({edit})',f'Edit({edit}/**)']},
                  'sandbox':{'enabled':True,'failIfUnavailable':True,'allowUnsandboxedCommands':False,
                             'filesystem':{'disabled':False,'denyWrite':[str(self.root)]}}}
        profile = ['--permission-mode','auto','--settings',json.dumps(settings,sort_keys=True,separators=(',',':'))]
        marker = 'Try "'
        if kind == 'codex':
            profile = ['--sandbox','workspace-write','--ask-for-approval','on-request',
                       '-c','approvals_reviewer="user"','-c','sandbox_workspace_write.writable_roots=[]']
            marker = 'Ask Codex'
        self.add(['agent','start',self.name,'--kind',kind,'--pane','w1:p2','--timeout','60000','--',*profile],
                 {'stdout_json':{'result':{}}})
        self.add(['pane','wait-output','w1:p2','--regex',marker,'--source','visible','--timeout','60000'],
                 {'error':'timeout'} if fail_marker else {'stdout_json':{'result':{}}})

    def test_daemon_launch_has_no_lead_pane_or_environment_dependency(self):
        self.launch()
        self.success(self.start())
        self.assertEqual(json.loads(self.path.read_text()), self.receipt)
        self.assertTrue(all(call[:2]==['--session','work'] for call in self.calls()))
        self.assertFalse(any('layout' in call or 'split' in call for call in self.calls()))

    def test_claude_lead_launches_codex_with_native_profile(self):
        self.live['agent']='codex'
        self.launch(kind='codex')
        result=self.run_helper('worker-start.sh',['--controller','lead-session','--lead-kind','claude',
                                               '--session','work','codex'])
        self.success(result)
        receipt=json.loads(self.path.read_text())
        self.assertEqual((receipt['lead_kind'],receipt['worker_kind']),('claude','codex'))

    def test_completed_run_preserves_partner_for_next_assignment(self):
        self.launch(); self.success(self.start())
        receipt=self.path.read_bytes()
        run=self.cwd/'.crew/run-1'
        (run/'task.md').write_text('# Task\nSynthetic accepted assignment.\n')
        (run/'report-1.md').write_text('# Report\nSynthetic result.\n## Phase 3 self-review\nChecked.\nSTATUS: done\n')
        (run/'review-1.md').write_text('# Review\nVerdict: approve\n')
        self.success(self.run_helper('artifact-done.sh',[str(run/'report-1.md')]))
        self.success(self.run_helper('run-finish.sh',['run-1']))
        self.assertFalse(self.pointer.exists())
        self.assertEqual(self.path.read_bytes(),receipt)
        self.assertTrue((run/'report-1.md').exists())
        self.assertFalse(any('close' in call for call in self.calls()))

    def test_workspace_selection_controls_placement_only(self):
        self.launch(workspace=True)
        self.success(self.start('--workspace','w1'))

    def test_workspace_python_modules_cannot_run_inside_helpers(self):
        marker=self.root/'planted.txt'
        payload=f'open({str(marker)!r}, "w").write("executed")\nraise RuntimeError("workspace module imported")\n'
        for name in ('pathlib','hashlib','json','re'):
            (self.cwd/(name+'.py')).write_text(payload)
        self.success(self.run_helper('state-root.sh'))
        self.store()
        self.add(['agent','get',self.name], {'agent':self.live},repeat=True)
        self.success(self.start())
        self.add(['agent','prompt',self.name,'review'], {'stdout':'accepted\n'})
        self.success(self.run_helper('herdr.sh',['agent','prompt',self.name,'review']))
        self.success(self.run_helper('relay.sh',['--help']))
        report=self.cwd/'report.md'; report.write_text('STATUS: done\n')
        self.success(self.run_helper('artifact-done.sh',[str(report)]))
        self.assertFalse(marker.exists())

    def test_pythonpath_and_sitecustomize_cannot_override_helper_imports(self):
        marker=self.root/'planted.txt'
        for name in ('sitecustomize','hashlib'):
            (self.cwd/(name+'.py')).write_text(f'open({str(marker)!r}, "w").write("executed")\n')
        self.env['PYTHONPATH']=str(self.cwd)
        self.success(self.run_helper('state-root.sh'))
        self.assertFalse(marker.exists())

    def test_missing_active_pointer_returns_documented_run_error(self):
        self.pointer.unlink()
        self.assertEqual(self.start().returncode,3)
        self.assertEqual(self.calls(),[])

    def test_retirement_owner_refusal_returns_documented_binding_error(self):
        self.store(self.receipt|{'controller_id':'old'})
        before=self.path.read_bytes()
        result=self.run_helper('worker-stop.sh',['--controller','lead-session','--lead-kind','codex','--session','work'])
        self.assertEqual(result.returncode,11)
        self.refused_unchanged(result,before)
        self.assertEqual(self.calls(),[])

    def test_same_controller_reuses_without_launch_or_rewrite(self):
        self.store(); before=self.path.read_bytes()
        self.add(['agent','get',self.name], {'agent':self.live})
        self.success(self.start())
        self.assertEqual(json.loads(self.path.read_text()),json.loads(before))
        self.assertEqual(len(self.calls()),1)
        self.assertEqual(list(self.root.glob('worker-*.json')), [])

    def test_new_controller_cannot_infer_ownership_from_absent_pane(self):
        self.store(self.receipt|{'controller_id':'old-session'}); before=self.path.read_bytes()
        self.refused_unchanged(self.start(),before)
        self.assertEqual(self.calls(),[])

    def test_session_collision_refused_before_contact(self):
        self.store(self.receipt|{'session':'other'}); before=self.path.read_bytes()
        self.refused_unchanged(self.start(),before)
        self.assertEqual(self.calls(),[])

    def test_live_worker_identity_mismatch(self):
        self.store(); before=self.path.read_bytes()
        self.add(['agent','get',self.name], {'agent':self.live|{'pane_id':'w9:p9'}})
        self.refused_unchanged(self.start(),before)

    def test_same_kind_refused_without_transport(self):
        result=self.run_helper('worker-start.sh',['--controller','lead','--lead-kind','claude','--session','work','claude'])
        self.assertEqual(result.returncode,12)
        self.assertEqual(self.calls(),[])

    def test_unowned_live_partner_is_not_adopted(self):
        self.add(['agent','get',self.name], {'agent':self.live})
        self.assertNotEqual(self.start().returncode,0)
        self.assertFalse(self.path.exists())

    def test_create_refuses_retained_live_worker(self):
        self.store(); self.add(['agent','get',self.name], {'agent':self.live})
        self.assertEqual(self.start('--create').returncode,13)

    def test_legacy_handoff_is_explicit_and_preserves_exact_bytes(self):
        legacy={k:v for k,v in self.receipt.items() if k not in ('controller_id','lead_kind','session')}
        legacy.update(version=1,lead_pane_id='w1:p1')
        self.store(legacy); before=self.path.read_bytes()
        self.refused_unchanged(self.start(),before)
        self.add(['agent','get',self.name], {'agent':self.live})
        self.success(self.start('--handoff-from','pane:w1:p1'))
        self.assertEqual(json.loads(self.path.read_text()),self.receipt)
        archives=list(self.root.glob('worker-*.json'))
        self.assertEqual(len(archives),1)
        self.assertEqual(archives[0].read_bytes(),before)
        self.assertEqual(self.pointer.read_text(),'run-1\n')

    def test_handoff_recovers_absent_worker_and_pane_preserving_history(self):
        self.store(self.receipt|{'controller_id':'old'}); before=self.path.read_bytes()
        self.launch()
        self.add(['pane','get','w1:p2'], {'error':'pane_not_found'})
        self.success(self.start('--handoff-from','old'))
        self.assertEqual(json.loads(self.path.read_text()),self.receipt)
        self.assertEqual([p.read_bytes() for p in self.root.glob('worker-*.json')],[before])
        self.assertEqual(self.pointer.read_text(),'run-1\n')
        self.assertFalse(any('close' in call for call in self.calls()))

    def test_handoff_refuses_absent_worker_with_existing_pane(self):
        self.store(self.receipt|{'controller_id':'old'}); before=self.path.read_bytes()
        self.add(['agent','get',self.name], {'error':'agent_not_found'})
        self.add(['pane','get','w1:p2'], {'pane':{'pane_id':'w1:p2'}})
        self.refused_unchanged(self.start('--handoff-from','old'),before)
        self.assertEqual(len(self.calls()),2)

    def test_handoff_refuses_unavailable_pane_query(self):
        self.store(self.receipt|{'controller_id':'old'}); before=self.path.read_bytes()
        self.add(['agent','get',self.name], {'error':'agent_not_found'})
        self.add(['pane','get','w1:p2'], {'error':'timeout'})
        self.refused_unchanged(self.start('--handoff-from','old'),before)
        self.assertEqual(len(self.calls()),2)

    def test_handoff_refuses_unavailable_agent_query(self):
        self.store(self.receipt|{'controller_id':'old'}); before=self.path.read_bytes()
        self.add(['agent','get',self.name], {'error':'timeout'})
        self.refused_unchanged(self.start('--handoff-from','old'),before)
        self.assertEqual(len(self.calls()),1)

    def test_failed_recovery_preserves_previous_owner(self):
        self.store(self.receipt|{'controller_id':'old'}); before=self.path.read_bytes()
        self.launch(fail_marker=True)
        self.add(['pane','get','w1:p2'], {'error':'pane_not_found'})
        self.add(['pane','close','w1:p2'], {'stdout_json':{'result':{}}})
        self.refused_unchanged(self.start('--handoff-from','old'),before)
        self.assertEqual(self.calls()[-1],['--session','work','pane','close','w1:p2'])

    def test_interrupted_history_write_can_retry_without_partial_archive(self):
        self.store(); before=self.path.read_bytes()
        replacement=self.receipt|{'controller_id':'next'}
        with patch.object(partner.os,'fsync',side_effect=OSError('injected write failure')):
            with self.assertRaises(OSError):
                partner.save(self.path,self.receipt,replacement)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(list(self.root.glob('worker-*.json')),[])
        partner.save(self.path,self.receipt,replacement)
        self.assertEqual(json.loads(self.path.read_text()),replacement)
        self.assertEqual([p.read_bytes() for p in self.root.glob('worker-*.json')],[before])

    def test_history_publication_survives_failed_receipt_replace_and_retry(self):
        self.store(); before=self.path.read_bytes()
        replacement=self.receipt|{'controller_id':'next'}
        with patch.object(partner.os,'replace',side_effect=OSError('injected replace failure')):
            with self.assertRaises(OSError):
                partner.save(self.path,self.receipt,replacement)
        self.assertEqual(self.path.read_bytes(),before)
        partner.save(self.path,self.receipt,replacement)
        self.assertEqual(json.loads(self.path.read_text()),replacement)
        self.assertEqual([p.read_bytes() for p in self.root.glob('worker-*.json')],[before])

    def test_conflicting_history_is_preserved_and_refused(self):
        self.store(); before=self.path.read_bytes()
        archive=self.root/('worker-'+hashlib.sha256(before).hexdigest()+'.json')
        archive.write_bytes(b'conflict')
        with self.assertRaisesRegex(partner.Refused,'conflicting partner history'):
            partner.save(self.path,self.receipt,self.receipt|{'controller_id':'next'})
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(archive.read_bytes(),b'conflict')

    def test_v2_handoff_requires_exact_old_owner(self):
        self.store(self.receipt|{'controller_id':'old'}); before=self.path.read_bytes()
        self.refused_unchanged(self.start('--handoff-from','different'),before)
        self.assertEqual(self.calls(),[])

    def test_failed_launch_closes_only_newly_created_pane(self):
        self.launch(fail_marker=True)
        self.add(['pane','close','w1:p2'], {'stdout_json':{'result':{}}})
        self.assertNotEqual(self.start().returncode,0)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.calls()[-1],['--session','work','pane','close','w1:p2'])

    def test_changed_receipt_during_start_does_not_overwrite_other_owner(self):
        self.launch()
        other=self.receipt|{'controller_id':'other'}
        self.responses[-1]['results'][0]['effects']=[{'action':'write','path':str(self.path),'content_json':other}]
        self.add(['pane','close','w1:p2'], {'stdout_json':{'result':{}}})
        self.assertNotEqual(self.start().returncode,0)
        self.assertEqual(json.loads(self.path.read_text()),other)

    def test_symlinked_receipt_is_never_followed(self):
        target=self.base/'other.json'; target.write_text(json.dumps(self.receipt))
        self.path.symlink_to(target); before=target.read_bytes()
        self.assertNotEqual(self.start().returncode,0)
        self.assertEqual(target.read_bytes(),before)
        self.assertEqual(self.calls(),[])

    def test_retirement_verifies_identity_twice(self):
        self.store()
        self.add(['agent','get',self.name], {'agent':self.live}, {'agent':self.live})
        self.add(['pane','close','w1:p2'], {'stdout_json':{'result':{}}})
        self.success(self.run_helper('worker-stop.sh',['--controller','lead-session','--lead-kind','codex','--session','work']))
        self.assertFalse(self.path.exists())
        self.assertTrue(self.pointer.exists())

    def test_retirement_refuses_worker_replaced_before_close(self):
        self.store();before=self.path.read_bytes()
        self.add(['agent','get',self.name], {'agent':self.live}, {'agent':self.live|{'pane_id':'w2:p3'}})
        result=self.run_helper('worker-stop.sh',['--controller','lead-session','--lead-kind','codex','--session','work'])
        self.refused_unchanged(result,before)
        self.assertFalse(any('close' in call for call in self.calls()))

    def test_bound_prompt_routes_and_preserves_arguments(self):
        self.store()
        self.add(['agent','get',self.name], {'agent':self.live})
        args=['agent','prompt',self.name,'Synthetic assignment']
        self.add(args, {'stdout':'accepted\n'})
        result=self.run_helper('herdr.sh',args)
        self.success(result); self.assertIn('accepted',result.stdout)

    def test_bound_prompt_rejects_other_controller(self):
        self.store(); self.env['CREW_CONTROLLER_ID']='other'
        self.assertEqual(self.run_helper('herdr.sh',['agent','prompt',self.name,'x']).returncode,11)
        self.assertEqual(self.calls(),[])

    def test_forwarded_prompt_with_changed_receipt_is_delivery_uncertain(self):
        self.store()
        self.add(['agent','get',self.name], {'agent':self.live})
        args=['agent','prompt',self.name,'review']
        self.add(args, {'stdout':'accepted\n','effects':[
            {'action':'write','path':str(self.path),'content_json':self.receipt|{'worker_pane_id':'w1:p3'}}]})
        result=self.run_helper('herdr.sh',args)
        self.assertEqual(result.returncode,15,result.stdout+result.stderr)
        self.assertIn('delivery-uncertain',result.stderr)
        self.assertIn('accepted',result.stdout)
        self.assertEqual(sum('prompt' in call for call in self.calls()),1)

    def test_forwarded_prompt_timeout_is_delivery_uncertain(self):
        self.store()
        self.add(['agent','get',self.name], {'agent':self.live})
        args=['agent','prompt',self.name,'review','--wait','--timeout','1000']
        self.add(args, {'error':'timeout'})
        result=self.run_helper('herdr.sh',args)
        self.assertEqual(result.returncode,15,result.stdout+result.stderr)
        self.assertIn('delivery-uncertain',result.stderr)
        self.assertEqual(sum('prompt' in call for call in self.calls()),1)

    def test_forwarded_keys_with_changed_receipt_are_delivery_uncertain(self):
        self.store()
        blocked=self.live|{'agent_status':'blocked','state_change_seq':10}
        self.add(['agent','get',self.name], *[{'agent':blocked} for _ in range(6)])
        self.add(['agent','read',self.name,'--source','visible','--lines','120','--format','text'],
                 {'stdout':'Would you like to continue?\n1. Yes\n2. No\n'})
        self.add(['agent','send-keys',self.name,'1'], {'stdout':'accepted\n','effects':[
            {'action':'write','path':str(self.path),'content_json':self.receipt|{'worker_pane_id':'w1:p3'}}]})
        result=self.run_helper('answer-dialog.sh',[self.name,'1'])
        self.assertEqual(result.returncode,6,result.stdout+result.stderr)
        self.assertIn('outcome=delivery-uncertain',result.stdout)
        self.assertNotIn('outcome=send-failed',result.stdout)
        self.assertEqual(sum('send-keys' in call for call in self.calls()),1)

    def test_keys_refused_before_forwarding_report_no_delivery(self):
        self.store()
        blocked=self.live|{'agent_status':'blocked','state_change_seq':10}
        self.add(['agent','get',self.name], *[{'agent':blocked} for _ in range(5)],
                 {'agent':blocked|{'pane_id':'w1:p3'}})
        self.add(['agent','read',self.name,'--source','visible','--lines','120','--format','text'],
                 {'stdout':'Would you like to continue?\n1. Yes\n2. No\n'})
        result=self.run_helper('answer-dialog.sh',[self.name,'1'])
        self.assertEqual(result.returncode,5,result.stdout+result.stderr)
        self.assertFalse(any('send-keys' in call for call in self.calls()))

    def test_dialog_send_uses_verified_session_and_one_shot_keys(self):
        self.store()
        blocked=self.live|{'agent_status':'blocked','state_change_seq':10}
        idle=self.live|{'agent_status':'idle','state_change_seq':11}
        self.add(['agent','get',self.name], *[{'agent':blocked} for _ in range(6)],
                 {'agent':idle}, {'agent':idle})
        self.add(['agent','read',self.name,'--source','visible','--lines','120','--format','text'],
                 {'stdout':'Would you like to run the following command?\n\n$ echo one\n\n› 1. Yes\n  2. No\n'})
        self.add(['agent','send-keys',self.name,'1'], {'stdout':'accepted\n'})
        self.success(self.run_helper('answer-dialog.sh',[self.name,'1']))
        self.assertEqual(sum('send-keys' in call for call in self.calls()),1)
        self.assertTrue(all(call[:2]==['--session','work'] for call in self.calls()))

    def test_missing_receipt_never_falls_back_to_ambient_dialog_target(self):
        result=self.run_helper('answer-dialog.sh',[self.name,'1'])
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.calls(),[])

    def test_typed_dialog_does_not_send_to_replacement_after_final_guard(self):
        self.store()
        blocked=self.live|{'agent_status':'blocked','state_change_seq':10}
        replacement=blocked|{'pane_id':'w1:p3','state_change_seq':20}
        advanced=replacement|{'agent_status':'working','state_change_seq':21}
        effect={'action':'write','path':str(self.path),
                'content_json':self.receipt|{'worker_pane_id':'w1:p3'}}
        self.add(['agent','get',self.name], *[{'agent':blocked} for _ in range(5)],
                 {'agent':blocked,'effects':[effect]}, {'agent':replacement},
                 {'agent':advanced}, {'agent':advanced})
        frame='Would you like to run the following command?\n\n$ echo one\n\n› 1. Yes\n  2. No\n'
        for lines in ('120','200'):
            self.add(['agent','read',self.name,'--source','visible','--lines',lines,'--format','text'],
                     {'stdout':frame})
        self.add(['agent','send-keys',self.name,'1'], {'stdout':'accepted\n'})
        token=base64.b64encode(json.dumps({'kind':'command','key':'echo one'}).encode()).decode()
        result=self.run_helper('answer-dialog.sh',['--expected-command-b64',token,self.name,'1'])
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('partner receipt changed',result.stderr)
        self.assertFalse(any('send-keys' in call for call in self.calls()))

    def test_typed_dialog_sends_once_when_binding_is_unchanged(self):
        self.store()
        marker=self.root/'planted.txt'
        (self.cwd/'json.py').write_text(f'open({str(marker)!r}, "w").write("executed")\n')
        blocked=self.live|{'agent_status':'blocked','state_change_seq':10}
        advanced=blocked|{'agent_status':'working','state_change_seq':11}
        self.add(['agent','get',self.name], *[{'agent':blocked} for _ in range(7)],
                 {'agent':advanced}, {'agent':advanced})
        frame='Would you like to run the following command?\n\n$ echo one\n\n› 1. Yes\n  2. No\n'
        for lines in ('120','200'):
            self.add(['agent','read',self.name,'--source','visible','--lines',lines,'--format','text'],
                     {'stdout':frame})
        self.add(['agent','send-keys',self.name,'1'], {'stdout':'accepted\n'})
        token=base64.b64encode(json.dumps({'kind':'command','key':'echo one'}).encode()).decode()
        result=self.run_helper('answer-dialog.sh',['--expected-command-b64',token,self.name,'1'])
        self.success(result)
        self.assertIn('outcome=expected-match',result.stdout)
        self.assertEqual(sum('send-keys' in call for call in self.calls()),1)
        self.assertFalse(marker.exists())

    def test_approval_rejects_receipt_changed_during_extraction(self):
        self.store()
        blocked=self.live|{'agent_status':'blocked','state_change_seq':10}
        self.add(['agent','get',self.name], {'agent':blocked})
        self.add(['agent','read',self.name,'--source','visible','--lines','200','--format','text'],
                 {'stdout':'Would you like to run the following command?\n\n$ echo one\n\n› 1. Yes\n  2. No\n',
                  'effects':[{'action':'write','path':str(self.path),
                              'content_json':self.receipt|{'worker_pane_id':'w1:p3'}}]})
        token=base64.b64encode(json.dumps({'kind':'command','key':'echo one'}).encode()).decode()
        result=self.run_helper('approval.sh',['check',self.name,'--expect-b64',token])
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('partner receipt changed',result.stderr)
        self.assertNotIn('outcome=expected-match',result.stdout)

    def test_dialog_does_not_accept_replacement_sequence_as_delivery_evidence(self):
        self.store()
        blocked=self.live|{'agent_status':'blocked','state_change_seq':10}
        replacement=blocked|{'pane_id':'w1:p3','agent_status':'working','state_change_seq':21}
        self.add(['agent','get',self.name], *[{'agent':blocked} for _ in range(7)],
                 {'agent':replacement,'effects':[{'action':'write','path':str(self.path),
                     'content_json':self.receipt|{'worker_pane_id':'w1:p3'}}]})
        self.add(['agent','read',self.name,'--source','visible','--lines','120','--format','text'],
                 {'stdout':'Would you like to continue?\n1. Yes\n2. No\n'})
        self.add(['agent','send-keys',self.name,'1'], {'stdout':'accepted\n'})
        result=self.run_helper('answer-dialog.sh',[self.name,'1'])
        self.assertEqual(result.returncode,6,result.stdout+result.stderr)
        self.assertNotIn('outcome=advanced',result.stdout)
        self.assertEqual(sum('send-keys' in call for call in self.calls()),1)

    def test_dialog_does_not_follow_receipt_changed_during_visible_read(self):
        self.store()
        blocked=self.live|{'agent_status':'blocked','state_change_seq':10}
        replacement=blocked|{'pane_id':'w1:p3'}
        advanced=replacement|{'agent_status':'working','state_change_seq':11}
        self.add(['agent','get',self.name], *[{'agent':blocked} for _ in range(3)],
                 *[{'agent':replacement} for _ in range(3)],
                 {'agent':advanced}, {'agent':advanced})
        self.add(['agent','read',self.name,'--source','visible','--lines','120','--format','text'],
                 {'stdout':'Would you like to continue?\n1. Yes\n2. No\n','effects':[
                     {'action':'write','path':str(self.path),
                      'content_json':self.receipt|{'worker_pane_id':'w1:p3'}}]})
        self.add(['agent','send-keys',self.name,'1'], {'stdout':'accepted\n'})
        result=self.run_helper('answer-dialog.sh',[self.name,'1'])
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('partner receipt changed',result.stderr)
        self.assertFalse(any('send-keys' in call for call in self.calls()))

    def test_bound_prompt_refuses_receipt_changed_during_identity_check(self):
        self.store()
        other=self.receipt|{'controller_id':'other'}
        self.add(['agent','get',self.name], {'agent':self.live,'effects':[
            {'action':'write','path':str(self.path),'content_json':other}]})
        self.assertNotEqual(self.run_helper('herdr.sh',['agent','prompt',self.name,'x']).returncode,0)
        self.assertFalse(any('prompt' in call for call in self.calls()))

    def test_concurrent_partner_operation_refused(self):
        import fcntl
        with (self.root/'partner.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.start().returncode,11)
        self.assertEqual(self.calls(),[])

    def test_failed_restart_does_not_close_reused_pane(self):
        self.store(); before=self.path.read_bytes()
        self.add(['agent','get',self.name], {'error':'agent_not_found'})
        self.add(['pane','get','w1:p2'], {'pane':{'pane_id':'w1:p2'}})
        self.add(['pane','wait-output','w1:p2','--regex','[#$%>❯] ?$','--source','detection',
                  '--lines','5','--timeout','60000'], {'error':'timeout'})
        self.refused_unchanged(self.start(),before)
        self.assertFalse(any('close' in call for call in self.calls()))

    def test_status_reads_bound_session_without_controller_authority(self):
        self.store();self.pointer.unlink();self.env.pop('CREW_CONTROLLER_ID')
        self.add(['agent','get',self.name], {'agent':self.live|{'agent_status':'idle'}})
        result=self.run_helper('status.sh',['--json'])
        self.success(result)
        result=json.loads(result.stdout)
        self.assertEqual(result['partner']['session'],'work')
        self.assertEqual(result['partner']['controller_id'],'lead-session')


if __name__=='__main__':
    unittest.main()
