import markdown, re
from trytond.model import ModelView, fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.modules.widgets import tools
from trytond.config import config

IMAGE_URL = config.get('image', 'source', default='')
TRYTOND_MARKETING_EMAIL_BASE = config.get('email', 'uri', default='')

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
    content_block = fields.Text('EditorJS')

    @fields.depends('list_', 'from_', 'template')
    def on_change_list_(self):
        if not self.list_:
            return
        if not self.from_:
            self.from_ = self.list_.default_from
        if not self.template:
            self.template = self.list_.default_template

    def get_html(self, name):
        if self.content_block:
            html = tools.js_to_html(self.content_block,
                url_prefix=TRYTOND_MARKETING_EMAIL_BASE)
            return html
        elif self.markdown:
            html = markdown.markdown(self.markdown)
            html = '<html><body>%s</body></html>' % html
            return html
        return ''

    @fields.depends('template', 'markdown', 'content_block')
    def update_content(self):
        pool = Pool()

        if not self.template:
            self.content = self.html
            return

        data = {
            'model': 'marketing.email.message',
            'model_context': None,
            'id': self.id,
            'ids': [self.id],
            'action_id': self.template.id,
            }
        Report = pool.get(self.template.report_name, 'report')
        document = Report.execute([self.id], data)
        if document:
            self.content = document[1]
            self.content = re.sub('<br>', '<br />', self.content)
        else:
            self.content = ''

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
            if 'template' in values or 'markdown' in values or 'content_block' in values:
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
