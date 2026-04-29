# This file is part marketing_email_template module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from unittest.mock import patch

from genshi.template.base import TemplateError as GenshiTemplateError
from trytond.pool import Pool
from trytond.tests.test_tryton import ModuleTestCase, with_transaction


class MarketingEmailTemplateTestCase(ModuleTestCase):
    'Test Marketing Email Template module'
    module = 'marketing_email_template'

    @with_transaction()
    def test_preview_uses_default_test_recipient(self):
        pool = Pool()
        EmailList = pool.get('marketing.email.list')
        Message = pool.get('marketing.email.message')

        email_list = EmailList(name='Test')
        email_list.save()

        message = Message(list_=email_list, title='Test')
        message.content = '<html><body>Hello ${email.email}</body></html>'
        message.save()

        preview = message.on_change_with_preview()

        self.assertIsNotNone(preview)
        self.assertIn(b'user@example.com', preview)

    @with_transaction()
    def test_content_is_readonly_when_template_is_set(self):
        Message = Pool().get('marketing.email.message')

        self.assertIn('template', str(Message.content.states['readonly']))

    @with_transaction()
    def test_preview_keeps_utf8_without_template(self):
        pool = Pool()
        EmailList = pool.get('marketing.email.list')
        Message = pool.get('marketing.email.message')

        email_list = EmailList(name='Test')
        email_list.save()

        message = Message(list_=email_list, title='Test')
        message.markdown = 'Missatge amb accénts: àéíòú'
        message.save()

        preview = message.on_change_with_preview()

        self.assertIsNotNone(preview)
        self.assertIn(b'<meta charset="utf-8"', preview.lower())
        self.assertIn('Missatge amb accénts: àéíòú'.encode('utf-8'), preview)

    @with_transaction()
    def test_preview_normalizes_template_charset_to_utf8(self):
        pool = Pool()
        EmailList = pool.get('marketing.email.list')
        Message = pool.get('marketing.email.message')

        email_list = EmailList(name='Test')
        email_list.save()

        message = Message(list_=email_list, title='Test')
        message.content = (
            '<html><head>'
            '<meta http-equiv="Content-Type" '
            'content="text/html; charset=iso-8859-1"/>'
            '</head><body>Plantilla amb àéíòú</body></html>')
        message.save()

        preview = message.on_change_with_preview()

        self.assertIsNotNone(preview)
        self.assertIn(b'charset="utf-8"', preview.lower())
        self.assertNotIn(b'charset=iso-8859-1', preview.lower())
        self.assertIn('Plantilla amb àéíòú'.encode('utf-8'), preview)

    @with_transaction()
    def test_preview_falls_back_to_raw_html_on_template_parse_error(self):
        pool = Pool()
        EmailList = pool.get('marketing.email.list')
        Message = pool.get('marketing.email.message')

        email_list = EmailList(name='Test')
        email_list.save()

        message = Message(list_=email_list, title='Test')
        message.content = '<html><body><div>Broken</div></body></html>'
        message.save()

        with patch(
                'trytond.modules.marketing_email_template.marketing'
                '.MarkupTemplate',
                side_effect=GenshiTemplateError('boom')):
            preview = message.on_change_with_preview()

        self.assertIsNotNone(preview)
        self.assertIn(b'Broken', preview)

del ModuleTestCase
