#!/usr/bin/env python3
"""Partner ownership and lifecycle, independent of the lead's terminal placement."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

# Shell entry points use isolated Python; add only the installed helper directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from herdr_transport import Herdr, TransportError

TOKEN = r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}'
KIND = r'[a-z][a-z0-9_-]{0,31}'


class Refused(RuntimeError):
    def __init__(self, message, status=10):
        super().__init__(message)
        self.status = status


def regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise Refused(f'not a regular record: {path}')
    return path.read_bytes()


def read_receipt(path):
    if not os.path.lexists(path):
        return None
    value = json.loads(regular(path))
    validate_receipt(value)
    return value


def validate_receipt(value):
    if not isinstance(value, dict) or value.get('version') not in (1, 2):
        raise Refused('invalid partner receipt')
    for key, pattern in [('worker_name', KIND), ('worker_kind', KIND), ('worker_pane_id', TOKEN)]:
        if not isinstance(value.get(key), str) or not re.fullmatch(pattern, value[key]):
            raise Refused('invalid partner identity')
    if value['version'] == 1:
        if not isinstance(value.get('lead_pane_id'), str) or not re.fullmatch(TOKEN, value['lead_pane_id']):
            raise Refused('invalid legacy owner')
    else:
        for key in ('controller_id', 'lead_kind', 'session'):
            if not isinstance(value.get(key), str) or not re.fullmatch(TOKEN, value[key]):
                raise Refused('invalid controller binding')
        if value['lead_kind'] == value['worker_kind']:
            raise Refused('same-kind receipt')


def owner(receipt):
    return receipt['controller_id'] if receipt['version'] == 2 else 'pane:' + receipt['lead_pane_id']


@contextmanager
def locked(root):
    # Serialize actual workspace partner start/stop/handoff calls. No service or lease.
    descriptor = os.open(root / 'partner.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise Refused('unsafe partner lock')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Refused('another partner operation is in progress', 11) from error
        yield
    finally:
        os.close(descriptor)


def unchanged(path, expected):
    if read_receipt(path) != expected:
        raise Refused('partner receipt changed; no further action taken')


def receipt_digest(receipt):
    return hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check_dialog_binding(receipt):
    # A dialog pins one complete receipt across separate adapter invocations.
    expected = os.environ.get('CREW_DIALOG_RECEIPT_SHA256')
    if expected is not None and receipt_digest(receipt) != expected:
        raise Refused('partner receipt changed during dialog; no further action taken')


def save(path, expected, value):
    unchanged(path, expected)
    if expected == value:
        return
    if expected is not None:
        # Retain the exact old bytes on explicit handoff/stale replacement, once per content.
        old = regular(path)
        archive = path.parent / ('worker-' + hashlib.sha256(old).hexdigest() + '.json')
        fd, temporary = tempfile.mkstemp(prefix='.worker-history-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(old)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, archive)
            except FileExistsError:
                if regular(archive) != old:
                    raise Refused('conflicting partner history')
        finally:
            os.unlink(temporary)
    fd, temporary = tempfile.mkstemp(prefix='.worker-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        unchanged(path, expected)
        if expected is None:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        os.unlink(temporary) if os.path.exists(temporary) else None


def verify(agent, receipt):
    if agent is None or any(agent.get(a) != receipt[r] for a, r in
                            [('name', 'worker_name'), ('pane_id', 'worker_pane_id'), ('agent', 'worker_kind')]):
        raise Refused('live-partner-ownership-mismatch')


def binding(args, receipt):
    if receipt is None:
        if args.handoff_from:
            raise Refused('handoff requires an existing partner receipt', 11)
        return
    if receipt['version'] == 2 and receipt['session'] != args.session:
        raise Refused('session mismatch; partner identity is session-scoped', 11)
    if receipt['version'] == 2 and owner(receipt) == args.controller:
        if receipt['lead_kind'] != args.lead_kind or args.handoff_from:
            raise Refused('controller kind mismatch or unnecessary handoff', 11)
        return
    if args.handoff_from != owner(receipt):
        raise Refused('owner mismatch; explicit --handoff-from ' + owner(receipt) + ' required', 11)


def operate(args, root, cwd, name):
    path = root / 'worker.json'
    with locked(root):
        receipt = read_receipt(path)
        binding(args, receipt)
        transport = Herdr(args.session)
        if args.action == 'stop':
            if receipt is None:
                raise Refused('partner receipt absent', 4)
            verify(transport.agent(receipt['worker_name']), receipt)
            unchanged(path, receipt)
            verify(transport.agent(receipt['worker_name']), receipt)
            transport.call('pane', 'close', receipt['worker_pane_id'])
            unchanged(path, receipt)
            path.unlink()
            print('closed_pane_id=' + receipt['worker_pane_id'])
            return
        try:
            current = regular(root / '.current').decode().splitlines()
        except FileNotFoundError as error:
            raise Refused('active-run pointer absent; initialize a run first', 3) from error
        if len(current) != 1 or not re.fullmatch(TOKEN, current[0]):
            raise Refused('invalid active-run pointer', 3)
        run = Path(cwd) / '.crew' / current[0]
        if run.is_symlink() or not run.is_dir():
            raise Refused('active run directory missing or unsafe', 3)
        if args.kind == args.lead_kind:
            raise Refused('same-kind collaboration refused', 12)
        if receipt and receipt['worker_kind'] != args.kind:
            raise Refused('worker-kind-mismatch; retire explicitly before changing kinds', 14)
        name = receipt['worker_name'] if receipt else name
        agent = transport.agent(name)
        if agent is not None:
            if not receipt:
                raise Refused('unowned live partner')
            verify(agent, receipt)
            if args.create:
                raise Refused('partner-live', 13)
        pane = receipt['worker_pane_id'] if receipt else None
        created = False
        if agent is None:
            if pane and transport.pane(pane) is None:
                pane = None
            if pane and args.handoff_from:
                raise Refused('handoff requires a matching live partner or confirmed absent agent and pane', 11)
            if pane is None:
                pane = transport.create(cwd, name, args.workspace)
                created = True
        value = {'version': 2, 'controller_id': args.controller, 'lead_kind': args.lead_kind,
                 'session': args.session, 'worker_name': name, 'worker_kind': args.kind,
                 'worker_pane_id': pane}
        try:
            if agent is None:
                transport.call('pane', 'wait-output', pane, '--regex', '[#$%>❯] ?$',
                               '--source', 'detection', '--lines', '5', '--timeout', '60000')
                transport.start(name, args.kind, pane, root)
                marker = 'Ask Codex' if args.kind == 'codex' else 'Try "'
                transport.call('pane', 'wait-output', pane, '--regex', marker,
                               '--source', 'visible', '--timeout', '60000')
                verify(transport.agent(name), value)
            # Recheck the active run after a potentially long launch before publishing.
            if regular(root / '.current').decode().splitlines() != current:
                raise Refused('active run changed during partner startup')
            save(path, receipt, value)
        except (OSError, ValueError, Refused, TransportError):
            if created:
                print("startup_incomplete_pane_id=" + pane, file=sys.stderr)
                unchanged(path, receipt)
                # Never close a reused pane. Inspect an ambiguous newly created process.
                live = transport.agent(name)
                if live is None or (live['pane_id'] == pane and live['agent'] == args.kind):
                    transport.call('pane', 'close', pane)
                else:
                    print('cleanup=refused:identity-changed\npane_id=' + pane, file=sys.stderr)
            raise
        print('outcome=' + ('attached' if agent else 'created'))
        print('ownership=' + ('transferred' if args.handoff_from else 'preserved'))
        print('partner_name=' + name + '\npartner_kind=' + args.kind + '\npane_id=' + pane)
        print('session=' + args.session + '\ncontroller_id=' + args.controller)
        print('ownership_receipt=' + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop'])
    parser.add_argument('--controller', required=True, help='stable ID for this lead session; not a pane ID')
    parser.add_argument('--lead-kind', choices=['codex', 'claude'], required=True)
    parser.add_argument('--session', required=True, help='explicit Herdr named session')
    parser.add_argument('--workspace', help='optional Herdr workspace for a new partner tab')
    parser.add_argument('--handoff-from', help='exact previous owner; use only with user-authorized handoff')
    parser.add_argument('--create', action='store_true')
    parser.add_argument('kind', nargs='?', choices=['codex', 'claude'])
    # The shell entry point prepends the action; flags may precede the worker kind.
    # Python 3.11 parse_args cannot resume that optional positional after flags.
    args = parser.parse_intermixed_args()
    if any(not re.fullmatch(TOKEN, value) for value in
           [args.controller, args.session, *([args.workspace] if args.workspace else []),
            *([args.handoff_from] if args.handoff_from else [])]):
        parser.error('invalid controller, session, workspace, or handoff identity')
    if (args.action == 'start' and args.kind is None) or (args.action == 'stop' and
            (args.kind or args.create or args.handoff_from or args.workspace)):
        parser.error('invalid action arguments')
    try:
        result = subprocess.run([str(Path(__file__).with_name('state-root.sh'))],
                                capture_output=True, text=True, check=True)
        context = json.loads(result.stdout)
        root = Path(context['state_root'])
        if not root.is_dir() or root.is_symlink():
            raise Refused('state root absent or unsafe; initialize a run first', 3)
        operate(args, root, context['cwd'], context['partner_name'])
    except Refused as error:
        print('outcome=refused:' + str(error), file=sys.stderr)
        return error.status
    except (OSError, ValueError, TransportError, subprocess.CalledProcessError) as error:
        print('outcome=unavailable:' + str(error), file=sys.stderr)
        return 10
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
