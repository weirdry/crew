"""Herdr CLI transport. No workflow decisions or inferred caller pane."""
import json
import subprocess


class TransportError(RuntimeError):
    pass


class Herdr:
    def __init__(self, session):
        self.prefix = ['herdr', '--session', session]

    def call(self, *args, absent=None):
        try:
            result = subprocess.run(self.prefix + list(args), capture_output=True,
                                    text=True, timeout=65)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise TransportError(f'Herdr request unavailable: {error}') from error
        if result.returncode:
            for text in (result.stdout, result.stderr):
                try:
                    payload = json.loads(text)
                    if absent and payload.get('error', {}).get('code') == absent:
                        return None
                except (ValueError, AttributeError):
                    pass
            raise TransportError(f'Herdr request failed: {args[0:2]}: {result.stderr.strip()}')
        try:
            payload = json.loads(result.stdout)
            return payload['result']
        except (ValueError, KeyError, TypeError) as error:
            raise TransportError('invalid Herdr response') from error

    def agent(self, name):
        result = self.call('agent', 'get', name, absent='agent_not_found')
        if result is None:
            return None
        agent = result.get('agent')
        if not isinstance(agent, dict) or any(not isinstance(agent.get(k), str) or not agent[k]
                                               for k in ('name', 'pane_id', 'agent')):
            raise TransportError('invalid Herdr agent identity')
        return agent

    def pane(self, pane):
        result = self.call('pane', 'get', pane, absent='pane_not_found')
        if result is not None and result.get('pane', {}).get('pane_id') != pane:
            raise TransportError('Herdr pane identity mismatch')
        return result

    def create(self, cwd, name, workspace):
        if workspace:
            result = self.call('tab', 'create', '--workspace', workspace,
                               '--cwd', cwd, '--label', name, '--no-focus')
        else:
            result = self.call('workspace', 'create', '--cwd', cwd, '--label', name, '--no-focus')
        pane = result.get('root_pane', {}).get('pane_id')
        if not isinstance(pane, str) or not pane:
            raise TransportError('creation response has no root pane; inspect Herdr before retrying')
        return pane

    def start(self, name, kind, pane, state_root):
        if kind == 'codex':
            profile = ['--sandbox', 'workspace-write', '--ask-for-approval', 'on-request',
                       '-c', 'approvals_reviewer="user"',
                       '-c', 'sandbox_workspace_write.writable_roots=[]']
        else:
            edit_root = '//' + str(state_root).lstrip('/')
            settings = {'permissions': {'deny': [f'Edit({edit_root})', f'Edit({edit_root}/**)']},
                        'sandbox': {'enabled': True, 'failIfUnavailable': True,
                                    'allowUnsandboxedCommands': False,
                                    'filesystem': {'disabled': False, 'denyWrite': [str(state_root)]}}}
            profile = ['--permission-mode', 'auto', '--settings',
                       json.dumps(settings, separators=(',', ':'), sort_keys=True)]
        self.call('agent', 'start', name, '--kind', kind, '--pane', pane,
                  '--timeout', '60000', '--', *profile)
