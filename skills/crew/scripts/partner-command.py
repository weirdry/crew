#!/usr/bin/env python3
"""Bound CLI entry for prompting, observing and answering the retained partner."""
import json
import os
from pathlib import Path
import subprocess
import sys

from partner import Refused, read_receipt, verify, locked, unchanged, check_dialog_binding
from herdr_transport import Herdr, TransportError


def main():
    args = sys.argv[1:]
    if len(args) < 3 or args[0] != 'agent' or args[1] not in ('get', 'read', 'prompt', 'wait', 'send-keys'):
        raise Refused('usage: herdr.sh agent <get|read|prompt|wait|send-keys> <partner> [options]', 2)
    context = json.loads(subprocess.check_output([str(Path(__file__).with_name('state-root.sh'))]))
    root = Path(context['state_root'])
    with locked(root):
        receipt = read_receipt(root / 'worker.json')
        check_dialog_binding(receipt)
        if not receipt or receipt['version'] != 2:
            raise Refused('controller-bound receipt required; legacy handoff is explicit')
        if receipt['controller_id'] != os.environ.get('CREW_CONTROLLER_ID'):
            raise Refused('not the recorded controller', 11)
        if args[2] != receipt['worker_name']:
            raise Refused('not the recorded partner')
        transport = Herdr(receipt['session'])
        verify(transport.agent(args[2]), receipt)
        unchanged(root / 'worker.json', receipt)
        # Keep output and command-specific semantics intact, including text and --wait.
        result = subprocess.run(transport.prefix + args)
        unchanged(root / 'worker.json', receipt)
        return result.returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Refused, TransportError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print('outcome=refused:' + str(error), file=sys.stderr)
        raise SystemExit(getattr(error, 'status', 10))
