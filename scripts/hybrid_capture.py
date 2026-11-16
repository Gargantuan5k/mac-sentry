"""Fixed M3 board capture checker. Pre-edge samples; no physical-evidence claim.

Replay never follows observed done/retry/ack to decide the expected terminal edge.
Initial idle storage/configuration is observed history; a busy prefix is unknown.
"""
import json

from model.mac import signed
from model.secded import SecdedCodec

SIGNALS = tuple('rst clear start_request operand_a operand_b attempt_select candidate_mask '
    'checker_mask commit_mask storage_mask abort_request start_pulse launched ready busy '
    'done result_valid error accumulator stored_codeword corrected detected retried '
    'retry_count inject_fired fired_attempt latched_a latched_b latched_attempts '
    'latched_candidate latched_checker latched_commit latched_storage applied_candidate '
    'applied_checker applied_commit candidate_before candidate_after prediction_before '
    'prediction_after commit_before commit_after source_usable commit_eligible'.split())
WIDTHS = (1,1,1,8,8,3,25,3,24,30,1,1,1,1,1,1,1,2,24,30,1,1,1,2,4,2,
          8,8,3,25,3,24,30,25,3,24,25,25,3,3,24,24,1,1)
LATCHES = dict(latched_a='operand_a', latched_b='operand_b',
    latched_attempts='attempt_select', latched_candidate='candidate_mask',
    latched_checker='checker_mask', latched_commit='commit_mask', latched_storage='storage_mask')
PULSES = ('done', 'result_valid', 'error', 'corrected', 'detected', 'retried',
          'launched', 'inject_fired')
REGS = (*PULSES, 'busy', 'retry_count', 'fired_attempt', 'stored_codeword', *LATCHES)
CODEC = SecdedCodec()


class Replay:
    def __init__(self, row):
        self.r = {k: row[k] for k in REGS}
        self.saved = None  # Core saved operands survive idle clear, unlike board latches.
        self.request = None

    def wires(self, row):
        r = self.r
        reset = row['rst'] or row['abort_request']
        decoded = CODEC.decode(r['stored_codeword'])
        acc = signed(decoded.data, 24)
        selected = not reset and r['busy'] and bool(r['latched_attempts'] & (1 << r['retry_count']))
        cm, pm, km = (r['latched_'+site] if selected else 0 for site in ('candidate','checker','commit'))
        full = ((acc + self.saved[0]*self.saved[1]) & 0x1ffffff
                if self.saved is not None else row['candidate_before'])
        prediction = ((acc + self.saved[0]*self.saved[1]) % 7
                      if self.saved is not None else row['prediction_before'])
        candidate, predicted = full ^ cm, prediction ^ pm
        good = not decoded.uncorrectable and predicted < 7 and signed(candidate,25) % 7 == predicted
        w = dict(ready=int(not (reset or row['clear'] or r['busy'])),
            accumulator=acc, source_usable=int(not decoded.uncorrectable),
            applied_candidate=cm, applied_checker=pm, applied_commit=km,
            candidate_after=candidate, prediction_after=predicted,
            commit_before=candidate & 0xffffff, commit_after=(candidate & 0xffffff)^km,
            commit_eligible=int(good))
        if self.saved is not None:
            w.update(candidate_before=full, prediction_before=prediction)
        if self.request is not None or reset or not row['start_request']:
            w['start_pulse'] = int(not reset and row['start_request'] and not self.request)
        return w, decoded

    def step(self, row, w, decoded):
        old = self.r
        r = dict(old)
        r.update({k: 0 for k in PULSES})
        reset = row['rst'] or row['abort_request']
        # First-row request history is not trusted; such events are incomplete.
        accept = bool(w.get('start_pulse', row['start_pulse']) and w['ready'])
        outcome = None
        if reset:
            r = {k: 0 for k in REGS}
            self.request, self.saved = 1, (0,0)
            if old['busy']:
                outcome = 'reset_aborted' if row['rst'] else 'abort_aborted'
        else:
            self.request = row['start_request']
            r['launched'] = int(accept)
            if old['busy']:
                r['fired_attempt'] = old['retry_count']
                if not decoded.uncorrectable:
                    r['inject_fired'] = (2*bool(w['applied_candidate']) |
                        4*bool(w['applied_checker']) | 8*bool(w['applied_commit'] and w['commit_eligible']))
                if decoded.uncorrectable:
                    r.update(busy=0, done=1, error=1)
                    outcome = 'uncorrectable'
                else:
                    r['corrected'] = int(decoded.corrected)
                    r['stored_codeword'] = decoded.codeword
                    if w['commit_eligible']:
                        r.update(stored_codeword=CODEC.encode(w['commit_after']), busy=0, done=1, result_valid=1)
                        outcome = 'retried' if old['retry_count'] else 'clean'
                    else:
                        r['detected'] = 1
                        if old['retry_count'] < 2:
                            r.update(retry_count=old['retry_count']+1, retried=1)
                        else:
                            r.update(busy=0, done=1, error=2)
                            outcome = 'exhausted'
            elif row['clear']:
                r.update(stored_codeword=0, retry_count=0, fired_attempt=0)
                r.update({k: 0 for k in LATCHES})
            else:
                if accept and row['storage_mask']:
                    r['stored_codeword'] ^= row['storage_mask']
                    r['inject_fired'] = 1
                elif decoded.corrected:
                    r.update(stored_codeword=decoded.codeword, corrected=1)
                if accept:
                    r.update(busy=1, retry_count=0, fired_attempt=0)
                    r.update({k: (row[v] & 0xff if k in ('latched_a','latched_b') else row[v])
                              for k,v in LATCHES.items()})
                    self.saved = (signed(row['operand_a'],8), signed(row['operand_b'],8))
        self.r = r
        return accept, outcome


