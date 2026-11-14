"""Small reviewed public-source corpus, not school authority or a general RAG.

Only fixed excerpts are searched. No network, arbitrary path, model, SQL or
business-write handle is available. Source snapshots remain outside Git.
"""
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class Source:
    title: str
    number: str
    issuer: str
    url: str
    snapshot_sha256: str
    issued_at: str | None
    published_at: str
    kind: str = 'official_original'
    jurisdiction: str = '湖南省'
    checked_at: str = '2026-11-14'
    validity: str = 'not_verified'


@dataclass(frozen=True)
class Passage:
    source: Source
    locator: str
    quote: str
    terms: tuple[str, ...]
    stages: tuple[str, ...] = ()


HUNAN = Source('湖南省规范中小学办学行为20条规定', '湘教发〔2024〕39号', '湖南省教育厅',
    'https://jyt.hunan.gov.cn/jyt/sjyt/xxgk/tzgg/202410/t20241015_1141349.html',
    'c1b685a7a6b5d9f30c1e4314f6535a532917449b8c15cc09a2b4108778560f24', '2024-08-30', '2024-10-15')
CHANGSHA = Source('长沙市义务教育课后服务工作实施办法', '长教发〔2024〕18号',
    '长沙市教育局等五部门', 'https://www.hunan.gov.cn/zqt/zcsd/202409/t20240910_33451793.html',
    'e3ae3442d4dcf0baad39f2cba11726e32ae4f9206de593cb542988f953141933',
    '2024-08-29', '2024-09-10', kind='official_reprint', jurisdiction='湖南省长沙市')
COURT = Source('人民法院案例库建设运行工作规程', '法〔2024〕92号', '最高人民法院',
    'https://www.court.gov.cn/zixun/xiangqing/431662.html',
    '4371621f3d1e7bce92d49e622ae0ba92ea737654692f23dba1ff5c6b75c9dcc3', None, '2024-05-07', jurisdiction='全国')

PASSAGES = (
    Passage(HUNAN, '第五部分第15条：进校园活动（摘录）',
        '各地要落实《湖南省中小学教师减负清单》（湘办〔2020〕19号）和督查检查评比考核、进校园活动白名单，严格控制面向中小学校的各类督查检查、考核评比、创建示范、宣传教育等活动，不得给中小学强制安排与教育教学无关的活动和工作。',
        ('减负', '进校园', '白名单', '摊派', '无关', '非教学', '检查', '考核', '填表'), ('小学', '初中', '高中')),
    Passage(HUNAN, '第六部分第17条：家校联系（摘录）',
        '学校要规范家长通讯群组信息发布管理，严禁学校和教师通过微信群、QQ群、钉钉群等发布成绩排名、学生在校表现、广告、求助、募捐等信息，要求家长发红包、刷屏问候、点赞，代收各类保险费、捐赠费及其他生活服务费等。',
        ('家长群', '微信群', '通讯群', '成绩', '排名', '家校', '发红包', '募捐', '点赞'), ('小学', '初中', '高中')),
    Passage(CHANGSHA, '第二部分第（一）项：自主自愿',
        '课后服务必须严格遵循学生自愿参加原则,学校和教师不得强制要求学生参加。学校开展课后服务要充分征求家长意见、征询学生需求,由学生和家长自愿报名、自主选课。',
        ('课后服务', '自愿', '强制参加'), ('小学', '初中')),
    Passage(CHANGSHA, '第三部分：课后服务对象',
        '义务教育阶段公、民办学校有课后服务需求的在校学生,并优先保障留守儿童、残疾儿童、进城务工人员随迁子女、家庭困难学生等亟需服务的群体。',
        ('课后服务', '民办', '公办', '义务教育', '对象'), ('小学', '初中')),
    Passage(CHANGSHA, '第四部分第（一）项：服务范围（摘录）',
        '课后服务仅限于全市义务教育阶段学校实施。各义务教育学校要全面开展课后服务,要覆盖到所有有需要的学生。学校为学生提供的早到校看管和自习、午餐午休看管、晚自习等服务不得纳入课后服务范围。',
        ('课后服务', '晚自习', '早到校', '午休', '看管', '范围'), ('小学', '初中')),
    Passage(COURT, '第四条：参考案例',
        '人民法院案例库收录的参考案例，应当是裁判已经发生法律效力，且对类案审判具有参考示范价值的案例。',
        ('案例', '判决', '裁判', '类案')),
    Passage(COURT, '第二十一条第一款：案例使用',
        '各级人民法院审理案件时参考入库类似案例的，可以将类似案例的裁判理由、裁判要旨作为本案裁判考量、理由参引，但不作为裁判依据。',
        ('案例', '判决', '裁判', '类案')),
)

COVERAGE = ('已收录湖南中小学办学规定、长沙义务教育课后服务办法和法院案例库使用规则的部分条款。'
    '宁乡市各校内部制度、官方学校总名录及具体裁判案件尚未收录。')
LIMITATION = '资料核对于2026-11-14；现行效力尚待复核，不能据此确认某校具体安排或作出个人责任结论。'


