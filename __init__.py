# This file is part marketing_email_template module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool
from . import marketing

def register():
    Pool.register(
        marketing.Template,
        marketing.Message,
        module='marketing_email_template', type_='model')
