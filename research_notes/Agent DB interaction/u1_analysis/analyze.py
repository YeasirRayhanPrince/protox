"""Extract agent DB operations per trajectory and compute traffic statistics.

Usage: python3 -I analyze.py <dataset> <path...>
  dataset in {wmo_bird, ptbr, tau, spider_tc}
Each trajectory -> list of "calls" (one agent tool invocation), each call has
a list of ops: dict(kind, text) and an error flag + error text.
"""
import sys, json, re, shlex, statistics, difflib, collections

# ---------------- SQL classification ----------------
CAT_RE = re.compile(r"information_schema|pg_catalog|\bpg_(class|attribute|tables|indexes|stat\w*|namespace|constraint|description|views|proc|type|settings)\b|sqlite_master|sqlite_schema|sqlite_sequence", re.I)

def split_sql(s):
    out, cur, q = [], [], None
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q: q = None
        elif ch in "'\"`":
            q = ch; cur.append(ch)
        elif ch == ';':
            out.append(''.join(cur)); cur = []
        else:
            cur.append(ch)
    out.append(''.join(cur))
    res = []
    for x in out:
        x = re.sub(r"--[^\n]*", "", x).strip()
        if x: res.append(x)
    return res

def classify_sql(s):
    t = s.strip()
    if t.startswith('.'):  # sqlite3 dot command
        return 'catalog' if re.match(r"\.(schema|tables|indexes|indices|fullschema|dbinfo)", t) else 'other'
    u = t.upper()
    first = re.match(r"[A-Z]+", u.lstrip('( '))
    w = first.group(0) if first else ''
    if w in ('PRAGMA', 'DESCRIBE', 'DESC', 'SHOW'): return 'catalog'
    if CAT_RE.search(t): return 'catalog'
    if w in ('INSERT', 'UPDATE', 'DELETE', 'MERGE', 'REPLACE', 'UPSERT', 'COPY'): return 'dml'
    if w in ('CREATE', 'ALTER', 'DROP', 'TRUNCATE', 'RENAME', 'COMMENT', 'GRANT', 'REVOKE', 'VACUUM', 'ANALYZE', 'REINDEX'): return 'ddl'
    if w in ('EXPLAIN',): return 'explain'
    if w in ('SET', 'BEGIN', 'COMMIT', 'ROLLBACK', 'START', 'USE', 'ATTACH', 'SAVEPOINT', 'RELEASE'): return 'other'
    if w in ('WITH',):
        if re.search(r"\)\s*(INSERT|UPDATE|DELETE)\b", u): return 'dml'
        return probe_or_select(u)
    if w in ('SELECT', 'VALUES', 'TABLE'): return probe_or_select(u)
    return 'other'

def probe_or_select(u):
    nojoin = not re.search(r"\bJOIN\b|\bGROUP\s+BY\b|\bUNION\b", u) and u.count('SELECT') == 1
    agg = re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", u)
    if nojoin and re.match(r"\s*SELECT\s+\*\s+FROM", u) and re.search(r"\bLIMIT\b", u) and not re.search(r"\bWHERE\b", u):
        return 'sample'
    if nojoin and re.match(r"\s*SELECT\s+DISTINCT\b", u) and not agg and not re.search(r"\bWHERE\b", u):
        return 'distinct_probe'
    return 'select'

META = {'catalog', 'schema_file', 'schema_tool', 'sample', 'distinct_probe'}
SQLKINDS = ('select', 'catalog', 'sample', 'distinct_probe', 'dml', 'ddl', 'explain', 'other')

def norm(s):
    return re.sub(r"\s+", " ", s.strip().rstrip(';')).lower()

# ---------------- dataset adapters ----------------
def attrs(r):
    return {a['key']: list(a['value'].values())[0] for a in r['attributes']}

SQLITE_ERR = re.compile(r"^(Parse error|Error:|Runtime error)|\nParse error|\nError:|\nRuntime error", re.M)

