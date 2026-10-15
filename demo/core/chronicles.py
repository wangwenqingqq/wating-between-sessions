import re


DOMAINS = {'research': '研究与实验', 'robotics': '具身与感知', 'craft': '工具与创作',
           'life': '生活与选择', 'other': '拾遗与未归档'}
TOPICS = [
    ('gts-tide', 'GTS 与 TIDE', 'research', '树索引、查询冗余与系统实验的来路', r'GTS|GTSPP|\bTIDE(?:\+\+)?\b'),
    ('vector-search', '向量检索与相似连接', 'research', '从索引选择到精确连接的探索', r'TensorJoin|BitIVF|Tensortree|\bANNS\b|Faiss|CAGRA|相似(?:性)?(?:查询|连接)|向量(?:检索|索引)'),
    ('temporal-graphs', '时序图与 TGN', 'research', '时序依赖、训练执行与图计算', r'TGN|时序图|temporal.graph|TGNTrain.PULSE'),
    ('gpu-computing', 'GPU 与低精度计算', 'research', '内核、访存与数值合同的实验记录', r'CUDA|Tensor[\s_-]*Core|SASS|E3M4|FP8|TensorRT|cuBLAS|\bPTX\b|QMMA|GPU'),
    ('research-notes', '论文阅读与选题', 'research', '尚未归入具体课题的研究问题', None),
    ('embodied-ai', '具身智能与世界模型', 'robotics', '机器人、动作、交互与部署中的问题', r'XR0|XRZero|OpenPI|机器人|夹爪|衣物|叠衣|LeRobot|世界模型|world.?model|sim2real|S2R|LiS.WAM|Action.?DiT|具身|RoboAgent|\bVLA\b|\bWAM\b'),
    ('sensing', '感知、标定与仿真', 'robotics', '相机、传感器与仿真教学的线索', r'相机|雷达|标定|视觉|RViz|点云|\bIMU\b|Kalibr|Gazebo'),
    ('agent-workflow', 'Agent 与知识工作流', 'craft', '工具、共同记忆与个人知识整理', r'Codex|Claude|工作流|Obsidian|知识库|(?<![a-z])agent(?![a-z])|skill|\bMCP\b|智能体|编年史|Between'),
    ('writing-teaching', '文稿、课程与表达', 'craft', '把想法写成文章、课件与讲稿', r'PPT|讲稿|逐字稿|排版|\bWord\b|文档|教学|课程|幻灯片|Overleaf|LaTeX'),
    ('systems-devices', '系统与设备手记', 'craft', '本机、远程服务与设备维护', r'磁盘|硬盘|清理|打印机|aibox|Firefly|\bUSB\b|缓存|显示器|\bSSH\b|远程|端口|服务器|登录'),
    ('life-decisions', '财务与职业选择', 'life', '当时的生活问题与选择记录', r'基金|持仓|收益率|流水|薪资|社保|招聘|职业|报销|交易|银行卡|收支|QDII|\bETF\b|理财|股票|合作合同'),
    ('misc', '日常拾遗', 'other', '暂时没有明确专题的原始片段', None),
]
PATTERNS = {key: re.compile(pattern, re.I) for key, _, _, _, pattern in TOPICS if pattern}
KIND_ORDER = {'request': 0, 'decision': 1, 'reported_result': 2, 'open_question': 3}


def event_topics(event):
    # Transport headings name the tool, not the subject of the request.
    text = re.sub(r'## My request(?: for (?:Codex|Claude))?\s*:?', '',
                  event['title'] + ' ' + event['summary'], flags=re.I)
    matches = [key for key, pattern in PATTERNS.items() if pattern.search(text)]
    return matches or ['research-notes' if event['category'] == 'research' else 'misc']


def topic_summary(definition, events):
    key, title, domain, subtitle, _ = definition
    counts = {kind: sum(e['kind'] == kind for e in events) for kind in KIND_ORDER}
    opening = next((e for e in events if e['kind'] == 'request'), events[0] if events else None)
    return dict(id=key, title=title, domain=domain, domain_label=DOMAINS[domain], subtitle=subtitle,
                count=len(events), sessions=len({(e['source_provider'], e['source_session_id']) for e in events}),
                first_date=events[0]['date'] if events else '', last_date=events[-1]['date'] if events else '',
                kinds=counts, preview=opening['summary'][:100] if opening else '',
                preview_event={k: opening[k] for k in ('event_id', 'source_hash')} if opening else None)


def load_chronicles(store, month='', topic=''):
    if topic and topic not in {t[0] for t in TOPICS}:
        raise ValueError('Unknown chronicle topic')
    events = []
    if store.get('history_enabled', False):
        with store.connect() as db:
            rows = db.execute('SELECT * FROM timeline WHERE date LIKE ? ORDER BY date,event_id', (month + '%',)).fetchall()
        # Stored dates have day precision; preserve source order, not a fabricated inter-session time.
        events = sorted((dict(row) for row in rows),
                        key=lambda e: (e['date'], e['source_provider'], e['source_session_id'],
                                       e['source_line'], e['event_id']))
    buckets = {t[0]: [] for t in TOPICS}
    for event in events:
        for key in event_topics(event):
            buckets[key].append(event)
    topics, selected = [], None
    for definition in TOPICS:
        entries = buckets[definition[0]]
        summary = topic_summary(definition, entries)
        if entries:
            topics.append(summary)
        if definition[0] == topic:
            selected = dict(summary, events=entries, chapters={
                kind: (next((e for e in entries if e['kind'] == kind), None) if kind == 'request'
                       else next((e for e in reversed(entries) if e['kind'] == kind), None))
                for kind in KIND_ORDER})
    domains = [dict(id=key, title=title, count=sum(t['domain'] == key for t in topics))
               for key, title in DOMAINS.items() if any(t['domain'] == key for t in topics)]
    return dict(topics=topics, domains=domains, selected=selected,
                stats=dict(events=len(events), sessions=len({(e['source_provider'], e['source_session_id']) for e in events}),
                           topics=len(topics), first_date=events[0]['date'] if events else '',
                           last_date=events[-1]['date'] if events else ''))
