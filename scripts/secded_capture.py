"""Check pre-edge samples of the idle-injectable SECDED board variant."""
from model.mac import signed
from model.mac_secded import SecdedMacModel
from model.secded import SecdedCodec

EXTRA_SIGNALS = ('corrected', 'inject_pulse', 'inject_mask', 'inject_fired', 'stored_codeword')
EXTRA_WIDTHS = (1, 1, 30, 1, 30)


def analyze_samples(samples, label):
    if not samples:
        raise ValueError('Empty capture')
    codec = SecdedCodec()
    failures, events, indexed_failures = [], [], []
    model = None
    checked = unchecked = 0

    def contiguous(i):
        return (i + 1 < len(samples)
                and samples[i+1]['sample'] == samples[i]['sample'] + 1
                and samples[i+1]['window_sample'] == samples[i]['window_sample'] + 1)

    def compare(i, field, expected):
        if samples[i][field] != expected:
            indexed_failures.append(i)
            failures.append(dict(capture=label, sample=samples[i]['sample'], signal=field,
                                 expected=expected, observed=samples[i][field]))

    def injecting(row):
        return bool(not (row['rst'] or row['clear'] or row['busy'])
                    and row['inject_pulse'] and row['inject_mask'])

    for i, row in enumerate(samples):
        decoded = codec.decode(row['stored_codeword'])
        compare(i, 'accumulator', signed(decoded.data, 24))
        compare(i, 'ready', int(not (row['rst'] or row['clear'] or row['busy'] or injecting(row))))
        if model is None and not row['busy']:
            model = SecdedMacModel()
            model.codeword = row['stored_codeword']
        if not contiguous(i):
            model = None
            continue
        if model is None and row['rst']:
            model = SecdedMacModel()
        if model is None:
            unchecked += 1
            continue
        if injecting(row):
            model.inject_accumulator_fault(row['inject_mask'])
            model.corrected = False
            expected = (0, 0, 0, 0, 0, model.accumulator, 0)
        else:
            expected = model.step(row['rst'], row['clear'], row['start_pulse'],
                                  row['operand_a'], row['operand_b'])
        for field, value in zip(('busy', 'done', 'result_valid', 'error', 'accumulator'), expected[1:6]):
            compare(i+1, field, value)
        compare(i+1, 'corrected', int(model.corrected))
        compare(i+1, 'inject_fired', int(injecting(row)))
        compare(i+1, 'stored_codeword', model.codeword)
        checked += 1

    for i, row in enumerate(samples):
        action, end, expected_acc, expected_word = None, i+1, '', ''
        notes = 'Initial stored word is observed; history and capture/build identity are not established.'
        decoded = codec.decode(row['stored_codeword'])
        if row['start_pulse'] and not row['ready']:
            action = 'ignored_start'
            notes += ' Request blocked by reset, clear, busy, or injection.'
        elif row['rst'] or (not row['busy'] and row['clear']):
            action = 'reset' if row['rst'] else 'clear'
            # Report the first edge of a held control, not hundreds of identical events.
            if i and contiguous(i-1) and samples[i-1][action if action == 'clear' else 'rst']:
                continue
            expected_acc = expected_word = 0
        elif injecting(row):
            action = 'inject_' + str(row['inject_mask'].bit_count()) + '_bits'
            expected_word = row['stored_codeword'] ^ row['inject_mask']
            expected_acc = signed(codec.decode(expected_word).data, 24)
            notes += ' PASS requires raw XOR and inject_fired; subsequent repair is a separate event.'
        elif row['ready'] and row['start_pulse']:
            end = i+2
            action = 'mac_rejected' if decoded.uncorrectable else 'mac'
            if contiguous(i) and samples[i+1]['rst']:
                action, expected_acc, expected_word = 'reset_aborted_mac', 0, 0
            elif decoded.uncorrectable:
                expected_word = row['stored_codeword']
                expected_acc = row['accumulator']  # diagnostic only
                notes += ' Detected uncorrectable state: require error=1 and result_valid=0.'
            else:
                expected_acc = signed(row['accumulator'] + row['operand_a'] * row['operand_b'], 24)
                expected_word = codec.encode(expected_acc % (1 << 24))
        elif not row['busy'] and decoded.corrected:
            action, expected_word = 'idle_repair', decoded.codeword
            expected_acc = signed(decoded.data, 24)
        elif row['inject_pulse']:
            action = 'ignored_injection'
            notes += ' No nonzero idle injection accepted.'
        if action is None:
            continue
        complete = all(contiguous(j) for j in range(i, end))
        status = 'INCOMPLETE' if not complete else (
            'FAIL' if any(i <= j <= end for j in indexed_failures) else
            'BLOCKED' if action == 'ignored_start' else 'PASS')
        events.append(dict(capture=label, sample=row['sample'], action=action,
                           initial_acc=row['accumulator'], a=row['operand_a'], b=row['operand_b'],
                           expected_acc=expected_acc,
                           observed_acc=samples[end]['accumulator'] if complete else '',
                           status=status, notes=notes, fault_mask=row['inject_mask'],
                           expected_codeword=expected_word,
                           observed_codeword=samples[end]['stored_codeword'] if complete else ''))
    summary = dict(capture=label, samples=len(samples), checked_transitions=checked,
                   unchecked_transitions=unchecked, observed_events=len(events),
                   complete_mac_transactions=sum(e['action'] in ('mac', 'mac_rejected')
                       and e['status'] != 'INCOMPLETE' for e in events),
                   mismatches=len(failures), initial_accumulator=samples[0]['accumulator'],
                   final_accumulator=samples[-1]['accumulator'])
    return samples, events, failures, summary