def wmo_bird(paths):
    traces = collections.OrderedDict(); meta = {}
    for p in paths:
        for line in open(p):
            r = json.loads(line)
            traces.setdefault(r['traceId'], []).append(r)
    out = []
    for tid, spans in traces.items():
        spans.sort(key=lambda r: r['startTimeUnixNano'])
        calls = []; model = None; md = {}
        pending = None
        for r in spans:
            a = attrs(r)
            if 'wmh.trace.metadata' in a:
                try: md = json.loads(a['wmh.trace.metadata'])
                except Exception: pass
            if r['name'].startswith('chat'):
                model = a.get('gen_ai.request.model', model)
                try: cmd = json.loads(a.get('gen_ai.tool.call.arguments', '{}')).get('command', '')
                except Exception: cmd = ''
                pending = {'cmd': cmd, 'ops': parse_bash(cmd), 'err': False, 'errtxt': ''}
                calls.append(pending)
            elif r['name'].startswith('execute_tool') and pending is not None:
                msg = a.get('gen_ai.tool.message', '') or ''
                m = SQLITE_ERR.search(msg)
                if m or r['status'].get('code') == 'STATUS_CODE_ERROR':
                    pending['err'] = True; pending['errtxt'] = msg[m.start():m.start()+120] if m else 'span-error'
                pending = None
        out.append({'id': tid, 'model': model or md.get('model'), 'reward': md.get('reward'), 'calls': calls, 'turns': [[i] for i in range(len(calls))]})
    return out

def parse_bash(cmd):
    ops = []
    if re.search(r"\b(cat|head|sed|grep|less|tail)\b[^|;&]*schema", cmd):
        ops.append({'kind': 'schema_file', 'text': cmd})
    try:
        lx = shlex.shlex(cmd, posix=True, punctuation_chars=True); lx.whitespace_split = True
        toks = list(lx)
    except Exception:
        toks = cmd.split()
    i = 0
    while i < len(toks):
        if toks[i] == 'sqlite3' or toks[i].endswith('/sqlite3'):
            j = i + 1
            while j < len(toks) and toks[j].startswith('-'): j += 1
            j += 1  # db file
            while j < len(toks) and toks[j] not in (';', '&&', '||', '|', '&', '<<', '<') and toks[j] not in ('echo', 'sqlite3', 'cat', 'head', 'grep', 'sed', 'ls', 'printf', 'database.db'):
                for s in split_sql(toks[j]):
                    ops.append({'kind': classify_sql(s), 'text': s})
                j += 1
            i = j
        else:
            i += 1
    return ops

def ptbr(paths):
    out = []
    for p in paths:
        data = json.load(open(p))
        for k, x in enumerate(data):
            msgs = x['messages']
            calls = []; turns = []; byid = {}
            for m in msgs:
                if m['role'] == 'assistant':
                    turn = []
                    for t in m.get('tool_calls') or []:
                        name = t['function']['name']
                        try: args = json.loads(t['function']['arguments'])
                        except Exception: args = {}
                        if name == 'execute_sql':
                            q = args.get('query') or args.get('sql') or next(iter(args.values()), '')
                            ops = [{'kind': classify_sql(s), 'text': s} for s in split_sql(str(q))]
                        elif name == 'get_table_schema':
                            ops = [{'kind': 'schema_tool', 'text': 'schema:' + str(args.get('table_name'))}]
                        else:
                            continue
                        c = {'ops': ops, 'err': False, 'errtxt': '', 'name': name}
                        byid[t['id']] = c; calls.append(c); turn.append(len(calls) - 1)
                    if turn: turns.append(turn)
                elif m['role'] == 'tool' and m.get('tool_call_id') in byid:
                    c = byid[m['tool_call_id']]; txt = m.get('content') or ''
                    if txt.startswith('SQL_ERROR') or txt.startswith('ERRO') or txt.lower().startswith('error'):
                        c['err'] = True; c['errtxt'] = txt[:120]
            db = re.search(r'# Banco de Dados: (\S+)', msgs[0]['content'] or '')
            out.append({'id': k, 'model': 'teacher (unstated; distilled, LLM-judged-correct only)', 'db': db.group(1) if db else None, 'calls': calls, 'turns': turns})
    return out

TAU_WRITE = re.compile(r"^(cancel|modify|exchange|return|book|update|send)_")
TAU_NONDB = {'think', 'calculate', 'transfer_to_human_agents'}

def tau(paths):
    out = []
    for p in paths:
        model = p.rsplit('/', 1)[-1].replace('.json', '')
        for x in json.load(open(p)):
            calls = []; turns = []; byid = {}
            for m in x['traj']:
                if m['role'] == 'assistant':
                    turn = []
                    for t in m.get('tool_calls') or []:
                        name = t['function']['name']
                        if name in TAU_NONDB: continue
                        kind = 'dml' if TAU_WRITE.match(name) else ('catalog' if name.startswith('list_all') else 'select')
                        c = {'ops': [{'kind': kind, 'text': name + json.dumps(t['function']['arguments'], sort_keys=True)}], 'err': False, 'errtxt': '', 'name': name}
                        byid[t['id']] = c; calls.append(c); turn.append(len(calls) - 1)
                    if turn: turns.append(turn)
                elif m['role'] == 'tool' and m.get('tool_call_id') in byid:
                    txt = str(m.get('content') or '')
                    if txt.startswith('Error'):
                        c = byid[m['tool_call_id']]; c['err'] = True; c['errtxt'] = txt[:120]
            out.append({'id': f"{model}:{x['task_id']}:{x.get('trial')}", 'model': model, 'reward': x.get('reward'), 'calls': calls, 'turns': turns})
    return out

