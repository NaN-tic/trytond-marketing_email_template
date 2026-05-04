import markdown, re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from genshi.template import MarkupTemplate
from genshi.template.base import TemplateError as GenshiTemplateError
from trytond.modules.html_report.engine import DualRecord
from trytond.model import ModelView, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Bool, Eval
from trytond.config import config

IMAGE_URL = config.get('image', 'source', default='')
PREVIEW_EMAIL = 'user@example.com'
PREVIEW_EMAIL_TOKEN = 'preview-token'


def _add_token(url, token):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k != 'token']
    query.append(('token', token))
    return urlunsplit((
            parts.scheme, parts.netloc, parts.path,
            urlencode(query), parts.fragment))


def _ensure_html_document(content):
    if not content:
        return ''
    if '<html' in content.lower():
        content = re.sub(
            r'<meta[^>]+charset=["\']?[^"\'>/\s]+["\']?[^>]*>',
            '<meta charset="utf-8"/>', content, flags=re.IGNORECASE)
        content = re.sub(
            r'(<\?xml[^>]+encoding=)["\']?[^"\'>]+(["\']?[^>]*\?>)',
            r'\1utf-8\2', content, flags=re.IGNORECASE)
        if 'charset=' not in content.lower():
            if re.search(r'<head[^>]*>', content, flags=re.IGNORECASE):
                content = re.sub(r'(<head[^>]*>)', r'\1<meta charset="utf-8"/>',
                    content, count=1, flags=re.IGNORECASE)
            else:
                content = re.sub(r'(<html[^>]*>)', r'\1<head><meta charset="utf-8"/></head>',
                    content, count=1, flags=re.IGNORECASE)
        if '<!doctype' not in content.lower():
            content = '<!DOCTYPE html>' + content
        return content
    return (
        '<!DOCTYPE html>'
        '<html>'
        '<head><meta charset="utf-8"/></head>'
        '<body>%s</body>'
        '</html>' % content)


class _PreviewRecipient:

    def __init__(self, list_):
        self.email = PREVIEW_EMAIL
        self.email_token = PREVIEW_EMAIL_TOKEN
        self.list_ = list_
        self.party = None
        self.rec_name = PREVIEW_EMAIL
        self.web_user = None

    def get_email_subscribe_url(self, url=None):
        if url is None:
            url = config.get('marketing', 'email_subscribe_url', default=None)
        if url:
            return _add_token(url, self.email_token)
        return ''


class _PreviewMessageProxy:

    def __init__(self, message):
        self._message = message
        self._fields = message._fields
        self.__name__ = message.__name__
        self.id = message.id

    @property
    def html(self):
        return self._message.get_html('html') or self._message.content or ''

    def __getattr__(self, name):
        return getattr(self._message, name)

    def get_email_unsubscribe_url(self, url=None):
        if url is None:
            url = config.get('marketing', 'email_unsubscribe_url', default=None)
        if url:
            return _add_token(url, self.email_token)
        return ''


class SendTest(metaclass=PoolMeta):
    __name__ = 'marketing.email.send_test'

    def default_start(self, fields):
        pool = Pool()
        List = pool.get('marketing.email.list')

        defaults = super().default_start(fields)
        email_list = defaults.get('list_')
        if email_list:
            email_list = List(email_list)
            if email_list.default_test_email:
                defaults['email'] = email_list.default_test_email.id
        return defaults


class EmailList(metaclass=PoolMeta):
    __name__ = 'marketing.email.list'

    default_from = fields.Char('Default From')
    default_test_email = fields.Many2One('marketing.email',
        'Default Test E-mail', domain=[
            ('list_', '=', Eval('id', -1)),
            ])
    default_template = fields.Many2One('ir.action.report', 'Template', domain=[
            ('single', '=', True),
            ('model', '=', 'marketing.email.message'),
            ])


class Email(metaclass=PoolMeta):
    __name__ = 'marketing.email'

    new = fields.Boolean('New')

    @staticmethod
    def default_new():
        return True


