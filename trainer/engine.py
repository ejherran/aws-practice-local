"""Certification-agnostic practice engine with immutable attempt snapshots."""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import secrets
from .banks import BankRepository, dump, validate_settings
from .errors import AppError

RNG = secrets.SystemRandom()


def targets(total, weights):
    """Allocate integer quotas using the largest-remainder method."""
    result = {domain: total * weight // 100 for domain, weight in weights.items()}
    order = sorted(weights, key=lambda domain: (total * weights[domain] % 100, weights[domain], domain), reverse=True)
    for domain in order[:total - sum(result.values())]:
        result[domain] += 1
    return result


class Trainer:
    def __init__(self, storage, banks):
        self.storage = storage
        self.banks = banks
        self.sweep()

    @staticmethod
    def answered(question):
        return len(question['selected']) == question['select_count']

    def expire(self, con):
        for row in con.execute("SELECT * FROM attempts WHERE status='active' AND deadline<=?",
                               (self.storage.clock(),)).fetchall():
            self.finalize(con, row, 'timeout')

    def sweep(self):
        with self.storage.connection() as con:
            self.expire(con)

    def draw(self, con, user_id, bank_id, version, questions, count, weights):
        row = con.execute('SELECT payload FROM decks WHERE user_id=? AND bank_id=? AND bank_version=?',
                          (user_id, bank_id, version)).fetchone()
        if row:
            deck = json.loads(row['payload'])
        else:
            remaining = list(questions)
            RNG.shuffle(remaining)
            deck = {'cycle': 1, 'remaining': remaining}
        selected, used, distribution = [], set(), Counter()
        desired = targets(count, weights)
        while len(selected) < count:
            if not deck['remaining']:
                deck['cycle'] += 1
                deck['remaining'] = list(questions)
                RNG.shuffle(deck['remaining'])
            eligible = [qid for qid in deck['remaining'] if qid not in used]
            if not eligible:
                raise RuntimeError('The bank is too small for a unique attempt.')
            available = {questions[qid]['domain_id'] for qid in eligible}
            needed = [d for d in available if distribution[d] < desired[d]]
            if needed:
                RNG.shuffle(needed)
                domain = max(needed, key=lambda d: desired[d] - distribution[d])
                qid = next(qid for qid in eligible if questions[qid]['domain_id'] == domain)
            else:
                qid = eligible[0]
            deck['remaining'].remove(qid)
            used.add(qid)
            distribution[questions[qid]['domain_id']] += 1
            selected.append((qid, deck['cycle']))
        con.execute('''INSERT INTO decks VALUES(?,?,?,?) ON CONFLICT(user_id,bank_id,bank_version)
                    DO UPDATE SET payload=excluded.payload''', (user_id, bank_id, version, dump(deck)))
        RNG.shuffle(selected)
        return selected

    def create(self, user_id, bank_id, kind):
        if kind not in ('quiz', 'exam', 'rush'):
            raise AppError(400, 'invalid_mode')
        if not isinstance(bank_id, str):
            raise AppError(400, 'bank_unavailable')
        with self.storage.connection() as con:
            self.expire(con)
            active = con.execute("SELECT id FROM attempts WHERE user_id=? AND status='active'", (user_id,)).fetchone()
            if active:
                raise AppError(409, 'active_attempt_exists', active_id=active['id'])
            bank = BankRepository.current(con, bank_id)
            manifest = json.loads(bank['manifest'])
            settings = validate_settings(json.loads(bank['settings']), len(json.loads(bank['questions'])),
                                         {d['id'] for d in manifest['domains']})
            mode = settings[kind]
            count, duration = mode['question_count'], mode['duration_seconds']
            scored_count = count if kind == 'rush' else count - mode['unscored_count']
            questions = {q['id']: q for q in json.loads(bank['questions'])}
            domains = {d['id']: d['name'] for d in manifest['domains']}
            selected = self.draw(con, user_id, bank_id, bank['current_version'], questions,
                                 count, settings['domain_weights'])
            snapshots = self.snapshot(questions, selected, manifest)
            desired = targets(scored_count, settings['domain_weights'])
            chosen = []
            for domain, target in desired.items():
                indices = [i for i, q in enumerate(snapshots) if q['domain_id'] == domain]
                RNG.shuffle(indices)
                chosen.extend(indices[:target])
            rest = [i for i in range(count) if i not in chosen]
            RNG.shuffle(rest)
            chosen.extend(rest[:scored_count - len(chosen)])
            for i in chosen:
                snapshots[i]['scored'] = True
            metadata = {'bank_title': manifest['title'], 'exam_code': manifest['exam_code'],
                        'languages': manifest['languages'], 'default_language': manifest['default_language'],
                        'settings': settings, 'domain_names': domains,
                        'target_percentage': None if kind == 'rush' else mode['target_percentage']}
            if kind == 'rush':
                metadata['rush'] = {'goal': count, 'round_number': 1, 'round_start': 0,
                                    'index': 0, 'streak': 0, 'best_streak': 0,
                                    'correct_count': 0, 'failures': 0,
                                    'phase': 'question', 'feedback_index': None}
                self.tag_round(snapshots, 1)
            attempt_id, now = secrets.token_hex(12), self.storage.clock()
            con.execute('''INSERT INTO attempts(id,user_id,bank_id,bank_version,kind,status,
                         started_at,deadline,duration,metadata,payload)
                         VALUES(?,?,?,?,?,'active',?,?,?,?,?)''',
                        (attempt_id, user_id, bank_id, bank['current_version'], kind, now,
                         now + duration, duration, dump(metadata), dump(snapshots)))
            return self.view(con.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone())

    @staticmethod
    def snapshot(questions, selected, manifest):
        """Freeze a draw's content and randomized option identities."""
        domains = {d['id']: d['name'] for d in manifest['domains']}
        snapshots = []
        for qid, cycle in selected:
            q = deepcopy(questions[qid])
            for option in q['options']:
                option['id'] = secrets.token_hex(8)
            RNG.shuffle(q['options'])
            snapshots.append({'id': qid, 'cycle': cycle, 'domain_id': q['domain_id'],
                              'domain_name': domains[q['domain_id']], 'task_id': q.get('task_id', ''),
                              'prompt': q['prompt'], 'explanation': q['explanation'],
                              'select_count': q['select_count'], 'options': q['options'],
                              'notes': q.get('notes'),
                              'references': [manifest['references'][key] for key in q['references']],
                              'selected': [], 'flagged': False, 'scored': False})
        return snapshots

    @staticmethod
    def tag_round(questions, number):
        for i, q in enumerate(questions):
            q.update({'round_number': number, 'round_position': i + 1,
                      'confirmed': False, 'skipped': False, 'scored': True})

    @staticmethod
    def public_question(q, index):
        # Correctness and learning material are only disclosed in final reports
        # or the explicitly confirmed failed question's RUSH feedback.
        return {'index': index, 'prompt': q['prompt'], 'select_count': q['select_count'],
                'selected': q['selected'], 'flagged': q['flagged'],
                'options': [{'id': option['id'], 'text': option['text']} for option in q['options']]}

    def view(self, row):
        questions = json.loads(row['payload'])
        metadata = json.loads(row['metadata'])
        rush = metadata.pop('rush', None)
        result = {key: row[key] for key in ('id', 'bank_id', 'bank_version', 'kind', 'status',
                  'started_at', 'deadline', 'finished_at', 'duration', 'revision')}
        result.update({'metadata': metadata, 'server_now': self.storage.clock(),
                       'total': len(questions),
                       'answered': sum(q.get('confirmed', False) if rush else self.answered(q) for q in questions),
                       'flagged': sum(q['flagged'] for q in questions)})
        if rush:
            result['rush'] = {**rush, 'generated_count': len(questions),
                              'percentage': round(100 * rush['correct_count'] / len(questions), 2)}
        if row['status'] == 'active':
            if rush:
                result['questions'] = ([self.public_question(questions[rush['index']], rush['index'])]
                                       if rush['phase'] == 'question' else [])
                if rush['phase'] == 'feedback':
                    result['feedback'] = deepcopy(questions[rush['feedback_index']])
            else:
                result['questions'] = [self.public_question(q, i) for i, q in enumerate(questions)]
        else:
            result['questions'] = questions
            result['result'] = json.loads(row['result'])
        return result

    @staticmethod
    def owned(con, user_id, attempt_id):
        row = con.execute('SELECT * FROM attempts WHERE id=? AND user_id=?', (attempt_id, user_id)).fetchone()
        if not row:
            raise AppError(404, 'attempt_not_found')
        return row

    def fetch(self, user_id, attempt_id):
        with self.storage.connection() as con:
            self.expire(con)
            return self.view(self.owned(con, user_id, attempt_id))

    def update(self, user_id, attempt_id, body):
        self.sweep()
        with self.storage.connection() as con:
            row = self.owned(con, user_id, attempt_id)
            if row['status'] != 'active':
                raise AppError(409, 'attempt_finished', attempt=self.view(row))
            if self.storage.clock() >= row['deadline']:
                self.finalize(con, row, 'timeout')
                return self.view(self.owned(con, user_id, attempt_id))
            if type(body.get('revision')) is not int or body['revision'] != row['revision']:
                raise AppError(409, 'revision_conflict', attempt=self.view(row))
            questions = json.loads(row['payload'])
            index = body.get('index')
            if type(index) is not int or not 0 <= index < len(questions):
                raise AppError(400, 'invalid_question_index')
            question = questions[index]
            if row['kind'] == 'rush':
                rush = json.loads(row['metadata'])['rush']
                if rush['phase'] != 'question' or index != rush['index']:
                    raise AppError(409, 'rush_current_only', attempt=self.view(row))
                if 'flagged' in body:
                    raise AppError(400, 'rush_no_flags')
            if 'selected' in body:
                selected = body['selected']
                if not isinstance(selected, list) or not all(isinstance(v, str) for v in selected):
                    raise AppError(400, 'invalid_selection')
                allowed = {o['id'] for o in question['options']}
                if len(selected) > question['select_count'] or len(set(selected)) != len(selected) or not set(selected) <= allowed:
                    raise AppError(400, 'invalid_selection')
                question['selected'] = selected
            if 'flagged' in body:
                if type(body['flagged']) is not bool:
                    raise AppError(400, 'invalid_flag')
                question['flagged'] = body['flagged']
            con.execute('UPDATE attempts SET payload=?,revision=revision+1 WHERE id=?', (dump(questions), attempt_id))
            return self.view(self.owned(con, user_id, attempt_id))

    def rush_action(self, user_id, attempt_id, body, action='answer'):
        """Atomically grade one answer or acknowledge persisted failure feedback.

        One absolute deadline covers every round and feedback screen. A failed
        answer consumes the entire old round and generates the next full round
        immediately, so every generated item contributes to the denominator.
        """
        if action not in ('answer', 'continue'):
            raise AppError(400, 'invalid_request')
        with self.storage.connection() as con:
            self.expire(con)
            row = self.owned(con, user_id, attempt_id)
            if row['kind'] != 'rush':
                raise AppError(400, 'invalid_mode')
            if row['status'] != 'active':
                return self.view(row)
            if type(body.get('revision')) is not int or body['revision'] != row['revision']:
                raise AppError(409, 'revision_conflict', attempt=self.view(row))
            metadata, questions = json.loads(row['metadata']), json.loads(row['payload'])
            rush = metadata['rush']
            if action == 'continue':
                if rush['phase'] != 'feedback':
                    raise AppError(409, 'rush_no_feedback', attempt=self.view(row))
                rush['phase'] = 'question'
                rush['feedback_index'] = None
            else:
                if rush['phase'] != 'question':
                    raise AppError(409, 'rush_feedback_pending', attempt=self.view(row))
                if type(body.get('index')) is not int or body['index'] != rush['index']:
                    raise AppError(409, 'rush_current_only', attempt=self.view(row))
                q = questions[rush['index']]
                selected = body.get('selected')
                allowed = {o['id'] for o in q['options']}
                if (not isinstance(selected, list) or not all(isinstance(v, str) for v in selected)
                        or len(selected) != q['select_count'] or len(set(selected)) != len(selected)
                        or not set(selected) <= allowed):
                    raise AppError(400, 'rush_complete_selection')
                q['selected'], q['confirmed'] = selected, True
                q['confirmed_at'] = self.storage.clock()
                q['is_correct'] = set(selected) == {o['id'] for o in q['options'] if o['correct']}
                q['outcome'] = 'correct' if q['is_correct'] else 'incorrect'
                if q['is_correct']:
                    rush['streak'] += 1
                    rush['correct_count'] += 1
                    rush['best_streak'] = max(rush['best_streak'], rush['streak'])
                    if rush['streak'] < rush['goal']:
                        rush['index'] += 1
                    else:
                        rush['phase'] = 'completed'
                else:
                    rush['feedback_index'] = rush['index']
                    for skipped in questions[rush['index'] + 1:]:
                        skipped['skipped'] = True
                    rush['failures'] += 1
                    rush['streak'] = 0
                    rush['round_number'] += 1
                    rush['round_start'] = len(questions)
                    # Use the attempt's immutable content version even if an
                    # administrator imported or disabled a bank during play.
                    bank = con.execute('SELECT manifest,questions FROM bank_versions WHERE bank_id=? AND version=?',
                                       (row['bank_id'], row['bank_version'])).fetchone()
                    manifest = json.loads(bank['manifest'])
                    source = {q['id']: q for q in json.loads(bank['questions'])}
                    selected_draw = self.draw(con, user_id, row['bank_id'], row['bank_version'], source,
                                              rush['goal'], metadata['settings']['domain_weights'])
                    batch = self.snapshot(source, selected_draw, manifest)
                    self.tag_round(batch, rush['round_number'])
                    questions.extend(batch)
                    rush['index'] = rush['round_start']
                    rush['phase'] = 'feedback'
            con.execute('UPDATE attempts SET metadata=?,payload=?,revision=revision+1 WHERE id=?',
                        (dump(metadata), dump(questions), row['id']))
            fresh = self.owned(con, user_id, attempt_id)
            if rush['phase'] == 'completed':
                self.finalize(con, fresh, 'rush_completed')
                fresh = self.owned(con, user_id, attempt_id)
            return self.view(fresh)

    def finalize(self, con, row, reason):
        questions = json.loads(row['payload'])
        domains = defaultdict(lambda: {'correct': 0, 'total': 0, 'all_correct': 0, 'all_total': 0})
        metadata = json.loads(row['metadata'])
        for domain_id, name in metadata['domain_names'].items():
            domains[domain_id]['name'] = name
        scored_correct = scored_total = all_correct = unanswered = incomplete = 0
        is_rush = row['kind'] == 'rush'
        for q in questions:
            confirmed = q.get('confirmed', False) if is_rush else True
            q['is_correct'] = confirmed and set(q['selected']) == {o['id'] for o in q['options'] if o['correct']}
            q['outcome'] = ('skipped' if q.get('skipped') else 'unconfirmed' if is_rush and q['selected'] and not confirmed
                            else 'unanswered' if not q['selected'] else 'correct' if q['is_correct'] else 'incorrect')
            q['incomplete'] = bool(q['selected']) and not self.answered(q)
            unanswered += (not confirmed) if is_rush else not q['selected']
            incomplete += q['incomplete']
            all_correct += q['is_correct']
            domain = domains[q['domain_id']]
            domain['name'] = q['domain_name']
            domain['all_total'] += 1
            domain['all_correct'] += q['is_correct']
            if q['scored']:
                scored_total += 1
                scored_correct += q['is_correct']
                domain['total'] += 1
                domain['correct'] += q['is_correct']
        finish = row['deadline'] if reason == 'timeout' else min(self.storage.clock(), row['deadline'])
        percentage = round(100 * scored_correct / scored_total, 2)
        weights = metadata['settings']['domain_weights']
        desired_all, desired_scored = targets(len(questions), weights), targets(scored_total, weights)
        report = {'reason': reason, 'correct': scored_correct, 'scored_total': scored_total,
                  'percentage': percentage, 'all_correct': all_correct, 'total': len(questions),
                  'unanswered': unanswered, 'incomplete': incomplete, 'unscored_total': len(questions) - scored_total,
                  'elapsed_seconds': max(0, round(finish - row['started_at'])), 'domains': dict(domains),
                  'target_percentage': metadata['target_percentage'],
                  'target_met': None if is_rush else percentage >= metadata['target_percentage'],
                  'distribution_adjusted': any(domains[d]['all_total'] != desired_all[d] or
                                               domains[d]['total'] != desired_scored[d] for d in weights)}
        if is_rush:
            rush = metadata['rush']
            report['rush'] = {'goal': rush['goal'], 'streak': rush['streak'],
                              'best_streak': rush['best_streak'], 'rounds': rush['round_number'],
                              'failures': rush['failures'], 'completed': reason == 'rush_completed',
                              'generated': len(questions), 'confirmed': sum(q['confirmed'] for q in questions),
                              'skipped': sum(q['skipped'] for q in questions)}
        con.execute("UPDATE attempts SET status='finished',finished_at=?,payload=?,result=?,revision=revision+1 WHERE id=?",
                    (finish, dump(questions), dump(report), row['id']))

    def finish(self, user_id, attempt_id, revision):
        with self.storage.connection() as con:
            self.expire(con)
            row = self.owned(con, user_id, attempt_id)
            if row['status'] != 'active':
                return self.view(row)
            if type(revision) is not int or revision != row['revision']:
                raise AppError(409, 'revision_conflict', attempt=self.view(row))
            self.finalize(con, row, 'submitted')
            return self.view(self.owned(con, user_id, attempt_id))

    @staticmethod
    def brief(row):
        result = {key: row[key] for key in ('id', 'bank_id', 'bank_version', 'kind', 'status',
                  'started_at', 'finished_at', 'deadline', 'duration')}
        result['metadata'] = json.loads(row['metadata'])
        result['result'] = json.loads(row['result']) if row['result'] else None
        return result

    def dashboard(self, user_id):
        with self.storage.connection() as con:
            self.expire(con)
            active = con.execute("SELECT * FROM attempts WHERE user_id=? AND status='active'", (user_id,)).fetchone()
            rows = con.execute('''SELECT b.*,v.manifest,v.questions,v.imported_at FROM banks b
                                 JOIN bank_versions v ON v.bank_id=b.id AND v.version=b.current_version
                                 WHERE b.enabled=1 ORDER BY b.id''').fetchall()
            bank_list = []
            for row in rows:
                bank = BankRepository.summary(row)
                recent = con.execute("""SELECT result FROM attempts WHERE user_id=? AND bank_id=?
                    AND kind='quiz' AND status='finished' ORDER BY finished_at DESC,rowid DESC LIMIT 5""",
                                     (user_id, row['id'])).fetchall()
                values = [json.loads(r[0])['percentage'] for r in recent]
                deck_row = con.execute('SELECT payload FROM decks WHERE user_id=? AND bank_id=? AND bank_version=?',
                                       (user_id, row['id'], row['current_version'])).fetchone()
                deck = json.loads(deck_row[0]) if deck_row else {'cycle': 1, 'remaining': [None] * bank['question_count']}
                bank['stats'] = {'average': round(sum(values) / len(values), 2) if values else None,
                                 'recent_count': len(values), 'cycle': deck['cycle'],
                                 'remaining': len(deck['remaining']),
                                 'completed': con.execute("SELECT COUNT(*) FROM attempts WHERE user_id=? AND bank_id=? AND status='finished'",
                                                          (user_id, row['id'])).fetchone()[0]}
                bank_list.append(bank)
            return {'banks': bank_list, 'active': self.brief(active) if active else None}

    def history(self, user_id, bank_id='', kind='all', offset=0, limit=25):
        if kind not in ('all', 'quiz', 'exam', 'rush') or not 0 <= offset <= 10_000_000 or not 1 <= limit <= 100:
            raise AppError(400, 'invalid_pagination')
        conditions, parameters = ["user_id=?", "status='finished'"], [user_id]
        if bank_id:
            conditions.append('bank_id=?')
            parameters.append(bank_id)
        if kind != 'all':
            conditions.append('kind=?')
            parameters.append(kind)
        where = ' AND '.join(conditions)
        with self.storage.connection() as con:
            self.expire(con)
            total = con.execute('SELECT COUNT(*) FROM attempts WHERE ' + where, parameters).fetchone()[0]
            rows = con.execute('SELECT * FROM attempts WHERE ' + where +
                               ' ORDER BY finished_at DESC,rowid DESC LIMIT ? OFFSET ?',
                               parameters + [limit, offset]).fetchall()
            # Include every bank represented in this profile's completed history,
            # even when a bank was disabled or is not on the current page.
            bank_rows = con.execute("""SELECT bank_id,metadata FROM attempts WHERE rowid IN
                (SELECT MAX(rowid) FROM attempts WHERE user_id=? AND status='finished'
                 GROUP BY bank_id) ORDER BY bank_id""", (user_id,)).fetchall()
            history_banks = [{'id': r['bank_id'], 'title': json.loads(r['metadata'])['bank_title']}
                             for r in bank_rows]
            return {'total': total, 'offset': offset, 'items': [self.brief(row) for row in rows],
                    'banks': history_banks}

    def export_profile(self, user_id):
        with self.storage.connection() as con:
            self.expire(con)
            row = con.execute('SELECT id,username,display_name,language FROM users WHERE id=?', (user_id,)).fetchone()
            if not row:
                raise AppError(401, 'sign_in_required')
            attempts = con.execute('SELECT * FROM attempts WHERE user_id=? ORDER BY started_at', (user_id,)).fetchall()
            decks = con.execute('SELECT bank_id,bank_version,payload FROM decks WHERE user_id=?', (user_id,)).fetchall()
            # Export is for review, not credential backup or automatic restoration.
            return {'format': 'practice-profile-v4', 'exported_at': self.storage.clock(), 'user': dict(row),
                    'decks': [{'bank_id': d['bank_id'], 'bank_version': d['bank_version'],
                               **json.loads(d['payload'])} for d in decks],
                    'attempts': [self.view(a) for a in attempts]}