def spider_tc(paths):
    import ast
    out = []
    for p in paths:
        for x in json.load(open(p)):
            calls = []; turns = []; queue = []
            for m in x['conversation']:
                if m['role'] == 'assistant' and m.get('tool_calls'):
                    tcs = m['tool_calls']
                    if isinstance(tcs, str):
                        try: tcs = ast.literal_eval(tcs)
                        except Exception: tcs = []
                    turn = []
                    for t in tcs:
                        name = t.get('name'); args = t.get('arguments') or {}
                        if 'sql' in (name or ''):
                            qq = args.get('sql') or args.get('query') or next(iter(args.values()), '')
                            ops = [{'kind': classify_sql(s2), 'text': s2} for s2 in split_sql(str(qq))]
                        elif name == 'execute_bash':
                            ops = [{'kind': 'schema_file', 'text': str(args.get('command', ''))}]
                        else:
                            ops = []
                        c = {'ops': ops, 'err': False, 'errtxt': '', 'name': name}
                        calls.append(c); queue.append(c); turn.append(len(calls) - 1)
                    if turn: turns.append(turn)
                elif m['role'] == 'tool' and queue:
                    c = queue.pop(0); txt = str(m.get('content') or '')
                    if re.search(r"error|exception|failed", txt[:400], re.I):
                        c['err'] = True; c['errtxt'] = txt[:200]
            out.append({'id': x['instance_id'], 'model': 'Claude 3.7 Sonnet (per dir name)', 'calls': calls, 'turns': turns})
    return out

# ---------------- statistics ----------------
def pct(a, b): return f"{a} / {b} = {100.0*a/b:.1f}%" if b else f"{a} / 0"

def q(xs, p):
    xs = sorted(xs); return xs[min(len(xs)-1, int(p*len(xs)))] if xs else 0