class Message(metaclass=PoolMeta):
    __name__ = 'marketing.email.message'
    template = fields.Many2One('ir.action.report', 'Template', domain=[
            ('single', '=', True),
            ('model', '=', 'marketing.email.message'),
            ])
    markdown = fields.Text('Markdown')
    html = fields.Function(fields.Text('HTML'), 'get_html')
    preview = fields.Function(fields.Binary('Preview',
            filename='preview_filename'), 'on_change_with_preview')
    preview_filename = fields.Function(fields.Char('Preview Filename'),
        'on_change_with_preview_filename')

    @classmethod
    def __setup__(cls):
        super().__setup__()
        readonly = cls.content.states.get('readonly', False)
        cls.content.states['readonly'] = readonly | Bool(Eval('template'))

    @fields.depends('list_', 'from_', 'template')
    def on_change_list_(self):
        if not self.list_:
            return
        if not self.from_:
            self.from_ = self.list_.default_from
        if not self.template:
            self.template = self.list_.default_template

    def get_html(self, name):
        if self.markdown:
            return markdown.markdown(self.markdown)
        return ''

    @fields.depends('template', 'markdown', 'content', 'list_')
    def on_change_with_preview_filename(self, name=None):
        return 'preview.html'

    def _get_rendered_content(self, use_current_values=False):
        pool = Pool()

        if not self.template:
            return self.get_html('html') or self.content or ''
        if use_current_values:
            Report = pool.get(self.template.report_name, 'report')
            if hasattr(Report, 'body_wrapper') and hasattr(Report, '_render_node'):
                record = DualRecord(_PreviewMessageProxy(self))
                return Report._render_node(
                    Report.body_wrapper(self.template, {}, [record]))
        if not self.id:
            return self.content or ''

        data = {
            'model': 'marketing.email.message',
            'model_context': None,
            'id': self.id,
            'ids': [self.id],
            'action_id': self.template.id,
            }
        Report = pool.get(self.template.report_name, 'report')
        document = Report.execute([self.id], data)
        if not document:
            return ''
        return re.sub('<br>', '<br />', document[1])

    @fields.depends('title', 'template', 'markdown', 'content', 'list_')
    def on_change_with_preview(self, name=None):
        content = self._get_rendered_content(use_current_values=True)
        if not content:
            return None
        try:
            content = MarkupTemplate(content).generate(
                email=_PreviewRecipient(self.list_),
                short=lambda url, record=None: url,
                ).render()
        except GenshiTemplateError:
            pass
        content = _ensure_html_document(content)
        return fields.Binary.cast(content.encode('utf-8'))

    @fields.depends('template', 'markdown')
    def update_content(self):
        self.content = self._get_rendered_content()

    @classmethod
    def create(cls, vlist):
        messages = super().create(vlist)
        for message in messages:
            message.update_content()
        cls.save(messages)
        return messages

    @classmethod
    def write(cls, *args):
        super().write(*args)
        actions = iter(args)
        for messages, values in zip(actions, actions):
            if 'template' in values or 'markdown' in values:
                for message in messages:
                    message.update_content()
            cls.save(messages)

    @classmethod
    @ModelView.button
    def draft(cls, messages):
        for message in messages:
            message.update_content()
        cls.save(messages)
        super().draft(messages)

    @classmethod
    @ModelView.button
    def send_test(cls, messages):
        for message in messages:
            message.update_content()
        cls.save(messages)
        return super().send_test(messages)

    @classmethod
    @ModelView.button
    def send(cls, messages):
        for message in messages:
            message.update_content()
        cls.save(messages)
        super().send(messages)

    @classmethod
    def process(cls, messages=None, emails=None, smptd_datamanager=None):
        pool = Pool()
        Email = pool.get('marketing.email')

        super().process(messages, emails, smptd_datamanager)
        if messages is None:
            messages = cls.search([
                    ('state', '=', 'sending'),
                    ])

        if not emails:
            emails = []
            for message in messages:
                emails += message.list_.emails

        emails = [x for x in emails if x.new]
        for email in emails:
            email.new = False
        Email.save(emails)
