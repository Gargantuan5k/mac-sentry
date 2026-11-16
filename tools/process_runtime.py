"""Reap private Linux command groups, including children outliving their parent."""
import os
from pathlib import Path
import signal
import subprocess
import time


def group_members(pgid):
    members=[]
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields=path.read_text().rsplit(')',1)[1].split()
            # Commands are launched with start_new_session: SID and PGID both
            # equal the original leader's PID. Never select another session.
            if int(fields[2])==pgid and int(fields[3])==pgid:
                members.append({'pid':int(path.parent.name),'state':fields[0]})
        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
    return members


def stop_group(proc):
    """A reaped leader is insufficient: check executable descendants after it exits."""
    evidence={'pgid':proc.pid,'signals':[]}
    for sig,grace in ((signal.SIGTERM,1.0),(signal.SIGKILL,2.0)):
        proc.poll()
        members=group_members(proc.pid)
        if proc.returncode is not None and not any(m['state'] not in ('Z','X') for m in members):
            return dict(evidence,quiescent=True,members=members)
        try:os.killpg(proc.pid,sig);evidence['signals'].append(sig.name)
        except ProcessLookupError:pass
        deadline=time.monotonic()+grace
        while time.monotonic()<deadline:
            proc.poll();members=group_members(proc.pid)
            if proc.returncode is not None and not any(m['state'] not in ('Z','X') for m in members):
                return dict(evidence,quiescent=True,members=members)
            time.sleep(0.02)
    proc.poll();members=group_members(proc.pid)
    return dict(evidence,quiescent=proc.returncode is not None and not any(m['state'] not in ('Z','X') for m in members),members=members)