def analyse(trajs):
    R = {}
    R['trajectories'] = len(trajs)
    R['models'] = dict(collections.Counter(t['model'] for t in trajs))
    kinds = collections.Counter(); calls_n = 0; dbcalls = 0
    per_traj_ops = []; per_traj_sql = []; err_calls = 0; err_traj = 0
    retry_any = retry_sim = err_last = 0; errs_total = 0
    meta_first = 0; all_meta_before = 0; has_both = 0
    dup_exact = 0; sql_total_for_dup = 0
    multi_stmt_calls = 0; parallel_turns = 0; turns_total = 0; par_sizes = collections.Counter()
    first_kind = collections.Counter(); errtypes = collections.Counter(); timeouts = 0
    phase_pos = collections.defaultdict(list)
    for t in trajs:
        seq = []  # flattened (kind, text, err, callidx)
        for ci, c in enumerate(t['calls']):
            if not c['ops']: continue
            dbcalls += 1
            if len([o for o in c['ops'] if o['kind'] in SQLKINDS]) > 1: multi_stmt_calls += 1
            if c['err']:
                err_calls += 1
                et = re.sub(r"\s+", " ", c['errtxt'])[:60]
                errtypes[re.sub(r'"[^"]*"|\'[^\']*\'|\b\w+\.\w+\b', 'X', et)[:45]] += 1
                if 'timeout' in c['errtxt'].lower() or 'canceling statement' in c['errtxt'].lower(): timeouts += 1
            for o in c['ops']:
                kinds[o['kind']] += 1; seq.append((o['kind'], o['text'], c['err'], ci))
        calls_n += len(t['calls'])
        for turn in t['turns']:
            dbt = [i for i in turn if t['calls'][i]['ops']]
            if dbt:
                turns_total += 1; par_sizes[len(dbt)] += 1
                if len(dbt) > 1: parallel_turns += 1
        per_traj_ops.append(len(seq))
        sqls = [s for s in seq if s[0] in SQLKINDS]
        per_traj_sql.append(len(sqls))
        if any(c['err'] for c in t['calls'] if c['ops']): err_traj += 1
        # retries: per erroring call, look at next db call
        dbc = [c for c in t['calls'] if c['ops']]
        for k, c in enumerate(dbc):
            if not c['err']: continue
            errs_total += 1
            if k + 1 >= len(dbc): err_last += 1; continue
            retry_any += 1
            a = norm(' '.join(o['text'] for o in c['ops'])); b = norm(' '.join(o['text'] for o in dbc[k+1]['ops']))
            if difflib.SequenceMatcher(None, a, b).ratio() >= 0.6: retry_sim += 1
        # ordering
        if seq:
            first_kind[seq[0][0]] += 1
            if seq[0][0] in META: meta_first += 1
            mi = [i for i, s in enumerate(seq) if s[0] in META]; ui = [i for i, s in enumerate(seq) if s[0] not in META]
            if mi and ui:
                has_both += 1
                if max(mi) < min(ui): all_meta_before += 1
            n = len(seq)
            for i, s in enumerate(seq):
                phase_pos['meta' if s[0] in META else s[0]].append(i / (n - 1) if n > 1 else 0.0)
        # exact duplicates among SQL within trajectory
        seen = set()
        for s in sqls:
            k2 = norm(s[1]); sql_total_for_dup += 1
            if k2 in seen: dup_exact += 1
            seen.add(k2)
    tot = sum(kinds.values())
    R['op_kinds'] = {k: pct(v, tot) for k, v in kinds.most_common()}
    sqltot = sum(kinds[k] for k in SQLKINDS)
    R['sql_statements_total'] = sqltot
    R['sql_kinds_of_sql_only'] = {k: pct(kinds[k], sqltot) for k in SQLKINDS if kinds[k]}
    R['ops_per_traj'] = dict(mean=round(statistics.mean(per_traj_ops), 2) if per_traj_ops else 0, median=statistics.median(per_traj_ops) if per_traj_ops else 0, p90=q(per_traj_ops, .9), max=max(per_traj_ops) if per_traj_ops else 0)
    R['sql_per_traj'] = dict(mean=round(statistics.mean(per_traj_sql), 2) if per_traj_sql else 0, median=statistics.median(per_traj_sql) if per_traj_sql else 0, p90=q(per_traj_sql, .9), max=max(per_traj_sql) if per_traj_sql else 0)
    R['db_tool_calls'] = dbcalls
    R['error_rate_calls'] = pct(err_calls, dbcalls)
    R['trajectories_with_any_error'] = pct(err_traj, len(trajs))
    R['timeouts'] = timeouts
    R['errors_followed_by_another_db_call'] = pct(retry_any, errs_total)
    R['errors_followed_by_similar_call(ratio>=0.6)'] = pct(retry_sim, errs_total)
    R['errors_as_last_db_call'] = pct(err_last, errs_total)
    R['top_error_types'] = errtypes.most_common(8)
    R['first_op_kind'] = dict(first_kind.most_common())
    R['first_op_is_metadata'] = pct(meta_first, sum(first_kind.values()))
    R['all_metadata_before_first_data_op (of trajs having both)'] = pct(all_meta_before, has_both)
    R['mean_relative_position'] = {k: round(statistics.mean(v), 3) for k, v in phase_pos.items()}
    R['exact_duplicate_sql_within_traj'] = pct(dup_exact, sql_total_for_dup)
    R['calls_with_>1_sql_statement'] = pct(multi_stmt_calls, dbcalls)
    R['assistant_turns_with_parallel_db_calls'] = pct(parallel_turns, turns_total)
    R['parallel_batch_size_hist'] = dict(sorted(par_sizes.items()))
    return R

if __name__ == '__main__':
    ds = sys.argv[1]; paths = sys.argv[2:]
    trajs = {'wmo_bird': wmo_bird, 'ptbr': ptbr, 'tau': tau, 'spider_tc': spider_tc}[ds](paths)
    R = analyse(trajs)
    if ds == 'tau':
        for model in sorted(set(t['model'] for t in trajs)):
            R['by_model:' + model] = {k: v for k, v in analyse([t for t in trajs if t['model'] == model]).items() if k in ('trajectories', 'op_kinds', 'ops_per_traj', 'error_rate_calls', 'assistant_turns_with_parallel_db_calls')}
    if ds == 'wmo_bird':
        for model in sorted(set(t['model'] for t in trajs)):
            R['by_model:' + str(model)] = {k: v for k, v in analyse([t for t in trajs if t['model'] == model]).items() if k in ('trajectories', 'sql_per_traj', 'error_rate_calls')}
        R['reward_mean'] = round(statistics.mean([t['reward'] or 0 for t in trajs]), 3)
    print(json.dumps(R, indent=1, default=str))