def analyze_samples(samples, label):
    if not samples:
        raise ValueError('Empty capture')
    failures, events, transactions = [], [], []
    bad_indices = set()
    replay = None
    pending = None
    checked = unchecked = 0
    ends = []
    # Evidence trust is separate from the decoder's present ability to return data.
    # Scrubbing/encoding a wrong value does not recover trust. Keep it across gaps.
    tainted = False

    def compare(i, key, value):
        if samples[i][key] != value:
            failures.append(dict(capture=label, sample=samples[i]['sample'], signal=key,
                                 expected=value, observed=samples[i][key]))
            bad_indices.add(i)

    def contiguous(i):
        return (i+1 < len(samples) and samples[i+1]['sample'] == samples[i]['sample']+1
                and samples[i+1]['window_sample'] == samples[i]['window_sample']+1)

    def event(i, action, **details):
        row = samples[i]
        e = dict(capture=label, sample=row['sample'], action=action,
            initial_acc=row['accumulator'], a=row['operand_a'], b=row['operand_b'],
            expected_acc='', observed_acc='', status='INCOMPLETE', notes='',
            fault_mask=row['storage_mask'], expected_codeword='', observed_codeword='')
        meta = dict(start=i, terminal=None, outcome='incomplete', attempts=0, requested=[],
                    fired=[], initial_history='Observed starting word; prior history not proven.', **details)
        events.append(e)
        ends.append((e,meta))
        return e,meta

    for i,row in enumerate(samples):
        if i and not contiguous(i-1):
            tainted = True
            for key in ('sample','window_sample'):
                compare(i,key,samples[i-1][key]+1)
        if i == 0 or not contiguous(i-1):
            replay, pending = None, None
            if row['busy']:
                event(i, 'hybrid_unknown_pending', reason='Capture starts/resumes busy without launch history')
        # Always check local decode and status invariants, even for unknown prefixes.
        decoded = CODEC.decode(row['stored_codeword'])
        if decoded.uncorrectable:
            tainted = True
        compare(i,'accumulator',signed(decoded.data,24))
        compare(i,'ready',int(not (row['rst'] or row['abort_request'] or row['clear'] or row['busy'])))
        if row['retry_count'] > 2:
            compare(i,'retry_count',2)
        if row['fired_attempt'] > 2:
            compare(i,'fired_attempt',2)
        if row['error'] == 3:
            compare(i,'error','one of 0, 1, 2')
        if row['result_valid']:
            compare(i,'done',1); compare(i,'error',0); compare(i,'busy',0)
        if row['error']:
            compare(i,'done',1); compare(i,'result_valid',0); compare(i,'busy',0)
        if row['done']:
            compare(i,'busy',0)
            if not row['error']:
                compare(i,'result_valid',1)
        if row['retried']:
            compare(i,'detected',1); compare(i,'busy',1); compare(i,'done',0)
        if row['detected']:
            if row['busy']:
                compare(i,'retried',1)
            else:
                compare(i,'done',1); compare(i,'error',2)
        if row['error'] == 1:
            compare(i,'corrected',0); compare(i,'detected',0); compare(i,'retried',0)
        if row['error'] == 2:
            compare(i,'detected',1); compare(i,'retried',0)
        if replay is None and not row['busy']:
            replay = Replay(row)
        if replay is None and (row['rst'] or row['abort_request']):
            replay = Replay(row)  # Only the reset transition is knowable here.
        if replay is not None:
            for k,v in replay.r.items():
                compare(i,k,v)
            w, decoded = replay.wires(row)
            for k,v in w.items():
                compare(i,k,v)
            reset = row['rst'] or row['abort_request']
            accept = bool(w.get('start_pulse',row['start_pulse']) and w['ready'])
            if accept:
                pending = event(i,'hybrid_mac', request_history_known=replay.request is not None)
                e,m = pending
                m['clean_acc'] = signed(w['accumulator'] + row['operand_a']*row['operand_b'],24)
                m['initial_source_usable'] = not decoded.uncorrectable
                m['initial_tainted'] = tainted
                m['clean_acc_usable'] = not decoded.uncorrectable and not tainted
                m['warnings'] = (['Nonzero arithmetic mask with attempt_select=0; no arithmetic injection requested']
                    if not row['attempt_select'] and any(row[s+'_mask'] for s in ('candidate','checker','commit')) else [])
                m['requested'] = ([['storage',0]] if row['storage_mask'] else []) + [
                    [site,attempt] for attempt in range(3) if row['attempt_select'] & (1<<attempt)
                    for site in ('candidate','checker','commit') if row[site+'_mask']]
                transactions.append(pending)
            elif (row['start_pulse'] or w.get('start_pulse',0)) and not w['ready']:
                e,m = event(i,'hybrid_ignored_start', reason='Busy/reset/clear request is not queued')
                m.update(terminal=i+1,outcome='ignored_start')
            if reset or (not replay.r['busy'] and row['clear']):
                action = 'reset' if row['rst'] else 'abort' if row['abort_request'] else 'clear'
                if not i or not contiguous(i-1) or not samples[i-1][{'reset':'rst','abort':'abort_request','clear':'clear'}[action]]:
                    e,m = event(i,action)
                    m.update(terminal=i+1,outcome=action)
                    e.update(expected_acc=0,expected_codeword=0)
            if pending and replay.r['busy'] and not reset:
                pending[1]['attempts'] += 1
                # In a busy attempt no arithmetic result has committed yet. A
                # changed usable source is a storage miscorrection, even if every
                # candidate is rejected or the later result happens to coincide.
                if (pending[1]['initial_source_usable'] and not decoded.uncorrectable
                        and w['accumulator'] != pending[0]['initial_acc']):
                    tainted = True
            if reset or (not replay.r['busy'] and row['clear']):
                tainted = False
            _,outcome = replay.step(row,w,decoded)
            if contiguous(i):
                checked += 1
                if pending:
                    e,m = pending
                    ack = samples[i+1]['inject_fired']
                    for bit,site in enumerate(('storage','candidate','checker','commit')):
                        if ack & (1<<bit):
                            m['fired'].append([site,samples[i+1]['fired_attempt']])
                if outcome and pending:
                    e,m = pending
                    m.update(terminal=i+1, outcome=outcome, retry_count=replay.r['retry_count'])
                    e['expected_acc'] = signed(CODEC.decode(replay.r['stored_codeword']).data,24)
                    e['expected_codeword'] = replay.r['stored_codeword']
                    if replay.r['result_valid']:
                        # Uncorrectable launch readback is diagnostic, not an oracle.
                        # A later usable decode can be a multi-bit miscorrection.
                        if not m['initial_source_usable']:
                            m['outcome'] = 'unusable_source_valid'
                        elif e['expected_acc'] != m['clean_acc']:
                            m['outcome'] = 'silent_escape'
                        elif tainted:
                            m['outcome'] = 'tainted_source_valid'
                        tainted = tainted or m['outcome'] in ('unusable_source_valid', 'silent_escape')
                    elif outcome in ('uncorrectable', 'exhausted'):
                        terminal_decode = CODEC.decode(replay.r['stored_codeword'])
                        if not terminal_decode.uncorrectable:
                            if (not m['initial_source_usable'] or
                                    e['expected_acc'] != e['initial_acc']):
                                m['outcome'] = 'rejected_state_escape'
                                tainted = True
                            elif tainted:
                                m['outcome'] = 'tainted_state_rejected'
                    m['terminal_tainted'] = tainted
                    pending = None
            # Missing successor cannot prove sampled acknowledgements or completion.
        elif contiguous(i):
            unchecked += 1

    for e,m in ends:
        start,terminal = m['start'],m['terminal']
        # A terminal sample without a successor cannot demonstrate pulse clearing.
        end = terminal+1 if terminal is not None else None
        complete = (end is not None and end < len(samples)
            and all(contiguous(j) for j in range(start,end))
            and m.get('request_history_known',True))
        if complete:
            e.update(observed_acc=samples[terminal]['accumulator'],
                     observed_codeword=samples[terminal]['stored_codeword'])
            e['status'] = ('FAIL' if any(j in bad_indices for j in range(start,end+1)) else
                           'ESCAPE' if m['outcome'] in ('silent_escape', 'unusable_source_valid',
                               'tainted_source_valid', 'rejected_state_escape', 'tainted_state_rejected') else 'PASS')
        if e['action']=='hybrid_ignored_start' and e['status']=='PASS':
            e['status'] = 'BLOCKED'
        if e['action']=='hybrid_mac':
            e['action'] = 'hybrid_'+m['outcome']
        remaining = [x for x in m['requested'] if x not in m['fired']]
        m['unfired'] = remaining if complete else []
        m['unresolved'] = remaining if not complete else []
        if complete and m['unfired'] and e['status']=='PASS':
            e['status'] = 'UNFIRED'
        m['terminal_sample'] = samples[terminal]['sample'] if terminal is not None and terminal<len(samples) else None
        m['capture_complete'] = complete
        e['notes'] = json.dumps(m,sort_keys=True)
    summary = dict(capture=label,samples=len(samples),checked_transitions=checked,
        unchecked_transitions=unchecked,observed_events=len(events),
        complete_mac_transactions=sum(m['capture_complete'] and m['outcome'] not in ('reset_aborted','abort_aborted') for _,m in transactions),
        mismatches=len(failures),initial_accumulator=samples[0]['accumulator'],
        final_accumulator=samples[-1]['accumulator'])
    return samples,events,failures,summary


def read_hybrid_capture(path):
    """Reuse the legacy radix/name parser without changing old archive semantics."""
    import csv
    from scripts.archive_fpga_run import read_capture
    with path.open(newline='') as handle:
        table = list(csv.reader(handle, strict=True))
    if len(table)<3 or len(table[0])<2 or table[0][:2] != ['Sample in Buffer','Sample in Window']:
        raise ValueError('Expected Vivado sample index columns')
    if any(len(row)!=len(table[0]) for row in table):
        raise ValueError('Malformed hybrid CSV row')
    rows = read_capture(path,SIGNALS,WIDTHS)
    if any(row['sample']<0 or row['window_sample']<0 for row in rows):
        raise ValueError('Negative capture sample index')
    return rows
