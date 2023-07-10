import markdown
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import PoolMeta, Pool


class Template(ModelSQL, ModelView):
    'Email Template'
    __name__ = 'marketing.email.template'
    name = fields.Char('Name', required=True)
    content = fields.Text('Content', required=True)


class Message(metaclass=PoolMeta):
    __name__ = 'marketing.email.message'
    template = fields.Many2One('ir.action.report', 'Template', domain=[
            ('single', '=', True),
            ('model', '=', 'marketing.email.message'),
            ])
    markdown = fields.Text('Markdown')
    html = fields.Function(fields.Text('HTML'), 'get_html')

    def get_html(self, name):
        if not self.markdown:
            return ''
        html = markdown.markdown(self.markdown)
        html = '<html><body>%s</body></html>' % html
        return html

    @fields.depends('template', 'markdown')
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