def requires_policy_search(question):
    """A narrow evidence prerequisite, not a general intent/authority router."""
    asking = any(term in question for term in ('查', '依据', '规定', '政策', '制度', '能否', '能不能', '可以吗',
        '是什么', '是否', '多少', '必须', '负责', '要求', '怎么'))
    return asking and (any(term in question for term in ('课后服务', '教师减负', '进校园', '学校制度', '校规', '法条', '法律责任', '教师职责'))
        or any(place in question for place in ('宁乡', '长沙', '湖南')) and any(term in question for term in
            ('政策', '规定', '依据', '制度', '报销', '职责', '责任'))
        or '法院' in question and any(term in question for term in ('案例', '判决', '裁判')))


def search_policy(question):
    if type(question) is not str or not 1 <= len(question.strip()) <= 2000:
        raise ValueError('Bounded policy question required')
    value = unicodedata.normalize('NFKC', question).strip().replace('宁乡县', '宁乡市')
    stages = {stage for stage in ('幼儿园', '小学', '初中', '高中', '中职', '大学', '特殊教育') if stage in value}
    if '幼儿' in value:
        stages.add('幼儿园')
    if '初一' in value or '初二' in value or '初三' in value:
        stages.add('初中')
    for stage, aliases in (
        ('高中', ('高一', '高二', '高三', '普高')),
        ('中职', ('职高', '中专')),
        ('大学', ('高职', '高校', '大专', '本科')),
        ('幼儿园', ('学前',)),
    ):
        if any(alias in value for alias in aliases):
            stages.add(stage)
    ranked, excluded = [], []
    # Geography is an applicability condition, never a similarity score.
    other_region = any(place in value for place in ('广东', '广州', '深圳', '北京', '上海', '湖北', '武汉',
        '浙江', '杭州', '四川', '成都', '河北', '山西', '辽宁', '吉林', '黑龙江', '江苏', '安徽', '福建',
        '江西', '山东', '河南', '海南', '贵州', '云南', '陕西', '甘肃', '青海', '台湾', '天津', '重庆',
        '内蒙古', '广西', '西藏', '宁夏', '新疆', '香港', '澳门'))
    for index, passage in enumerate(PASSAGES):
        if passage.source is CHANGSHA and not any(term in value for term in ('课后服务', '晚自习', '早到校', '午休', '看管')):
            continue
        score = sum(len(term) for term in passage.terms if term in value)
        if not score:
            continue
        other_hunan_city = passage.source is CHANGSHA and any(place in value for place in
            ('岳阳', '株洲', '湘潭', '衡阳', '邵阳', '常德', '张家界', '益阳', '郴州', '永州', '怀化', '娄底', '湘西'))
        if passage.source is not COURT and (other_region or other_hunan_city or stages and passage.stages and not stages.intersection(passage.stages)):
            excluded.append(passage.source.title)
            continue
        ranked.append((score, index, passage))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    matches = []
    for _, index, passage in ranked[:3]:
        source = passage.source
        matches.append({'ref': f'P{index + 1}', 'title': source.title, 'document_number': source.number,
            'issuer': source.issuer, 'url': source.url, 'locator': passage.locator, 'quote': passage.quote,
            'issued_at': source.issued_at, 'published_at': source.published_at,
            'checked_at': source.checked_at, 'validity': source.validity, 'source_kind': source.kind,
            'snapshot_sha256': source.snapshot_sha256, 'applicability': 'candidate_only'})
        matches[-1].update(jurisdiction=source.jurisdiction, applicable_stages=list(passage.stages))
    return {'status': 'matches' if matches else 'no_verified_basis', 'matches': matches,
        'coverage': COVERAGE, 'limitation': LIMITATION,
        'excluded_scope': sorted(set(excluded)), 'school_rules_available': False,
        'instruction': 'Use only returned excerpts for policy claims. Cite [P<number>]. Do not invent school procedures, case outcomes or current validity. Missing evidence is not proof that a rule does not exist. Ask only for conditions that affect applicability. No business changes are authorized.'}


def policy_answer(answer, result):
    """Persist exact excerpts and provenance in the existing answer field.

    The model cannot supply or modify the authoritative citation appendix.
    It survives refresh/restart without a new schema or retrieval of live text.
    """
    matches = result['matches']
    if not matches:
        scope = '找到的相关资料与问题中的地区或学段不符。' if result['excluded_scope'] else ''
        return f'{scope}现有资料中没有找到可引用的具体依据。\n\n{COVERAGE}\n\n请提供要核对的通知或制度原文；缺少资料不代表不存在相关规定。'
    allowed = {item['ref'] for item in matches}
    if set(re.findall(r'\[(P\d+)\]', answer)) - allowed:
        raise ValueError('Citation does not belong to this retrieval')
    if set(re.findall(r'https?://[^\s)<>]+', answer)) - {item['url'] for item in matches}:
        raise ValueError('URL does not belong to this retrieval')
    # URLs and quotations come from reviewed source data, not model prose.
    lines = [answer, '', '### 依据']
    for item in matches:
        kind = '；官方转载' if item['source_kind'] == 'official_reprint' else ''
        lines.extend([f"**[{item['ref']}] {item['title']} · {item['locator']}**",
            f"> {item['quote']}", f"{item['document_number']} · {item['issuer']}{kind}", f"[原文]({item['url']})", ''])
    lines.extend([LIMITATION, '宁乡各校内部制度尚未收录。'])
    rendered = '\n\n'.join(lines)
    if len(rendered) > 4000:
        raise ValueError('Policy answer must leave room for exact evidence')
    return rendered
